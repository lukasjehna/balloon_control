#!/usr/bin/env python3
"""
MPU6050 gyroscope + accelerometer logger.

PEP 8 naming, unified CLI, consistent CSV:
- File: {YYYYMMDDHHMMSS}_gyro.csv in project_root/data by default.
- Columns: timestamp, gyro_x_dps, gyro_y_dps, gyro_z_dps, accel_x_g, accel_y_g, accel_z_g, rot_x_deg, rot_y_deg.
"""

import argparse
import csv
from datetime import datetime
from pathlib import Path
import math
import time

import smbus

POWER_MGMT_1 = 0x6B
DEFAULT_BUS = 1
DEFAULT_ADDR = 0x68
DEFAULT_MEASUREMENT_INTERVAL = 13.0

_bus = None


def init_sensor(bus_number: int = DEFAULT_BUS, address: int = DEFAULT_ADDR):
    global _bus
    _bus = smbus.SMBus(bus_number)
    _bus.write_byte_data(address, POWER_MGMT_1, 0)


def _read_word(reg: int, address: int = DEFAULT_ADDR) -> int:
    h = _bus.read_byte_data(address, reg)
    l = _bus.read_byte_data(address, reg + 1)
    return (h << 8) + l


def _read_word_2c(reg: int, address: int = DEFAULT_ADDR) -> int:
    val = _read_word(reg, address)
    return -((65535 - val) + 1) if val >= 0x8000 else val


def _dist(a: float, b: float) -> float:
    return math.sqrt(a * a + b * b)


def _get_y_rotation(x: float, y: float, z: float) -> float:
    radians = math.atan2(x, _dist(y, z))
    return -math.degrees(radians)


def _get_x_rotation(x: float, y: float, z: float) -> float:
    radians = math.atan2(y, _dist(x, z))
    return math.degrees(radians)


def read_gyroscope(address: int = DEFAULT_ADDR):
    gx = _read_word_2c(0x43, address) / 131.0
    gy = _read_word_2c(0x45, address) / 131.0
    gz = _read_word_2c(0x47, address) / 131.0
    return gx, gy, gz


def read_accelerometer(address: int = DEFAULT_ADDR):
    ax = _read_word_2c(0x3B, address) / 16384.0
    ay = _read_word_2c(0x3D, address) / 16384.0
    az = _read_word_2c(0x3F, address) / 16384.0
    return ax, ay, az


def read_sensor_frame(address: int = DEFAULT_ADDR):
    gx, gy, gz = read_gyroscope(address)
    ax, ay, az = read_accelerometer(address)
    rot_x = _get_x_rotation(ax, ay, az)
    rot_y = _get_y_rotation(ax, ay, az)
    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "gyro_x_dps": gx,
        "gyro_y_dps": gy,
        "gyro_z_dps": gz,
        "accel_x_g": ax,
        "accel_y_g": ay,
        "accel_z_g": az,
        "rot_x_deg": rot_x,
        "rot_y_deg": rot_y,
    }


def main():
    parser = argparse.ArgumentParser(description="MPU6050 gyroscope + accelerometer logger.")
    parser.add_argument("--interval", type=float, default=DEFAULT_MEASUREMENT_INTERVAL, help="Seconds between samples.")
    parser.add_argument("--duration", type=float, default=None, help="Total seconds to run; None = until Ctrl+C.")
    parser.add_argument("--print-only", action="store_true", help="Print to console without saving CSV.")
    parser.add_argument("--data-dir", type=str, default=None, help="Optional data directory override.")
    parser.add_argument("--bus", type=int, default=DEFAULT_BUS, help="I2C bus number.")
    parser.add_argument("--address", type=lambda x: int(x, 0), default=DEFAULT_ADDR, help="I2C address (e.g., 0x68).")
    args = parser.parse_args()

    if args.data_dir:
        data_dir = Path(args.data_dir)
    else:
        data_dir = Path(__file__).resolve().parents[2] / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    start_ts = datetime.now().strftime("%Y%m%d%H%M%S")
    out_path = data_dir / f"{start_ts}_gyro.csv"
    fieldnames = [
        "timestamp",
        "gyro_x_dps", "gyro_y_dps", "gyro_z_dps",
        "accel_x_g", "accel_y_g", "accel_z_g",
        "rot_x_deg", "rot_y_deg",
    ]

    init_sensor(bus_number=args.bus, address=args.address)

    writer = None
    csv_file = None
    if not args.print_only:
        csv_file = out_path.open("a", newline="", buffering=1)
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        if out_path.stat().st_size == 0:
            writer.writeheader()
        print(f"Saving to {out_path}")

    t0 = time.time()
    try:
        while True:
            row = read_sensor_frame(address=args.address)
            if writer:
                writer.writerow({k: (round(v, 4) if isinstance(v, float) else v) for k, v in row.items()})
            print(
                f"{row['timestamp']} | "
                f"gyro=({row['gyro_x_dps']:.2f},{row['gyro_y_dps']:.2f},{row['gyro_z_dps']:.2f}) dps | "
                f"accel=({row['accel_x_g']:.3f},{row['accel_y_g']:.3f},{row['accel_z_g']:.3f}) g | "
                f"rot=({row['rot_x_deg']:.1f},{row['rot_y_deg']:.1f}) deg"
            )
            if args.duration is not None and (time.time() - t0) >= args.duration:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        if csv_file:
            csv_file.close()


if __name__ == "__main__":
    main()


