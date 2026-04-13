"""WitMotion WT901 serial protocol (USB / UART).

Supports:
  - Combined 0x61 packet (accel + gyro + angle) — default on many WT901BLE units
  - Separate 0x51 (accel), 0x52 (gyro), 0x53 (angle) 11-byte frames
"""

from __future__ import annotations

import glob
import struct
from typing import Optional

import serial

HEADER = 0x55
BAUD_RATE = 115200
SHORT = 11
LONG = 21  # 0x61: header + type + 18 data + checksum


def find_serial_port() -> Optional[str]:
    for pattern in ("/dev/ttyUSB*", "/dev/ttyACM*"):
        ports = sorted(glob.glob(pattern))
        if ports:
            return ports[0]
    return None


def open_serial(port: Optional[str] = None) -> Optional[serial.Serial]:
    p = port or find_serial_port()
    if not p:
        return None
    try:
        ser = serial.Serial(p, BAUD_RATE, timeout=0.05)
        ser.reset_input_buffer()
        return ser
    except Exception:
        return None


def _chk11(buf: bytes) -> bool:
    return len(buf) >= SHORT and (sum(buf[:10]) & 0xFF) == buf[10]


def _chk21(buf: bytes) -> bool:
    return len(buf) >= LONG and (sum(buf[:20]) & 0xFF) == buf[20]


class WT901Parser:
    """Incremental parser with cached orientation / accel."""

    __slots__ = ("buf", "roll", "pitch", "yaw", "ax", "ay", "az", "packets")

    def __init__(self) -> None:
        self.buf = bytearray()
        self.roll = self.pitch = self.yaw = 0.0
        self.ax = self.ay = self.az = 0.0
        self.packets = 0

    def drain(self, ser: serial.Serial, max_read: int = 4096) -> bool:
        """Read available bytes, parse frames, update cached values. Returns True if any frame parsed."""
        n = ser.in_waiting
        if n:
            self.buf.extend(ser.read(min(n, max_read)))
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
                if _chk21(frame):
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
        # 18 data bytes: Ax,Ay,Az, Gx,Gy,Gz, Roll,Pitch,Yaw (int16 LE each)
        vals = struct.unpack("<9h", frame[2:20])
        ax, ay, az = vals[0], vals[1], vals[2]
        # Gyro vals[3:6] — not forwarded in UDP packet today
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

