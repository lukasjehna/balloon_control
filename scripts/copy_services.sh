#!/usr/bin/env bash
set -e

sudo cp systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload