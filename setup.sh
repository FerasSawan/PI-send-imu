#!/bin/bash
set -e

echo "=== IMU2CV Setup ==="

sudo apt update
sudo apt install -y python3 python3-pip i2c-tools

pip3 install --break-system-packages smbus2 2>/dev/null || pip3 install --user smbus2

if ! sudo raspi-config nonint get_i2c | grep -q "0"; then
    echo "Enabling I2C..."
    sudo raspi-config nonint do_i2c 0
fi

sudo usermod -aG i2c "$USER"

echo ""
echo "=== Done! Reboot to finish setup ==="
echo "  sudo reboot"
echo ""
echo "Then run:"
echo "  python3 imu_reader.py <RECEIVER_IP>"
