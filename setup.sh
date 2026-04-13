#!/bin/bash
set -e

echo "=== IMU2CV Setup ==="

sudo apt update
sudo apt install -y python3 python3-pip

pip3 install --break-system-packages pyserial flask 2>/dev/null || pip3 install --user pyserial flask

sudo usermod -aG dialout "$USER"

SERVICE_FILE="/etc/systemd/system/imu2cv@.service"
sudo cp "$(dirname "$0")/imu2cv.service" "$SERVICE_FILE"
sudo systemctl daemon-reload
sudo systemctl enable "imu2cv@${USER}.service"
sudo systemctl start "imu2cv@${USER}.service"

IP=$(hostname -I | awk '{print $1}')
echo ""
echo "=== Done! ==="
echo "  Web UI: http://${IP}:2323"
echo ""
echo "  Reboot so the dialout group takes effect:"
echo "    sudo reboot"
