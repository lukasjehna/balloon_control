#!/usr/bin/env bash
# Checks status of balloon mission services

set -euo pipefail

services=(
  balloon-udp@chopper.service
  balloon-udp@pressure.service
  balloon-udp@temperature.service
  balloon-udp@gyro.service
  balloon-udp@receiver.service
  balloon-udp@telemetry.service
  balloon-udp-spectrometer.service
  balloon-main.service
)

printf "\n=== Balloon Services Status ===\n\n"
for service in "${services[@]}"; do
  status=$(systemctl is-active --quiet "$service" && echo "running" || systemctl show -p SubState --value "$service")
  printf "%-35s: %s\n" "$service" "$status"
done

# Summary
active_count=$(systemctl list-units 'balloon-udp@*' 'balloon-main.service' 'balloon-udp-spectrometer.service' --state=active --no-legend | wc -l)
printf "\n%d active instances found.\n" "$active_count"
