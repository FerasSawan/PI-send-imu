"""WitMotion WT901 serial protocol (USB / UART).

Supports:
  - Combined 0x61 packet (accel + gyro + angle) — default on many WT901BLE units
  - Separate 0x51 (accel), 0x52 (gyro), 0x53 (angle) 11-byte frames

Environment:
  IMU2CV_SERIAL  — force device path, e.g. /dev/ttyUSB0
  IMU2CV_BAUD      — baud rate (default 115200; try 9600 if your module uses it)
"""

from __future__ import annotations

import glob
import os
import struct
from typing import Optional

import serial

HEADER = 0x55
SHORT = 11   # 0x51/0x52/0x53: header + type + 6 data + 2 temp + checksum
LONG = 20    # 0x61: header + type + 18 data (no checksum on WT901BLE)


def configured_baud() -> int:
    try:
        return int(os.environ.get("IMU2CV_BAUD", "115200"))
    except ValueError:
        return 115200


def list_serial_ports() -> list[str]:
    """All candidate USB serial devices (deduped by realpath)."""
    paths: set[str] = set()
    for pattern in (
        "/dev/ttyUSB*",
        "/dev/ttyACM*",
        "/dev/serial/by-id/usb-*",
    ):
        for p in glob.glob(pattern):
            try:
                rp = os.path.realpath(p)
                if os.path.exists(rp):
                    paths.add(rp)
            except OSError:
                continue
    return sorted(paths)


def pick_serial_port(index: int = 0) -> Optional[str]:
    """Resolve device path. IMU2CV_SERIAL wins; else rotate through list_serial_ports()."""
    forced = os.environ.get("IMU2CV_SERIAL", "").strip()
    if forced:
        return forced
    ports = list_serial_ports()
    if not ports:
        return None
    return ports[index % len(ports)]


RATE_CODES = {10: 0x06, 20: 0x07, 50: 0x08, 100: 0x09, 200: 0x0B}
DEFAULT_HZ = 50


def configure_rate(ser: serial.Serial, hz: int = DEFAULT_HZ) -> None:
    """Unlock config, set output rate, save. Persists across power cycles."""
    import time
    code = RATE_CODES.get(hz, RATE_CODES[DEFAULT_HZ])
    ser.write(bytes([0xFF, 0xAA, 0x69, 0x88, 0xB5]))  # unlock
    time.sleep(0.05)
    ser.write(bytes([0xFF, 0xAA, 0x03, code, 0x00]))   # set rate
    time.sleep(0.05)
    ser.write(bytes([0xFF, 0xAA, 0x00, 0x00, 0x00]))   # save
    time.sleep(0.1)
    ser.reset_input_buffer()


def open_serial(port: Optional[str] = None, baud: Optional[int] = None, hz: int = DEFAULT_HZ) -> Optional[serial.Serial]:
    """Open one serial port and configure output rate."""
    b = baud if baud is not None else configured_baud()
    p = port or pick_serial_port(0)
    if not p:
        return None
    try:
        ser = serial.Serial(p, b, timeout=0.05)
        ser.reset_input_buffer()
        configure_rate(ser, hz)
        return ser
    except Exception:
        return None


def open_serial_error() -> str:
    """Human-readable reason why open_serial might fail (for diagnostics)."""
    forced = os.environ.get("IMU2CV_SERIAL", "").strip()
    if forced:
        return f"Cannot open {forced} — check path, permissions (dialout), cable."
    ports = list_serial_ports()
    if not ports:
        return "No USB serial device found (/dev/ttyUSB* / ttyACM*). Plug in the WT901 USB cable."
    return f"Cannot open any of: {', '.join(ports)} — permissions or in use?"


def _chk11(buf: bytes) -> bool:
    return len(buf) >= SHORT and (sum(buf[:10]) & 0xFF) == buf[10]


def _valid_61(buf: bytes) -> bool:
    """0x61 frames on WT901BLE are 20 bytes with no checksum."""
    return len(buf) >= LONG and buf[0] == HEADER and buf[1] == 0x61


class WT901Parser:
    """Incremental parser with cached orientation / accel."""

    __slots__ = ("buf", "roll", "pitch", "yaw", "ax", "ay", "az", "packets")

    def __init__(self) -> None:
        self.buf = bytearray()
        self.roll = self.pitch = self.yaw = 0.0
        self.ax = self.ay = self.az = 0.0
        self.packets = 0

    def drain(self, ser: serial.Serial, max_read: int = 4096) -> bool:
        """Read available bytes from serial, parse frames. Returns True if any frame parsed."""
        n = ser.in_waiting
        if n:
            self.buf.extend(ser.read(min(n, max_read)))
        return self.drain_buf()

    def drain_buf(self) -> bool:
        """Parse any complete frames already in self.buf. Returns True if any frame parsed."""
        if len(self.buf) > 8192:
            self.buf.clear()

        parsed = False
        while True:
            if len(self.buf) < 2:
                break
            i = 0
            while i < len(self.buf) and self.buf[i] != HEADER:
                i += 1
            if i > 0:
                del self.buf[:i]
            if len(self.buf) < 2:
                break

            ptype = self.buf[1]

            if ptype == 0x61 and len(self.buf) >= LONG:
                frame = bytes(self.buf[:LONG])
                if _valid_61(frame):
                    self._parse_61(frame)
                    parsed = True
                    self.packets += 1
                    del self.buf[:LONG]
                    continue
                del self.buf[:1]
                continue

            if ptype in (0x51, 0x52, 0x53) and len(self.buf) >= SHORT:
                frame = bytes(self.buf[:SHORT])
                if _chk11(frame):
                    self._parse_11(frame)
                    parsed = True
                    self.packets += 1
                    del self.buf[:SHORT]
                    continue
                del self.buf[:1]
                continue

            if ptype == 0x61 and len(self.buf) < LONG:
                break

            del self.buf[:1]

        return parsed

    def _parse_61(self, frame: bytes) -> None:
        vals = struct.unpack("<9h", frame[2:20])
        ax, ay, az = vals[0], vals[1], vals[2]
        roll, pitch, yaw = vals[6], vals[7], vals[8]
        self.ax = ax * (16.0 / 32768.0)
        self.ay = ay * (16.0 / 32768.0)
        self.az = az * (16.0 / 32768.0)
        self.roll = roll * (180.0 / 32768.0)
        self.pitch = pitch * (180.0 / 32768.0)
        self.yaw = yaw * (180.0 / 32768.0)

    def _parse_11(self, frame: bytes) -> None:
        ptype = frame[1]
        v0, v1, v2 = struct.unpack("<3h", frame[2:8])
        if ptype == 0x51:
            s = 16.0 / 32768.0
            self.ax, self.ay, self.az = v0 * s, v1 * s, v2 * s
        elif ptype == 0x53:
            s = 180.0 / 32768.0
            self.roll, self.pitch, self.yaw = v0 * s, v1 * s, v2 * s
