#!/usr/bin/env python3
import csv
import os
import subprocess
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"


def _run(cmd):
    out = subprocess.check_output(cmd)
    return out.decode("utf-8").strip()


def read_cpu_temp_degC():
    # /sys/class/thermal/thermal_zone0/temp gives millidegrees Celsius. [web:10]
    with open("/sys/class/thermal/thermal_zone0/temp", "r", encoding="utf-8") as f:
        milli = int(f.read().strip())
    return milli / 1000.0


def read_passive_state():
    # thermal_zone0/passive is 0/1 depending on passive cooling trigger. [web:13]
    path = "/sys/class/thermal/thermal_zone0/passive"
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return int(f.read().strip())


def read_pmic_temp_degC():
    # Example output: b"temp=39.5'C\n" -> 39.5. [web:4]
    raw = _run(["vcgencmd", "measure_temp", "pmic"])
    # raw like "temp=39.5'C"
    val = raw.split("=")[1].split("'")[0]
    return float(val)


def read_core_voltage_V():
    # Example output: "volt=0.8600V". [web:20]
    raw = _run(["vcgencmd", "measure_volts", "core"])
    val = raw.split("=")[1].split("V")[0]
    return float(val)

def read_throttled():
    # Example output: "throttled=0x0". [web:20]
    raw = _run(["vcgencmd", "get_throttled"])
    val = raw.split("=")[1]
    return val

def get_timestamp_str():
    # YYYYMMDDHHMMSS
    return datetime.utcnow().strftime("%Y%m%d%H%M%S")


def get_csv_path(ts_str):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fname = f"{ts_str}_system_telemetry.csv"
    return DATA_DIR / fname


def write_telemetry_row(ts_str, cpu_temp, pmic_temp, passive_state, core_voltage,throttled):
    """
    Adjust the fieldnames/order to match src/temperature_sensor.py.
    For example, if that module uses a header row, reuse the same here.
    """
    path = get_csv_path(ts_str)

    # Example header; change to whatever temperature_sensor.py uses.
    fieldnames = [
        "timestamp_utc",
        "cpu_temp_degC",
        "pmic_temp_degC",
        "passive_state",
        "core_voltage_V",
        "throttled",
    ]

    new_file = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if new_file:
            writer.writeheader()
        writer.writerow(
            {
                "timestamp_utc": ts_str,
                "cpu_temp_degC": f"{cpu_temp:.3f}",
                "pmic_temp_degC": f"{pmic_temp:.3f}",
                "passive_state": passive_state if passive_state is not None else "",
                "core_voltage_V": f"{core_voltage:.4f}",
                "throttled": throttled
            }
        )


def measure_and_log_once():
    ts_str = get_timestamp_str()
    cpu_temp = read_cpu_temp_degC()
    pmic_temp = read_pmic_temp_degC()
    passive_state = read_passive_state()
    core_voltage = read_core_voltage_V()
    throttled = read_throttled()
    write_telemetry_row(ts_str, cpu_temp, pmic_temp, passive_state, core_voltage, throttled)


if __name__ == "__main__":
    measure_and_log_once()

