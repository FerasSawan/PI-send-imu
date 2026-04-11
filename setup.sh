#!/bin/bash
set -e

echo "=== IMU2CV Setup ==="

sudo apt update
sudo apt install -y python3 python3-pip i2c-tools

pip3 install --break-system-packages smbus2 flask 2>/dev/null || pip3 install --user smbus2 flask

if ! sudo raspi-config nonint get_i2c | grep -q "0"; then
    echo "Enabling I2C..."
    sudo raspi-config nonint do_i2c 0
fi

sudo usermod -aG i2c "$USER"

SERVICE_FILE="/etc/systemd/system/imu2cv@.service"
sudo cp "$(dirname "$0")/imu2cv.service" "$SERVICE_FILE"
sudo systemctl daemon-reload
sudo systemctl enable "imu2cv@${USER}.service"
sudo systemctl start "imu2cv@${USER}.service"

IP=$(hostname -I | awk '{print $1}')
echo ""
echo "=== Done! ==="
echo "  Web UI: http://${IP}:5000"
echo ""
echo "  Reboot to finish I2C setup if this is a fresh install:"
echo "    sudo reboot"
