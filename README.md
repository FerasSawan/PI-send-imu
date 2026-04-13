# IMU2CV

Streams real-time IMU orientation (pitch, roll, yaw) and acceleration data over UDP from a Raspberry Pi with a WitMotion WT901BLECL sensor. Supports both **USB serial** and **Bluetooth Low Energy** — switch between them in the web UI. Includes a web UI to configure the target IP, switch transport mode, and monitor live values.

## Setup

Clone and run the setup script on any Pi:

```bash
git clone -b bluetooth https://github.com/FerasSawan/PI-send-imu.git ~/IMU2CV
cd ~/IMU2CV
./setup.sh
sudo reboot
```

After reboot the web UI starts automatically at `http://<PI_IP>:2323`.

## Usage

1. Open the web UI in a browser
2. Choose your transport mode: **BLE** or **USB**
   - **BLE**: Click **Connect BLE** to scan and connect wirelessly
   - **USB**: Plug in the WT901BLECL via USB — it auto-detects
3. Enter the target IP and port (default 9000)
4. Click **Start Sending**

On the receiving computer, run:

```bash
python3 receiver.py
```

## CLI (no UI)

```bash
python3 imu_reader.py <RECEIVER_IP> 9000
```

## Files

- `app.py` — web UI server (Flask); set `IMU2CV_MODE=usb|ble|auto` for transport
- `imu_reader.py` — headless CLI sender (USB serial)
- `ble_transport.py` — BLE scan/connect/notify (branch `bluetooth`; see [BLE_README.md](BLE_README.md))
- `receiver.py` — listens for UDP packets and prints live values
- `setup.sh` — installs dependencies and starts the web UI service
- `imu2cv.service` — systemd unit for auto-start on boot
