#!/usr/bin/env bash

#   try this new version which uses ctrl+c to stop the services and exit
#   ./run_services.sh enable           # enable autostart
#   ./run_services.sh enable --now     # enable autostart and start now
#   ./run_services.sh start            # start now only
#   ./run_services.sh disable          # disable autostart

set -euo pipefail

SERVICES=(
    balloon-udp@chopper.service
    balloon-udp@pressure.service
    balloon-udp@temperature.service
    balloon-udp@gyro.service
    balloon-udp@receiver.service
    balloon-udp@telemetry.service
    balloon-udp-spectrometer.service
    balloon-main.service
)

stop_services() {
    echo
    echo "Stopping balloon services..."
    sudo systemctl stop "${SERVICES[@]}"
    echo "Services stopped."
}

trap stop_services INT TERM

ARGS1="${1:-enable}"
ARGS2="${2:-}"

case "$ARGS1" in
    enable)
        if [[ "$ARGS2" == "--now" ]]; then
            sudo systemctl enable --now "${SERVICES[@]}"
        else
            sudo systemctl enable "${SERVICES[@]}"
        fi
        ;;
    start)
        sudo systemctl start "${SERVICES[@]}"
        ;;
    restart)
        sudo systemctl restart "${SERVICES[@]}"
        ;;
    stop)
        sudo systemctl stop "${SERVICES[@]}"
        ;;
    disable)
        sudo systemctl disable --now "${SERVICES[@]}"
        ;;
    *)
        echo "Usage: $0 enable [--now] | start | restart | stop | disable" >&2
        exit 1
        ;;
esac

echo "Following logs; press Ctrl-C to stop the services..."

sudo journalctl -f \
    -u balloon-main.service \
    -u 'balloon-udp@*.service' \
    -u balloon-udp-spectrometer.service