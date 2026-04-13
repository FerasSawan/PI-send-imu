#!/usr/bin/env python3
"""Real-time Pitch/Roll/Yaw from WitMotion WT901BLECL over USB serial.

The WT901BLE has onboard sensor fusion and outputs orientation directly.
Connects via USB (CH340 serial) and streams data over UDP.

Usage:
    python3 imu_reader.py                        # local display only
    python3 imu_reader.py 192.168.1.50           # stream to one PC
    python3 imu_reader.py 192.168.1.50 9000      # stream to PC on custom port
    python3 imu_reader.py 255.255.255.255         # broadcast to all on LAN
"""

import argparse
import socket
import struct
import sys
import time

from witmotion import WT901Parser, open_serial

REFRESH_HZ = 50
DEFAULT_PORT = 9000
RECONNECT_INTERVAL = 1.0
FRAME_STALE_SEC = 2.0


def main():
    parser = argparse.ArgumentParser(description="IMU2CV — WT901BLE orientation over UDP")
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
    ser = open_serial()
    serial_open = ser is not None
    imu_parser = WT901Parser() if ser else None
    last_reconnect = 0.0
    last_frame = 0.0

    if serial_open:
        print(f"IMU2CV — WT901BLE on {ser.port}  (Ctrl+C to quit)")
    else:
        print("IMU2CV — WT901BLE not detected, sending zeros until connected  (Ctrl+C to quit)")
    print("=" * 56)

    try:
        while True:
            if not serial_open:
                now = time.time()
                if now - last_reconnect >= RECONNECT_INTERVAL:
                    last_reconnect = now
                    ser = open_serial()
                    if ser is not None:
                        imu_parser = WT901Parser()
                        serial_open = True
                        last_frame = 0.0
                        sys.stdout.write(f"\n[Serial opened {ser.port}]\n")
                        sys.stdout.flush()

            pitch = roll = yaw = 0.0
            ax = ay = az = 0.0
            imu_ok = False

            if serial_open and ser is not None and imu_parser is not None:
                try:
                    if imu_parser.drain(ser):
                        last_frame = time.time()
                    pitch, roll, yaw = imu_parser.pitch, imu_parser.roll, imu_parser.yaw
                    ax, ay, az = imu_parser.ax, imu_parser.ay, imu_parser.az
                    imu_ok = last_frame > 0 and (time.time() - last_frame <= FRAME_STALE_SEC)
                except Exception:
                    sys.stdout.write("\n[Serial error — reconnecting]\n")
                    sys.stdout.flush()
                    try:
                        ser.close()
                    except Exception:
                        pass
                    ser = None
                    imu_parser = None
                    serial_open = False
                    last_reconnect = time.time()

            status = " " if imu_ok else "!"
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
        if ser:
            ser.close()
        if udp_sock:
            udp_sock.close()


if __name__ == "__main__":
    main()
