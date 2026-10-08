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

        # SS-10 Guard: If already connected, do not regress terminal success to ASSOCIATING
        if assoc.state == AssociationState.CONNECTED.value:
            return self._assoc_to_response(assoc)

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

        # SS-10 Guard: Do not regress CONNECTED back to ASSOCIATING from late callbacks
        if assoc.state == AssociationState.CONNECTED.value and payload.state == AssociationState.ASSOCIATING.value:
            # Preserve connected state but still update networking details if supplied
            payload_state = AssociationState.CONNECTED.value
        else:
            payload_state = payload.state

        old_state = assoc.state
        assoc.state = payload_state
        now = datetime.now(timezone.utc)

        if payload_state == AssociationState.CONNECTED.value:
            assoc.associated_at = now
        elif payload_state in (AssociationState.IDLE.value, AssociationState.FAILED.value):
            assoc.disconnected_at = now

        if payload.ipv4:
            assoc.ipv4 = payload.ipv4
        if payload.ipv6:
            assoc.ipv6 = payload.ipv6
        if payload.prefix:
            prefix_str = payload.prefix.strip()
            # Bound validation check: prefix must be valid RFC 1918 and not wider than /16
            try:
                net = ipaddress.ip_network(prefix_str, strict=False)
                if net.version != 4:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="LAN_PREFIX_UNSUPPORTED: Only IPv4 prefixes are supported",
                    )
                if net.prefixlen < 16:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="LAN_PREFIX_UNSUPPORTED: IPv4 prefix wider than /16 is rejected",
                    )
                from app.core.lan_port_scanner import RFC1918_NETWORKS
                if not any(net.subnet_of(rfc) for rfc in RFC1918_NETWORKS):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"LAN_PREFIX_NOT_RFC1918: Prefix '{prefix_str}' must be within RFC 1918 private ranges",
                    )
            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"INVALID_PREFIX: Malformed network prefix '{prefix_str}': {e}",
                )
            assoc.prefix = prefix_str
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
        if not assoc.prefix:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"MISSING_ATTACHED_PREFIX: Association '{association_id}' does not have an attached prefix for host validation",
            )

        try:
            attached_net = ipaddress.ip_network(assoc.prefix.strip(), strict=False)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"INVALID_ATTACHED_PREFIX: Malformed association prefix '{assoc.prefix}': {e}",
            )

        from app.core.lan_port_scanner import RFC1918_NETWORKS

        count = 0
        now = datetime.now(timezone.utc)
        for h in hosts:
            # Bound validation check: ignore target outside attached subnet or outside RFC 1918
            try:
                ip_obj = ipaddress.ip_address(h.ip)
                if not isinstance(ip_obj, ipaddress.IPv4Address):
                    continue
                if ip_obj.is_loopback or ip_obj.is_link_local:
                    continue
                if not any(ip_obj in rfc for rfc in RFC1918_NETWORKS):
                    continue
                if not h.is_self and not h.is_gateway and ip_obj not in attached_net:
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
                if h.open_ports:
                    existing.open_ports = [
                        p.model_dump() if hasattr(p, "model_dump") else p for p in h.open_ports
                    ]
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
                    open_ports=[
                        p.model_dump() if hasattr(p, "model_dump") else p for p in h.open_ports
                    ] if h.open_ports else [],
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
                open_ports=h.open_ports or [],
                last_seen=h.last_seen,
            )
            for h in hosts
        ]
        return items, total

    @staticmethod
    async def scan_host_ports(
        db: AsyncSession,
        association_id: str,
        host_ip: str,
        ports: Optional[List[int]] = None,
        timeout: float = 0.5,
    ) -> LanHostItem:
        """
        Executes bounded, safe TCP port scan on an authorized LAN host within the attached prefix.
        Updates database and notifies frontend via WebSocket.
        """
        assoc_res = await db.execute(
            select(WifiAssociationModel).where(WifiAssociationModel.id == association_id)
        )
        assoc = assoc_res.scalar_one_or_none()
        if not assoc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Association '{association_id}' not found",
            )

        # Enforce that association must be in active CONNECTED state
        if assoc.state != AssociationState.CONNECTED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"ASSOCIATION_NOT_CONNECTED: Cannot scan LAN ports because association '{association_id}' state is '{assoc.state}', not 'connected'.",
            )

        if not assoc.prefix:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"MISSING_ATTACHED_PREFIX: Association '{association_id}' lacks a valid attached subnet prefix.",
            )

        # Strict Scope Validation Gate
        from app.core.lan_port_scanner import lan_port_scanner, validate_lan_target

        try:
            validate_lan_target(host_ip, attached_prefix=assoc.prefix)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

        # Retrieve target host from DB
        host_res = await db.execute(
            select(LanHostModel).where(
                LanHostModel.association_id == association_id,
                LanHostModel.ip == host_ip,
            )
        )
        host = host_res.scalar_one_or_none()
        if not host:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Host '{host_ip}' not found in association '{association_id}'",
            )

        # Run non-blocking async port scan
        open_ports = await lan_port_scanner.scan_host_ports(
            ip=host_ip,
            ports=ports,
            timeout=timeout,
            attached_prefix=assoc.prefix,
        )

        now = datetime.now(timezone.utc)
        host.open_ports = open_ports
        host.last_seen = now
        methods = list(host.discovery_methods)
        if "port_scan" not in methods:
            methods.append("port_scan")
        host.discovery_methods = methods

        await db.commit()
        await db.refresh(host)

        host_item = LanHostItem(
            id=host.id,
            ip=host.ip,
            ip_version=host.ip_version,
            hostname=host.hostname,
            mac_hash=host.mac_hash,
            oui_vendor=host.oui_vendor,
            discovery_methods=host.discovery_methods,
            reachability=host.reachability,
            rtt_ms=host.rtt_ms,
            is_self=host.is_self,
            is_gateway=host.is_gateway,
            quality_flags=host.quality_flags,
            open_ports=host.open_ports or [],
            last_seen=host.last_seen,
        )

        # Broadcast update over WebSocket
        await stream_engine.publish_event(
            assoc.session_id,
            {
                "schema_version": "1.1",
                "type": "inventory.host_updated",
                "session_id": assoc.session_id,
                "association_id": association_id,
                "captured_at": now.isoformat(),
                "host": host_item.model_dump(mode="json"),
            },
        )

        return host_item

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
                "open_ports",
                "last_seen",
            ])
            for h in hosts:
                ports_str = ", ".join(
                    f"{p.get('port')}/{p.get('service', 'unknown')}"
                    for p in (h.open_ports or [])
                )
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
                    ports_str,
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
                    "open_ports": h.open_ports or [],
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
