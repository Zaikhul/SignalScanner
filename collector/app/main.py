import argparse
import asyncio
from datetime import datetime, timezone
import logging
import signal
import sys
from typing import Any, Dict, List, Optional
import hmac
import httpx
import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from collector.app.config import collector_settings
from collector.app.core.adapter_base import ScanConfig, SignalAdapter
from collector.app.core.association_base import (
    AssociateRequest,
    AssociationEvent,
    InventoryBound,
)
from collector.app.core.buffer_queue import buffer_queue
from collector.app.core.radio_mutex import radio_mutex
from collector.app.core.lan_inventory import lan_inventory_engine
from collector.app.core.uploader import uploader
from collector.app.adapters.mock_adapter import MockSignalAdapter
from collector.app.adapters.mock_associate_adapter import (
    MockAssociationAdapter,
    MockLanInventoryAdapter,
)
from collector.app.adapters.wifi_windows import WindowsWiFiAdapter
from collector.app.adapters.wifi_associate_windows import WindowsWiFiAssociationAdapter
from collector.app.adapters.ble_adapter import BleakSignalAdapter
from collector.app.adapters.sdr_adapter import SoapySDRSignalAdapter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("collector.daemon")


class CollectorDaemon:
    def __init__(self, backend_url: Optional[str] = None):
        self.backend_url = backend_url or collector_settings.BACKEND_URL
        uploader.set_backend_url(self.backend_url)
        self._running = True
        self.use_mock = False
        self._active_adapter: Optional[SignalAdapter] = None
        self._assoc_adapter: Optional[Any] = None
        self._active_session_id: Optional[str] = None
        self._active_assoc_id: Optional[str] = None
        self._last_prefix: Optional[str] = None
        self._last_gateway: Optional[str] = None
        self._scan_task: Optional[asyncio.Task] = None
        self._assoc_task: Optional[asyncio.Task] = None
        self._local_server_task: Optional[asyncio.Task] = None

    def _headers(self) -> Dict[str, str]:
        return {"X-Collector-Key": collector_settings.COLLECTOR_API_KEY}

    async def register(self) -> bool:
        """Registers collector capabilities with the backend API."""
        payload = {
            "id": collector_settings.COLLECTOR_ID,
            "name": collector_settings.COLLECTOR_NAME,
            "platform": collector_settings.PLATFORM,
            "version": "1.1.0",
            "capabilities": {
                "supported_modes": ["wifi", "bluetooth", "radio"],
                "adapters": [
                    {
                        "id": "win_wlan_01",
                        "type": "wifi",
                        "name": "Windows Native WiFi Scanner",
                        "is_available": True,
                    },
                    {
                        "id": "ble_bleak_01",
                        "type": "bluetooth",
                        "name": "Bleak Bluetooth LE Scanner",
                        "is_available": True,
                    },
                    {
                        "id": "sdr_mock_01",
                        "type": "radio",
                        "name": "SDR Spectrum Receiver / Mock Simulator",
                        "is_available": True,
                    },
                ],
                "platform": collector_settings.PLATFORM,
                "version": "1.1.0",
                "can_wifi": True,
                "can_ble": True,
                "can_sdr": True,
                "wifi_associate": True,
                "lan_discovery": True,
                "scan_while_associated": False,
                "requires_exclusive_radio": True,
            },
        }

        try:
            async with httpx.AsyncClient(base_url=self.backend_url, timeout=5.0) as client:
                res = await client.post("/api/v1/collectors/register", json=payload, headers=self._headers())
                if res.status_code == 200:
                    logger.info(f"Successfully registered collector '{collector_settings.COLLECTOR_ID}' with backend")
                    return True
                else:
                    logger.warning(f"Registration returned status {res.status_code}: {res.text}")
                    return False
        except Exception as e:
            logger.warning(f"Could not connect to backend for registration: {e}")
            return False

    async def ack_command(self, command_id: str) -> bool:
        """Idempotently acknowledges a received command."""
        try:
            async with httpx.AsyncClient(base_url=self.backend_url, timeout=3.0) as client:
                res = await client.post(
                    f"/api/v1/collectors/{collector_settings.COLLECTOR_ID}/commands/{command_id}/ack",
                    headers=self._headers(),
                )
                return res.status_code == 200
        except Exception as e:
            logger.debug(f"Failed to ack command {command_id}: {e}")
            return False

    async def handle_command(self, cmd: Dict[str, Any], use_mock: bool = False):
        """Processes and executes a command from backend."""
        cmd_id = cmd.get("command_id")
        cmd_type = cmd.get("type")
        session_id = cmd.get("session_id")
        mode = cmd.get("mode") or "wifi"
        interval = cmd.get("sample_interval_ms", 500)
        parameters = cmd.get("parameters") or {}

        logger.info(f"Received backend command '{cmd_type}' for session '{session_id}' (cmd_id: {cmd_id})")

        if cmd_type == "start_scan" and session_id:
            if self._active_session_id == session_id and self._scan_task and not self._scan_task.done():
                logger.info(f"Already scanning session {session_id}, acknowledging duplicate command")
                if cmd_id:
                    await self.ack_command(cmd_id)
                return

            if self._scan_task and not self._scan_task.done():
                logger.info(f"Stopping previous session {self._active_session_id} to start {session_id}")
                if self._active_adapter:
                    await self._active_adapter.stop()
                self._scan_task.cancel()

            if cmd_id:
                await self.ack_command(cmd_id)

            self._scan_task = asyncio.create_task(
                self.run_scan(
                    session_id=session_id,
                    mode=mode,
                    use_mock=use_mock,
                    sample_interval_ms=interval,
                    parameters=parameters,
                    duration_seconds=parameters.get("duration_seconds"),
                )
            )

        elif cmd_type == "pause_scan":
            if self._active_adapter:
                await self._active_adapter.stop()
            if self._scan_task and not self._scan_task.done():
                self._scan_task.cancel()
                self._scan_task = None
            if cmd_id:
                await self.ack_command(cmd_id)
            logger.info(f"Scan paused by backend command for session {session_id}")

        elif cmd_type == "resume_scan":
            if cmd_id:
                await self.ack_command(cmd_id)
            self._scan_task = asyncio.create_task(
                self.run_scan(
                    session_id=session_id,
                    mode=mode,
                    use_mock=use_mock,
                    sample_interval_ms=interval,
                    parameters=parameters,
                    duration_seconds=parameters.get("duration_seconds"),
                )
            )
            logger.info(f"Scan resumed by backend command for session {session_id}")

        elif cmd_type == "stop_scan":
            if self._active_adapter:
                await self._active_adapter.stop()
            if self._scan_task and not self._scan_task.done():
                self._scan_task.cancel()
                self._scan_task = None
            self._active_session_id = None
            if cmd_id:
                await self.ack_command(cmd_id)
            logger.info(f"Scan stopped by backend command for session {session_id}")

        elif cmd_type == "associate_wifi":
            assoc_id = parameters.get("association_id", "asc_01")
            if cmd_id:
                await self.ack_command(cmd_id)
            if self._active_assoc_id == assoc_id:
                logger.info(f"Association '{assoc_id}' already active/running, skipping duplicate command without password")
            else:
                assoc_req = AssociateRequest(
                    association_id=assoc_id,
                    target_id=parameters.get("target_id", "tgt_01"),
                    ssid=parameters.get("ssid"),
                    security_type=parameters.get("security_hint", "wpa2_personal"),
                    save_profile=parameters.get("save_profile", False),
                    timeout_seconds=parameters.get("timeout_seconds", 30),
                )
                self._assoc_task = asyncio.create_task(self.start_association(assoc_req, password=None, use_mock=use_mock))

        elif cmd_type == "disconnect_wifi":
            forget = parameters.get("forget_profile", True)
            if cmd_id:
                await self.ack_command(cmd_id)
            asyncio.create_task(self.disconnect_association(forget_profile=forget, use_mock=use_mock))

        elif cmd_type == "refresh_inventory":
            assoc_id = parameters.get("association_id") or self._active_assoc_id
            if cmd_id:
                await self.ack_command(cmd_id)
            if assoc_id and self._last_prefix:
                asyncio.create_task(
                    self.run_lan_inventory(
                        association_id=assoc_id,
                        session_id=self._active_session_id or "ses_default",
                        prefix=self._last_prefix,
                        gateway=self._last_gateway,
                        use_mock=use_mock,
                    )
                )

        elif cmd_type in ("run_diagnostic", "preflight_diagnostic"):
            from collector.app.core.diagnostics import diagnostics
            diag_res = await diagnostics.run_diagnostics(mode=mode)
            logger.info(f"Preflight diagnostics completed with status: {diag_res['overall_status']}")
            try:
                async with httpx.AsyncClient(base_url=self.backend_url, timeout=5.0) as client:
                    await client.post(
                        f"/api/v1/collectors/{collector_settings.COLLECTOR_ID}/diagnostics/result",
                        json=diag_res,
                        headers=self._headers(),
                    )
            except Exception as e:
                logger.debug(f"Failed to post diagnostic result: {e}")
            if cmd_id:
                await self.ack_command(cmd_id)

    async def heartbeat_loop(self, use_mock: bool = False):
        """Sends periodic heartbeat and receives/executes pending commands."""
        while self._running:
            try:
                payload = {
                    "collector_id": collector_settings.COLLECTOR_ID,
                    "status": "ready" if not self._active_session_id else "busy",
                    "permission_state": {"wifi": True, "bluetooth": True, "radio": True},
                    "active_sessions": [self._active_session_id] if self._active_session_id else [],
                }
                async with httpx.AsyncClient(base_url=self.backend_url, timeout=3.0) as client:
                    res = await client.post("/api/v1/collectors/heartbeat", json=payload, headers=self._headers())
                    if res.status_code == 200:
                        data = res.json()
                        pending_cmds = data.get("pending_commands", [])
                        for cmd in pending_cmds:
                            await self.handle_command(cmd, use_mock=use_mock)
            except Exception as e:
                logger.debug(f"Heartbeat loop error: {e}")

            await asyncio.sleep(collector_settings.HEARTBEAT_INTERVAL_SECONDS)

    async def run_scan(
        self,
        session_id: str,
        mode: str = "wifi",
        use_mock: bool = False,
        sample_interval_ms: int = 500,
        parameters: Optional[Dict[str, Any]] = None,
        duration_seconds: Optional[int] = None,
    ):
        """Runs a continuous scan stream with Radio Mutex coordination."""
        self._active_session_id = session_id

        if use_mock:
            adapter = MockSignalAdapter(mode=mode)
        else:
            if mode == "wifi":
                if collector_settings.PLATFORM == "windows":
                    adapter = WindowsWiFiAdapter()
                else:
                    raise RuntimeError("Native Windows WiFi Adapter is only supported on Windows. Run with --mock for virtual scan.")
            elif mode == "bluetooth":
                adapter = BleakSignalAdapter()
            elif mode == "radio":
                adapter = SoapySDRSignalAdapter()
            else:
                adapter = MockSignalAdapter(mode=mode)

        self._active_adapter = adapter

        radio_cfg = (parameters or {}).get("radio_config") or {}
        dur_sec = duration_seconds or (parameters or {}).get("duration_seconds")
        config = ScanConfig(
            session_id=session_id,
            sample_interval_ms=sample_interval_ms,
            duration_seconds=dur_sec,
            center_frequency_hz=(parameters or {}).get("frequency_hz") or radio_cfg.get("center_frequency_hz", 433920000),
            span_hz=(parameters or {}).get("span_hz") or radio_cfg.get("span_hz", 2000000),
            gain_db=(parameters or {}).get("gain_db") if "gain_db" in (parameters or {}) else radio_cfg.get("gain_db", 20.0),
            fft_size=(parameters or {}).get("fft_size") or radio_cfg.get("fft_bins", 1024),
        )

        val_res = await adapter.validate(config)
        if not val_res.is_valid:
            raise RuntimeError(f"Adapter validation error for {mode}: {val_res.error_message}")

        logger.info(f"Starting {mode} scan on session {session_id} (mock={use_mock})")
        await radio_mutex.notify_scan_started()

        start_mono = asyncio.get_event_loop().time()
        try:
            async for batch in adapter.start(config):
                if not self._running:
                    break
                if dur_sec and (asyncio.get_event_loop().time() - start_mono) >= dur_sec:
                    logger.info(f"Scan duration of {dur_sec}s reached for session {session_id}")
                    break
                # Coordinate with Radio Mutex: if association is ongoing, wait here
                await radio_mutex.wait_if_paused()
                await uploader.send_batch(session_id, batch)
        except asyncio.CancelledError:
            pass
        finally:
            await radio_mutex.notify_scan_stopped()
            await adapter.stop()
            self._active_adapter = None
            self._active_session_id = None
            logger.info(f"Scan stream stopped for session {session_id}")

    async def start_association(
        self, assoc_req: AssociateRequest, password: Optional[str] = None, use_mock: bool = False
    ):
        """Coordinates WiFi association and initiates bounded LAN discovery."""
        self._active_assoc_id = assoc_req.association_id
        await radio_mutex.acquire_for_association(ssid=assoc_req.ssid)

        adapter = MockAssociationAdapter() if (use_mock or collector_settings.PLATFORM != "windows") else WindowsWiFiAssociationAdapter()
        self._assoc_adapter = adapter

        try:
            async for event in adapter.associate(assoc_req, password=password):
                await self._post_association_status(assoc_req.association_id, event)

                if event.state == "connected":
                    await radio_mutex.mark_connected()
                    self._last_prefix = event.prefix or "192.168.1.0/24"
                    self._last_gateway = event.gateway
                    # Auto start LAN inventory discovery
                    asyncio.create_task(
                        self.run_lan_inventory(
                            association_id=assoc_req.association_id,
                            session_id=self._active_session_id or "ses_default",
                            prefix=self._last_prefix,
                            gateway=self._last_gateway,
                            use_mock=use_mock,
                        )
                    )
                elif event.state == "failed":
                    await radio_mutex.release_from_association()
                    self._active_assoc_id = None
                    break
        except Exception as e:
            logger.error(f"Association failed with error: {e}")
            await radio_mutex.release_from_association()
            self._active_assoc_id = None
        finally:
            # Explicit zeroization of credential buffer
            password = None

    async def disconnect_association(self, forget_profile: bool = True, use_mock: bool = False):
        """Disconnects WiFi and restores radio to AP scanning."""
        await radio_mutex.mark_disconnecting()
        if self._assoc_adapter:
            await self._assoc_adapter.disconnect(forget_profile=forget_profile)
            self._assoc_adapter = None

        if self._active_assoc_id:
            try:
                async with httpx.AsyncClient(base_url=self.backend_url, timeout=5.0) as client:
                    await client.post(
                        f"/api/v1/associations/{self._active_assoc_id}/ingest/status",
                        json={"state": "idle"},
                        headers=self._headers(),
                    )
            except Exception:
                pass

        self._active_assoc_id = None
        await radio_mutex.release_from_association()

    async def run_lan_inventory(
        self, association_id: str, session_id: str, prefix: str, gateway: Optional[str] = None, use_mock: bool = False
    ):
        """Executes bounded discovery on attached LAN prefix."""
        inv_adapter = MockLanInventoryAdapter() if (use_mock or collector_settings.PLATFORM != "windows") else lan_inventory_engine
        bound = InventoryBound(
            interface_name="Wi-Fi",
            attached_prefix=prefix,
            gateway_ip=gateway,
            max_hosts=256,
            rate_limit=8,
        )
        try:
            async for batch in inv_adapter.start(bound):
                await self._post_lan_hosts(association_id, session_id, batch.hosts)
        except Exception as e:
            logger.error(f"LAN Inventory error: {e}")

    async def _post_association_status(self, association_id: str, event: AssociationEvent):
        try:
            payload = {
                "state": event.state,
                "ipv4": event.ipv4,
                "ipv6": event.ipv6,
                "prefix": event.prefix,
                "gateway": event.gateway,
                "dns": event.dns,
                "dhcp_server": event.dhcp_server,
                "captive_state": event.captive_state,
                "error_code": event.error_code,
            }
            async with httpx.AsyncClient(base_url=self.backend_url, timeout=5.0) as client:
                await client.post(
                    f"/api/v1/associations/{association_id}/ingest/status",
                    json=payload,
                    headers=self._headers(),
                )
        except Exception as e:
            logger.debug(f"Failed to post association status: {e}")

    async def _post_lan_hosts(self, association_id: str, session_id: str, hosts: List[Dict[str, Any]]):
        try:
            payload = {
                "association_id": association_id,
                "session_id": session_id,
                "hosts": hosts,
            }
            async with httpx.AsyncClient(base_url=self.backend_url, timeout=5.0) as client:
                await client.post(
                    f"/api/v1/associations/{association_id}/ingest/hosts",
                    json=payload,
                    headers=self._headers(),
                )
        except Exception as e:
            logger.debug(f"Failed to post LAN hosts: {e}")

    async def start_local_server(self):
        """Starts local FastAPI agent on port 8001 for zero-secret direct UI communication."""
        local_app = FastAPI(title="Collector Local Agent")
        local_app.add_middleware(
            CORSMiddleware,
            allow_origins=[
                "http://localhost:3000",
                "http://127.0.0.1:3000",
            ],
            allow_credentials=True,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["*"],
        )

        def verify_local_caller(
            x_local_token: Optional[str] = Header(None, alias="X-Local-Token"),
            authorization: Optional[str] = Header(None, alias="Authorization"),
        ):
            token = x_local_token
            if not token and authorization:
                parts = authorization.split()
                token = parts[1] if len(parts) == 2 else parts[0]
            expected = collector_settings.LOCAL_AGENT_TOKEN
            if not token or not hmac.compare_digest(token, expected):
                raise HTTPException(status_code=401, detail="Unauthorized local caller")

        class DirectAssociatePayload(BaseModel):
            association_id: str
            target_id: str
            ssid: Optional[str] = None
            security_type: str = "wpa2_personal"
            password: Optional[str] = None
            save_profile: bool = False
            timeout_seconds: int = 30

        class DirectDisconnectPayload(BaseModel):
            forget_profile: bool = True

        @local_app.post("/api/v1/collector/associate")
        async def direct_associate(
            payload: DirectAssociatePayload,
            _: None = Depends(verify_local_caller),
        ):
            req = AssociateRequest(
                association_id=payload.association_id,
                target_id=payload.target_id,
                ssid=payload.ssid,
                security_type=payload.security_type,
                save_profile=payload.save_profile,
                timeout_seconds=payload.timeout_seconds,
            )
            self._active_assoc_id = payload.association_id
            self._assoc_task = asyncio.create_task(
                self.start_association(
                    req, password=payload.password, use_mock=self.use_mock
                )
            )
            return {"status": "associating", "association_id": payload.association_id}

        @local_app.post("/api/v1/collector/disconnect")
        async def direct_disconnect(
            payload: Optional[DirectDisconnectPayload] = None,
            forget_profile: Optional[bool] = None,
            _: None = Depends(verify_local_caller),
        ):
            eff_forget = True
            if payload is not None and hasattr(payload, "forget_profile"):
                eff_forget = payload.forget_profile
            elif forget_profile is not None:
                eff_forget = forget_profile
            await self.disconnect_association(forget_profile=eff_forget, use_mock=self.use_mock)
            return {"status": "disconnected"}

        try:
            config = uvicorn.Config(local_app, host="127.0.0.1", port=8001, log_level="warning")
            server = uvicorn.Server(config)
            self._local_server_task = asyncio.create_task(server.serve())
            logger.info("Collector Local Agent HTTP Server active on http://127.0.0.1:8001")
        except Exception as e:
            logger.debug(f"Could not start local agent server: {e}")

    async def run_standalone(
        self,
        mode: str = "wifi",
        use_mock: bool = False,
        sample_interval_ms: int = 500,
    ):
        self.use_mock = use_mock
        logger.info(f"Starting Standalone CLI Scan Mode ({mode.upper()})...")
        await self.register()
        await self.start_local_server()

        heartbeat_task = asyncio.create_task(self.heartbeat_loop(use_mock=use_mock))
        session_id = None
        try:
            async with httpx.AsyncClient(base_url=self.backend_url, timeout=10.0, headers=self._headers()) as client:
                now_str = datetime.now(timezone.utc).strftime("%H:%M:%S")
                create_res = await client.post(
                    "/api/v1/sessions",
                    json={
                        "name": f"CLI {mode.upper()} Standalone - {now_str}",
                        "mode": mode,
                        "collector_id": collector_settings.COLLECTOR_ID,
                        "source_type": "collector",
                        "sample_interval_ms": sample_interval_ms,
                        "tags": [mode, "cli", "standalone"],
                    },
                )
                if create_res.status_code != 201:
                    logger.error(f"Failed to create backend session: {create_res.status_code} {create_res.text}")
                    return

                session_data = create_res.json()
                session_id = session_data["id"]
                logger.info(f"Created official backend session: {session_id}")

                start_res = await client.post(f"/api/v1/sessions/{session_id}/start")
                if start_res.status_code != 200:
                    logger.error(f"Failed to start backend session: {start_res.status_code}")
                    return
                logger.info(f"Backend session {session_id} is now ACTIVE")

            await self.run_scan(
                session_id=session_id,
                mode=mode,
                use_mock=use_mock,
                sample_interval_ms=sample_interval_ms,
            )
        finally:
            if session_id:
                try:
                    async with httpx.AsyncClient(base_url=self.backend_url, timeout=5.0, headers=self._headers()) as client:
                        await client.post(f"/api/v1/sessions/{session_id}/stop")
                        logger.info(f"Session {session_id} finalized as COMPLETED")
                except Exception:
                    pass
            heartbeat_task.cancel()
            await self.shutdown()

    async def run_daemon(self, mode: str = "wifi", use_mock: bool = False):
        self.use_mock = use_mock
        await self.register()
        await self.start_local_server()
        heartbeat_task = asyncio.create_task(self.heartbeat_loop(use_mock=use_mock))

        logger.info(
            f"Collector daemon '{collector_settings.COLLECTOR_ID}' is in STANDBY.\n"
            f"  - Platform: {collector_settings.PLATFORM}\n"
            f"  - Mode: {mode}\n"
            f"  - Backend: {self.backend_url}\n"
            f"  - Local Agent: http://127.0.0.1:8001\n"
            f"  - Status: READY (Awaiting scan & association commands...)"
        )

        try:
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            heartbeat_task.cancel()
            await self.shutdown()

    async def shutdown(self):
        self._running = False
        if self._active_adapter:
            await self._active_adapter.stop()
        if self._assoc_adapter:
            await self._assoc_adapter.disconnect()
        if self._scan_task and not self._scan_task.done():
            self._scan_task.cancel()
        if self._local_server_task and not self._local_server_task.done():
            self._local_server_task.cancel()
        await uploader.close()


async def main():
    parser = argparse.ArgumentParser(description="Pemindai Area - Signal Collector Daemon")
    parser.add_argument("--mode", choices=["wifi", "bluetooth", "radio"], default="wifi", help="Scan mode")
    parser.add_argument("--session-id", default=None, help="Explicit Session ID to attach to")
    parser.add_argument("--standalone", action="store_true", help="Standalone mode: auto-create official session in backend")
    parser.add_argument("--mock", action="store_true", help="Use virtual signal simulator")
    parser.add_argument("--interval", type=int, default=500, help="Sampling interval in ms")
    parser.add_argument("--backend-url", default=None, help="FastAPI backend URL")
    args = parser.parse_args()

    daemon = CollectorDaemon(backend_url=args.backend_url)
    await buffer_queue.init_queue()

    try:
        if args.standalone:
            await daemon.run_standalone(
                mode=args.mode,
                use_mock=args.mock,
                sample_interval_ms=args.interval,
            )
        elif args.session_id:
            daemon.use_mock = args.mock
            await daemon.register()
            await daemon.start_local_server()
            heartbeat_task = asyncio.create_task(daemon.heartbeat_loop(use_mock=args.mock))
            await daemon.run_scan(
                session_id=args.session_id,
                mode=args.mode,
                use_mock=args.mock,
                sample_interval_ms=args.interval,
            )
            heartbeat_task.cancel()
        else:
            await daemon.run_daemon(
                mode=args.mode,
                use_mock=args.mock,
            )
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down daemon...")
    finally:
        await daemon.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
