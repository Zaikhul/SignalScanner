from datetime import datetime, timezone
import hashlib
import ipaddress
import io
import csv
from typing import Any, Dict, List, Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.stream_engine import stream_engine
from app.db.models import (
    AssociationEventModel,
    LanHostModel,
    ScanSessionModel,
    WifiAssociationModel,
)
from app.schemas.association import (
    AssociationEventResponse,
    AssociationResponse,
    AssociationState,
    ConnectAssociationRequest,
    CreateAssociationDraftRequest,
    IngestAssociationStatusRequest,
    LanHostItem,
)
from app.schemas.common import ScanMode
from app.services.collector_service import collector_service


class AssociationService:
    @staticmethod
    async def create_draft(
        db: AsyncSession, session_id: str, payload: CreateAssociationDraftRequest
    ) -> AssociationResponse:
        # Check session exists
        session_res = await db.execute(
            select(ScanSessionModel).where(ScanSessionModel.id == session_id)
        )
        session = session_res.scalar_one_or_none()
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Scan session '{session_id}' not found",
            )

        association = WifiAssociationModel(
            session_id=session_id,
            collector_id=session.collector_id,
            adapter_id="win_wlan_01",
            target_id=payload.target_id,
            ssid=payload.ssid,
            bssid_hash=payload.bssid_hash,
            security_type=payload.security_hint or "wpa2_personal",
            state=AssociationState.IDLE.value,
        )
        db.add(association)
        await db.flush()

        event = AssociationEventModel(
            association_id=association.id,
            from_state="none",
            to_state=AssociationState.IDLE.value,
            actor_id="user",
            metadata_json={"action": "create_draft"},
        )
        db.add(event)
        await db.commit()
        await db.refresh(association)

        return AssociationService._to_response(association)

    @staticmethod
    async def connect(
        db: AsyncSession, association_id: str, payload: ConnectAssociationRequest
    ) -> AssociationResponse:
        assoc_res = await db.execute(
            select(WifiAssociationModel).where(WifiAssociationModel.id == association_id)
        )
        assoc = assoc_res.scalar_one_or_none()
        if not assoc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Association '{association_id}' not found",
            )

        # FR-CON-06: Authorized use gate
        if not payload.authorized_use_confirmed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="AUTHORIZED_USE_REQUIRED: Hubungkan hanya berjalan setelah konfirmasi wewenang.",
            )

        # FR-CON-04: Enterprise is unsupported
        if payload.security_hint.lower() in ("enterprise", "wpa_enterprise", "wpa2_enterprise", "802.1x"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="WIFI_ENTERPRISE_UNSUPPORTED: Jaringan enterprise belum didukung pada versi ini.",
            )

        old_state = assoc.state
        assoc.state = AssociationState.ASSOCIATING.value
        assoc.security_type = payload.security_hint
        assoc.save_profile_requested = payload.save_profile
        assoc.forget_profile_on_exit = not payload.save_profile

        # Audit event
        event = AssociationEventModel(
            association_id=assoc.id,
            from_state=old_state,
            to_state=AssociationState.ASSOCIATING.value,
            actor_id="user",
            metadata_json={
                "authorized_use_confirmed": True,
                "save_profile": payload.save_profile,
                "timeout_seconds": payload.timeout_seconds,
                "credential_supplied": True,  # Flag boolean only, never the secret!
            },
        )
        db.add(event)
        await db.commit()
        await db.refresh(assoc)

        # Queue command to collector (without password!)
        collector_service.queue_command(
            collector_id=assoc.collector_id,
            type="associate_wifi",
            session_id=assoc.session_id,
            mode=ScanMode.WIFI,
            parameters={
                "association_id": assoc.id,
                "target_id": payload.target_id,
                "ssid": assoc.ssid,
                "security_hint": payload.security_hint,
                "save_profile": payload.save_profile,
                "timeout_seconds": payload.timeout_seconds,
            },
        )

        # Broadcast WS event
        await stream_engine.publish_event(
            assoc.session_id,
            {
                "schema_version": "1.1",
                "type": "association.state_changed",
                "session_id": assoc.session_id,
                "association_id": assoc.id,
                "from_state": old_state,
                "to_state": assoc.state,
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "quality": {
                    "credential_supplied": True,
                    "save_profile_requested": payload.save_profile,
                },
            },
        )

        return AssociationService._to_response(assoc)

    @staticmethod
    async def disconnect(
        db: AsyncSession, association_id: str, forget_profile: bool = True
    ) -> AssociationResponse:
        assoc_res = await db.execute(
            select(WifiAssociationModel).where(WifiAssociationModel.id == association_id)
        )
        assoc = assoc_res.scalar_one_or_none()
        if not assoc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Association '{association_id}' not found",
            )

        old_state = assoc.state
        assoc.state = AssociationState.DISCONNECTING.value
        assoc.disconnected_at = datetime.now(timezone.utc)
        assoc.forget_profile_on_exit = forget_profile

        event = AssociationEventModel(
            association_id=assoc.id,
            from_state=old_state,
            to_state=AssociationState.DISCONNECTING.value,
            actor_id="user",
            metadata_json={"forget_profile": forget_profile},
        )
        db.add(event)
        await db.commit()
        await db.refresh(assoc)

        collector_service.queue_command(
            collector_id=assoc.collector_id,
            type="disconnect_wifi",
            session_id=assoc.session_id,
            mode=ScanMode.WIFI,
            parameters={
                "association_id": assoc.id,
                "forget_profile": forget_profile,
            },
        )

        await stream_engine.publish_event(
            assoc.session_id,
            {
                "schema_version": "1.1",
                "type": "association.state_changed",
                "session_id": assoc.session_id,
                "association_id": assoc.id,
                "from_state": old_state,
                "to_state": assoc.state,
                "captured_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        return AssociationService._to_response(assoc)

    @staticmethod
    async def trigger_refresh(db: AsyncSession, association_id: str) -> Dict[str, Any]:
        assoc_res = await db.execute(
            select(WifiAssociationModel).where(WifiAssociationModel.id == association_id)
        )
        assoc = assoc_res.scalar_one_or_none()
        if not assoc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Association '{association_id}' not found",
            )

        collector_service.queue_command(
            collector_id=assoc.collector_id,
            type="refresh_inventory",
            session_id=assoc.session_id,
            mode=ScanMode.WIFI,
            parameters={"association_id": assoc.id},
        )
        return {"status": "ok", "message": "LAN discovery refresh requested"}

    @staticmethod
    async def get_by_id(db: AsyncSession, association_id: str) -> AssociationResponse:
        assoc_res = await db.execute(
            select(WifiAssociationModel).where(WifiAssociationModel.id == association_id)
        )
        assoc = assoc_res.scalar_one_or_none()
        if not assoc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Association '{association_id}' not found",
            )
        return AssociationService._to_response(assoc)

    @staticmethod
    async def update_status_from_collector(
        db: AsyncSession, association_id: str, payload: IngestAssociationStatusRequest
    ) -> AssociationResponse:
        assoc_res = await db.execute(
            select(WifiAssociationModel).where(WifiAssociationModel.id == association_id)
        )
        assoc = assoc_res.scalar_one_or_none()
        if not assoc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Association '{association_id}' not found",
            )

        old_state = assoc.state
        assoc.state = payload.state
        now = datetime.now(timezone.utc)

        if payload.state == AssociationState.CONNECTED.value:
            assoc.associated_at = now
        elif payload.state in (AssociationState.IDLE.value, AssociationState.FAILED.value):
            assoc.disconnected_at = now

        if payload.ipv4:
            assoc.ipv4 = payload.ipv4
        if payload.ipv6:
            assoc.ipv6 = payload.ipv6
        if payload.prefix:
            # Bound validation check: prefix wider than /16 must be rejected
            try:
                net = ipaddress.ip_network(payload.prefix, strict=False)
                if net.version == 4 and net.prefixlen < 16:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="LAN_PREFIX_UNSUPPORTED: IPv4 prefix wider than /16 is rejected",
                    )
            except ValueError:
                pass
            assoc.prefix = payload.prefix
        if payload.gateway:
            assoc.gateway = payload.gateway
        if payload.dns is not None:
            assoc.dns = payload.dns
        if payload.dhcp_server:
            assoc.dhcp_server = payload.dhcp_server
        if payload.captive_state:
            assoc.captive_state = payload.captive_state

        event = AssociationEventModel(
            association_id=assoc.id,
            from_state=old_state,
            to_state=payload.state,
            error_code=payload.error_code,
            actor_id="collector",
            metadata_json={"state": payload.state, "ipv4": payload.ipv4},
        )
        db.add(event)
        await db.commit()
        await db.refresh(assoc)

        # Broadcast WebSocket event
        event_type = "association.state_changed"
        if payload.state == AssociationState.CONNECTED.value and payload.ipv4:
            event_type = "association.address_acquired"
        elif payload.state == AssociationState.FAILED.value:
            event_type = "association.failed"

        await stream_engine.publish_event(
            assoc.session_id,
            {
                "schema_version": "1.1",
                "type": event_type,
                "session_id": assoc.session_id,
                "association_id": assoc.id,
                "from_state": old_state,
                "to_state": assoc.state,
                "ipv4": assoc.ipv4,
                "gateway": assoc.gateway,
                "prefix": assoc.prefix,
                "error_code": payload.error_code,
                "captured_at": now.isoformat(),
            },
        )

        return AssociationService._to_response(assoc)

    @staticmethod
    async def ingest_hosts(
        db: AsyncSession, association_id: str, session_id: str, hosts: List[LanHostItem]
    ) -> int:
        assoc_res = await db.execute(
            select(WifiAssociationModel).where(WifiAssociationModel.id == association_id)
        )
        assoc = assoc_res.scalar_one_or_none()
        if not assoc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Association '{association_id}' not found",
            )

        # Parse attached prefix for bound validation (FR-INV-02)
        attached_net = None
        if assoc.prefix:
            try:
                attached_net = ipaddress.ip_network(assoc.prefix, strict=False)
            except ValueError:
                attached_net = None

        count = 0
        now = datetime.now(timezone.utc)
        for h in hosts:
            # Bound validation check: ignore target outside attached subnet if attached_net exists
            if attached_net and not h.is_self and not h.is_gateway:
                try:
                    ip_obj = ipaddress.ip_address(h.ip)
                    if ip_obj not in attached_net:
                        continue
                except ValueError:
                    continue

            # Check existing host by association_id and (mac_hash OR ip)
            existing_res = await db.execute(
                select(LanHostModel).where(
                    LanHostModel.association_id == association_id,
                    (LanHostModel.mac_hash == h.mac_hash) | (LanHostModel.ip == h.ip),
                )
            )
            existing = existing_res.scalar_one_or_none()

            if existing:
                existing.ip = h.ip
                existing.hostname = h.hostname or existing.hostname
                existing.oui_vendor = h.oui_vendor or existing.oui_vendor
                existing.reachability = h.reachability
                existing.rtt_ms = h.rtt_ms
                existing.last_seen = now
                existing.discovery_methods = list(
                    set(existing.discovery_methods + h.discovery_methods)
                )
                existing.quality_flags = list(set(existing.quality_flags + h.quality_flags))
            else:
                new_host = LanHostModel(
                    association_id=association_id,
                    session_id=session_id,
                    ip=h.ip,
                    ip_version=h.ip_version,
                    hostname=h.hostname,
                    mac_hash=h.mac_hash,
                    oui_vendor=h.oui_vendor,
                    discovery_methods=h.discovery_methods,
                    reachability=h.reachability,
                    rtt_ms=h.rtt_ms,
                    is_self=h.is_self,
                    is_gateway=h.is_gateway,
                    quality_flags=h.quality_flags,
                    last_seen=now,
                )
                db.add(new_host)
            count += 1

            # Broadcast host event to WS
            await stream_engine.publish_event(
                session_id,
                {
                    "schema_version": "1.1",
                    "type": "inventory.host_discovered",
                    "session_id": session_id,
                    "association_id": association_id,
                    "captured_at": now.isoformat(),
                    "host": h.model_dump(mode="json"),
                },
            )

        await db.commit()

        # Complete batch notification
        await stream_engine.publish_event(
            session_id,
            {
                "schema_version": "1.1",
                "type": "inventory.completed",
                "session_id": session_id,
                "association_id": association_id,
                "host_count": count,
                "captured_at": now.isoformat(),
            },
        )

        return count

    @staticmethod
    async def list_hosts(
        db: AsyncSession, association_id: str, page: int = 1, page_size: int = 100
    ) -> Tuple[List[LanHostItem], int]:
        count_res = await db.execute(
            select(func.count(LanHostModel.id)).where(
                LanHostModel.association_id == association_id
            )
        )
        total = count_res.scalar_one()

        offset = (page - 1) * page_size
        hosts_res = await db.execute(
            select(LanHostModel)
            .where(LanHostModel.association_id == association_id)
            .order_by(LanHostModel.is_self.desc(), LanHostModel.is_gateway.desc(), LanHostModel.ip)
            .offset(offset)
            .limit(page_size)
        )
        hosts = hosts_res.scalars().all()

        items = [
            LanHostItem(
                id=h.id,
                ip=h.ip,
                ip_version=h.ip_version,
                hostname=h.hostname,
                mac_hash=h.mac_hash,
                oui_vendor=h.oui_vendor,
                discovery_methods=h.discovery_methods,
                reachability=h.reachability,
                rtt_ms=h.rtt_ms,
                is_self=h.is_self,
                is_gateway=h.is_gateway,
                quality_flags=h.quality_flags,
                last_seen=h.last_seen,
            )
            for h in hosts
        ]
        return items, total

    @staticmethod
    async def export_inventory(
        db: AsyncSession, association_id: str, format: str = "json"
    ) -> Dict[str, Any]:
        assoc_res = await db.execute(
            select(WifiAssociationModel).where(WifiAssociationModel.id == association_id)
        )
        assoc = assoc_res.scalar_one_or_none()
        if not assoc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Association '{association_id}' not found",
            )

        hosts_res = await db.execute(
            select(LanHostModel).where(LanHostModel.association_id == association_id)
        )
        hosts = hosts_res.scalars().all()

        now_iso = datetime.now(timezone.utc).isoformat()
        if format.lower() == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow([
                "ip",
                "ip_version",
                "hostname",
                "mac_hash",
                "oui_vendor",
                "discovery_methods",
                "reachability",
                "rtt_ms",
                "is_self",
                "is_gateway",
                "last_seen",
            ])
            for h in hosts:
                writer.writerow([
                    h.ip,
                    h.ip_version,
                    h.hostname or "",
                    h.mac_hash,
                    h.oui_vendor or "",
                    ";".join(h.discovery_methods),
                    h.reachability,
                    h.rtt_ms if h.rtt_ms is not None else "",
                    h.is_self,
                    h.is_gateway,
                    h.last_seen.isoformat(),
                ])
            content = output.getvalue()
        else:
            host_items = [
                {
                    "ip": h.ip,
                    "ip_version": h.ip_version,
                    "hostname": h.hostname,
                    "mac_hash": h.mac_hash,
                    "oui_vendor": h.oui_vendor,
                    "discovery_methods": h.discovery_methods,
                    "reachability": h.reachability,
                    "rtt_ms": h.rtt_ms,
                    "is_self": h.is_self,
                    "is_gateway": h.is_gateway,
                    "last_seen": h.last_seen.isoformat(),
                }
                for h in hosts
            ]
            import json
            content = json.dumps({
                "schema_version": "1.1",
                "exported_at": now_iso,
                "association": {
                    "id": assoc.id,
                    "session_id": assoc.session_id,
                    "collector_id": assoc.collector_id,
                    "ssid": assoc.ssid,
                    "attached_prefix": assoc.prefix,
                    "gateway": assoc.gateway,
                    "ipv4": assoc.ipv4,
                },
                "total_hosts": len(hosts),
                "hosts": host_items,
            }, indent=2)

        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return {
            "format": format,
            "checksum_sha256": checksum,
            "content": content,
            "total_hosts": len(hosts),
            "generated_at": now_iso,
        }

    @staticmethod
    def _to_response(model: WifiAssociationModel) -> AssociationResponse:
        return AssociationResponse(
            id=model.id,
            session_id=model.session_id,
            collector_id=model.collector_id,
            adapter_id=model.adapter_id,
            target_id=model.target_id,
            ssid=model.ssid,
            bssid_hash=model.bssid_hash,
            security_type=model.security_type,
            state=model.state,
            associated_at=model.associated_at,
            disconnected_at=model.disconnected_at,
            ipv4=model.ipv4,
            ipv6=model.ipv6,
            prefix=model.prefix,
            gateway=model.gateway,
            dns=model.dns or [],
            dhcp_server=model.dhcp_server,
            captive_state=model.captive_state,
            save_profile_requested=model.save_profile_requested,
            forget_profile_on_exit=model.forget_profile_on_exit,
            created_at=model.created_at,
        )


association_service = AssociationService()
