#!/bin/bash
git pull origin main
sudo systemctl daemon-reload
sudo systemctl restart my_service.service
chmod +x *