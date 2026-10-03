from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
import uuid

import httpx
from fastapi.encoders import jsonable_encoder
from sqlalchemy import desc, func, select, update

from app.config import settings
from app.core.web_scan.engine import WebScanEngine
from app.db.session import AsyncSessionLocal
from app.db.web_scan_models import (
    WebScanAuditRecordModel,
    WebScanEventRecordModel,
    WebScanFindingModel,
    WebScanJobModel,
    WebScanObservationModel,
)
from app.schemas.web_scan import ScanConfiguration, ScanState, WebScanEvent

logger = logging.getLogger("signal_scanner.web_scan.scheduler")


class WebScanScheduler:
    """Manages the in-process execution queue and worker lifecycle for web scans."""

    def __init__(self):
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None
        self._cancel_events: Dict[str, asyncio.Event] = {}
        self._active_tasks: Dict[str, asyncio.Task] = {}
        self._global_semaphore: Optional[asyncio.Semaphore] = None
        self._mock_transport: Optional[httpx.AsyncBaseTransport] = None
        self._wake_event = asyncio.Event()

    def set_mock_transport(self, transport: Optional[httpx.AsyncBaseTransport]) -> None:
        """Injects a custom/mock transport for offline testing."""
        self._mock_transport = transport

    async def start(self) -> None:
        """Starts the background worker and recovers interrupted scans."""
        if self._running:
            return
        self._running = True
        self._global_semaphore = asyncio.Semaphore(
            getattr(settings, "WEB_SCAN_GLOBAL_MAX_CONCURRENCY", 10)
        )

        # Mark any stale scanning/queued jobs from previous process run as interrupted
        await self._recover_interrupted_jobs()

        self._worker_task = asyncio.create_task(self._worker_loop(), name="web_scan_worker")
        logger.info("WebScanScheduler background worker started.")

    async def stop(self) -> None:
        """Stops the background worker and cancels running scans gracefully."""
        self._running = False
        self._wake_event.set()

        # Signal cancel to all active scans
        for scan_id, event in list(self._cancel_events.items()):
            event.set()

        # Cancel all active tasks immediately
        for scan_id, task in list(self._active_tasks.items()):
            if not task.done():
                task.cancel()

        # Wait for active tasks with timeout
        active_list = list(self._active_tasks.values())
        if active_list:
            await asyncio.wait(active_list, timeout=5.0)

        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

        logger.info("WebScanScheduler stopped.")

    def trigger(self) -> None:
        """Notifies the worker loop that a new job is available."""
        self._wake_event.set()

    def request_cancel(self, scan_id: str) -> bool:
        """Signals cancellation to an actively executing scan."""
        if scan_id in self._cancel_events:
            self._cancel_events[scan_id].set()
            return True
        return False

    async def _recover_interrupted_jobs(self) -> None:
        """Marks any dangling jobs as INTERRUPTED upon service restart."""
        try:
            async with AsyncSessionLocal() as db:
                stmt = (
                    select(WebScanJobModel)
                    .where(
                        WebScanJobModel.status.in_([ScanState.QUEUED.value, ScanState.SCANNING.value])
                    )
                )
                res = await db.execute(stmt)
                stale_jobs = res.scalars().all()
                now = datetime.now(timezone.utc)
                for job in stale_jobs:
                    job.status = ScanState.INTERRUPTED.value
                    job.status_reason = "Server process restarted while scan was active"
                    job.ended_at = now
                    job.version += 1
                if stale_jobs:
                    await db.commit()
                    logger.info("Recovered %d interrupted web scan jobs", len(stale_jobs))
        except Exception as exc:
            logger.warning("Error recovering stale web scan jobs: %s", exc)

    async def _worker_loop(self) -> None:
        """Continuously pulls pending jobs from the database and runs them."""
        while self._running:
            try:
                # Poll pending job
                job_id = await self._claim_next_job()
                if job_id:
                    # Register cancel event immediately upon queuing (F-07)
                    cancel_event = asyncio.Event()
                    self._cancel_events[job_id] = cancel_event

                    # Spawn task bounded by global semaphore
                    task = asyncio.create_task(self._execute_job_wrapper(job_id, cancel_event))
                    self._active_tasks[job_id] = task
                    task.add_done_callback(lambda t, jid=job_id: (
                        self._active_tasks.pop(jid, None),
                        self._cancel_events.pop(jid, None),
                    ))
                else:
                    # Wait for trigger or timeout (default poll interval 2s)
                    try:
                        await asyncio.wait_for(self._wake_event.wait(), timeout=2.0)
                        self._wake_event.clear()
                    except asyncio.TimeoutError:
                        pass
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Unexpected error in WebScanScheduler loop: %s", exc)
                await asyncio.sleep(1.0)

    async def _claim_next_job(self) -> Optional[str]:
        """Atomically claims the next pending job using optimistic status transition."""
        async with AsyncSessionLocal() as db:
            stmt = (
                select(WebScanJobModel)
                .where(WebScanJobModel.status == ScanState.PENDING.value)
                .order_by(WebScanJobModel.created_at.asc())
                .limit(1)
            )
            res = await db.execute(stmt)
            job = res.scalar_one_or_none()
            if not job:
                return None

            now = datetime.now(timezone.utc)
            # CAS update
            update_stmt = (
                update(WebScanJobModel)
                .where(
                    WebScanJobModel.id == job.id,
                    WebScanJobModel.version == job.version,
                    WebScanJobModel.status == ScanState.PENDING.value,
                )
                .values(
                    status=ScanState.QUEUED.value,
                    queued_at=now,
                    version=job.version + 1,
                )
            )
            res_update = await db.execute(update_stmt)
            if res_update.rowcount > 0:
                await db.commit()
                return job.id
            return None

    async def _execute_job_wrapper(self, job_id: str, cancel_event: asyncio.Event) -> None:
        """Executes a single job within semaphore and manages persistence of results."""
        if not self._global_semaphore:
            self._global_semaphore = asyncio.Semaphore(
                getattr(settings, "WEB_SCAN_GLOBAL_MAX_CONCURRENCY", 10000)
            )

        async with self._global_semaphore:
            if cancel_event.is_set():
                logger.info("Job %s was cancelled before acquiring semaphore slot; aborting", job_id)
                return

            try:
                # Load job details and enforce CAS transition from QUEUED -> SCANNING (F-07)
                async with AsyncSessionLocal() as db:
                    job = await db.get(WebScanJobModel, job_id)
                    if not job or job.status == ScanState.CANCELLED.value or cancel_event.is_set():
                        logger.info("Job %s is cancelled or absent; aborting execution", job_id)
                        return

                    now = datetime.now(timezone.utc)
                    update_stmt = (
                        update(WebScanJobModel)
                        .where(
                            WebScanJobModel.id == job_id,
                            WebScanJobModel.status == ScanState.QUEUED.value,
                        )
                        .values(
                            status=ScanState.SCANNING.value,
                            started_at=now,
                            version=job.version + 1,
                        )
                    )
                    res_update = await db.execute(update_stmt)
                    if res_update.rowcount == 0:
                        await db.rollback()
                        logger.info("Job %s status is not QUEUED; CAS aborted", job_id)
                        return
                    await db.commit()

                    config = ScanConfiguration(**(job.effective_configuration or {}))
                    target_url = job.normalized_target
                    current_seq = job.snapshot_sequence or 1

                # Define persistent event sink
                async def event_sink(event: WebScanEvent) -> None:
                    try:
                        async with AsyncSessionLocal() as ev_db:
                            ev_record = WebScanEventRecordModel(
                                scan_id=event.scan_id,
                                sequence=event.sequence,
                                type=event.type,
                                payload=jsonable_encoder(
                                    event.payload.model_dump(mode="json")
                                    if hasattr(event.payload, "model_dump")
                                    else event.payload
                                ),
                                occurred_at=event.occurred_at,
                            )
                            ev_db.add(ev_record)
                            await ev_db.commit()
                    except Exception as ev_err:
                        logger.warning("Error persisting scan event: %s", ev_err)

                # Initialize & run Engine
                engine = WebScanEngine(
                    scan_id=job_id,
                    target_url=target_url,
                    config=config,
                    cancel_event=cancel_event,
                    transport=self._mock_transport,
                    event_sink=event_sink,
                    initial_sequence=current_seq,
                    global_semaphore=self._global_semaphore,
                )

                final_state, scan_result, findings, observations, errors, status_reason = (
                    await engine.run()
                )

                summary_dict = scan_result.model_dump(mode="json")
                summary_dict["errors"] = [e.model_dump(mode="json") for e in errors]
                summary_dict = jsonable_encoder(summary_dict)

                # Persist outcomes in database
                async with AsyncSessionLocal() as db:
                    now = datetime.now(timezone.utc)
                    job_record = await db.get(WebScanJobModel, job_id)
                    if job_record:
                        if job_record.status == ScanState.CANCELLED.value and final_state != ScanState.CANCELLED:
                            logger.info("Job %s cancelled while executing; preserving CANCELLED state", job_id)
                            final_state = ScanState.CANCELLED

                        job_record.status = final_state.value
                        job_record.status_reason = status_reason
                        job_record.ended_at = now
                        job_record.version += 1
                        job_record.summary_data = summary_dict

                        # Save findings
                        for f in findings:
                            finding_model = WebScanFindingModel(
                                id=f.id,
                                scan_id=job_id,
                                module=f.module.value,
                                check_id=f.check_id,
                                category=f.category,
                                source_category=f.source_category,
                                severity=f.severity.value,
                                source_severity=f.source_severity.value if f.source_severity else None,
                                severity_reason=f.severity_reason,
                                confidence=f.confidence.value,
                                title=f.title,
                                description=f.description,
                                remediation=f.remediation,
                                evidence=jsonable_encoder(
                                    f.evidence.model_dump(mode="json")
                                    if hasattr(f.evidence, "model_dump")
                                    else f.evidence
                                ),
                                fingerprint=f.fingerprint,
                                occurrence_count=f.occurrence_count,
                                assessment_version=f.assessment_version,
                                first_seen_at=f.first_seen_at,
                                last_seen_at=f.last_seen_at,
                            )
                            db.add(finding_model)

                        # Save observations (sample up to 200 to bound DB size)
                        for obs in observations[:200]:
                            obs_model = WebScanObservationModel(
                                id=str(uuid.uuid4()),
                                scan_id=job_id,
                                module=obs.get("module", "recon"),
                                kind=obs.get("kind", "http_response"),
                                request_id=obs.get("request_id"),
                                data=jsonable_encoder(obs.get("data", {})),
                                observed_at=now,
                            )
                            db.add(obs_model)

                        await db.commit()

                # Stream finding_upserted events so dashboard findings table populates in real time (F-12)
                for f in findings:
                    engine.sequence += 1
                    await event_sink(
                        WebScanEvent(
                            scan_id=job_id,
                            sequence=engine.sequence,
                            occurred_at=datetime.now(timezone.utc),
                            type="finding_upserted",
                            payload=jsonable_encoder(
                                f.model_dump(mode="json")
                                if hasattr(f, "model_dump")
                                else f
                            ),
                        )
                    )

                # Emit final state_changed and completed events now that DB is fully committed
                next_seq = engine.sequence + 1
                await event_sink(
                    WebScanEvent(
                        scan_id=job_id,
                        sequence=next_seq,
                        occurred_at=datetime.now(timezone.utc),
                        type="state_changed",
                        payload={"status": final_state.value},
                    )
                )
                await event_sink(
                    WebScanEvent(
                        scan_id=job_id,
                        sequence=next_seq + 1,
                        occurred_at=datetime.now(timezone.utc),
                        type="completed",
                        payload=summary_dict,
                    )
                )

                # Update job's snapshot_sequence
                async with AsyncSessionLocal() as db:
                    job_record = await db.get(WebScanJobModel, job_id)
                    if job_record:
                        job_record.snapshot_sequence = next_seq + 1
                        await db.commit()

            except Exception as exc:
                logger.exception("Error executing scan job %s: %s", job_id, exc)
                async with AsyncSessionLocal() as db:
                    job_record = await db.get(WebScanJobModel, job_id)
                    if job_record:
                        job_record.status = ScanState.FAILED.value
                        job_record.status_reason = f"Execution error: {exc}"
                        job_record.ended_at = datetime.now(timezone.utc)
                        job_record.version += 1
                        await db.commit()
                if "engine" in locals() and "event_sink" in locals():
                    try:
                        await event_sink(
                            WebScanEvent(
                                scan_id=job_id,
                                sequence=getattr(engine, "sequence", 1) + 1,
                                occurred_at=datetime.now(timezone.utc),
                                type="state_changed",
                                payload={"status": ScanState.FAILED.value},
                            )
                        )
                    except Exception:
                        pass
            finally:
                self._cancel_events.pop(job_id, None)


# Global scheduler instance
web_scan_scheduler = WebScanScheduler()
