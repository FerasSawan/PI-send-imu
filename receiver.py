#!/usr/bin/env python3
"""
IMU2CV Receiver — run this on YOUR computer to receive live IMU data.

No dependencies beyond Python 3 standard library.

Usage:
    python3 receiver.py              # listen on port 9000
    python3 receiver.py 9000         # explicit port

The packet format is a compact binary struct (36 bytes):
    uint32  seq        — packet sequence number
    float64 timestamp  — Unix epoch from the Pi
    float32 pitch      — degrees
    float32 roll       — degrees
    float32 yaw        — degrees
    float32 ax         — acceleration X in g
    float32 ay         — acceleration Y in g
    float32 az         — acceleration Z in g

You can also import this in your own code:

    from receiver import IMUReceiver
    imu = IMUReceiver(port=9000)
    for data in imu.stream():
        print(data["pitch"], data["roll"], data["yaw"])
        print(data["ax"], data["ay"], data["az"])
"""

import socket
import struct
import sys


PACKET_FMT = "<Idffffff"
PACKET_SIZE = struct.calcsize(PACKET_FMT)


class IMUReceiver:
    """Minimal UDP receiver that yields IMU packets as dicts."""

    def __init__(self, port=9000, bind_addr="0.0.0.0"):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((bind_addr, port))
        self.port = port

    def recv_one(self):
        """Block until one packet arrives, return dict."""
        data, addr = self.sock.recvfrom(PACKET_SIZE)
        seq, ts, pitch, roll, yaw, ax, ay, az = struct.unpack(PACKET_FMT, data)
        return {"seq": seq, "timestamp": ts, "pitch": pitch, "roll": roll, "yaw": yaw,
                "ax": ax, "ay": ay, "az": az, "addr": addr}

    def stream(self):
        """Infinite generator yielding packets."""
        while True:
            yield self.recv_one()

    def close(self):
        self.sock.close()


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9000

    imu = IMUReceiver(port=port)
    print(f"IMU2CV Receiver — listening on UDP port {port}  (Ctrl+C to quit)")
    print("=" * 60)

    try:
        for pkt in imu.stream():
            sys.stdout.write(
                f"\r[#{pkt['seq']:>6}]  "
                f"P:{pkt['pitch']:+7.2f}° R:{pkt['roll']:+7.2f}° Y:{pkt['yaw']:+7.2f}°  "
                f"AX:{pkt['ax']:+5.2f}g AY:{pkt['ay']:+5.2f}g AZ:{pkt['az']:+5.2f}g  "
            )
            sys.stdout.flush()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        imu.close()


if __name__ == "__main__":
    main()
