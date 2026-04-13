# IMU2CV

Streams real-time IMU orientation (pitch, roll, yaw) and acceleration data over UDP from a Raspberry Pi with a WitMotion WT901BLECL sensor connected via USB. Includes a web UI to configure the target IP and monitor live values.

## Setup

Clone and run the setup script on any Pi:

```bash
git clone https://github.com/FerasSawan/PI-send-imu.git ~/IMU2CV
cd ~/IMU2CV
./setup.sh
sudo reboot
```

After reboot the web UI starts automatically. Plug in the WT901BLE via USB and open `http://<PI_IP>:2323` in a browser.

## Usage

1. Plug the WT901BLECL into the Pi via USB
2. Open the web UI in a browser
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

- `app.py` — web UI server (Flask)
- `imu_reader.py` — headless CLI sender (reads WT901BLE over USB serial, sends UDP at 50 Hz)
- `receiver.py` — listens for UDP packets and prints live values
- `setup.sh` — installs dependencies and starts the web UI service
- `imu2cv.service` — systemd unit for auto-start on boot
