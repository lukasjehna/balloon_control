#!/bin/bash
INTERFACE="wlan0"
sudo ip link set "$INTERFACE" down
echo "try to turn WLAN ($INTERFACE) off."
sleep 30
sudo ip link set "$INTERFACE" up
echo "Try to turn WLAN ($INTERFACE) on."
