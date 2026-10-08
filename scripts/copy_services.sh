 #!/usr/bin/env bash
set -e

sudo cp system/balloon-*.service /etc/systemd/system/
sudo chmod 644 /etc/systemd/system/balloon-*.service
sudo systemctl daemon-reload 
