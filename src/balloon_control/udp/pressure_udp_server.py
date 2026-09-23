#!/usr/bin/env python3

"""
MS8607 pressure/temperature + HTU21D humidity UDP server.
"""

import argparse
import csv
from datetime import datetime
from pathlib import Path
import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from src.devices.pressure_sensor import read_ms8607

from src.udp.udp_utility import (
    BaseLoggerState,
    JsonCommandHandler,
    ThreadedUDPServer,
    DEFAULT_HOST,
    build_timestamped_filepath,
    install_signal_shutdown,
)


DEFAULT_PORT = 5004


class PressureState(BaseLoggerState):
    def __init__(self, log_interval=None, enable_logging=False, bus_num=1):
        self.bus_num = bus_num
        super().__init__(log_interval=log_interval, enable_logging=enable_logging)

    def _build_filepath(self):
        return build_timestamped_filepath("pressure", "csv")

    def _ensure_writer(self):
        if self.fp is None:
            self.fp = self.filepath.open("a", newline="", buffering=1)
            fieldnames = ["timestamp", "temperature_c", "humidity_pct", "pressure_hpa"]
            self.writer = csv.DictWriter(self.fp, fieldnames=fieldnames)
            if self.filepath.stat().st_size == 0:
                self.writer.writeheader()

    def read_once(self):
        """Read sensor and return dict with ISO timestamp and measurements."""
        with self.lock:
            temperature_c, humidity_pct, pressure_hpa = read_ms8607(bus_num=self.bus_num)
            return {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "temperature_c": round(temperature_c, 3),
                "humidity_pct": round(humidity_pct, 3),
                "pressure_hpa": round(pressure_hpa, 3),
            }

    def _write_row(self, reading):
        row = {
            k: (round(v, 4) if isinstance(v, float) else v)
            for k, v in reading.items()
        }
        self.writer.writerow(row)
        print(
            f"{row['timestamp']} | "
            f"temp={row['temperature_c']:.3f} C | "
            f"hum={row['humidity_pct']:.3f} % | "
            f"pressure={row['pressure_hpa']:.3f} hPa",
            flush=True,
        )
    
def main():
    parser = argparse.ArgumentParser(description="MS8607 pressure UDP server.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Bind host/interface.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="UDP port.")
    parser.add_argument("--bus", type=int, default=1, help="I2C bus number.")
    parser.add_argument(
        "--background-log",
        action="store_true",
        help="Enable continuous background logging to CSV.",
    )
    parser.add_argument(
        "--log-interval",
        type=float,
        default=13.0,
        help="Logging interval in seconds.",
    )
    args = parser.parse_args()

    server = ThreadedUDPServer((args.host, args.port), JsonCommandHandler)
    server.state = PressureState(
        log_interval=args.log_interval,
        enable_logging=args.background_log,
        bus_num=args.bus,
    )

    install_signal_shutdown(server)

    print(f"Pressure UDP server listening on {args.host}:{args.port}")
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.state.stop_logging()
        server.server_close()


if __name__ == "__main__":
    main()

