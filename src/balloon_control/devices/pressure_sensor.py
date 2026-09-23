#!/usr/bin/env python3
"""
MS8607 (pressure/temperature) + HTU21D (humidity) logger.

PEP 8 naming, unified CLI, consistent CSV:
- File: {YYYYMMDDHHMMSS}_pressure.csv in project_root/data by default.
- Columns: timestamp, temperature_c, humidity_pct, pressure_mbar.
"""

import argparse
import csv
from datetime import datetime
from pathlib import Path
import time

import smbus

# I2C addresses
MS8607_ADDR = 0x76
HTU21D_ADDR = 0x40

# Registers/commands
MS8607_RESET = 0x1E
MS8607_CONV_D1_OSR256 = 0x40
MS8607_CONV_D2_OSR256 = 0x50
MS8607_ADC_READ = 0x00

HTU21D_RESET = 0xFE
HTU21D_HUMID_NOHOLD = 0xF5
DEFAULT_MEASUREMENT_INTERVAL = 13.0


def read_ms8607(bus_num: int = 1):
    """
    Read temperature (C), humidity (%), and pressure (mbar) from MS8607/HTU21D.
    Returns: (temperature_c, humidity_pct, pressure_mbar)
    """
    bus = smbus.SMBus(bus_num)

    # Reset pressure/temperature part
    bus.write_byte(MS8607_ADDR, MS8607_RESET)
    time.sleep(0.5)

    # Read calibration coefficients C1..C6
    c = []
    for cmd in (0xA2, 0xA4, 0xA6, 0xA8, 0xAA, 0xAC):
        data = bus.read_i2c_block_data(MS8607_ADDR, cmd, 2)
        c.append(data[0] * 256 + data[1])
    c1, c2, c3, c4, c5, c6 = c

    # D1 (pressure)
    bus.write_byte(MS8607_ADDR, MS8607_CONV_D1_OSR256)
    time.sleep(0.5)
    d1_bytes = bus.read_i2c_block_data(MS8607_ADDR, MS8607_ADC_READ, 3)
    d1 = d1_bytes[0] * 65536 + d1_bytes[1] * 256 + d1_bytes[2]

    # D2 (temperature)
    bus.write_byte(MS8607_ADDR, MS8607_CONV_D2_OSR256)
    time.sleep(0.5)
    d2_bytes = bus.read_i2c_block_data(MS8607_ADDR, MS8607_ADC_READ, 3)
    d2 = d2_bytes[0] * 65536 + d2_bytes[1] * 256 + d2_bytes[2]

    # First-order calculations
    d_t = d2 - c5 * 256
    temp = 2000 + d_t * c6 / 8388608  # 0.01 C
    off = c2 * 131072 + (c4 * d_t) / 64
    sens = c1 * 65536 + (c3 * d_t) / 128

    # Second-order compensation
    if temp >= 2000:
        t_i = 5 * (d_t * d_t) / 274877906944
        off_i = 0
        sens_i = 0
    else:
        t_i = 3 * (d_t * d_t) / 8589934592
        off_i = 61 * ((temp - 2000) ** 2) / 16
        sens_i = 29 * ((temp - 2000) ** 2) / 16
        if temp < -1500:
            off_i += 17 * ((temp + 1500) ** 2)
            sens_i += 9 * ((temp + 1500) ** 2)

    temp_c = (temp - t_i) / 100.0
    off2 = off - off_i
    sens2 = sens - sens_i
    pressure_pa = (((d1 * sens2) / 2097152) - off2) / 32768.0  # Pa
    pressure_mbar = pressure_pa / 100.0  # mbar

    # Humidity reset + no-hold measurement
    bus.write_byte(HTU21D_ADDR, HTU21D_RESET)
    time.sleep(0.3)
    bus.write_byte(HTU21D_ADDR, HTU21D_HUMID_NOHOLD)
    time.sleep(0.5)
    rh_msb = bus.read_byte(HTU21D_ADDR)
    rh_lsb = 0
    raw_rh = rh_msb * 256 + rh_lsb
    humidity_pct = -6.0 + (125.0 * (raw_rh / 65536.0))

    return float(temp_c), float(humidity_pct), float(pressure_mbar)


def main():
    parser = argparse.ArgumentParser(description="MS8607 pressure/temperature + HTU21D humidity logger.")
    parser.add_argument("--interval", type=float, default=DEFAULT_MEASUREMENT_INTERVAL, help="Seconds between samples.")
    parser.add_argument("--duration", type=float, default=None, help="Total seconds to run; None = until Ctrl+C.")
    parser.add_argument("--print-only", action="store_true", help="Print to console without saving CSV.")
    parser.add_argument("--data-dir", type=str, default=None, help="Optional data directory override.")
    parser.add_argument("--bus", type=int, default=1, help="I2C bus number.")
    args = parser.parse_args()

    # Data directory
    if args.data_dir:
        data_dir = Path(args.data_dir)
    else:
        data_dir = Path(__file__).resolve().parents[2] / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    start_ts = datetime.now().strftime("%Y%m%d%H%M%S")
    out_path = data_dir / f"{start_ts}_pressure.csv"

    fieldnames = ["timestamp", "temperature_c", "humidity_pct", "pressure_mbar"]
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
            temperature_c, humidity_pct, pressure_mbar = read_ms8607(bus_num=args.bus)
            row = {
                "timestamp": now_iso,
                "temperature_c": round(temperature_c, 3),
                "humidity_pct": round(humidity_pct, 3),
                "pressure_mbar": round(pressure_mbar, 3),
            }

            if writer:
                writer.writerow(row)
            print(f"{row['timestamp']} | T={row['temperature_c']} C | RH={row['humidity_pct']} % | p={row['pressure_mbar']} mbar")

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


