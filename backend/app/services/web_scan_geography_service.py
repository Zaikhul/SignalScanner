from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.web_scan.geolocation import OfflineGeoIPService
from app.db.web_scan_models import (
    WebScanFindingModel,
    WebScanJobModel,
    WebScanObservationModel,
)
from app.schemas.web_scan_geography import (
    GeoCoverage,
    GeoEndpoint,
    GeoPoint,
    GeoRelation,
    WebScanGeographyResponse,
)

logger = logging.getLogger("signal_scanner.web_scan.geography")

MANDATORY_DISCLAIMER = (
    "Lokasi IP merupakan perkiraan. Garis menunjukkan hubungan permintaan yang divisualisasikan, "
    "bukan rute paket atau lokasi fisik yang terverifikasi."
)

SEVERITY_RANK: Dict[str, int] = {
    "critical": 5,
    "high": 4,
    "medium": 3,
    "low": 2,
    "info": 1,
    "none": 0,
}


def _compute_finding_summary(
    finding_ids: List[str],
    findings_by_id: Dict[str, WebScanFindingModel],
) -> Tuple[str, Dict[str, int]]:
    # Menghitung tingkat keparahan tertinggi dan distribusi jumlah temuan untuk suatu relasi/endpoint.
    counts: Dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    highest = "none"
    for fid in finding_ids:
        f_obj = findings_by_id.get(fid)
        if not f_obj:
            continue
        sev = (f_obj.severity or "info").lower()
        if sev in counts:
            counts[sev] += 1
        if SEVERITY_RANK.get(sev, 0) > SEVERITY_RANK.get(highest, 0):
            highest = sev
    return highest, {k: v for k, v in counts.items() if v > 0}


class WebScanGeographyService:
    """Orchestrates scan relationship graph, endpoint geolocation enrichment, and coverage metrics."""

    @classmethod
    async def get_scan_geography(
        cls,
        db: AsyncSession,
        tenant_id: str,
        scan_id: str,
    ) -> Optional[WebScanGeographyResponse]:
        # 1. Fetch scan job
        job_stmt = select(WebScanJobModel).where(
            WebScanJobModel.tenant_id == tenant_id,
            WebScanJobModel.id == scan_id,
        )
        res_job = await db.execute(job_stmt)
        job = res_job.scalar_one_or_none()
        if not job:
            return None

        now = datetime.now(timezone.utc)
        summary_data = job.summary_data or {}
        obs_total_reported = summary_data.get("observations_total", 0)

        # 2. Fetch observations
        obs_stmt = select(WebScanObservationModel).where(
            WebScanObservationModel.scan_id == scan_id
        ).order_by(WebScanObservationModel.observed_at.asc())
        res_obs = await db.execute(obs_stmt)
        obs_records = res_obs.scalars().all()
        obs_stored_count = len(obs_records)
        is_subset = obs_total_reported > obs_stored_count and obs_stored_count >= 200

        # 3. Fetch findings to cross-reference evidence
        find_stmt = select(WebScanFindingModel).where(
            WebScanFindingModel.scan_id == scan_id
        )
        res_find = await db.execute(find_stmt)
        findings = res_find.scalars().all()
        findings_by_id: Dict[str, WebScanFindingModel] = {f.id: f for f in findings}

        obs_to_findings: Dict[str, Set[str]] = {}
        for f in findings:
            ev = f.evidence or {}
            matched_obs_ids = ev.get("observation_ids") or []
            if isinstance(matched_obs_ids, list):
                for oid in matched_obs_ids:
                    obs_to_findings.setdefault(oid, set()).add(f.id)
            req_id = ev.get("request_id")
            if req_id:
                obs_to_findings.setdefault(req_id, set()).add(f.id)

        # 4. Resolve source endpoint
        source_ep = OfflineGeoIPService.resolve_source_endpoint(settings)
        endpoints_map: Dict[str, GeoEndpoint] = {source_ep.id: source_ep}
        relations_map: Dict[Tuple[str, str], GeoRelation] = {}
        latency_samples_by_rel: Dict[Tuple[str, str], List[float]] = {}

        eligible_records_count = 0

        # 5. Process observations
        for obs in obs_records:
            data = obs.data or {}
            kind = obs.kind

            # Filter for eligible HTTP/endpoint touch observations
            is_http = kind == "http_response" or "url_display" in data or "target_ip" in data
            if not is_http:
                continue

            eligible_records_count += 1

            # Extract target IP and DNS attribution
            target_ip = data.get("target_ip") or data.get("peer_ip")
            dns_candidates = data.get("dns_candidates") or []
            url_disp = data.get("url_display") or job.target_display or job.normalized_target

            host = ""
            if url_disp:
                parsed_url = urlsplit(url_disp if "://" in url_disp else f"http://{url_disp}")
                host = parsed_url.hostname or url_disp

            # If no explicit target_ip, inspect if host is an IP
            if not target_ip and host:
                is_valid_ip, _ = OfflineGeoIPService.parse_ip(host)
                if is_valid_ip:
                    target_ip = host
                elif dns_candidates and len(dns_candidates) > 0:
                    target_ip = dns_candidates[0]

            # Determine address basis
            if data.get("peer_ip"):
                address_basis = "observed_connection"
            elif data.get("target_ip"):
                address_basis = "transport_selected"
            elif dns_candidates:
                address_basis = "dns_candidate"
            elif target_ip:
                address_basis = "transport_selected"
            else:
                address_basis = "unresolved"

            target_key = target_ip or host or "unresolved_target"
            target_ep_id = f"tgt_{target_key.replace(".", "_").replace(":", "_")}"

            if target_ep_id not in endpoints_map:
                geo_point, level, status, basis, reason = OfflineGeoIPService.lookup_target_ip(target_ip)
                endpoints_map[target_ep_id] = GeoEndpoint(
                    id=target_ep_id,
                    role="target",
                    display_name=host if host else (target_ip or "Target Endpoint"),
                    ip=target_ip,
                    address_basis=address_basis,
                    executor_id=None,
                    location=geo_point,
                    location_level=level,
                    location_basis=basis,
                    location_status=status,
                    status_reason=reason,
                    provider_info="Offline GeoIP Registry v2026.1" if status == "located" else None,
                    hostnames=[host] if host else [],
                )
            else:
                if host and host not in endpoints_map[target_ep_id].hostnames:
                    endpoints_map[target_ep_id].hostnames.append(host)

            # Map into relationship
            rel_key = (source_ep.id, target_ep_id)
            sc = data.get("status_code")
            meth = data.get("method") or "GET"

            elapsed = data.get("elapsed_ms")
            if elapsed is None:
                elapsed = data.get("latency_ms")
            if elapsed is not None:
                try:
                    latency_samples_by_rel.setdefault(rel_key, []).append(float(elapsed))
                except (ValueError, TypeError):
                    pass

            b_val = data.get("decompressed_bytes") or data.get("response_bytes") or data.get("content_length") or 0
            try:
                b_count = int(b_val)
            except (ValueError, TypeError):
                b_count = 0

            obs_at = obs.observed_at

            linked_fids = list(obs_to_findings.get(obs.id, set()))
            obs_mod = getattr(obs, "module", None)

            if rel_key not in relations_map:
                relations_map[rel_key] = GeoRelation(
                    id=f"rel_{source_ep.id}_{target_ep_id}",
                    source_endpoint_id=source_ep.id,
                    target_endpoint_id=target_ep_id,
                    direction="source_to_target",
                    relation_basis="observed_http" if address_basis == "observed_connection" else "transport_attempt",
                    record_count=1,
                    unit="records",
                    status_codes=[sc] if isinstance(sc, int) else [],
                    methods=[meth] if meth else [],
                    supporting_observation_ids=[obs.id],
                    linked_finding_ids=linked_fids,
                    module_ids=[obs_mod] if obs_mod else [],
                    total_bytes=b_count,
                    first_observed_at=obs_at,
                    last_observed_at=obs_at,
                )
            else:
                rel = relations_map[rel_key]
                rel.record_count += 1
                if isinstance(sc, int) and sc not in rel.status_codes:
                    rel.status_codes.append(sc)
                if meth and meth not in rel.methods:
                    rel.methods.append(meth)
                if obs.id not in rel.supporting_observation_ids:
                    rel.supporting_observation_ids.append(obs.id)
                for fid in linked_fids:
                    if fid not in rel.linked_finding_ids:
                        rel.linked_finding_ids.append(fid)
                if obs_mod and obs_mod not in rel.module_ids:
                    rel.module_ids.append(obs_mod)
                rel.total_bytes += b_count
                if obs_at:
                    if not rel.first_observed_at or obs_at < rel.first_observed_at:
                        rel.first_observed_at = obs_at
                    if not rel.last_observed_at or obs_at > rel.last_observed_at:
                        rel.last_observed_at = obs_at

        # 6. Fallback if scan has no observations yet or empty
        if not relations_map:
            parsed_tgt = urlsplit(job.normalized_target if "://" in job.normalized_target else f"http://{job.normalized_target}")
            tgt_host = parsed_tgt.hostname or job.target_display
            is_valid_ip, _ = OfflineGeoIPService.parse_ip(tgt_host)
            ip_val = tgt_host if is_valid_ip else None
            geo_point, level, status, basis, reason = OfflineGeoIPService.lookup_target_ip(ip_val)

            fallback_tgt_id = f"tgt_{tgt_host.replace(".", "_").replace(":", "_")}"
            fallback_finding_count = len(findings)
            fallback_highest_sev, _ = _compute_finding_summary([f.id for f in findings], findings_by_id)

            endpoints_map[fallback_tgt_id] = GeoEndpoint(
                id=fallback_tgt_id,
                role="target",
                display_name=job.target_display,
                ip=ip_val,
                address_basis="configured",
                executor_id=None,
                location=geo_point,
                location_level=level,
                location_basis=basis,
                location_status=status,
                status_reason=reason or "Configured scan target with no recorded HTTP observations yet",
                provider_info="Offline GeoIP Registry v2026.1" if status == "located" else None,
                hostnames=[tgt_host] if tgt_host else [],
                highest_severity=fallback_highest_sev,  # type: ignore[assignment]
                finding_count=fallback_finding_count,
            )
        else:
            # Jika semua temuan berasal dari domain target utama namun belum memiliki observation_ids spesifik,
            # kaitkan pada relasi utama jika hanya ada 1 target endpoint:
            if len(relations_map) == 1 and findings:
                only_rel = next(iter(relations_map.values()))
                if not only_rel.linked_finding_ids:
                    only_rel.linked_finding_ids = [f.id for f in findings]

            for rel_key, rel in relations_map.items():
                latencies = latency_samples_by_rel.get(rel_key, [])
                if latencies:
                    rel.avg_latency_ms = round(sum(latencies) / len(latencies), 1)
                    rel.max_latency_ms = round(max(latencies), 1)

                highest_sev, sev_counts = _compute_finding_summary(rel.linked_finding_ids, findings_by_id)
                rel.highest_severity = highest_sev  # type: ignore[assignment]
                rel.finding_counts = sev_counts

            # Agregasi temuan ke setiap target endpoint
            ep_findings_map: Dict[str, Set[str]] = {}
            for rel in relations_map.values():
                if rel.target_endpoint_id in endpoints_map:
                    ep_findings_map.setdefault(rel.target_endpoint_id, set()).update(rel.linked_finding_ids)

            for ep_id, fids in ep_findings_map.items():
                tgt_ep = endpoints_map.get(ep_id)
                if tgt_ep:
                    tgt_ep.finding_count = len(fids)
                    highest_sev, _ = _compute_finding_summary(list(fids), findings_by_id)
                    tgt_ep.highest_severity = highest_sev  # type: ignore[assignment]

        endpoints_list = list(endpoints_map.values())
        relations_list = list(relations_map.values())

        # 7. Calculate coverage metrics
        both_located = 0
        partial_located = 0
        unlocated = 0

        for r in relations_list:
            s_ep = endpoints_map.get(r.source_endpoint_id)
            t_ep = endpoints_map.get(r.target_endpoint_id)
            s_loc = s_ep and s_ep.location_status == "located"
            t_loc = t_ep and t_ep.location_status == "located"
            if s_loc and t_loc:
                both_located += 1
            elif s_loc or t_loc:
                partial_located += 1
            else:
                unlocated += 1

        coverage = GeoCoverage(
            observations_total=max(obs_total_reported, obs_stored_count),
            observations_stored=obs_stored_count,
            eligible_records=eligible_records_count,
            both_located_count=both_located,
            partial_located_count=partial_located,
            unlocated_count=unlocated,
            is_subset=is_subset,
            storage_ceiling=200,
        )

        # 8. Readiness status
        if job.status in ("pending", "queued", "scanning") and obs_stored_count == 0:
            readiness_status = "processing"
        elif obs_stored_count == 0 and not relations_list:
            readiness_status = "empty"
        elif both_located > 0:
            readiness_status = "ready"
        elif partial_located > 0:
            readiness_status = "partial"
        else:
            readiness_status = "no_locations"

        return WebScanGeographyResponse(
            scan_id=scan_id,
            schema_version="web_scan.geo.v1",
            data_revision=job.version,
            generated_at=now,
            readiness_status=readiness_status,
            target_display=job.target_display,
            scan_status=job.status,
            coverage=coverage,
            endpoints=endpoints_list,
            relations=relations_list,
            time_info={
                "event_at": None,
                "persisted_at": now.isoformat(),
                "time_basis": "observation_persistence_time",
                "is_legacy_data": False,
            },
            disclaimers={
                "mandatory_notice": MANDATORY_DISCLAIMER,
                "data_provenance": "Observed scan responses cross-referenced with server executor configuration and offline IP registry.",
            },
        )
