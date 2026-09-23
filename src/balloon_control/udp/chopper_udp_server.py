# chopper_udp_server.py
#!/usr/bin/env python3
from pathlib import Path
import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import argparse
import signal
import socketserver
import threading
#test:
#echo "90" | nc -u 127.0.0.1 5001  
#kill udp process:
#ps aux | grep chopper_udp_server.py 
# take first number and kill -9 <PID>
from src.devices.chopper_control import (
    init_servo,
    set_angle as servo_set_angle,
    stop_servo,
    SERVO_PIN,
    PWM_FREQ,
)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5001

class ServoController:
    def __init__(self, pin=SERVO_PIN, freq=PWM_FREQ):
        self.pwm = init_servo(pin=pin, freq=freq)
        self.lock = threading.Lock()

    def set_angle(self, angle: float) -> float:
        angle = max(0.0, min(180.0, float(angle)))
        with self.lock:
            servo_set_angle(angle, self.pwm)
        return angle

    def cleanup(self):
        stop_servo(self.pwm)

class ChopperHandler(socketserver.BaseRequestHandler):
    # For UDP, self.request == (data, socket)
    def handle(self):
        data, sock = self.request
        raw = data.decode("ascii", errors="ignore").strip()
        try:
            angle = float(raw)
            if not (0.0 <= angle <= 180.0):
                raise ValueError("angle out of range")
            final_angle = self.server.servo.set_angle(angle)
            resp = f"OK {final_angle:.1f}\n".encode()
        except Exception as e:
            resp = f"ERR {str(e)}\n".encode()
        sock.sendto(resp, self.client_address)

class ThreadedUDPServer(socketserver.ThreadingMixIn, socketserver.UDPServer):
    daemon_threads = True
    allow_reuse_address = True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--pin", type=int, default=SERVO_PIN)
    parser.add_argument("--freq", type=int, default=PWM_FREQ)
    args = parser.parse_args()

    servo = ServoController(pin=args.pin, freq=args.freq)
    server = ThreadedUDPServer((args.host, args.port), ChopperHandler)
    server.servo = servo

    def shutdown(signum, frame):
        server.shutdown()
        server.server_close()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        servo.cleanup()

if __name__ == "__main__":
    main()
