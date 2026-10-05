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
            target_ep_id = f"tgt_{target_key.replace('.', '_').replace(':', '_')}"

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
                )

            # Map into relationship
            rel_key = (source_ep.id, target_ep_id)
            sc = data.get("status_code")
            meth = data.get("method") or "GET"

            linked_fids = list(obs_to_findings.get(obs.id, set()))

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

        # 6. Fallback if scan has no observations yet or empty
        if not relations_map:
            # Handle empty scan or scan with target configured only
            parsed_tgt = urlsplit(job.normalized_target if "://" in job.normalized_target else f"http://{job.normalized_target}")
            tgt_host = parsed_tgt.hostname or job.target_display
            is_valid_ip, _ = OfflineGeoIPService.parse_ip(tgt_host)
            ip_val = tgt_host if is_valid_ip else None
            geo_point, level, status, basis, reason = OfflineGeoIPService.lookup_target_ip(ip_val)

            fallback_tgt_id = f"tgt_{tgt_host.replace('.', '_').replace(':', '_')}"
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
            )

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
