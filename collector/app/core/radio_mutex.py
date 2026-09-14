import asyncio
import logging
from typing import Optional

logger = logging.getLogger("collector.radio_mutex")


class RadioMutex:
    """
    Radio Mutex Manager (PRD v1.1 - Section 15.4 & FR-ADP-01).
    Manages physical radio state transitions:
    idle -> scanning -> associating -> associated -> inventory -> disconnecting -> idle
    Ensures that AP scanning on the shared WiFi radio is paused while associating/associated,
    and cleanly resumed after disconnection.
    """

    def __init__(self):
        self._lock = asyncio.Lock()
        self._state: str = "idle"  # idle, scanning, associating, associated, inventory, disconnecting
        self._associated_ssid: Optional[str] = None
        self._was_scanning_before_assoc: bool = False
        self._pause_scan_event = asyncio.Event()
        self._pause_scan_event.set()  # set means scanning is allowed

    @property
    def state(self) -> str:
        return self._state

    @property
    def is_associated(self) -> bool:
        return self._state in ("associated", "inventory")

    @property
    def associated_ssid(self) -> Optional[str]:
        return self._associated_ssid

    async def wait_if_paused(self) -> None:
        """Called by scanner loop: awaits if scanning is paused due to association."""
        await self._pause_scan_event.wait()

    async def notify_scan_started(self) -> None:
        async with self._lock:
            if self._state == "idle":
                self._state = "scanning"

    async def notify_scan_stopped(self) -> None:
        async with self._lock:
            if self._state == "scanning":
                self._state = "idle"

    async def acquire_for_association(self, ssid: Optional[str] = None) -> None:
        """
        Pauses AP scanning on the shared radio and transitions into associating.
        """
        async with self._lock:
            logger.info(f"RadioMutex: acquiring radio for association to '{ssid}'")
            if self._state == "scanning":
                self._was_scanning_before_assoc = True
            self._pause_scan_event.clear()  # Block scan loop
            self._state = "associating"
            self._associated_ssid = ssid

    async def mark_connected(self) -> None:
        async with self._lock:
            self._state = "associated"
            logger.info(f"RadioMutex: radio is now ASSOCIATED to '{self._associated_ssid}'")

    async def mark_disconnecting(self) -> None:
        async with self._lock:
            self._state = "disconnecting"
            logger.info("RadioMutex: radio is DISCONNECTING")

    async def release_from_association(self) -> bool:
        """
        Releases radio lock from association.
        Returns True if scanning should be resumed.
        """
        async with self._lock:
            logger.info(f"RadioMutex: releasing association to '{self._associated_ssid}'")
            self._associated_ssid = None
            should_resume = self._was_scanning_before_assoc
            self._was_scanning_before_assoc = False

            if should_resume:
                self._state = "scanning"
                self._pause_scan_event.set()  # Unblock scanner
            else:
                self._state = "idle"
                self._pause_scan_event.set()

            return should_resume


radio_mutex = RadioMutex()
