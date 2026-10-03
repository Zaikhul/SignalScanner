from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.web_scan.network_policy import redact_url_query_params
from app.core.web_scan.result_processor import score_to_risk_band
from app.db.web_scan_models import (
    WebScanAuditRecordModel,
    WebScanFindingModel,
    WebScanJobModel,
    WebScanObservationModel,
)
from app.schemas.web_scan import ScanJob, ScanResult, ScanSnapshot, Severity


def _sanitize_evidence(evidence: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Ensures all URL strings in evidence have query parameters redacted (F-18)."""
    if not evidence:
        return {}
    sanitized = dict(evidence)
    if "url_display" in sanitized and isinstance(sanitized["url_display"], str):
        sanitized["url_display"] = redact_url_query_params(sanitized["url_display"])
    if "url" in sanitized and isinstance(sanitized["url"], str):
        sanitized["url"] = redact_url_query_params(sanitized["url"])
    return sanitized


class WebScanExportService:
    """Provides multi-format exporting with deterministic checksums and audit logging."""

    @staticmethod
    async def export_scan(
        db: AsyncSession,
        tenant_id: str,
        principal_id: str,
        scan_id: str,
        export_format: str = "json",
    ) -> Tuple[str, str, str, str]:
        """
        Exports scan results.
        Returns: (content_str, content_type, filename, sha256_checksum)
        """
        # Load job
        stmt = select(WebScanJobModel).where(
            WebScanJobModel.tenant_id == tenant_id,
            WebScanJobModel.id == scan_id,
        )
        res = await db.execute(stmt)
        job = res.scalar_one_or_none()
        if not job:
            raise ValueError(f"Scan {scan_id} not found")

        # Load findings
        f_stmt = (
            select(WebScanFindingModel)
            .where(WebScanFindingModel.scan_id == scan_id)
            .order_by(WebScanFindingModel.first_seen_at.asc())
        )
        f_res = await db.execute(f_stmt)
        findings = f_res.scalars().all()

        # Load observations
        obs_stmt = (
            select(WebScanObservationModel)
            .where(WebScanObservationModel.scan_id == scan_id)
            .order_by(WebScanObservationModel.observed_at.asc())
        )
        obs_res = await db.execute(obs_stmt)
        observations = obs_res.scalars().all()

        summary = job.summary_data or {}
        fmt = export_format.lower().strip()

        if fmt == "json":
            content, ctype, fname = WebScanExportService._export_native_json(job, summary, findings, observations)
        elif fmt == "v2_json":
            content, ctype, fname = WebScanExportService._export_v2_json(job, summary, findings, observations)
        elif fmt == "txt":
            content, ctype, fname = WebScanExportService._export_txt(job, summary, findings)
        elif fmt == "sql":
            content, ctype, fname = WebScanExportService._export_sql(job, findings)
        else:
            raise ValueError(f"Unsupported export format: {export_format}. Supported: json, v2_json, txt, sql")

        # Compute SHA256 checksum
        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()

        # Audit record
        audit = WebScanAuditRecordModel(
            tenant_id=tenant_id,
            principal_id=principal_id,
            scan_id=scan_id,
            action="scan_exported",
            details={
                "format": fmt,
                "filename": fname,
                "checksum_sha256": checksum,
                "bytes": len(content.encode("utf-8")),
            },
            created_at=datetime.now(timezone.utc),
        )
        db.add(audit)
        await db.commit()

        return content, ctype, fname, checksum

    @staticmethod
    def _export_native_json(
        job: WebScanJobModel,
        summary: Dict[str, Any],
        findings: List[WebScanFindingModel],
        observations: List[WebScanObservationModel],
    ) -> Tuple[str, str, str]:
        data = {
            "schema_version": "web_scan.v1",
            "job": {
                "id": job.id,
                "target": redact_url_query_params(job.normalized_target),
                "target_display": redact_url_query_params(job.target_display),
                "status": job.status,
                "status_reason": job.status_reason,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "ended_at": job.ended_at.isoformat() if job.ended_at else None,
                "effective_configuration": job.effective_configuration,
            },
            "summary": summary,
            "findings": [
                {
                    "id": f.id,
                    "check_id": f.check_id,
                    "module": f.module,
                    "title": f.title,
                    "severity": f.severity,
                    "source_severity": f.source_severity,
                    "confidence": f.confidence,
                    "description": f.description,
                    "remediation": f.remediation,
                    "evidence": _sanitize_evidence(f.evidence),
                    "fingerprint": f.fingerprint,
                    "occurrence_count": f.occurrence_count,
                    "first_seen_at": f.first_seen_at.isoformat() if f.first_seen_at else None,
                }
                for f in findings
            ],
            "observations_count": len(observations),
        }
        content = json.dumps(data, indent=2)
        fname = f"scan_report_{job.id[:8]}_native.json"
        return content, "application/json", fname

    @staticmethod
    def _export_v2_json(
        job: WebScanJobModel,
        summary: Dict[str, Any],
        findings: List[WebScanFindingModel],
        observations: List[WebScanObservationModel],
    ) -> Tuple[str, str, str]:
        """Faithful projection to local Ghost Web Scanner json_report.py schema."""
        start_ts = job.started_at.isoformat() if job.started_at else ""
        end_ts = job.ended_at.isoformat() if job.ended_at else ""
        duration_sec = 0.0
        if job.started_at and job.ended_at:
            duration_sec = round((job.ended_at - job.started_at).total_seconds(), 2)

        v2_indices = summary.get("legacy_indices", {}).get("v2", {})
        risk_score = v2_indices.get("value", 0)
        risk_level = score_to_risk_band(risk_score).upper()

        # Extract technologies, subdomains, directories from observations
        technologies = []
        directories = []
        subdomains = []
        for obs in observations:
            obs_data = obs.data or {}
            if obs.kind == "http_response":
                srv = obs_data.get("server")
                if srv and srv not in technologies:
                    technologies.append(srv)
                waf = obs_data.get("waf")
                if waf and waf not in technologies:
                    technologies.append(waf)
                cms = obs_data.get("cms")
                if cms and cms not in technologies:
                    technologies.append(cms)
            elif obs.kind == "subdomain":
                sub = obs_data.get("subdomain")
                if sub and sub not in subdomains:
                    subdomains.append(sub)
            elif obs.kind == "path":
                p = obs_data.get("path")
                if p and p not in directories:
                    directories.append(p)

        report_dict = {
            "scan_id": job.id,
            "target": redact_url_query_params(job.normalized_target),
            "profile": (job.effective_configuration or {}).get("profile", "v2"),
            "start_time": start_ts,
            "end_time": end_ts,
            "duration": duration_sec,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "stats": {
                "total_requests": summary.get("requests", {}).get("completed", 0),
                "findings_count": len(findings),
                "duration_seconds": duration_sec,
            },
            "findings": [
                {
                    "category": f.source_category or f.category,
                    "severity": f.severity.upper(),
                    "description": f.description,
                    "url": redact_url_query_params((f.evidence or {}).get("url_display", job.normalized_target)),
                    "param": "",
                    "evidence": (
                        (f.evidence.get("excerpts", [{}])[0].get("value_redacted", ""))
                        if f.evidence and f.evidence.get("excerpts")
                        else ""
                    ),
                    "confidence": f.confidence.upper(),
                }
                for f in findings
            ],
            "technologies": technologies,
            "directories": directories,
            "subdomains": subdomains,
        }
        content = json.dumps(report_dict, indent=2)
        fname = f"scan_report_{job.id[:8]}_v2.json"
        return content, "application/json", fname

    @staticmethod
    def _export_txt(
        job: WebScanJobModel,
        summary: Dict[str, Any],
        findings: List[WebScanFindingModel],
    ) -> Tuple[str, str, str]:
        lines = [
            "=" * 70,
            "SIGNAL SCANNER - WEB SECURITY AUDIT REPORT",
            "=" * 70,
            f"Job ID:      {job.id}",
            f"Target:      {redact_url_query_params(job.target_display)}",
            f"Status:      {job.status.upper()}",
            f"Created At:  {job.created_at.isoformat() if job.created_at else 'N/A'}",
            f"Started At:  {job.started_at.isoformat() if job.started_at else 'N/A'}",
            f"Ended At:    {job.ended_at.isoformat() if job.ended_at else 'N/A'}",
            "-" * 70,
            "SUMMARY OF FINDINGS:",
        ]

        counts = summary.get("counts_by_severity", {})
        for sev in ["critical", "high", "medium", "low", "info"]:
            lines.append(f"  {sev.upper():<10}: {counts.get(sev, 0)}")

        v2_score = summary.get("legacy_indices", {}).get("v2", {}).get("value", 0)
        lines.append(f"  Risk Index (v2): {v2_score}/100")
        lines.append("-" * 70)
        lines.append("DETAILED FINDINGS:")

        if not findings:
            lines.append("  No security findings recorded.")
        else:
            for i, f in enumerate(findings, start=1):
                lines.append(f"\n[{i}] [{f.severity.upper()}] {f.title}")
                lines.append(f"    Check ID:    {f.check_id}")
                lines.append(f"    Confidence:  {f.confidence}")
                lines.append(f"    Reason:      {f.severity_reason}")
                lines.append(f"    Description: {f.description}")
                lines.append(f"    Remediation: {f.remediation}")
                evidence = f.evidence or {}
                if evidence.get("url_display"):
                    lines.append(f"    Target URL:  {redact_url_query_params(evidence.get('url_display'))}")

        lines.append("\n" + "=" * 70)
        content = "\n".join(lines)
        fname = f"scan_report_{job.id[:8]}.txt"
        return content, "text/plain", fname

    @staticmethod
    def _export_sql(
        job: WebScanJobModel,
        findings: List[WebScanFindingModel],
    ) -> Tuple[str, str, str]:
        """
        Exports findings as safe data-only SQL INSERT statements for breaker_logs.
        Strictly avoids DDL/DROP table stimulus.
        """
        lines = [
            "-- Signal Scanner Web Audit Data-Only Log Export",
            f"-- Generated for Scan: {job.id}",
            f"-- Target: {redact_url_query_params(job.target_display)}",
            f"-- Date: {datetime.now(timezone.utc).isoformat()}",
            "",
        ]

        def escape_sql(val: Optional[str]) -> str:
            if val is None:
                return "NULL"
            escaped = val.replace("'", "''")
            return f"'{escaped}'"

        for f in findings:
            evidence_json = json.dumps(_sanitize_evidence(f.evidence))
            now_iso = f.first_seen_at.isoformat() if f.first_seen_at else datetime.now(timezone.utc).isoformat()
            stmt = (
                f"INSERT INTO breaker_logs "
                f"(scan_id, target, check_id, title, severity, category, evidence, created_at) "
                f"VALUES ("
                f"{escape_sql(f.scan_id)}, "
                f"{escape_sql(redact_url_query_params(job.normalized_target))}, "
                f"{escape_sql(f.check_id)}, "
                f"{escape_sql(f.title)}, "
                f"{escape_sql(f.severity)}, "
                f"{escape_sql(f.category)}, "
                f"{escape_sql(evidence_json)}, "
                f"{escape_sql(now_iso)}"
                f");"
            )
            lines.append(stmt)

        content = "\n".join(lines)
        fname = f"scan_report_{job.id[:8]}_breaker_logs.sql"
        return content, "application/sql", fname
