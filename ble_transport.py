"""BLE transport for WitMotion WT901BLE sensors.

Scans for devices advertising the WitMotion service, connects, subscribes
to notifications, and feeds raw bytes into a WT901Parser.

Connection is manual — call connect() / disconnect() from any thread.
The asyncio event loop runs in the main thread (required by BlueZ/D-Bus).
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Optional

from bleak import BleakClient, BleakScanner

from witmotion import WT901Parser

WITMOTION_SERVICE = "0000ffe5-0000-1000-8000-00805f9a34fb"
NOTIFY_CHAR = "0000ffe4-0000-1000-8000-00805f9a34fb"
WRITE_CHAR = "0000ffe9-0000-1000-8000-00805f9a34fb"
SCAN_TIMEOUT = 8.0
CONNECT_TIMEOUT = 10.0


class BLETransport:
    """Manages a BLE connection to a WT901BLE.

    call run_forever() from the main thread (it keeps the asyncio loop alive).
    Use connect() / disconnect() from any thread to control the connection.
    Read .parser, .connected, .last_data_age from any thread.
    """

    def __init__(self, target_name: Optional[str] = None, target_addr: Optional[str] = None):
        self._target_name = target_name
        self._target_addr = target_addr
        self.parser = WT901Parser()
        self.connected = False
        self.connecting = False
        self.device_name: str = ""
        self.device_addr: str = ""
        self._last_data_time = 0.0
        self._lock = threading.Lock()
        self._stop = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._connect_requested = False
        self._disconnect_requested = False
        self._client: Optional[BleakClient] = None

    @property
    def last_data_age(self) -> float:
        t = self._last_data_time
        if t == 0:
            return float("inf")
        return time.time() - t

    def stop(self):
        self._stop = True

    def connect(self):
        """Request a BLE connection (thread-safe)."""
        self._connect_requested = True

    def disconnect(self):
        """Request a BLE disconnection (thread-safe)."""
        self._disconnect_requested = True

    def run_forever(self):
        """Block the calling thread (must be main) running BLE event loop."""
        asyncio.run(self._main())

    async def _main(self):
        self._loop = asyncio.get_running_loop()
        while not self._stop:
            if self._disconnect_requested:
                self._disconnect_requested = False
                if self._client and self._client.is_connected:
                    try:
                        await self._client.stop_notify(NOTIFY_CHAR)
                    except Exception:
                        pass
                    try:
                        await self._client.disconnect()
                    except Exception:
                        pass
                    self._client = None
                with self._lock:
                    self.connected = False
                    self.connecting = False

            if self._connect_requested:
                self._connect_requested = False
                if not self.connected:
                    with self._lock:
                        self.connecting = True
                    try:
                        addr = await self._find_device()
                        if addr:
                            client = BleakClient(addr, timeout=CONNECT_TIMEOUT)
                            await client.connect()
                            self._client = client
                            self.parser = WT901Parser()
                            await client.start_notify(NOTIFY_CHAR, self._on_notify)
                            with self._lock:
                                self.connected = True
                                self.connecting = False
                        else:
                            with self._lock:
                                self.connecting = False
                    except Exception:
                        with self._lock:
                            self.connected = False
                            self.connecting = False

            # Check if connection dropped
            if self.connected and self._client and not self._client.is_connected:
                self._client = None
                with self._lock:
                    self.connected = False

            await asyncio.sleep(0.3)

    async def _find_device(self) -> Optional[str]:
        if self._target_addr:
            return self._target_addr

        devices = await BleakScanner.discover(
            timeout=SCAN_TIMEOUT,
            return_adv=True,
        )
        for addr, (dev, adv) in devices.items():
            name = dev.name or ""
            uuids = adv.service_uuids if adv else []
            is_wt = "WT" in name.upper() or WITMOTION_SERVICE in uuids
            if not is_wt:
                continue
            if self._target_name and self._target_name.lower() not in name.lower():
                continue
            self.device_name = name
            self.device_addr = addr
            return addr
        return None

    def _on_notify(self, handle: int, data: bytearray):
        with self._lock:
            self.parser.buf.extend(data)
            self.parser.drain_buf()
            self._last_data_time = time.time()
