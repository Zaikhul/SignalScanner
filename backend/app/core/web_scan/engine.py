from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple
import uuid

import httpx

from app.core.web_scan.html_parser import DiscoveredForm, parse_page_html
from app.core.web_scan.http_client import WebScanHttpClient, WebScanResponse
from app.core.web_scan.modules.cookie_audit import CookieAuditModule
from app.core.web_scan.modules.forms import FormsModule
from app.core.web_scan.modules.header_probes import HeaderProbesModule
from app.core.web_scan.modules.load_resilience import LoadResilienceModule
from app.core.web_scan.modules.parameters import ParametersModule
from app.core.web_scan.modules.recon import ReconModule
from app.core.web_scan.modules.security_headers import SecurityHeadersModule
from app.core.web_scan.registry import CAPABILITIES_CATALOG
from app.core.web_scan.result_processor import (
    build_scan_result,
    deduplicate_findings,
)
from app.schemas.web_scan import (
    CheckStatus,
    CoverageEntry,
    ErrorStage,
    ModuleId,
    ScanConfiguration,
    ScanError,
    ScanFinding,
    ScanResult,
    ScanState,
    WebScanEvent,
)

logger = logging.getLogger("signal_scanner.web_scan.engine")


class WebScanEngine:
    """Executes configured web scan modules with timeout, cancellation, and error handling."""

    def __init__(
        self,
        scan_id: str,
        target_url: str,
        config: ScanConfiguration,
        cancel_event: Optional[asyncio.Event] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        event_sink: Optional[Callable[[WebScanEvent], Awaitable[None]]] = None,
        initial_sequence: int = 1,
        global_semaphore: Optional[asyncio.Semaphore] = None,
        scope_rules: Optional[List[Dict[str, Any]]] = None,
    ):
        self.scan_id = scan_id
        self.target_url = target_url
        self.config = config
        self.cancel_event = cancel_event or asyncio.Event()
        self.transport = transport
        self.event_sink = event_sink
        self.sequence = initial_sequence
        self.global_semaphore = global_semaphore
        self.scope_rules = scope_rules

    async def _emit_event(self, event_type: str, payload: Any) -> None:
        """Helper to emit sequential scan events."""
        if not self.event_sink:
            return
        self.sequence += 1
        event = WebScanEvent(
            scan_id=self.scan_id,
            sequence=self.sequence,
            occurred_at=datetime.now(timezone.utc),
            type=event_type,  # type: ignore[arg-type]
            payload=payload,
        )
        try:
            await self.event_sink(event)
        except Exception as exc:
            logger.warning("Failed to emit scan event %s: %s", event_type, exc)

    async def run(
        self,
    ) -> Tuple[ScanState, ScanResult, List[ScanFinding], List[Dict[str, Any]], List[ScanError], Optional[str]]:
        """Executes the scan modules end-to-end within timeout and cancellation constraints."""
        all_raw_findings: List[Dict[str, Any]] = []
        all_observations: List[Dict[str, Any]] = []
        all_errors: List[ScanError] = []
        coverage_map: Dict[str, CoverageEntry] = {}
        load_metrics_data: Optional[Dict[str, Any]] = None

        # Determine enabled modules
        enabled_modules = list(self.config.modules)
        # Always run recon first if enabled
        module_order = [
            ModuleId.RECON,
            ModuleId.HEADERS,
            ModuleId.COOKIES,
            ModuleId.FORMS,
            ModuleId.PARAMETERS,
            ModuleId.HEADER_PROBES,
            ModuleId.LOAD,
        ]
        active_modules = [m for m in module_order if m in enabled_modules]

        # Populate initial coverage entries
        for desc in CAPABILITIES_CATALOG.checks:
            if desc.module in active_modules:
                coverage_map[desc.check_id] = CoverageEntry(
                    check_id=desc.check_id,
                    module=desc.module,
                    status=CheckStatus.PENDING,
                )
            else:
                coverage_map[desc.check_id] = CoverageEntry(
                    check_id=desc.check_id,
                    module=desc.module,
                    status=CheckStatus.SKIPPED,
                    reason_code="MODULE_DISABLED_BY_PROFILE",
                )

        final_state = ScanState.COMPLETED
        status_reason: Optional[str] = None

        http_client = WebScanHttpClient(
            target_url=self.target_url,
            config=self.config,
            transport=self.transport,
            cancel_event=self.cancel_event,
            global_semaphore=self.global_semaphore,
            scope_rules=self.scope_rules,
        )

        try:
            await self._emit_event("state_changed", {"status": ScanState.SCANNING.value})

            root_response: Optional[WebScanResponse] = None
            discovered_forms: List[DiscoveredForm] = []
            discovered_links: List[str] = []

            total_modules = len(active_modules)
            for idx, mod in enumerate(active_modules, start=1):
                if self.cancel_event.is_set():
                    final_state = ScanState.CANCELLED
                    status_reason = "Scan cancelled by operator"
                    break

                progress_percent = int(((idx - 1) / max(total_modules, 1)) * 100)
                await self._emit_event(
                    "progress",
                    {
                        "current_module": mod.value,
                        "progress_percent": progress_percent,
                        "modules_completed": idx - 1,
                        "modules_total": total_modules,
                    },
                )

                try:
                    if mod == ModuleId.RECON:
                        recon = ReconModule(http_client, self.target_url)
                        res = await asyncio.wait_for(
                            recon.run(),
                            timeout=min(self.config.timeout_seconds * 10, 60.0),
                        )
                        mod_findings = res.get("findings", [])
                        mod_obs = res.get("observations", [])
                        all_raw_findings.extend(mod_findings)
                        all_observations.extend(mod_obs)
                        root_response = res.get("root_response")

                        # Capture root response for downstream modules if not already captured
                        if not root_response:
                            for obs in mod_obs:
                                if obs.get("kind") == "http_response":
                                    root_response = await http_client.fetch(self.target_url)
                                    break

                        # Mark recon checks accurately (F-08, F-15)
                        if not root_response and res.get("status") == "failed":
                            for cid, entry in coverage_map.items():
                                if entry.module == ModuleId.RECON:
                                    entry.status = CheckStatus.INCONCLUSIVE
                                    entry.reason_code = "ROOT_TARGET_UNREACHABLE"
                        else:
                            for cid, entry in coverage_map.items():
                                if entry.module == ModuleId.RECON:
                                    if cid == "recon.geolocation":
                                        entry.status = CheckStatus.SKIPPED
                                        entry.reason_code = "OPTIONAL_FEATURE_DISABLED"
                                    elif cid == "recon.subdomain_enumeration":
                                        entry.status = CheckStatus.SKIPPED
                                        entry.reason_code = "SUBDOMAIN_ENUM_DISABLED"
                                    else:
                                        entry.status = CheckStatus.COMPLETED

                    elif mod == ModuleId.HEADERS:
                        if not root_response:
                            root_response = await http_client.fetch(self.target_url)
                        if root_response:
                            sec_headers = SecurityHeadersModule(root_response, self.target_url)
                            res = sec_headers.run()
                            mod_findings = res.get("findings", [])
                            all_raw_findings.extend(mod_findings)
                            all_observations.extend(res.get("observations", []))

                            for cid, entry in coverage_map.items():
                                if entry.module == ModuleId.HEADERS:
                                    entry.status = CheckStatus.COMPLETED
                        else:
                            for cid, entry in coverage_map.items():
                                if entry.module == ModuleId.HEADERS:
                                    entry.status = CheckStatus.INCONCLUSIVE
                                    entry.reason_code = "ROOT_TARGET_UNREACHABLE"

                    elif mod == ModuleId.COOKIES:
                        if not root_response:
                            root_response = await http_client.fetch(self.target_url)
                        if root_response:
                            cookie_audit = CookieAuditModule(root_response, self.target_url)
                            res = cookie_audit.run()
                            mod_findings = res.get("findings", [])
                            all_raw_findings.extend(mod_findings)
                            all_observations.extend(res.get("observations", []))

                            for cid, entry in coverage_map.items():
                                if entry.module == ModuleId.COOKIES:
                                    entry.status = CheckStatus.COMPLETED
                        else:
                            for cid, entry in coverage_map.items():
                                if entry.module == ModuleId.COOKIES:
                                    entry.status = CheckStatus.INCONCLUSIVE
                                    entry.reason_code = "ROOT_TARGET_UNREACHABLE"

                    elif mod == ModuleId.FORMS:
                        if not root_response:
                            root_response = await http_client.fetch(self.target_url)
                        if root_response:
                            discovered_forms, discovered_links = parse_page_html(
                                self.target_url, root_response.text
                            )
                            forms_mod = FormsModule(root_response, self.target_url)
                            res = forms_mod.run()
                            mod_findings = res.get("findings", [])
                            all_raw_findings.extend(mod_findings)
                            all_observations.extend(res.get("observations", []))

                            for cid, entry in coverage_map.items():
                                if entry.module == ModuleId.FORMS:
                                    entry.status = CheckStatus.COMPLETED
                        else:
                            for cid, entry in coverage_map.items():
                                if entry.module == ModuleId.FORMS:
                                    entry.status = CheckStatus.INCONCLUSIVE
                                    entry.reason_code = "ROOT_TARGET_UNREACHABLE"

                    elif mod == ModuleId.PARAMETERS:
                        if not discovered_forms and root_response:
                            discovered_forms, _ = parse_page_html(self.target_url, root_response.text)
                        param_mod = ParametersModule(
                            http_client=http_client,
                            target_url=self.target_url,
                            discovered_forms=discovered_forms,
                            seed=self.config.random_seed,
                        )
                        res = await asyncio.wait_for(
                            param_mod.run(),
                            timeout=min(self.config.timeout_seconds * 10, 90.0),
                        )
                        mod_findings = res.get("findings", [])
                        all_raw_findings.extend(mod_findings)
                        all_observations.extend(res.get("observations", []))

                        if res.get("status") == "skipped":
                            for cid, entry in coverage_map.items():
                                if entry.module == ModuleId.PARAMETERS:
                                    entry.status = CheckStatus.SKIPPED
                                    entry.reason_code = res.get("reason", "NO_PARAMETERS_FOUND")
                        else:
                            for cid, entry in coverage_map.items():
                                if entry.module == ModuleId.PARAMETERS:
                                    entry.status = CheckStatus.COMPLETED

                    elif mod == ModuleId.HEADER_PROBES:
                        if not discovered_links and root_response:
                            _, discovered_links = parse_page_html(self.target_url, root_response.text)
                        header_probes_mod = HeaderProbesModule(
                            http_client=http_client,
                            target_url=self.target_url,
                            discovered_links=discovered_links,
                        )
                        res = await asyncio.wait_for(
                            header_probes_mod.run(),
                            timeout=min(self.config.timeout_seconds * 10, 60.0),
                        )
                        mod_findings = res.get("findings", [])
                        all_raw_findings.extend(mod_findings)
                        all_observations.extend(res.get("observations", []))

                        for cid, entry in coverage_map.items():
                            if entry.module == ModuleId.HEADER_PROBES:
                                entry.status = CheckStatus.COMPLETED

                    elif mod == ModuleId.LOAD:
                        load_mod = LoadResilienceModule(
                            http_client=http_client,
                            target_url=self.target_url,
                            load_config=self.config.load,
                            cancel_event=self.cancel_event,
                        )
                        res = await load_mod.run()
                        load_metrics_data = res.get("metrics")
                        mod_findings = res.get("findings", [])
                        all_raw_findings.extend(mod_findings)
                        all_observations.extend(res.get("observations", []))

                        for cid, entry in coverage_map.items():
                            if entry.module == ModuleId.LOAD:
                                entry.status = CheckStatus.COMPLETED

                except asyncio.CancelledError:
                    final_state = ScanState.CANCELLED
                    status_reason = "Scan cancelled by operator"
                    break
                except asyncio.TimeoutError:
                    logger.warning("Module %s timed out", mod.value)
                    err = ScanError(
                        id=str(uuid.uuid4()),
                        scan_id=self.scan_id,
                        module=mod,
                        code="MODULE_TIMEOUT",
                        stage=ErrorStage.MODULE_EXECUTION,
                        message=f"Module {mod.value} exceeded allocated time budget",
                        retryable=False,
                        occurred_at=datetime.now(timezone.utc),
                    )
                    all_errors.append(err)
                    await self._emit_event("error_added", err)
                    for cid, entry in coverage_map.items():
                        if entry.module == mod and entry.status == CheckStatus.PENDING:
                            entry.status = CheckStatus.INCONCLUSIVE
                            entry.reason_code = "TIMEOUT"
                except Exception as exc:
                    logger.exception("Error executing module %s: %s", mod.value, exc)
                    err = ScanError(
                        id=str(uuid.uuid4()),
                        scan_id=self.scan_id,
                        module=mod,
                        code="MODULE_EXCEPTION",
                        stage=ErrorStage.MODULE_EXECUTION,
                        message=str(exc),
                        retryable=False,
                        occurred_at=datetime.now(timezone.utc),
                    )
                    all_errors.append(err)
                    await self._emit_event("error_added", err)
                    for cid, entry in coverage_map.items():
                        if entry.module == mod and entry.status == CheckStatus.PENDING:
                            entry.status = CheckStatus.INCONCLUSIVE
                            entry.reason_code = "MODULE_ERROR"

            if self.cancel_event.is_set() and final_state != ScanState.CANCELLED:
                final_state = ScanState.CANCELLED
                status_reason = "Scan cancelled by operator"

        except Exception as fatal_exc:
            logger.exception("Fatal scan engine error: %s", fatal_exc)
            final_state = ScanState.FAILED
            status_reason = f"Fatal scan engine error: {fatal_exc}"
            err = ScanError(
                id=str(uuid.uuid4()),
                scan_id=self.scan_id,
                code="FATAL_ENGINE_ERROR",
                stage=ErrorStage.MODULE_EXECUTION,
                message=str(fatal_exc),
                retryable=False,
                occurred_at=datetime.now(timezone.utc),
            )
            all_errors.append(err)
            await self._emit_event("error_added", err)
        finally:
            # Harvest recorded network errors from http_client (F-08, F-11)
            for req_err in http_client.recorded_errors:
                err = ScanError(
                    id=str(uuid.uuid4()),
                    scan_id=self.scan_id,
                    module=None,
                    code=req_err.get("code", "NETWORK_REQUEST_FAILED"),
                    stage=ErrorStage.MODULE_EXECUTION,
                    message=req_err.get("message", "HTTP request failed"),
                    retryable=False,
                    occurred_at=datetime.now(timezone.utc),
                )
                all_errors.append(err)
            await http_client.aclose()

        # F-08: Target unreachable taxonomy & scan state determination
        if final_state != ScanState.CANCELLED:
            total_attempts = http_client.ledger.attempt_count
            total_success = http_client.ledger.success_count
            if total_attempts > 0 and total_success == 0:
                final_state = ScanState.FAILED
                status_reason = "Target host unreachable or all network requests failed"
            elif not root_response and any(m in active_modules for m in [ModuleId.HEADERS, ModuleId.COOKIES, ModuleId.FORMS]):
                final_state = ScanState.FAILED
                status_reason = "Target root URL unreachable"
            elif any(e.stage == ErrorStage.MODULE_EXECUTION and e.code in ("MODULE_EXCEPTION", "MODULE_TIMEOUT") for e in all_errors):
                final_state = ScanState.PARTIAL
                status_reason = "Scan completed with partial module failures"
            elif any(entry.status == CheckStatus.INCONCLUSIVE for entry in coverage_map.values()):
                final_state = ScanState.PARTIAL
                status_reason = "Scan completed with inconclusive checks"
            else:
                final_state = ScanState.COMPLETED

        # Build deduplicated findings and result summary (F-16: ledger metrics passed)
        deduped_findings = deduplicate_findings(all_raw_findings, self.scan_id)
        scan_result = build_scan_result(
            findings=deduped_findings,
            observations=all_observations,
            errors_count=len(all_errors),
            load_metrics_data=load_metrics_data,
            coverage=list(coverage_map.values()),
            request_metrics=http_client.ledger.to_metrics(),
        )

        if final_state != ScanState.CANCELLED:
            await self._emit_event(
                "progress",
                {
                    "current_module": "completed",
                    "progress_percent": 100,
                    "modules_completed": total_modules,
                    "modules_total": total_modules,
                },
            )

        return final_state, scan_result, deduped_findings, all_observations, all_errors, status_reason
