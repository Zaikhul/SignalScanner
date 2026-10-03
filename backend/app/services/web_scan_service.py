from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Tuple
import uuid

from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.web_scan.network_policy import (
    validate_and_normalize_target,
    validate_target_against_scope,
)
from app.db.web_scan_models import (
    WebScanAuditRecordModel,
    WebScanEventRecordModel,
    WebScanFindingModel,
    WebScanJobModel,
    WebScanObservationModel,
    WebScanScopeModel,
    WebScanWsTicketModel,
)
from app.schemas.web_scan import (
    Confidence,
    CreateScanRequest,
    CreateScopeGrant,
    Evidence,
    EvidenceExcerpt,
    ModuleId,
    ScanConfiguration,
    ScanFinding,
    ScanJob,
    ScanObservation,
    ScanResult,
    ScanSnapshot,
    ScanState,
    ScopeGrant,
    Severity,
    WebScanEvent,
)

logger = logging.getLogger("signal_scanner.web_scan.service")


class WebScanService:
    """Service layer for Web Scanner scope, scan jobs, results, and ticketing."""

    # ──────────────────────────────────────────────────────────────────────────
    # Scope Grants
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    async def create_scope_grant(
        db: AsyncSession,
        tenant_id: str,
        principal_id: str,
        req: CreateScopeGrant,
    ) -> ScopeGrant:
        scope_id = str(uuid.uuid4())
        rules_dict = [r.model_dump() for r in req.rules]
        budget_dict = req.budget.model_dump()
        raw_hash = f"{req.authorization_reference}:{rules_dict}:{budget_dict}"
        scope_hash = hashlib.sha256(raw_hash.encode("utf-8")).hexdigest()[:32]

        now = datetime.now(timezone.utc)
        record = WebScanScopeModel(
            id=scope_id,
            tenant_id=tenant_id,
            authorization_reference=req.authorization_reference,
            assigned_principals=req.assigned_principal_ids,
            rules=rules_dict,
            budget=budget_dict,
            revision=1,
            scope_hash=scope_hash,
            allow_tls_unverified=req.allow_tls_unverified,
            allow_geolocation=req.allow_geolocation,
            allow_load=req.allow_load,
            allow_header_variants=req.allow_header_variants,
            created_at=now,
            created_by=principal_id,
            expires_at=req.expires_at,
        )
        db.add(record)

        audit = WebScanAuditRecordModel(
            tenant_id=tenant_id,
            principal_id=principal_id,
            action="scope_grant_created",
            details={"scope_id": scope_id, "ref": req.authorization_reference},
            created_at=now,
        )
        db.add(audit)
        await db.commit()
        await db.refresh(record)

        return ScopeGrant(
            id=record.id,
            tenant_id=record.tenant_id,
            authorization_reference=record.authorization_reference,
            assigned_principal_ids=record.assigned_principals,
            rules=req.rules,
            budget=req.budget,
            revision=record.revision,
            created_at=record.created_at,
            created_by=record.created_by,
            expires_at=record.expires_at,
            revoked_at=record.revoked_at,
            scope_hash=record.scope_hash,
            allow_tls_unverified=record.allow_tls_unverified,
            allow_geolocation=record.allow_geolocation,
            allow_load=record.allow_load,
            allow_header_variants=record.allow_header_variants,
        )

    @staticmethod
    async def get_scope_grant(
        db: AsyncSession,
        tenant_id: str,
        scope_id: str,
    ) -> Optional[ScopeGrant]:
        stmt = select(WebScanScopeModel).where(
            WebScanScopeModel.tenant_id == tenant_id,
            WebScanScopeModel.id == scope_id,
        )
        res = await db.execute(stmt)
        record = res.scalar_one_or_none()
        if not record:
            return None

        return ScopeGrant(
            id=record.id,
            tenant_id=record.tenant_id,
            authorization_reference=record.authorization_reference,
            assigned_principal_ids=record.assigned_principals,
            rules=record.rules,  # type: ignore[arg-type]
            budget=record.budget,  # type: ignore[arg-type]
            revision=record.revision,
            created_at=record.created_at,
            created_by=record.created_by,
            expires_at=record.expires_at,
            revoked_at=record.revoked_at,
            scope_hash=record.scope_hash,
            allow_tls_unverified=record.allow_tls_unverified,
            allow_geolocation=record.allow_geolocation,
            allow_load=record.allow_load,
            allow_header_variants=record.allow_header_variants,
        )

    @staticmethod
    async def list_scope_grants(
        db: AsyncSession,
        tenant_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[ScopeGrant], int]:
        total_stmt = select(func.count(WebScanScopeModel.id)).where(WebScanScopeModel.tenant_id == tenant_id)
        total_res = await db.execute(total_stmt)
        total = total_res.scalar_one() or 0

        stmt = (
            select(WebScanScopeModel)
            .where(WebScanScopeModel.tenant_id == tenant_id)
            .order_by(desc(WebScanScopeModel.created_at))
            .limit(limit)
            .offset(offset)
        )
        res = await db.execute(stmt)
        items = []
        for r in res.scalars().all():
            items.append(
                ScopeGrant(
                    id=r.id,
                    tenant_id=r.tenant_id,
                    authorization_reference=r.authorization_reference,
                    assigned_principal_ids=r.assigned_principals,
                    rules=r.rules,  # type: ignore[arg-type]
                    budget=r.budget,  # type: ignore[arg-type]
                    revision=r.revision,
                    created_at=r.created_at,
                    created_by=r.created_by,
                    expires_at=r.expires_at,
                    revoked_at=r.revoked_at,
                    scope_hash=r.scope_hash,
                    allow_tls_unverified=r.allow_tls_unverified,
                    allow_geolocation=r.allow_geolocation,
                    allow_load=r.allow_load,
                    allow_header_variants=r.allow_header_variants,
                )
            )
        return items, total

    @staticmethod
    async def revoke_scope_grant(
        db: AsyncSession,
        tenant_id: str,
        principal_id: str,
        scope_id: str,
    ) -> Optional[ScopeGrant]:
        stmt = select(WebScanScopeModel).where(
            WebScanScopeModel.tenant_id == tenant_id,
            WebScanScopeModel.id == scope_id,
        )
        res = await db.execute(stmt)
        record = res.scalar_one_or_none()
        if not record:
            return None

        now = datetime.now(timezone.utc)
        record.revoked_at = now
        audit = WebScanAuditRecordModel(
            tenant_id=tenant_id,
            principal_id=principal_id,
            action="scope_grant_revoked",
            details={"scope_id": scope_id},
            created_at=now,
        )
        db.add(audit)
        await db.commit()
        await db.refresh(record)

        return await WebScanService.get_scope_grant(db, tenant_id, scope_id)

    # ──────────────────────────────────────────────────────────────────────────
    # Scan Jobs
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    async def create_scan_job(
        db: AsyncSession,
        tenant_id: str,
        principal_id: str,
        req: CreateScanRequest,
        idempotency_key: Optional[str] = None,
    ) -> ScanJob:
        # Check idempotency key if provided
        if idempotency_key:
            stmt = select(WebScanJobModel).where(
                WebScanJobModel.tenant_id == tenant_id,
                WebScanJobModel.created_by == principal_id,
                WebScanJobModel.idempotency_key == idempotency_key,
            )
            res = await db.execute(stmt)
            existing = res.scalar_one_or_none()
            if existing:
                return WebScanService._model_to_schema(existing)

        # Validate target URL and policy
        config = req.configuration or ScanConfiguration()
        allow_private = config.allow_private

        # Validate Scope if specified
        scope_record = None
        if req.scope_id:
            scope_record = await db.get(WebScanScopeModel, req.scope_id)
            if not scope_record or scope_record.tenant_id != tenant_id:
                raise ValueError("Referenced scope_id does not exist")
            if scope_record.revoked_at:
                raise ValueError("Referenced scope_id has been revoked")
            exp = scope_record.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp < datetime.now(timezone.utc):
                raise ValueError("Referenced scope_id has expired")
            # If scope grants allow private, inherit
            for rule in scope_record.rules:
                if rule.get("allow_private"):
                    allow_private = True
                    break

        norm_target, display_target = validate_and_normalize_target(
            req.target,
            allow_private=allow_private,
        )

        if scope_record:
            is_valid, reason = validate_target_against_scope(norm_target, scope_record.rules)
            if not is_valid:
                raise ValueError(f"Target URL is outside authorized scope: {reason}")

        now = datetime.now(timezone.utc)
        job_id = str(uuid.uuid4())
        job = WebScanJobModel(
            id=job_id,
            tenant_id=tenant_id,
            created_by=principal_id,
            idempotency_key=idempotency_key,
            scope_id=scope_record.id if scope_record else None,
            scope_revision=scope_record.revision if scope_record else 1,
            scope_hash=scope_record.scope_hash if scope_record else "inline_scope",
            raw_target=req.target,
            normalized_target=norm_target,
            target_display=display_target,
            requested_configuration=config.model_dump(),
            effective_configuration=config.model_dump(),
            status=ScanState.PENDING.value,
            version=1,
            created_at=now,
            snapshot_sequence=1,
            summary_data={},
        )
        db.add(job)

        # Record initial event
        event = WebScanEventRecordModel(
            scan_id=job_id,
            sequence=1,
            type="state_changed",
            payload={"status": ScanState.PENDING.value},
            occurred_at=now,
        )
        db.add(event)

        audit = WebScanAuditRecordModel(
            tenant_id=tenant_id,
            principal_id=principal_id,
            scan_id=job_id,
            action="scan_created",
            details={"target": display_target, "profile": config.profile.value},
            created_at=now,
        )
        db.add(audit)

        await db.commit()
        await db.refresh(job)
        return WebScanService._model_to_schema(job)

    @staticmethod
    async def get_scan_job(
        db: AsyncSession,
        tenant_id: str,
        scan_id: str,
    ) -> Optional[ScanJob]:
        stmt = select(WebScanJobModel).where(
            WebScanJobModel.tenant_id == tenant_id,
            WebScanJobModel.id == scan_id,
        )
        res = await db.execute(stmt)
        record = res.scalar_one_or_none()
        if not record:
            return None
        return WebScanService._model_to_schema(record)

    @staticmethod
    async def list_scan_jobs(
        db: AsyncSession,
        tenant_id: str,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[ScanJob], int]:
        query = select(WebScanJobModel).where(WebScanJobModel.tenant_id == tenant_id)
        count_query = select(func.count(WebScanJobModel.id)).where(WebScanJobModel.tenant_id == tenant_id)

        if status:
            query = query.where(WebScanJobModel.status == status)
            count_query = count_query.where(WebScanJobModel.status == status)

        total_res = await db.execute(count_query)
        total = total_res.scalar_one() or 0

        stmt = query.order_by(desc(WebScanJobModel.created_at)).limit(limit).offset(offset)
        res = await db.execute(stmt)
        return [WebScanService._model_to_schema(r) for r in res.scalars().all()], total

    @staticmethod
    async def cancel_scan_job(
        db: AsyncSession,
        tenant_id: str,
        principal_id: str,
        scan_id: str,
    ) -> Optional[ScanJob]:
        stmt = select(WebScanJobModel).where(
            WebScanJobModel.tenant_id == tenant_id,
            WebScanJobModel.id == scan_id,
        )
        res = await db.execute(stmt)
        job = res.scalar_one_or_none()
        if not job:
            return None

        if job.status in (ScanState.COMPLETED.value, ScanState.FAILED.value, ScanState.TIMED_OUT.value):
            return WebScanService._model_to_schema(job)

        now = datetime.now(timezone.utc)
        job.cancel_requested_at = now

        # If still pending or queued, transition immediately to cancelled
        if job.status in (ScanState.PENDING.value, ScanState.QUEUED.value):
            job.status = ScanState.CANCELLED.value
            job.status_reason = "Cancelled by operator before execution"
            job.ended_at = now
            job.version += 1

            event = WebScanEventRecordModel(
                scan_id=job.id,
                sequence=job.snapshot_sequence + 1,
                type="state_changed",
                payload={"status": ScanState.CANCELLED.value},
                occurred_at=now,
            )
            job.snapshot_sequence += 1
            db.add(event)

        audit = WebScanAuditRecordModel(
            tenant_id=tenant_id,
            principal_id=principal_id,
            scan_id=scan_id,
            action="scan_cancellation_requested",
            details={"previous_status": job.status},
            created_at=now,
        )
        db.add(audit)
        await db.commit()
        await db.refresh(job)
        return WebScanService._model_to_schema(job)

    # ──────────────────────────────────────────────────────────────────────────
    # Findings, Observations, Snapshot
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    async def get_scan_snapshot(
        db: AsyncSession,
        tenant_id: str,
        scan_id: str,
    ) -> Optional[ScanSnapshot]:
        job_schema = await WebScanService.get_scan_job(db, tenant_id, scan_id)
        if not job_schema:
            return None

        stmt = select(WebScanJobModel).where(WebScanJobModel.id == scan_id)
        res = await db.execute(stmt)
        job = res.scalar_one()

        summary_data = job.summary_data or {}
        result = ScanResult(**summary_data) if summary_data else ScanResult()

        return ScanSnapshot(
            job=job_schema,
            result=result,
            errors=[],
        )

    @staticmethod
    async def list_scan_findings(
        db: AsyncSession,
        tenant_id: str,
        scan_id: str,
        severity: Optional[str] = None,
        module: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[ScanFinding], int]:
        # Verify job access
        job = await WebScanService.get_scan_job(db, tenant_id, scan_id)
        if not job:
            return [], 0

        query = select(WebScanFindingModel).where(WebScanFindingModel.scan_id == scan_id)
        count_query = select(func.count(WebScanFindingModel.id)).where(WebScanFindingModel.scan_id == scan_id)

        if severity:
            query = query.where(WebScanFindingModel.severity == severity.lower())
            count_query = count_query.where(WebScanFindingModel.severity == severity.lower())
        if module:
            query = query.where(WebScanFindingModel.module == module.lower())
            count_query = count_query.where(WebScanFindingModel.module == module.lower())
        if search:
            query = query.where(WebScanFindingModel.title.ilike(f"%{search}%"))
            count_query = count_query.where(WebScanFindingModel.title.ilike(f"%{search}%"))

        total_res = await db.execute(count_query)
        total = total_res.scalar_one() or 0

        stmt = query.order_by(desc(WebScanFindingModel.first_seen_at)).limit(limit).offset(offset)
        res = await db.execute(stmt)

        findings = []
        for r in res.scalars().all():
            evidence_data = r.evidence or {}
            excerpts = [
                EvidenceExcerpt(kind=e.get("kind", "text"), value_redacted=e.get("value_redacted", ""))
                for e in evidence_data.get("excerpts", [])
            ]
            findings.append(
                ScanFinding(
                    id=r.id,
                    scan_id=r.scan_id,
                    module=ModuleId(r.module),
                    check_id=r.check_id,
                    category=r.category,
                    source_category=r.source_category,
                    severity=Severity(r.severity.lower()),
                    source_severity=Severity(r.source_severity.lower()) if r.source_severity else None,
                    severity_reason=r.severity_reason,
                    confidence=Confidence(r.confidence),
                    title=r.title,
                    description=r.description,
                    remediation=r.remediation,
                    evidence=Evidence(
                        url_display=evidence_data.get("url_display", ""),
                        method=evidence_data.get("method"),
                        status_code=evidence_data.get("status_code"),
                        header_names=evidence_data.get("header_names", []),
                        excerpts=excerpts,
                        elapsed_ms=evidence_data.get("elapsed_ms"),
                        baseline_elapsed_ms=evidence_data.get("baseline_elapsed_ms"),
                    ),
                    fingerprint=r.fingerprint,
                    occurrence_count=r.occurrence_count,
                    assessment_version=r.assessment_version,
                    first_seen_at=r.first_seen_at,
                    last_seen_at=r.last_seen_at,
                )
            )

        return findings, total

    @staticmethod
    async def list_scan_observations(
        db: AsyncSession,
        tenant_id: str,
        scan_id: str,
        kind: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[ScanObservation], int]:
        job = await WebScanService.get_scan_job(db, tenant_id, scan_id)
        if not job:
            return [], 0

        query = select(WebScanObservationModel).where(WebScanObservationModel.scan_id == scan_id)
        count_query = select(func.count(WebScanObservationModel.id)).where(WebScanObservationModel.scan_id == scan_id)

        if kind:
            query = query.where(WebScanObservationModel.kind == kind)
            count_query = count_query.where(WebScanObservationModel.kind == kind)

        total_res = await db.execute(count_query)
        total = total_res.scalar_one() or 0

        stmt = query.order_by(desc(WebScanObservationModel.observed_at)).limit(limit).offset(offset)
        res = await db.execute(stmt)

        obs_list = []
        for r in res.scalars().all():
            obs_list.append(
                ScanObservation(
                    id=r.id,
                    scan_id=r.scan_id,
                    module=ModuleId(r.module),
                    kind=r.kind,
                    request_id=r.request_id,
                    data=r.data,
                    observed_at=r.observed_at,
                )
            )
        return obs_list, total

    @staticmethod
    async def list_scan_events(
        db: AsyncSession,
        tenant_id: str,
        scan_id: str,
        after_sequence: int = 0,
        limit: int = 500,
    ) -> List[WebScanEvent]:
        job = await WebScanService.get_scan_job(db, tenant_id, scan_id)
        if not job:
            return []

        stmt = (
            select(WebScanEventRecordModel)
            .where(
                WebScanEventRecordModel.scan_id == scan_id,
                WebScanEventRecordModel.sequence > after_sequence,
            )
            .order_by(WebScanEventRecordModel.sequence.asc())
            .limit(limit)
        )
        res = await db.execute(stmt)
        events = []
        for r in res.scalars().all():
            events.append(
                WebScanEvent(
                    scan_id=r.scan_id,
                    sequence=r.sequence,
                    occurred_at=r.occurred_at,
                    type=r.type,  # type: ignore[arg-type]
                    payload=r.payload,
                )
            )
        return events

    # ──────────────────────────────────────────────────────────────────────────
    # WebSocket Tickets
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    async def create_ws_ticket(
        db: AsyncSession,
        tenant_id: str,
        principal_id: str,
        scan_id: str,
    ) -> str:
        ticket = str(uuid.uuid4())
        ticket_hash = hashlib.sha256(ticket.encode("utf-8")).hexdigest()
        now = datetime.now(timezone.utc)
        record = WebScanWsTicketModel(
            ticket_hash=ticket_hash,
            scan_id=scan_id,
            principal_id=principal_id,
            tenant_id=tenant_id,
            created_at=now,
            expires_at=now + timedelta(seconds=60),  # Valid for 60 seconds
        )
        db.add(record)
        await db.commit()
        return ticket

    @staticmethod
    async def consume_ws_ticket(
        db: AsyncSession,
        ticket: str,
    ) -> Optional[Dict[str, Any]]:
        ticket_hash = hashlib.sha256(ticket.encode("utf-8")).hexdigest()
        stmt = select(WebScanWsTicketModel).where(
            WebScanWsTicketModel.ticket_hash == ticket_hash,
            WebScanWsTicketModel.consumed_at.is_(None),
        )
        res = await db.execute(stmt)
        record = res.scalar_one_or_none()
        if not record:
            return None

        now = datetime.now(timezone.utc)
        exp = record.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < now:
            return None

        record.consumed_at = now
        await db.commit()
        return {
            "scan_id": record.scan_id,
            "principal_id": record.principal_id,
            "tenant_id": record.tenant_id,
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Helper Serialization
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _model_to_schema(model: WebScanJobModel) -> ScanJob:
        req_cfg = ScanConfiguration(**(model.requested_configuration or {}))
        eff_cfg = ScanConfiguration(**(model.effective_configuration or {}))

        return ScanJob(
            id=model.id,
            schema_version="web_scan.v1",
            tenant_id=model.tenant_id,
            created_by=model.created_by,
            scope_id=model.scope_id,
            scope_revision=model.scope_revision,
            scope_hash=model.scope_hash,
            target_display=model.target_display,
            requested_configuration=req_cfg,
            effective_configuration=eff_cfg,
            status=ScanState(model.status),
            status_reason=model.status_reason,
            version=model.version,
            created_at=model.created_at,
            queued_at=model.queued_at,
            started_at=model.started_at,
            ended_at=model.ended_at,
            cancel_requested_at=model.cancel_requested_at,
            snapshot_sequence=model.snapshot_sequence,
        )
