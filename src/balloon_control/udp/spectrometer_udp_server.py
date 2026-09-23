#!/usr/bin/env python3
import sys
import argparse
import json
import os
import signal
import socketserver
import struct
import threading
import time
import shlex
from datetime import datetime
from pathlib import Path
from typing import Optional
import traceback
import sdnotify

# ensure project root is on sys.path so "import src.devices..." works when running the script directly
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))



import src.devices.spectrometer_backend as pmc_backend
from src.utility.verbose_utils import set_verbose, vprint
CONFIG = PROJECT_ROOT / "config" / "allregs.bin"

REGS = pmc_backend.load(CONFIG)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5005
DEFAULT_DEV = "eth0"
DEFAULT_COEFF = PROJECT_ROOT / "config" / "wind_coeff_hamm.csv"


def _ts():
    return datetime.now().strftime("%Y%m%d%H%M%S")


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def _ok(payload):
    return (
        json.dumps({"status": "ok", **payload}, separators=(",", ":")) + "\n"
    ).encode("ascii")


def _err(msg):
    return (
        json.dumps({"status": "err", "error": str(msg)}, separators=(",", ":")) + "\n"
    ).encode("ascii")

def build_parser() -> argparse.ArgumentParser:
    epilog = (
        "Examples:\n"
        "Quick UDP test from bash: echo \"PING\" | nc -u -w1 127.0.0.1 5005\n"
        "quick tests: bash  echo \"PING\" | nc -u -w1 127.0.0.1 5005\n"
        "Alternative test commands: CONN INIT 2GHz 500  MEAS 5 /tmp HOTCOLD 5 /tmp hot"
    )  
    parser = argparse.ArgumentParser(
        description="Spectrometer UDP server (PmcBackend)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=epilog,
    )

    parser.add_argument("--host", default=DEFAULT_HOST, help="bind host/interface")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="UDP port")
    parser.add_argument("--dev", default=DEFAULT_DEV, help="device name (e.g. eth0)")
    parser.add_argument("--coeff", default=DEFAULT_COEFF, help="window coefficients csv")
    parser.add_argument("-v", "--verbose", action="store_true", help="enable verbose diagnostic output")
    return parser

def parse_args(argv=None):
    parser = build_parser()
    return parser.parse_args(argv)

class SpectrometerState:
    def __init__(self, dev_name=DEFAULT_DEV, window_coefficients_csv=DEFAULT_COEFF):
        self.lock = threading.Lock()
        self.dev_name = dev_name.encode("ascii") if isinstance(dev_name, str) else dev_name
        self.window_coefficients_csv = window_coefficients_csv
        self.pmc = pmc_backend.PmcBackend(
            self.dev_name,
            window_coefficients_csv=self.window_coefficients_csv,
        )

    def connect(self):
        with self.lock:
            self.pmc = pmc_backend.PmcBackend(
                self.dev_name,
                window_coefficients_csv=self.window_coefficients_csv,
            )
        return {"message": "Recreated backend and reopened spectrometer link"}

    def init(self, bandwidth: str, int_time_ms: int):
        last_exc = None
        for attempt in range(5):
            try:
                with self.lock:
                    self.pmc = pmc_backend.PmcBackend(
                        self.dev_name,
                        window_coefficients_csv=self.window_coefficients_csv,
                    )
                    self.pmc.setup_pmcc(
                        REGS,
                        bandwidth=bandwidth,
                        int_time_ms=int(int_time_ms),
                    )
                return {
                    "message": "initialized",
                    "bandwidth": bandwidth,
                    "int_time_ms": int(int_time_ms),
                }
            except Exception as exc:
                last_exc = exc
                time.sleep(1.5)
        raise last_exc



    def read_adc(self, out_dir: str, num_samples: int = 8192):
        """
        Reads ADC samples from backend (num_samples) and writes a text file with one sample per line.
        backend.read_adc returns list-of-lists (adc channels), so we flatten or store per-channel.
        """
        ts = _ts()
        out_path = Path(out_dir)
        _ensure_dir(out_path)
        fn = out_path / f"{ts}_adc.txt"
        with self.lock:
            adc = self.pmc.read_adc(int(num_samples))
        # adc likely returns list-of-lists (adc0..adcn); write as csv-like: channel, index, value
        with open(fn, "w", encoding="ascii") as f:
            # write a small header
            f.write(f"# adc dump timestamp={_ts()}, samples={num_samples}\n")
            # if adc is a list of channel lists:
            if isinstance(adc, (list, tuple)):
                nch = len(adc)
                lengths = [len(ch) for ch in adc]
                f.write(f"# channels={nch}, lengths={lengths}\n")
                for ch_idx, ch in enumerate(adc):
                    for i, val in enumerate(ch):
                        f.write(f"{ch_idx},{i},{int(val)}\n")
            else:
                # fallback: write raw str repr
                f.write(repr(adc) + "\n")
        return {"file": str(fn), "num_samples": num_samples}

    def measure(self, n_spectra: int, out_dir: str):
        out_path = Path(out_dir)
        _ensure_dir(out_path)
        ts = _ts()
        fn = out_path / f"{ts}.spec"
        with self.lock:
            d, t = self.pmc.meas_spectra(int(n_spectra))
            t_acc = getattr(self.pmc, "t_acc", None)
            bw = getattr(self.pmc, "bw", None)
        # write file: human header, then big-endian doubles for t, then big-endian unsigned longs per spectrum
        with open(fn, "wb") as f:
            header = (
                f"number of spectra: {len(d)}, "
                f"integration time: {t_acc}ms, bandwidth: {bw}\n"
            )
            f.write(header.encode("ascii"))
            # pack times (floats) as big-endian doubles
            f.write(struct.pack(">" + "d" * len(t), *t))
            for d_ in d:
                # ensure d_ is iterable of ints
                f.write(struct.pack(">" + "l" * len(d_), *[int(x) for x in d_]))
        return {
            "file": str(fn),
            "n_spectra": len(d),
            "int_time_ms": t_acc,
            "bandwidth": bw,
        }

    def write_header(
        self,
        out_dir: str,
        n_spectra: Optional[int] = None,
        f_rx_ghz: Optional[float] = None,
        bw_override: Optional[str] = None,
        n_iterations: Optional[int] = None,
        int_ms_override: Optional[int] = None,
    ):
        out_path = Path(out_dir)
        _ensure_dir(out_path)
        ts = _ts()
        fn = out_path / f"{ts}_pi_lab_header.csv"

        # Read defaults from backend (if available)
        with self.lock:
            t_acc = getattr(self.pmc, "t_acc", None)
            bw = getattr(self.pmc, "bw", None)

        # Prefer explicit values when provided
        if int_ms_override is not None:
            int_time_ms = int(int_ms_override)
        else:
            int_time_ms = int(t_acc) if t_acc is not None else None

        if bw_override is not None:
            bw_val = bw_override
        else:
            bw_val = bw

        with open(fn, "w", encoding="utf-8") as f:
            f.write("key,value\n")
            if f_rx_ghz is not None:
                f.write(f"f_RX,{f_rx_ghz:.6f}GHz\n")
            if bw_val is not None:
                f.write(f"bandwidth,{bw_val}\n")
            if n_iterations is not None:
                f.write(f"n_iterations,{int(n_iterations)}\n")
            if int_time_ms is not None:
                f.write(f"integration_time_ms,{int_time_ms}ms\n")
            if n_spectra is not None:
                f.write(f"n_spectra,{int(n_spectra)}\n")

        return {
            "file": str(fn),
            "int_time_ms": int_time_ms,
            "bandwidth": bw_val,
            "n_spectra": n_spectra,
            "f_rx_ghz": f_rx_ghz,
            "n_iterations": n_iterations,
        }
   
    def create_dir(self, out_root: str):
        """
        Create a new subdirectory inside out_root with the current timestamp
        as its name, e.g. <out_root>/20250814151100.
        """
        session_ts = _ts()
        session_dir = Path(out_root) / session_ts
        _ensure_dir(session_dir)
        return {
            "session_dir": str(session_dir),
            "timestamp": session_ts,
        }

    def hot_cold(self, n_spectra: int, out_dir: str, tag: str):
        """
        Perform a single hot OR cold measurement.
        <timestamp><tag>.spec into out_dir, where tag is 'hot' or 'cold'.
        """
        tag = tag.lower()
        if tag not in ("hot", "cold"):
            raise ValueError("tag must be 'hot' or 'cold'")

        out_path = Path(out_dir)
        _ensure_dir(out_path)

        meas_ts = _ts()
        fn = out_path / f"{meas_ts}{tag}.spec"

        with self.lock:
            d, t = self.pmc.meas_spectra(int(n_spectra))
            t_acc = getattr(self.pmc, "t_acc", None)
            bw = getattr(self.pmc, "bw", None)

        with open(fn, "wb") as f:
            header = (
                f"tag: {tag}, "
                f"number of spectra: {len(d)}, "
                f"integration time: {t_acc}ms, bandwidth: {bw}\n"
            )
            f.write(header.encode("ascii"))
            f.write(struct.pack(">" + "d" * len(t), *t))
            for d_ in d:
                f.write(
                    struct.pack(
                        ">" + "L" * len(d_),
                        *[int(x) for x in d_],
                    )
                )

        return {
            "file": str(fn),
            "tag": tag,
            "n_spectra": len(d),
            "int_time_ms": t_acc,
            "bandwidth": bw,
        }
class SpectrometerHandler(socketserver.BaseRequestHandler):
    server: socketserver.BaseServer
    # UDP: request == (data, socket)
    def handle(self):
        data, sock = self.request
        raw = data.decode("ascii", errors="ignore").strip()
        try:
            parts = shlex.split(raw) if raw else []
        except Exception:
            parts = raw.split() if raw else []
        cmd = parts[0].upper() if parts else "PING"
        args = parts[1:] if len(parts) > 1 else []

        try:
            if cmd == "PING":
                result = {"message": "PONG", "ts": _ts()}
                resp = _ok(result)

            elif cmd in ("CONN", "CONNECT"):
                result = self.server.state.connect()
                resp = _ok(result)

            elif cmd == "INIT":
                # INIT <bandwidth> <int_time_ms>
                if len(args) < 2:
                    raise ValueError("usage: INIT <bandwidth> <int_time_ms>")
                bandwidth = args[0]
                int_time_ms = int(args[1])
                result = self.server.state.init(bandwidth, int_time_ms)
                resp = _ok(result)

            elif cmd == "MEAS":
                # MEAS <n_spectra> <out_dir>
                if len(args) < 2:
                    raise ValueError("usage: MEAS <n_spectra> <out_dir>")
                n_spec = int(args[0])
                out_dir = args[1]
                result = self.server.state.measure(n_spec, out_dir)
                resp = _ok(result)

            elif cmd in ("TEMP", "HOTCOLD"):
                # HOTCOLD <n_spectra> <out_dir> <tag>
                if len(args) < 3:
                    raise ValueError("usage: HOTCOLD <n_spectra> <out_dir> <tag>")
                n_spec = int(args[0])
                out_dir = args[1]
                tag = str(args[2])
                result = self.server.state.hot_cold(n_spec, out_dir, tag)
                resp = _ok(result)

            elif cmd in ("ADC", "ADC_"):
                # ADC <out_dir> [num_samples]
                if len(args) < 1:
                    raise ValueError("usage: ADC <out_dir> [num_samples]")
                out_dir = args[0]
                num_samples = int(args[1]) if len(args) > 1 else 8192
                result = self.server.state.read_adc(out_dir, num_samples)
                resp = _ok(result)

            elif cmd == "HEAD":
                # HEAD <out_dir> [n_spectra] [f_rx_ghz] [bw] [n_iterations] [int_ms]
                if len(args) < 1:
                    raise ValueError(
                        "usage: HEAD <out_dir> [n_spectra] [f_rx_ghz] [bw] [n_iterations] [int_ms]"
                    )

                out_dir = args[0]
                n_spectra = int(args[1]) if len(args) > 1 and args[1] != "None" else None
                f_rx_ghz = float(args[2]) if len(args) > 2 and args[2] != "None" else None
                bw_arg = args[3] if len(args) > 3 and args[3] != "None" else None
                n_iter = int(args[4]) if len(args) > 4 and args[4] != "None" else None
                int_ms = int(args[5]) if len(args) > 5 and args[5] != "None" else None

                result = self.server.state.write_header(
                    out_dir,
                    n_spectra=n_spectra,
                    f_rx_ghz=f_rx_ghz,
                    bw_override=bw_arg,
                    n_iterations=n_iter,
                    int_ms_override=int_ms,
                )
                resp = _ok(result)

            elif cmd in ("DIR", "DIR_"):
                # DIR <out_root>
                if len(args) < 1:
                    raise ValueError("usage: DIR <out_root>")
                out_root = args[0]
                result = self.server.state.create_dir(out_root)
                resp = _ok(result)

            else:
                resp = _err(f"unknown command: {raw}")

        except Exception as exc:
            print(f"Spectrometer command failed: cmd={cmd}, args={args}, error={exc}", flush=True)
            traceback.print_exc()
            resp = _err(exc)
        
        sock.sendto(resp, self.client_address)

class ThreadedUDPServer(socketserver.ThreadingMixIn, socketserver.UDPServer):
    daemon_threads = True
    allow_reuse_address = True
    # inform the type checker that instances will have a `state`
    state: Optional["SpectrometerState"] = None


def main(argv=None):
    args = parse_args(argv)

    server = ThreadedUDPServer((args.host, args.port), SpectrometerHandler)
    try:
        server.state = SpectrometerState(
            dev_name=args.dev,
            window_coefficients_csv=args.coeff,
        )
    except Exception as exc:
        print(f"Failed to initialize spectrometer state: {exc}",flush=True)
        traceback.print_exc()
        raise
        
    # lightweight readiness probe
    with server.state.lock:
        _ = server.state.pmc.read_reg(0)
        
    # send signal to systemd /etc/systemd/system/balloon-udp-spectrometer.service
    n = sdnotify.SystemdNotifier()
    n.notify("READY=1")

    def shutdown(_signum, _frame):
        try:
            # call shutdown from a different thread to avoid deadlock
            threading.Thread(target=server.shutdown, daemon=True).start()
        except Exception:
            pass

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    server.serve_forever(poll_interval=0.5)


if __name__ == "__main__":
    main()

