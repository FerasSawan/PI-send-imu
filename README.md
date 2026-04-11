# IMU2CV

Streams real-time IMU orientation (pitch, roll, yaw) and acceleration data over UDP from a Raspberry Pi with a WitMotion WT901 sensor.

## Setup (on the Pi)

Clone and run the setup script:

```bash
git clone https://github.com/FerasSawan/PI-send-imu.git ~/IMU2CV
cd ~/IMU2CV
./setup.sh
sudo reboot
```

This installs all dependencies and enables I2C automatically.

## Send IMU data

```bash
python3 imu_reader.py <RECEIVER_IP>
```

Example:

```bash
python3 imu_reader.py 192.168.1.68 9000
```

If the IMU isn't connected it sends zeros and auto-reconnects when plugged in.

## Receive IMU data

On the receiving computer:

```bash
python3 receiver.py
```

Listens on UDP port 9000 by default.

## Files

- `setup.sh` — installs dependencies and enables I2C
- `imu_reader.py` — reads the WT901 over I2C and sends UDP packets at 50 Hz
- `receiver.py` — listens for UDP packets and prints live values
