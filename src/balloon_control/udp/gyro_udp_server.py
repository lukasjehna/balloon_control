#!/usr/bin/env python3

"""
MPU6050 gyroscope + accelerometer UDP server.
"""

import argparse
import csv
from datetime import datetime
from pathlib import Path
import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from src.devices.gyro_sensor import init_sensor, read_sensor_frame

from src.udp.udp_utility import (
    BaseLoggerState,
    JsonCommandHandler,
    ThreadedUDPServer,
    DEFAULT_HOST,
    build_timestamped_filepath,
    install_signal_shutdown,
)


DEFAULT_PORT = 5003


class GyroState(BaseLoggerState):
    def __init__(self, log_interval=None, enable_logging=False, address=0x68):
        self.address = address
        super().__init__(log_interval=log_interval, enable_logging=enable_logging)

    def _build_filepath(self):
        return build_timestamped_filepath("gyro", "csv")

    def _ensure_writer(self):
        if self.fp is None:
            self.fp = self.filepath.open("a", newline="", buffering=1)
            fieldnames = [
                "timestamp",
                "gyro_x_dps",
                "gyro_y_dps",
                "gyro_z_dps",
                "accel_x_g",
                "accel_y_g",
                "accel_z_g",
                "rot_x_deg",
                "rot_y_deg",
            ]
            self.writer = csv.DictWriter(self.fp, fieldnames=fieldnames)
            if self.filepath.stat().st_size == 0:
                self.writer.writeheader()

    def read_once(self):
        """Read sensor frame with ISO timestamp."""
        with self.lock:
            return read_sensor_frame(address=self.address)
    
    def _write_row(self, reading):
        row = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in reading.items()}
        self.writer.writerow(row)
        print(
            f"{row['timestamp']} | "
            f"gyro=({row['gyro_x_dps']:.2f},{row['gyro_y_dps']:.2f},{row['gyro_z_dps']:.2f}) dps | "
            f"accel=({row['accel_x_g']:.3f},{row['accel_y_g']:.3f},{row['accel_z_g']:.3f}) g | "
            f"rot=({row['rot_x_deg']:.1f},{row['rot_y_deg']:.1f}) deg",
            flush=True,
    )

def main():
    parser = argparse.ArgumentParser(description="MPU6050 gyro UDP server.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Bind host/interface.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="UDP port.")
    parser.add_argument("--bus", type=int, default=1, help="I2C bus number.")
    parser.add_argument(
        "--address",
        type=lambda x: int(x, 0),
        default=0x68,
        help="I2C address (e.g., 0x68).",
    )
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

    # Initialize sensor once at startup
    init_sensor(bus_number=args.bus, address=args.address)

    server = ThreadedUDPServer((args.host, args.port), JsonCommandHandler)
    server.state = GyroState(
        log_interval=args.log_interval,
        enable_logging=args.background_log,
        address=args.address,
    )

    install_signal_shutdown(server)

    print(f"Gyro UDP server listening on {args.host}:{args.port}")
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.state.stop_logging()
        server.server_close()


if __name__ == "__main__":
    main()

