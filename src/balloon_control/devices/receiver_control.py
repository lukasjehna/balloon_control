#!/usr/bin/env python3
import smbus
import math
import argparse
from pathlib import Path

#Setting RX frequency
# - Calculation of only the first two registers (R0, R1) [the last ones to write], other registers are not affected by frequency
# - Setting of the frequency only, all other parameters as default for recevier board and recevier T415
#disconnecting data or clock cable leads to an i/o error (error 121). The rx controll still seems to function of the ground is disconnected.
#
#catch the following error:
#pi@raspberrypi:~/projects/ballon_mission/src $ python3 rx_control.py 225
#Traceback (most recent call last):
#  File "rx_control.py", line 121, in <module>
#    f=main()
#  File "rx_control.py", line 116, in main
#    enable_v(bus)
#  File "rx_control.py", line 59, in enable_v
#    bus.write_i2c_block_data(address,reg,msg) #Write I2C
#OSError: [Errno 121] Remote I/O error
channel = 1 # I2C channel 1 is connected to the GPIO pins
bus = smbus.SMBus(channel) # Initialize I2C (SMBus)

def input_freq():
    parser= argparse.ArgumentParser(description="Insert LO frequency in GHz")
    parser.add_argument("LO",type=float,nargs="?", default=225.41) #nargs="?" for an optional argument
    args=parser.parse_args()
    f=args.LO #Frequency in GHz
    return f

#Calculation of frequency registers------------------------------------------------------------
#Maybe convert string operation into bitiwse operations
def calc_f(f):
#    x1=((f/256*1000/20)-math.floor(f/256*1000/20))*33554432;
#    x2=math.floor(f/256*1000/20);
    tmp = (f* 1000) / (256*20)
    frac = tmp - math.floor(tmp)
    x1 = frac* (2**25)
    x2 = math.floor(tmp)

    R01='000'
    R02=('{:032b}'.format(int(x1))[::-1])[13:25]
    R03=('{:032b}'.format(int(x2))[::-1])[0:12]
    R04='1011'
    R05='0'
    R0str=(R01+R02+R03+R04+R05)[::-1]
    R0=[]
    for i in range(4):
        R0.append(int((R0str[i*8:(i+1)*8]),2))

    R11='100'
    R12='000000000000'
    R13=('{:032b}'.format(int(x1))[::-1])[0:13]
    R14='0'
    R15='000'
    R1str=(R11+R12+R13+R14+R15)[::-1]
    R1=[]
    for i in range(4):
        R1.append(int((R1str[i*8:(i+1)*8]),2))
    return R0, R1


#Voltage enable
def enable_v(bus):
    address = 0x25 # Voltage enable Ch1

    reg=0x06 # Configuration register
    msg=[0x00,0x00] # Set all ports to outputs
    bus.write_i2c_block_data(address,reg,msg) #Write I2C
    reg=0x02 # Set output register
    msg=[0xff,0x03] # Set first 10 outputs high
    bus.write_i2c_block_data(address,reg,msg) #Write I2C

    address = 0x23 # Voltage enable Ch2

    reg=0x06 # Configuration register
    msg=[0x00,0x00] # Set all ports to outputs
    bus.write_i2c_block_data(address,reg,msg) #Write I2C
    reg=0x02 # Set output register
    msg=[0x00,0x00] # Set all outputs low
    bus.write_i2c_block_data(address,reg,msg) #Write I2C


def write_pll(bus, R0, R1):
    address = 0x29  # PLL I2C address
    reg = 0x02      # PLL register/function ID (assumed constant for this device)

    # Static configuration sequence (HIGH → LOW register order)
    # Each element: 4 bytes for one PLL register write
    config_sequence = [
        [0x00, 0x00, 0x00, 0x07],
        [0x00, 0x80, 0x00, 0x06],
        [0x00, 0x7A, 0x12, 0x06],
        [0x00, 0xBF, 0xFE, 0x05],
        [0x00, 0x08, 0x00, 0x25],
        [0x00, 0x18, 0x00, 0xC4],
        [0x01, 0x43, 0x0C, 0xC3],
        [0x07, 0x02, 0x80, 0xF2],
    ]

    # Write static config registers
    for msg in config_sequence:
        try:
            bus.write_i2c_block_data(address, reg, msg)
        except OSError:
            print(f"I2C write failed (config): {msg}")
            return

    # Write R1 (upper-frequency register)
    try:
        bus.write_i2c_block_data(address, reg, R1)
    except OSError:
        print(f"I2C write failed: R1 = {R1}")
        return

    # Write R0 last (PLL latch trigger)
    try:
        bus.write_i2c_block_data(address, reg, R0)
    except OSError:
        print(f"I2C write failed: R0 = {R0}")
        return

def main(): 
    f=input_freq() #returns frequency in GHz
    R0,R1=calc_f(f)
    enable_v(bus)
    write_pll(bus,R0,R1)
    return f
    
if __name__=="__main__":
    f=main()
    IF_MHz = (f/256*1000) #Convert to MHz
    print(f"LO frequency: {f:f} GHz")
    print(f"IF frequency: {IF_MHz:f} MHz")


