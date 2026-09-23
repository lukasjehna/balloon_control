#!/usr/bin/env python3
"""
DS18B20 1-Wire temperature logger.

PEP 8 naming, unified CLI, consistent CSV:
- File: {YYYYMMDDHHMMSS}_temperature.csv in project_root/data by default.
- Columns: timestamp, <sensor_id>_temp_C for each detected sensor.
- One row per timestamp with one column per sensor.
"""

import argparse
import csv
from pathlib import Path
import time
import glob
import os
from datetime import datetime

BASE_DIR = "/sys/bus/w1/devices"
DEFAULT_MEASUREMENT_INTERVAL = 13.0


def find_sensors() -> dict:
    paths = sorted(glob.glob(os.path.join(BASE_DIR, "28-*")))
    if not paths:
        raise RuntimeError("No 1-Wire temperature sensors found.")
    return {os.path.basename(p): os.path.join(p, "w1_slave") for p in paths}


def _read_raw(device_file: str):
    with open(device_file, "r") as f:
        return f.readlines()


def read_temperature_c(device_file: str, max_retries: int = 10, retry_delay: float = 0.2):
    for _ in range(max_retries):
        lines = _read_raw(device_file)
        if lines and lines[0].strip().endswith("YES"):
            pos = lines[1].find("t=")
            if pos != -1:
                try:
                    return float(lines[1][pos + 2:]) / 1000.0
                except ValueError:
                    pass
        time.sleep(retry_delay)
    return None


def main():
    parser = argparse.ArgumentParser(description="DS18B20 temperature logger (all detected sensors).")
    parser.add_argument("--interval", type=float, default=DEFAULT_MEASUREMENT_INTERVAL, help="Seconds between samples.")
    parser.add_argument("--duration", type=float, default=None, help="Total seconds to run; None = until Ctrl+C.")
    parser.add_argument("--print-only", action="store_true", help="Print to console without saving CSV.")
    parser.add_argument("--data-dir", type=str, default=None, help="Optional data directory override.")
    args = parser.parse_args()

    if args.data_dir:
        data_dir = Path(args.data_dir)
    else:
        data_dir = Path(__file__).resolve().parents[2] / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    start_ts = datetime.now().strftime("%Y%m%d%H%M%S")
    out_path = data_dir / f"{start_ts}_temperature.csv"

    try:
        sensors = find_sensors()
    except RuntimeError as e:
        print(str(e))
        return

    sensor_ids = sorted(sensors.keys())
    fieldnames = ["timestamp"] + [f"{sensor_id}_temp_C" for sensor_id in sensor_ids]

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
            now_iso = datetime.now().isoformat(timespec="seconds")
            row = {"timestamp": now_iso}
            line_parts = []

            for sensor_id in sensor_ids:
                temp_c = read_temperature_c(sensors[sensor_id])
                column_name = f"{sensor_id}_temp_C"

                if temp_c is None:
                    row[column_name] = ""
                    line_parts.append(f"{sensor_id}: NaN")
                else:
                    row[column_name] = f"{temp_c:.3f}"
                    line_parts.append(f"{sensor_id}: {temp_c:.3f} C")

            if writer:
                writer.writerow(row)

            print(f"{now_iso} | " + " | ".join(line_parts))

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
