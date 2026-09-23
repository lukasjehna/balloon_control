#!/usr/bin/env python3

"""
System telemetry UDP server.

Monitors:
- CPU temperature
- PMIC temperature
- passive cooling state
- core voltage
- throttled flag (vcgencmd get_throttled)
"""

import argparse
import csv
from datetime import datetime as _dt
from pathlib import Path
import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from src.devices.telemetry_sensor import (
    read_cpu_temp_degC,
    read_pmic_temp_degC,
    read_passive_state,
    read_core_voltage_V,
    read_throttled,
)

from src.udp.udp_utility import (
    BaseLoggerState,
    JsonCommandHandler,
    ThreadedUDPServer,
    DEFAULT_HOST,
    build_timestamped_filepath,
    install_signal_shutdown,
)

DEFAULT_PORT = 5007


class SystemTelemetryState(BaseLoggerState):
    """State + background logger for system telemetry."""

    def __init__(self, log_interval=None, enable_logging=False):
        super().__init__(log_interval=log_interval, enable_logging=enable_logging)

    def _build_filepath(self):
        # data/YYYYMMDDHHMMSS_system_telemetry.csv
        return build_timestamped_filepath("system_telemetry", "csv")

    def _ensure_writer(self):
        # Use DictWriter so BaseLoggerState._write_row can write dict rows directly.
        if self.fp is None:
            self.fp = self.filepath.open("a", newline="", buffering=1)
            fieldnames = [
                "timestamp",
                "cpu_temp_c",
                "pmic_temp_c",
                "passive_state",
                "core_voltage_v",
                "throttled",
            ]
            self.writer = csv.DictWriter(self.fp, fieldnames=fieldnames)
            if self.filepath.stat().st_size == 0:
                self.writer.writeheader()

    def read_once(self):
        """Read one telemetry snapshot."""
        with self.lock:
            cpu = read_cpu_temp_degC()
            pmic = read_pmic_temp_degC()
            passive = read_passive_state()
            core_v = read_core_voltage_V()
            throttled = read_throttled()

        return {
            "timestamp": _dt.now().isoformat(timespec="seconds"),
            "cpu_temp_c": None if cpu is None else round(cpu, 3),
            "pmic_temp_c": None if pmic is None else round(pmic, 3),
            "passive_state": passive,
            "core_voltage_v": None if core_v is None else round(core_v, 4),
            "throttled": throttled,
        }
        # Default BaseLoggerState._write_row() will write this dict to CSV.
    
    
    def _write_row(self, reading):
        self.writer.writerow(reading)

        cpu = "NaN" if reading["cpu_temp_c"] is None else f"{reading['cpu_temp_c']:.3f} C"
        pmic = "NaN" if reading["pmic_temp_c"] is None else f"{reading['pmic_temp_c']:.3f} C"
        core = "NaN" if reading["core_voltage_v"] is None else f"{reading['core_voltage_v']:.4f} V"

        print(
            f"{reading['timestamp']} | "
            f"cpu={cpu} | "
            f"pmic={pmic} | "
            f"passive={reading['passive_state']} | "
            f"core={core} | "
            f"throttled={reading['throttled']}",
            flush=True,
        )

def main():
    parser = argparse.ArgumentParser(
        description="System telemetry UDP server (CPU/PMIC temperature, core voltage, throttled)."
    )
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
    server.state = SystemTelemetryState(
        log_interval=args.log_interval,
        enable_logging=args.background_log,
    )

    install_signal_shutdown(server)

    print(f"System telemetry UDP server listening on {args.host}:{args.port}")

    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.state.stop_logging()
        server.server_close()


if __name__ == "__main__":
    main()

