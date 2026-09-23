#!/usr/bin/env python3
try:
    import RPi.GPIO as GPIO
except Exception:
    # Dummy fallback for non-Pi development
    class _FakeGPIO:
        BCM = 11    # same value used by real RPi.GPIO for BCM mode
        BOARD = 10  # same value used by real RPi.GPIO for BOARD mode
        OUT = 1
        IN = 0
        def setmode(self, *a, **k): pass
        def setup(self, *a, **k): pass
        def PWM(self, *a, **k):
            class _P:
                def start(self, *_): pass
                def ChangeDutyCycle(self, *_): pass
                def stop(self): pass
            return _P()
        def cleanup(self): pass
    GPIO = _FakeGPIO()
import time
import argparse
 
# =====================
# Constants
# =====================
RED_PIN = 27
GREEN_PIN = 22
BLUE_PIN = 17
PWM_FREQ = 1000   # LED PWM frequency (Hz)


# =====================
# Argument Parsing
# =====================
def parse_arguments():
    epilog = (
        "Examples:\n"
        "led_control.py 5 --red 0.2 --green 0.2 --blue 0.2"
    )
        
    parser = argparse.ArgumentParser(
        description="RGB LED control with optional blinking",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=epilog,
    )

    parser.add_argument(
        "frequency",
        type=float,
        nargs="?",
        default=0.0,
        help="Blink frequency in Hz (0 = continuous)"
    )

    parser.add_argument("--red", type=float, default=0.0,
                        help="Red intensity (0.0 – 1.0)")
    parser.add_argument("--green", type=float, default=0.0,
                        help="Green intensity (0.0 – 1.0)")
    parser.add_argument("--blue", type=float, default=0.0,
                        help="Blue intensity (0.0 – 1.0)")

    return parser.parse_args()


# =====================
# Initialization
# =====================
def init_leds():
    GPIO.setmode(GPIO.BCM)

    GPIO.setup(RED_PIN, GPIO.OUT)
    GPIO.setup(GREEN_PIN, GPIO.OUT)
    GPIO.setup(BLUE_PIN, GPIO.OUT)

    red_pwm = GPIO.PWM(RED_PIN, PWM_FREQ)
    green_pwm = GPIO.PWM(GREEN_PIN, PWM_FREQ)
    blue_pwm = GPIO.PWM(BLUE_PIN, PWM_FREQ)

    red_pwm.start(0)
    green_pwm.start(0)
    blue_pwm.start(0)

    return red_pwm, green_pwm, blue_pwm


# =====================
# LED Control
# =====================
def set_color(red_pwm, green_pwm, blue_pwm, r, g, b):
    red_pwm.ChangeDutyCycle(100 * r)
    green_pwm.ChangeDutyCycle(100 * g)
    blue_pwm.ChangeDutyCycle(100 * b)


def run_led(frequency, red_pwm, green_pwm, blue_pwm, r, g, b):
    r = max(0.0, min(1.0, r))
    g = max(0.0, min(1.0, g))
    b = max(0.0, min(1.0, b))

    if frequency == 0:
        set_color(red_pwm, green_pwm, blue_pwm, r, g, b)
        while True:
            time.sleep(1)

    else:
        period = 1.0 / frequency
        on_time = period / 2
        off_time = period / 2

        while True:
            set_color(red_pwm, green_pwm, blue_pwm, r, g, b)
            time.sleep(on_time)
            set_color(red_pwm, green_pwm, blue_pwm, 0, 0, 0)
            time.sleep(off_time)


# =====================
# Cleanup
# =====================
def cleanup(red_pwm, green_pwm, blue_pwm):
    red_pwm.stop()
    green_pwm.stop()
    blue_pwm.stop()
    GPIO.cleanup()


# =====================
# Main
# =====================
def main():
    args = parse_arguments()
    red_pwm, green_pwm, blue_pwm = init_leds()

    try:
        run_led(args.frequency,
                red_pwm, green_pwm, blue_pwm,
                args.red, args.green, args.blue)
    finally:
        cleanup(red_pwm, green_pwm, blue_pwm)


if __name__ == "__main__":
    main()


