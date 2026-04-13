"""BLE transport for WitMotion WT901BLE sensors.

Scans for devices advertising the WitMotion service, connects, subscribes
to notifications, and feeds raw bytes into a WT901Parser.

Uses the main-thread asyncio loop (required by BlueZ/D-Bus on Linux).
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

    call run_forever() from the main thread (it blocks).
    Read .parser, .connected, .last_data_age from any thread.
    """

    def __init__(self, target_name: Optional[str] = None, target_addr: Optional[str] = None):
        self._target_name = target_name
        self._target_addr = target_addr
        self.parser = WT901Parser()
        self.connected = False
        self.device_name: str = ""
        self.device_addr: str = ""
        self._last_data_time = 0.0
        self._lock = threading.Lock()
        self._stop = False

    @property
    def last_data_age(self) -> float:
        t = self._last_data_time
        if t == 0:
            return float("inf")
        return time.time() - t

    def stop(self):
        self._stop = True

    def run_forever(self):
        """Block the calling thread (must be main) running BLE."""
        asyncio.run(self._main())

    async def _main(self):
        while not self._stop:
            try:
                addr = await self._find_device()
                if not addr:
                    await asyncio.sleep(2.0)
                    continue

                async with BleakClient(addr, timeout=CONNECT_TIMEOUT) as client:
                    with self._lock:
                        self.connected = True
                    self.parser = WT901Parser()

                    await client.start_notify(NOTIFY_CHAR, self._on_notify)

                    while not self._stop and client.is_connected:
                        await asyncio.sleep(0.5)

                    try:
                        await client.stop_notify(NOTIFY_CHAR)
                    except Exception:
                        pass

            except Exception:
                pass
            finally:
                with self._lock:
                    self.connected = False
                if not self._stop:
                    await asyncio.sleep(2.0)

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
