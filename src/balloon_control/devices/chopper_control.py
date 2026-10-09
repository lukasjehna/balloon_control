#!/usr/bin/env python3
"""
chopper_control.py

Controls a servo on a Raspberry Pi using gpiozero.
"""
import argparse
import time
from gpiozero import AngularServo
from gpiozero.pins.pigpio import PiGPIOFactory
import os

# Configuration based on original RPi.GPIO parameters
SERVO_PIN: int = 12
MIN_ANGLE: float = 0.0
MAX_ANGLE: float = 180.0

# The original 50Hz frequency gives a 20ms period.
# A 2.5% duty cycle equals 0.5ms; a 10.5% duty cycle equals 2.1ms.
MIN_PULSE_WIDTH: float = 0.0005  
MAX_PULSE_WIDTH: float = 0.0021

def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Set servo angle between 0 and 180°")
    parser.add_argument(
        "angle", 
        type=float, 
        nargs="?", 
        default=0.0,
        help="Target angle in degrees"
    )
    parser.add_argument(
        "--smooth",
        action="store_true",
        help="Enable stepped movement to limit servo angular velocity"
    )
    return parser.parse_args()

def set_angle(servo: AngularServo, target_angle: float, smooth: bool = False) -> None:
    """
    Drives the servo to a specific angle, maintaining physical boundary limits.
    """
    # Enforce strict hardware boundaries to prevent mechanical stalling
    target_angle = max(MIN_ANGLE, min(MAX_ANGLE, target_angle))

    if smooth:
        # Resolves the pending requirement to slow down the chopper movement.
        current_angle: float = servo.angle if servo.angle is not None else MIN_ANGLE
        step: float = 1.0 if target_angle > current_angle else -1.0
        
        while abs(target_angle - current_angle) > abs(step):
            current_angle += step
            servo.angle = current_angle
            time.sleep(0.04) # 40ms delay per degree

    servo.angle = target_angle
    
    # Wait for mechanical actuation to complete.
    time.sleep(0.5)
    
    # Detach to disable the PWM signal, replacing the 0% duty cycle assignment.
    servo.detach()

def main() -> None:
    args = parse_arguments()
    
    # Force pigpio factory if available to offload PWM to DMA, reducing jitter 
    # during high-load I/O operations.
    pin_factory = PiGPIOFactory() if "PIGPIO_ADDR" in os.environ or os.path.exists("/var/run/pigpio.pid") else None
    
    servo = AngularServo(
        SERVO_PIN,
        initial_angle=None,  # Do not force a position upon initialization
        min_angle=MIN_ANGLE,
        max_angle=MAX_ANGLE,
        min_pulse_width=MIN_PULSE_WIDTH,
        max_pulse_width=MAX_PULSE_WIDTH,
        pin_factory=pin_factory
    )
    
    try:
        set_angle(servo, args.angle, smooth=args.smooth)
    finally:
        servo.close()

if __name__ == "__main__":
    main()