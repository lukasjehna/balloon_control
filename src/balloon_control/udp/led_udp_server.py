#!/usr/bin/env python3
import argparse
import threading
import time
from pathlib import Path
import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from src.udp.udp_utility import ThreadedUDPServer, DEFAULT_HOST, install_signal_shutdown
import socketserver

import RPi.GPIO as GPIO


# ======================
# LED hardware constants
# run this script and execute form another bash
# echo ready into netcat in udp mode, to test it.
# echo READY | nc -u 127.0.0.1 5008    
# ======================

RED_PIN = 27
GREEN_PIN = 22
BLUE_PIN = 17
PWM_FREQ = 1000

DEFAULT_PORT = 5008


# ======================
# LED Controller
# ======================

class LEDController:

    def __init__(self):
        GPIO.setmode(GPIO.BCM)

        GPIO.setup(RED_PIN, GPIO.OUT)
        GPIO.setup(GREEN_PIN, GPIO.OUT)
        GPIO.setup(BLUE_PIN, GPIO.OUT)

        self.red = GPIO.PWM(RED_PIN, PWM_FREQ)
        self.green = GPIO.PWM(GREEN_PIN, PWM_FREQ)
        self.blue = GPIO.PWM(BLUE_PIN, PWM_FREQ)

        self.red.start(0)
        self.green.start(0)
        self.blue.start(0)

        self.lock = threading.Lock()

        self.thread = None
        self.stop_event = threading.Event()

    def _set_color(self, r, g, b):
        self.red.ChangeDutyCycle(100 * r)
        self.green.ChangeDutyCycle(100 * g)
        self.blue.ChangeDutyCycle(100 * b)

    def _run_pattern(self, pattern):
        while not self.stop_event.is_set():

            if pattern == "blue_pulse":
                for x in range(0, 100, 5):
                    self._set_color(0, 0, x/100)
                    time.sleep(0.05)
                for x in range(100, 0, -5):
                    self._set_color(0, 0, x/100)
                    time.sleep(0.05)

            elif pattern == "green_solid":
                self._set_color(0,1,0)
                time.sleep(1)

            elif pattern == "green_blink":
                self._set_color(0,1,0)
                time.sleep(1)
                self._set_color(0,0,0)
                time.sleep(1)

            elif pattern == "yellow_blink":
                self._set_color(1,1,0)
                time.sleep(1)
                self._set_color(0,0,0)
                time.sleep(1)

            elif pattern == "red_solid":
                self._set_color(1,0,0)
                time.sleep(1)

            elif pattern == "red_fast":
                self._set_color(1,0,0)
                time.sleep(0.2)
                self._set_color(0,0,0)
                time.sleep(0.2)

    def set_pattern(self, pattern):

        with self.lock:

            self.stop_event.set()

            if self.thread:
                self.thread.join(timeout=0.5)

            self.stop_event.clear()

            self.thread = threading.Thread(
                target=self._run_pattern,
                args=(pattern,),
                daemon=True
            )

            self.thread.start()

    def cleanup(self):
        self.stop_event.set()

        if self.thread:
            self.thread.join(timeout=0.5)

        self.red.stop()
        self.green.stop()
        self.blue.stop()

        GPIO.cleanup()


# ======================
# UDP Handler
# ======================

class LEDHandler(socketserver.BaseRequestHandler):

    def handle(self):

        data, sock = self.request
        raw = data.decode("ascii", errors="ignore").strip().upper()

        try:

            mapping = {
                "BOOT": "blue_pulse",
                "READY": "green_solid",
                "RUN": "green_blink",
                "IDLE": "yellow_blink",
                "FATAL": "red_solid",
                "FAIL": "red_fast"
            }

            if raw not in mapping:
                raise ValueError("unknown command")

            pattern = mapping[raw]

            self.server.led.set_pattern(pattern)

            resp = f"OK {pattern}\n".encode()

        except Exception as e:
            resp = f"ERR {str(e)}\n".encode()

        sock.sendto(resp, self.client_address)


# ======================
# Main
# ======================

def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)

    args = parser.parse_args()

    led = LEDController()

    server = ThreadedUDPServer((args.host, args.port), LEDHandler)
    server.led = led

    install_signal_shutdown(server)

    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        led.cleanup()


if __name__ == "__main__":
    main()


