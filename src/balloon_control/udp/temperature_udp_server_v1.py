#!/usr/bin/env python3

"""
DS18B20 temperature UDP server.
"""

import argparse
import csv
from datetime import datetime
from pathlib import Path
import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from src.devices.temperature_sensor import find_sensors, read_temperature_c

from src.udp.udp_utility import (
    BaseLoggerState,
    JsonCommandHandler,
    ThreadedUDPServer,
    DEFAULT_HOST,
    build_timestamped_filepath,
    install_signal_shutdown,
)


DEFAULT_PORT = 5006


class TemperatureState(BaseLoggerState):
    def __init__(self, log_interval=None, enable_logging=False):
        # Discover sensors before calling BaseLoggerState to have them ready
        self.sensors = {}
        try:
            self.sensors = find_sensors()
        except Exception:
            self.sensors = {}
        super().__init__(log_interval=log_interval, enable_logging=enable_logging)

    def _build_filepath(self):
        return build_timestamped_filepath("temperature", "csv")

    def _ensure_writer(self):
        if self.fp is None:
            self.fp = self.filepath.open("a", newline="", buffering=1)
            self.writer = csv.writer(self.fp)
            if self.filepath.stat().st_size == 0:
                self.writer.writerow(["timestamp", "sensor_id", "temperature_c"])

    def list_ids(self):
        return list(self.sensors.keys())

    def read_once(self):
        """Read all sensors and return dict with ISO timestamp."""
        from datetime import datetime as _dt

        with self.lock:
            readings = {}
            for sensor_id, path in self.sensors.items():
                val = read_temperature_c(path)
                readings[sensor_id] = None if val is None else round(val, 3)
            return {
                "timestamp": _dt.now().isoformat(timespec="seconds"),
                "temperatures_c": readings,
            }
    def _write_row(self, reading):
        ts = reading["timestamp"]
        parts = []

        for sensor_id, temp in reading["temperatures_c"].items():
            if temp is None:
                self.writer.writerow([ts, sensor_id, "NaN"])
                parts.append(f"{sensor_id}=NaN")
            else:
                self.writer.writerow([ts, sensor_id, f"{temp:.3f}"])
                parts.append(f"{sensor_id}={temp:.3f} C")

        print(f"{ts} | temperature | " + ", ".join(parts), flush=True)

def main():
    parser = argparse.ArgumentParser(description="DS18B20 temperature UDP server.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Bind host/interface.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="UDP port.")
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
    server.state = TemperatureState(
        log_interval=args.log_interval,
        enable_logging=args.background_log,
    )

    install_signal_shutdown(server)

    print(f"Temperature UDP server listening on {args.host}:{args.port}")
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.state.stop_logging()
        server.server_close()


if __name__ == "__main__":
    main()

