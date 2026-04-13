#!/usr/bin/env python3
"""IMU2CV Web UI — configure and monitor IMU streaming from a browser.

Tries BLE first; falls back to USB serial if no BLE device found.
"""

import json
import os
import socket
import struct
import threading
import time
from queue import Queue, Empty

from flask import Flask, render_template, request, jsonify, Response

from witmotion import WT901Parser, open_serial
from ble_transport import BLETransport

app = Flask(__name__)

REFRESH_HZ = 50
RECONNECT_INTERVAL = 1.0
FRAME_STALE_SEC = 2.0
MODE = os.environ.get("IMU2CV_MODE", "auto").lower()  # "ble", "usb", or "auto"

state = {
    "imu_connected": False,
    "sending": False,
    "target_ip": "",
    "target_port": 9000,
    "seq": 0,
    "pitch": 0.0, "roll": 0.0, "yaw": 0.0,
    "ax": 0.0, "ay": 0.0, "az": 0.0,
    "transport": "",
}

_lock = threading.Lock()
_udp_sock = None
_stop_event = threading.Event()
_sse_clients: list[Queue] = []


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


def _imu_loop_usb():
    """USB serial transport loop."""
    ser = None
    parser = None
    last_frame = 0.0
    last_reconnect = 0.0
    serial_open = False

    while not _stop_event.is_set():
        now = time.time()

        if not serial_open:
            if now - last_reconnect >= RECONNECT_INTERVAL:
                last_reconnect = now
                ser = open_serial()
                if ser is not None:
                    parser = WT901Parser()
                    last_frame = 0.0
                    serial_open = True
                    with _lock:
                        state["transport"] = f"USB ({ser.port})"

        pitch = roll = yaw = 0.0
        ax = ay = az = 0.0

        if serial_open and ser is not None and parser is not None:
            try:
                if parser.drain(ser):
                    last_frame = time.time()
                pitch, roll, yaw = parser.pitch, parser.roll, parser.yaw
                ax, ay, az = parser.ax, parser.ay, parser.az
            except Exception:
                try:
                    ser.close()
                except Exception:
                    pass
                ser = None
                parser = None
                serial_open = False
                last_frame = 0.0
                last_reconnect = time.time()

        imu_ok = serial_open and last_frame > 0 and (now - last_frame <= FRAME_STALE_SEC)
        _update_state(imu_ok, pitch, roll, yaw, ax, ay, az)
        time.sleep(1.0 / REFRESH_HZ)


def _ble_state_poller(ble: BLETransport):
    """Background thread that reads BLE parser and updates shared state."""
    with _lock:
        state["transport"] = "BLE (scanning...)"

    while not _stop_event.is_set():
        p = ble.parser
        pitch, roll, yaw = p.pitch, p.roll, p.yaw
        ax, ay, az = p.ax, p.ay, p.az
        imu_ok = ble.connected and ble.last_data_age <= FRAME_STALE_SEC

        if ble.connected:
            with _lock:
                state["transport"] = f"BLE ({ble.device_name or ble.device_addr})"
        elif not imu_ok:
            with _lock:
                state["transport"] = "BLE (scanning...)"

        _update_state(imu_ok, pitch, roll, yaw, ax, ay, az)
        time.sleep(1.0 / REFRESH_HZ)


def _update_state(imu_ok, pitch, roll, yaw, ax, ay, az):
    global _udp_sock
    with _lock:
        state["imu_connected"] = imu_ok
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
        "transport": state["transport"],
    })


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
    if MODE in ("ble", "auto"):
        ble = BLETransport()
        # State poller in background thread
        threading.Thread(target=_ble_state_poller, args=(ble,), daemon=True).start()
        # Flask in background thread
        threading.Thread(target=lambda: app.run(host="0.0.0.0", port=2323, threaded=True),
                         daemon=True).start()
        # BLE must run in main thread (BlueZ/D-Bus requirement)
        try:
            ble.run_forever()
        except KeyboardInterrupt:
            ble.stop()
    else:
        threading.Thread(target=_imu_loop_usb, daemon=True).start()
        app.run(host="0.0.0.0", port=2323, threaded=True)
