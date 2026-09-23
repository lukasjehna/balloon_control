from gpiozero import PWMLED
import time

# Define PWM LEDs
red = PWMLED(27)
green = PWMLED(22)
blue = PWMLED(17)

def set_color(r, g, b):
    """
    r, g, b: intensity between 0 and 1
    """
    red.value = r
    green.value = g
    blue.value = b

def run_led(frequency, r, g, b):
    """
    frequency = 0  -> continuous mode
    frequency > 0  -> blinking at given Hz
    r, g, b        -> color intensities (0…1)
    """

    if frequency == 0:
        # Continuous mode
        set_color(r, g, b)
        while True:
            time.sleep(1)

    else:
        period = 1 / frequency
        on_time = period / 2
        off_time = period / 2

        while True:
            set_color(r, g, b)
            time.sleep(on_time)
            set_color(0, 0, 0)
            time.sleep(off_time)


# ===== USER INPUT =====
f = 2.0          # Hz (0 = continuous)
r = 1.0          # red intensity
g = 0.0          # green intensity
b = 1.0          # blue intensity

run_led(f, r, g, b)
