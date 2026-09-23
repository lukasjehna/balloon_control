#!/usr/bin/env python3
"""
Shared utilities for simple UDP sensor servers with optional background logging.
"""

import csv
import json
import signal
import socketserver
import threading
import time
from datetime import datetime
from pathlib import Path


DEFAULT_HOST = "0.0.0.0"
DEFAULT_LOG_INTERVAL = 13.0


class BaseLoggerState:
    """
    Base state for a UDP sensor server with background CSV logging.

    Subclasses must implement:
      - _build_filepath(self) -> Path
      - _ensure_writer(self)
      - read_once(self)  # or read_all_once for multi-sensor
    """

    def __init__(self, log_interval=None, enable_logging=False):
        self.lock = threading.Lock()
        self.log_interval = DEFAULT_LOG_INTERVAL if log_interval is None else log_interval
        self.enable_logging = enable_logging
        self.log_thread = None
        self.stop_event = threading.Event()

        # CSV setup
        self.data_dir = Path(__file__).resolve().parents[2] / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.filepath = self._build_filepath()
        self.fp = None
        self.writer = None

        if self.enable_logging and self.log_interval and self.log_interval > 0:
            self.start_logging()

    def _build_filepath(self):
        """Override in subclass to return a Path."""
        raise NotImplementedError

    def _ensure_writer(self):
        """Override in subclass to create csv writer and header if needed."""
        raise NotImplementedError

    def _log_loop(self):
        self._ensure_writer()
        while not self.stop_event.is_set():
            try:
                reading = self.read_once()
                self._write_row(reading)
            except Exception as exc:
                print(f"background logger error: {exc}", flush=True)
                time.sleep(1.0)
                continue
            time.sleep(self.log_interval)

    def _write_row(self, reading):
        """
        Override if you need custom writing (e.g., multi-row per reading).
        Default: assume dict and writer with DictWriter interface.
        """
        self.writer.writerow(reading)

    def start_logging(self):
        if self.log_thread and self.log_thread.is_alive():
            return
        if not self.log_interval or self.log_interval <= 0:
            self.log_interval = DEFAULT_LOG_INTERVAL
        self.stop_event.clear()
        self.log_thread = threading.Thread(
            target=self._log_loop, name=f"{self.__class__.__name__}Logger", daemon=True
        )
        self.log_thread.start()

    def stop_logging(self):
        self.stop_event.set()
        if self.log_thread:
            self.log_thread.join(timeout=1.0)
        if self.fp is not None:
            try:
                self.fp.close()
            except Exception:
                pass
        self.fp = None
        self.writer = None


class JsonCommandHandler(socketserver.BaseRequestHandler):
    """
    Generic handler for simple text commands over UDP.

    Expects server.state to provide:
      - read_once() or read_all_once()
      - optionally: list_ids()  (for LIST)
      - start_logging()
      - stop_logging()
    """

    def handle(self):
        data, sock = self.request
        raw = data.decode("ascii", errors="ignore").strip()
        try:
            cmd = raw.upper() if raw else "READ"
            if cmd == "PING":
                resp = b"OK PONG\n"
            elif cmd == "READ":
                # Try multi-sensor API first, then single.
                state = self.server.state
                if hasattr(state, "read_all_once"):
                    reading = state.read_all_once()
                else:
                    reading = state.read_once()
                resp = (json.dumps(reading, separators=(",", ":")) + "\n").encode("ascii")
            elif cmd == "LIST" and hasattr(self.server.state, "list_ids"):
                ids = self.server.state.list_ids()
                resp = (json.dumps({"sensors": ids}, separators=(",", ":")) + "\n").encode(
                    "ascii"
                )
            elif cmd == "START":
                self.server.state.start_logging()
                resp = b"OK LOG STARTED\n"
            elif cmd == "STOP":
                self.server.state.stop_logging()
                resp = b"OK LOG STOPPED\n"
            else:
                resp = f"ERR unknown command: {raw}\n".encode("ascii")
        except Exception as e:
            resp = f"ERR {str(e)}\n".encode("ascii")

        sock.sendto(resp, self.client_address)


class ThreadedUDPServer(socketserver.ThreadingMixIn, socketserver.UDPServer):
    daemon_threads = True
    allow_reuse_address = True


def build_timestamped_filepath(prefix: str, suffix: str) -> Path:
    data_dir = Path(__file__).resolve().parents[2] / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    start_ts = datetime.now().strftime("%Y%m%d%H%M%S")
    return data_dir / f"{start_ts}_{prefix}.{suffix}"


def install_signal_shutdown(server, state_attr: str = "state"):
    """
    Install SIGINT/SIGTERM handlers that stop logging and shut down the server.
    """

    def shutdown(signum, frame):
        state = getattr(server, state_attr, None)
        if state is not None:
            try:
                state.stop_logging()
            except Exception:
                pass
        try:
            server.shutdown()
        except Exception:
            pass

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

