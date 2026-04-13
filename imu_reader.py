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
import glob
import socket
import struct
import sys
import time

import serial

BAUD_RATE = 115200
REFRESH_HZ = 50
DEFAULT_PORT = 9000
RECONNECT_INTERVAL = 1.0
PACKET_HEADER = 0x55
PACKET_LEN = 11


def find_serial_port():
    """Auto-detect the WT901 USB serial device."""
    for pattern in ["/dev/ttyUSB*", "/dev/ttyACM*"]:
        ports = sorted(glob.glob(pattern))
        if ports:
            return ports[0]
    return None


def open_serial():
    """Try to open the serial port and return the connection."""
    port = find_serial_port()
    if not port:
        return None
    try:
        ser = serial.Serial(port, BAUD_RATE, timeout=0.5)
        ser.reset_input_buffer()
        return ser
    except Exception:
        return None


def parse_packet(buf):
    """Parse one 11-byte WitMotion packet. Returns (type, values) or None."""
    if len(buf) != PACKET_LEN or buf[0] != PACKET_HEADER:
        return None
    checksum = sum(buf[:10]) & 0xFF
    if checksum != buf[10]:
        return None
    pkt_type = buf[1]
    v0, v1, v2 = struct.unpack("<3h", buf[2:8])
    return pkt_type, (v0, v1, v2)


def read_imu(ser):
    """Read serial data and return (pitch, roll, yaw, ax, ay, az) or None on failure."""
    pitch = roll = yaw = None
    ax = ay = az = None
    deadline = time.time() + 0.1

    while time.time() < deadline:
        if ser.in_waiting < PACKET_LEN:
            time.sleep(0.001)
            continue

        byte = ser.read(1)
        if not byte or byte[0] != PACKET_HEADER:
            continue

        rest = ser.read(PACKET_LEN - 1)
        if len(rest) != PACKET_LEN - 1:
            continue

        result = parse_packet(bytes([PACKET_HEADER]) + rest)
        if result is None:
            continue

        pkt_type, (v0, v1, v2) = result

        if pkt_type == 0x51:
            s = 16.0 / 32768.0
            ax, ay, az = v0 * s, v1 * s, v2 * s
        elif pkt_type == 0x53:
            s = 180.0 / 32768.0
            roll, pitch, yaw = v0 * s, v1 * s, v2 * s

        if all(v is not None for v in (pitch, roll, yaw, ax, ay, az)):
            return pitch, roll, yaw, ax, ay, az

    if pitch is not None and roll is not None and yaw is not None:
        return pitch, roll, yaw, ax or 0.0, ay or 0.0, az or 0.0

    return None


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
    connected = ser is not None
    last_reconnect = 0.0

    if connected:
        print(f"IMU2CV — WT901BLE on {ser.port}  (Ctrl+C to quit)")
    else:
        print("IMU2CV — WT901BLE not detected, sending zeros until connected  (Ctrl+C to quit)")
    print("=" * 56)

    try:
        while True:
            if not connected:
                now = time.time()
                if now - last_reconnect >= RECONNECT_INTERVAL:
                    last_reconnect = now
                    ser = open_serial()
                    if ser is not None:
                        connected = True
                        sys.stdout.write(f"\n[IMU connected on {ser.port}]\n")
                        sys.stdout.flush()

            pitch = roll = yaw = 0.0
            ax = ay = az = 0.0

            if connected:
                try:
                    result = read_imu(ser)
                    if result:
                        pitch, roll, yaw, ax, ay, az = result
                except Exception:
                    sys.stdout.write("\n[IMU disconnected — sending zeros]\n")
                    sys.stdout.flush()
                    connected = False
                    try:
                        ser.close()
                    except Exception:
                        pass
                    ser = None
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
        if ser:
            ser.close()
        if udp_sock:
            udp_sock.close()


if __name__ == "__main__":
    main()
