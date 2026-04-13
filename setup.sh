#!/bin/bash
set -e

echo "=== IMU2CV Setup ==="

sudo apt update
sudo apt install -y python3 python3-pip bluetooth bluez

pip3 install --break-system-packages pyserial flask bleak 2>/dev/null || pip3 install --user pyserial flask bleak

# dialout for USB serial, bluetooth for BLE
sudo usermod -aG dialout "$USER"
sudo usermod -aG bluetooth "$USER"

# Make sure bluetooth service is running
sudo systemctl enable bluetooth
sudo systemctl start bluetooth

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
echo "  Reboot so group changes take effect:"
echo "    sudo reboot"
