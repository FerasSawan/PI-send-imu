# IMU2CV — Bluetooth (WT901BLE)

Use the WitMotion **WT901BLE** over **Bluetooth Low Energy** so the Pi does not need a USB data cable. Power the sensor from its battery or a separate USB charger.

## Requirements

- Raspberry Pi OS with **Bluetooth** enabled (default on Pi 3 / 4 / 5 / Zero 2 W).
- Python packages: **`bleak`** (installed by `./setup.sh`).
- The IMU must be **on** and **advertising** (name usually contains `WT901`, e.g. `WT901BLE68`).

## How it works

- The app scans for a device whose name includes **WT** or that advertises WitMotion service **`0000ffe5-...`**.
- It connects, subscribes to notify characteristic **`0000ffe4-...`**, and parses the same binary frames as USB (about **50 Hz**).
- The web UI shows **`BLE (device name)`** next to the status when connected.

## Run the web UI over BLE

```bash
cd ~/IMU2CV
export IMU2CV_MODE=ble
python3 app.py
```

Then open **`http://<PI_IP>:2323`**.

Modes:

| `IMU2CV_MODE` | Behavior |
|---------------|----------|
| `ble` or `auto` | BLE stack in the main process (recommended for wireless). |
| `usb` | USB serial only (`/dev/ttyUSB*` / `ttyACM*`). |

## systemd (auto-start on boot)

Add the environment variable to the service override, or edit the unit:

```ini
[Service]
Environment=IMU2CV_MODE=ble
```

Example with drop-in:

```bash
sudo systemctl edit imu2cv@$USER
```

Paste:

```ini
[Service]
Environment=IMU2CV_MODE=ble
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl restart imu2cv@$USER.service
```

## Troubleshooting

- **“BLE (scanning…)” forever** — IMU off, out of range, or not advertising. Turn it on; move closer; ensure it is not stuck connected only to another host if your firmware does that.
- **Works on USB but not BLE** — Some units prioritize USB when plugged in; try **power only** (no data) or battery so BLE can advertise.
- **Permission / adapter errors** — Run as a user that can use Bluetooth (default desktop user). Avoid running the app as root unless needed.
- **Multiple WT901s** — The first matching device wins. Use a dedicated Pi per sensor or extend the code to filter by MAC / name.

## Technical reference

| Item | UUID / value |
|------|----------------|
| WitMotion service | `0000ffe5-0000-1000-8000-00805f9a34fb` |
| Notify (sensor data) | `0000ffe4-0000-1000-8000-00805f9a34fb` |
| Write (commands) | `0000ffe9-0000-1000-8000-00805f9a34fb` |

Payload matches the USB protocol: combined `0x61` frames (20 bytes each); notifications may bundle two frames per packet (40 bytes).
