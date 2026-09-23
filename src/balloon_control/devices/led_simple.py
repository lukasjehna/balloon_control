from gpiozero import LED
import time

roteled = LED(27)
blueled = LED(17)
greenled = LED(22)

while True:
    greenled.on()
    blueled.on()
    time.sleep(1)
    greenled.off()
    blueled.off()
    time.sleep(1)
