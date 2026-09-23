#!/usr/bin/env python3
import RPi.GPIO as GPIO #raspberry pi general purpose input/output
import time
import argparse

#Constans
SERVO_PIN=12
PWM_FREQ=50
MIN_DUTY=2.5
MAX_DUTY=10.5

current_angle=0 # not used right now.

# Find a way to let the chopper move slower.

def parse_arguments():
    parser= argparse.ArgumentParser(description="Set servo angle between 0 and 180°")
    parser.add_argument("angle",type=float,nargs="?", default=0)
    return parser.parse_args()
    
def init_servo(pin=SERVO_PIN, freq=PWM_FREQ):
    GPIO.setmode(GPIO.BCM) #Internal broadcom numbering instead of physical numbering from the board
    GPIO.setup(pin, GPIO.OUT) #define pin as out
    pwm = GPIO.PWM(pin, PWM_FREQ) # GPIO 12 als PWM mit 50Hz
    pwm.start(0) #0% duty cycle
    return pwm  

def set_angle(angle,pwm):
    duty= MIN_DUTY + (angle / 180.0) * (MAX_DUTY-MIN_DUTY) 
    pwm.ChangeDutyCycle(duty)
    time.sleep(0.5)
    pwm.ChangeDutyCycle(0)  # set duty cycle to 0

def stop_servo(pwm):
   pwm.stop()
   GPIO.cleanup()
    
#def move_smooth(target_angle, pwm, current_angle=current_angle,step=1, delay=0.04):
#    if target_angle > current_angle:
#        angles = range(int(current_angle), int(target_angle)+1, step)
#    else:
#        angles = range(int(current_angle), int(target_angle)-1, -step)
#
#    for angle in angles:
#        duty = MIN_DUTY + (angle / 180.0) * (MAX_DUTY - MIN_DUTY)
#        pwm.ChangeDutyCycle(duty)
#        time.sleep(delay)
#
#    pwm.ChangeDutyCycle(0)
#    return target_angle

def main():
    args = parse_arguments()
    pwm=init_servo()
    try:
        set_angle(args.angle,pwm)
    finally:
        stop_servo(pwm)

if __name__ == "__main__":
    main()
