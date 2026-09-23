#!/usr/bin/env python3
import argparse
import signal
import socketserver
import threading
import time
from smbus import SMBus
from pathlib import Path
import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
# Import shared hardware helpers from the sibling module in the same package
from src.devices.receiver_control import calc_f, enable_v, write_pll

# Defaults
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5002
I2C_BUS = 1  # Raspberry Pi default I2C bus

# ----------------- UDP server -----------------
class ReceiverState:
    def __init__(self, bus_num=I2C_BUS):
        self.bus = SMBus(bus_num)
        self.lock = threading.Lock()
        self.rails_enabled = False

    def program_frequency(self, f_ghz: float):
        if not (0.1 <= f_ghz <= 300.0):
            raise ValueError("frequency out of range")
        R0, R1 = calc_f(f_ghz)
        with self.lock:
            if not self.rails_enabled:
                enable_v(self.bus)
                # small settle time for rails
                time.sleep(0.02)
                self.rails_enabled = True
            write_pll(self.bus, R0, R1)
        if_mhz = (f_ghz / 256 * 1000.0)
        return R0, R1, if_mhz

class ReceiverHandler(socketserver.BaseRequestHandler):
    def handle(self):
        data, sock = self.request
        raw = data.decode("ascii", errors="ignore").strip()
        try:
            f_ghz = float(raw)
            R0, R1, if_mhz = self.server.state.program_frequency(f_ghz)
            resp = f"OK {f_ghz:.6f} GHz IF {if_mhz:.3f} MHz R0={R0} R1={R1}\n".encode("ascii")
        except Exception as e:
            resp = f"ERR {str(e)}\n".encode("ascii")
        sock.sendto(resp, self.client_address)

class ThreadedUDPServer(socketserver.ThreadingMixIn, socketserver.UDPServer):
    daemon_threads = True
    allow_reuse_address = True

def main():
    parser = argparse.ArgumentParser(description="Receiver UDP server (frequency in GHz)")
    parser.add_argument("--host", default=DEFAULT_HOST, help="bind host/interface")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="UDP port")
    parser.add_argument("--i2c-bus", type=int, default=I2C_BUS, help="I2C bus number")
    args = parser.parse_args()

    state = ReceiverState(bus_num=args.i2c_bus)
    server = ThreadedUDPServer((args.host, args.port), ReceiverHandler)
    server.state = state

    def shutdown(signum, frame):
        server.shutdown()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        try:
            state.bus.close()
        except Exception:
            pass

if __name__ == "__main__":
    main()
