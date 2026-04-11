#!/usr/bin/env python3
"""Real-time Pitch/Roll/Yaw from WitMotion WT901 IMU over I2C.

The WT901 has onboard sensor fusion (accel + gyro + mag) and outputs
orientation directly — no external filtering needed.

Streams data over UDP for near-zero-latency consumption by any program.
Usage:
    python3 imu_reader.py                        # local display only
    python3 imu_reader.py 192.168.1.50           # stream to one PC
    python3 imu_reader.py 192.168.1.50 9000      # stream to PC on custom port
    python3 imu_reader.py 255.255.255.255         # broadcast to all on LAN
"""

import argparse
import math
import socket
import struct
import sys
import time

import smbus2

I2C_BUS = 1
WT901_ADDR = 0x50

# WT901 register addresses (each holds a signed int16)
REG_AX = 0x34
REG_AY = 0x35
REG_AZ = 0x36
REG_GX = 0x37
REG_GY = 0x38
REG_GZ = 0x39
REG_HX = 0x3A
REG_HY = 0x3B
REG_HZ = 0x3C
REG_ROLL = 0x3D
REG_PITCH = 0x3E
REG_YAW = 0x3F

REFRESH_HZ = 50
DEFAULT_PORT = 9000


def read_angles(bus):
    """Read fused Roll/Pitch/Yaw from WT901 onboard processor."""
    data = bus.read_i2c_block_data(WT901_ADDR, REG_ROLL, 6)
    roll_raw, pitch_raw, yaw_raw = struct.unpack("<3h", bytes(data))
    scale = 180.0 / 32768.0
    return roll_raw * scale, pitch_raw * scale, yaw_raw * scale


def read_accel(bus):
    """Read acceleration (g). Scale: raw / 32768 * 16g."""
    data = bus.read_i2c_block_data(WT901_ADDR, REG_AX, 6)
    ax, ay, az = struct.unpack("<3h", bytes(data))
    scale = 16.0 / 32768.0
    return ax * scale, ay * scale, az * scale


def read_gyro(bus):
    """Read angular velocity (deg/s). Scale: raw / 32768 * 2000."""
    data = bus.read_i2c_block_data(WT901_ADDR, REG_GX, 6)
    gx, gy, gz = struct.unpack("<3h", bytes(data))
    scale = 2000.0 / 32768.0
    return gx * scale, gy * scale, gz * scale


RECONNECT_INTERVAL = 1.0


def open_bus():
    """Try to open the I2C bus and verify the WT901 is present."""
    try:
        bus = smbus2.SMBus(I2C_BUS)
        bus.read_byte_data(WT901_ADDR, REG_ROLL)
        return bus
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description="IMU2CV — WT901 orientation over UDP")
    parser.add_argument("target_ip", nargs="?", default=None,
                        help="IP of the receiving computer (omit for local-only display)")
    parser.add_argument("port", nargs="?", type=int, default=DEFAULT_PORT,
                        help=f"UDP port (default {DEFAULT_PORT})")
    args = parser.parse_args()

    udp_sock = None
    if args.target_ip:
        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if args.target_ip == "255.255.255.255":
            udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        print(f"Streaming UDP → {args.target_ip}:{args.port}")
    else:
        print("Local display only (pass an IP to stream over UDP)")

    seq = 0
    bus = open_bus()
    connected = bus is not None
    last_reconnect = 0.0

    if connected:
        print("IMU2CV — WitMotion WT901  (Ctrl+C to quit)")
    else:
        print("IMU2CV — WT901 not detected, sending zeros until connected  (Ctrl+C to quit)")
    print("=" * 56)

    try:
        while True:
            if not connected:
                now = time.time()
                if now - last_reconnect >= RECONNECT_INTERVAL:
                    last_reconnect = now
                    bus = open_bus()
                    if bus is not None:
                        connected = True
                        sys.stdout.write("\n[IMU connected]\n")
                        sys.stdout.flush()

            pitch = roll = yaw = 0.0
            ax = ay = az = 0.0

            if connected:
                try:
                    roll, pitch, yaw = read_angles(bus)
                    ax, ay, az = read_accel(bus)
                except Exception:
                    sys.stdout.write("\n[IMU disconnected — sending zeros]\n")
                    sys.stdout.flush()
                    connected = False
                    try:
                        bus.close()
                    except Exception:
                        pass
                    bus = None
                    last_reconnect = time.time()

            status = " " if connected else "!"
            sys.stdout.write(
                f"\r{status} P:{pitch:+7.2f}° R:{roll:+7.2f}° Y:{yaw:+7.2f}°  "
                f"AX:{ax:+5.2f}g AY:{ay:+5.2f}g AZ:{az:+5.2f}g  "
            )
            sys.stdout.flush()

            if udp_sock:
                packet = struct.pack("<Idffffff", seq, time.time(),
                                     pitch, roll, yaw, ax, ay, az)
                udp_sock.sendto(packet, (args.target_ip, args.port))
                seq += 1

            time.sleep(1.0 / REFRESH_HZ)

    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        if bus:
            bus.close()
        if udp_sock:
            udp_sock.close()


if __name__ == "__main__":
    main()
