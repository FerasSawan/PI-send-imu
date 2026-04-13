#!/usr/bin/env python3
"""IMU2CV Web UI — configure and monitor IMU streaming from a browser."""

import glob
import json
import socket
import struct
import threading
import time
from queue import Queue, Empty

import serial
from flask import Flask, render_template, request, jsonify, Response

app = Flask(__name__)

BAUD_RATE = 115200
REFRESH_HZ = 50
RECONNECT_INTERVAL = 1.0
PACKET_HEADER = 0x55
PACKET_LEN = 11

state = {
    "imu_connected": False,
    "sending": False,
    "target_ip": "",
    "target_port": 9000,
    "seq": 0,
    "pitch": 0.0, "roll": 0.0, "yaw": 0.0,
    "ax": 0.0, "ay": 0.0, "az": 0.0,
}

_lock = threading.Lock()
_ser = None
_udp_sock = None
_stop_event = threading.Event()
_sse_clients: list[Queue] = []


def _find_serial_port():
    for pattern in ["/dev/ttyUSB*", "/dev/ttyACM*"]:
        ports = sorted(glob.glob(pattern))
        if ports:
            return ports[0]
    return None


def _open_serial():
    port = _find_serial_port()
    if not port:
        return None
    try:
        ser = serial.Serial(port, BAUD_RATE, timeout=0.5)
        ser.reset_input_buffer()
        return ser
    except Exception:
        return None


def _parse_packet(buf):
    if len(buf) != PACKET_LEN or buf[0] != PACKET_HEADER:
        return None
    checksum = sum(buf[:10]) & 0xFF
    if checksum != buf[10]:
        return None
    pkt_type = buf[1]
    v0, v1, v2 = struct.unpack("<3h", buf[2:8])
    return pkt_type, (v0, v1, v2)


def _read_imu(ser):
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

        result = _parse_packet(bytes([PACKET_HEADER]) + rest)
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


def _broadcast_sse(data: dict):
    msg = f"data: {json.dumps(data)}\n\n"
    dead = []
    for q in _sse_clients:
        try:
            q.put_nowait(msg)
        except Exception:
            dead.append(q)
    for q in dead:
        _sse_clients.remove(q)


def _imu_loop():
    global _ser, _udp_sock
    last_reconnect = 0.0

    while not _stop_event.is_set():
        with _lock:
            connected = state["imu_connected"]

        if not connected:
            now = time.time()
            if now - last_reconnect >= RECONNECT_INTERVAL:
                last_reconnect = now
                _ser = _open_serial()
                if _ser is not None:
                    with _lock:
                        state["imu_connected"] = True
                        connected = True

        pitch = roll = yaw = 0.0
        ax = ay = az = 0.0

        if connected:
            try:
                result = _read_imu(_ser)
                if result:
                    pitch, roll, yaw, ax, ay, az = result
            except Exception:
                with _lock:
                    state["imu_connected"] = False
                try:
                    _ser.close()
                except Exception:
                    pass
                _ser = None
                last_reconnect = time.time()

        with _lock:
            state["pitch"] = round(pitch, 2)
            state["roll"] = round(roll, 2)
            state["yaw"] = round(yaw, 2)
            state["ax"] = round(ax, 3)
            state["ay"] = round(ay, 3)
            state["az"] = round(az, 3)
            sending = state["sending"]
            target_ip = state["target_ip"]
            target_port = state["target_port"]
            seq = state["seq"]

        if sending and target_ip and _udp_sock:
            try:
                packet = struct.pack("<Idffffff", seq, time.time(),
                                     pitch, roll, yaw, ax, ay, az)
                _udp_sock.sendto(packet, (target_ip, target_port))
                with _lock:
                    state["seq"] += 1
            except Exception:
                pass

        _broadcast_sse({
            "pitch": state["pitch"], "roll": state["roll"], "yaw": state["yaw"],
            "ax": state["ax"], "ay": state["ay"], "az": state["az"],
            "imu_connected": state["imu_connected"],
            "sending": state["sending"],
            "target_ip": state["target_ip"],
            "target_port": state["target_port"],
            "seq": state["seq"],
        })

        time.sleep(1.0 / REFRESH_HZ)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/state")
def get_state():
    with _lock:
        return jsonify(state)


@app.route("/api/start", methods=["POST"])
def start_sending():
    global _udp_sock
    data = request.json or {}
    ip = data.get("ip", "").strip()
    port = int(data.get("port", 9000))
    if not ip:
        return jsonify({"error": "IP is required"}), 400
    with _lock:
        state["target_ip"] = ip
        state["target_port"] = port
        state["seq"] = 0
        state["sending"] = True
    if _udp_sock is None:
        _udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if ip == "255.255.255.255":
            _udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    return jsonify({"ok": True})


@app.route("/api/stop", methods=["POST"])
def stop_sending():
    global _udp_sock
    with _lock:
        state["sending"] = False
    if _udp_sock:
        _udp_sock.close()
        _udp_sock = None
    return jsonify({"ok": True})


@app.route("/api/stream")
def stream():
    q: Queue = Queue(maxsize=50)
    _sse_clients.append(q)

    def generate():
        try:
            while True:
                try:
                    msg = q.get(timeout=30)
                    yield msg
                except Empty:
                    yield ": keepalive\n\n"
        except GeneratorExit:
            if q in _sse_clients:
                _sse_clients.remove(q)

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    t = threading.Thread(target=_imu_loop, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=2323, threaded=True)
