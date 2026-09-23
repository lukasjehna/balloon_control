#!/usr/bin/env python3
import ctypes as ct
import time
import libpcap as pcap
import struct
import numpy as np
from pathlib import Path

# pcap.config(LIBPCAP="npcap")

PKTHDR_DEFAULT = pcap.pkthdr()
PKT_DATA = ct.POINTER(ct.c_ubyte)()
PKT_HDR = ct.POINTER(pcap.pkthdr)()
PKT_HDR_REF = ct.byref(PKT_HDR)

SEQ_ADDR = b'\x1A\x2B\x3C\x4D\x5E\x6F\xFF\xFF\xFF\xFF\xFF\xFF'
SEQ_RETURN = b'\xff\xff\xff\xff\xff\xff\x1a+<M^o\xca\xfe\xb0\xba'

TIMEOUT = 1  # sec
BANDWIDTH = {'8GHz': 0b11, '4GHz': 0b10, '2GHz': 0b01, '1GHz': 0b00}
TIME_DIVIDER = {'8GHz': 0.5, '4GHz': 1, '2GHz': 2, '1GHz': 4}
PRINT_ALL = False

_i_debug = 0
_dt_debug = [-1] * 256


def b_array(seq, length=-1):
    if length == -1:
        return ct.cast(seq, ct.POINTER(ct.c_ubyte * len(seq)))[0]
    else:
        ptr_type = ct.POINTER(ct.c_ubyte * length)
        return ct.cast(PKT_DATA, ptr_type)[0]


def dt(timestamps):
    return timestamps[1:] - timestamps[:-1]


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"

#remove if it causes trouble.
def _resolve_data_path(filename):
    path = Path(filename)
    if path.is_absolute():
        return path
    # prefer project-level config/ (common layout)
    candidate = PROJECT_ROOT / path
    if candidate.exists():
        return candidate
    # fallback to data/ for bundled test data
    return DATA_DIR / path

#def _resolve_data_path(filename):
#    path = Path(filename)
#    return path if path.is_absolute() else DATA_DIR / path


def load(filename):
    path = _resolve_data_path(filename)
    with open(path, 'rb') as f:
        var = np.load(f)
    return var


def load_window_coefficients(filename):
    with open(filename, 'r') as f:
        coefficients = [int(row) for row in f.readlines()]
    return coefficients


def read_next(pd):
    global _deadtime
    perr = pcap.geterr(pd)
    if perr != b'':
        print(perr)
        raise Exception('read_next: perr')
    if pcap.next_ex(pd, PKT_HDR_REF, PKT_DATA) == 1:
        buf = b_array(PKT_DATA, PKT_HDR.contents.caplen)
        return bytes(buf[:])
    else:
        return b''


def send_packet(pd, seq):
    if pcap.sendpacket(pd, b_array(seq), 100) != 0:
        perr = pcap.geterr(pd)
        print(perr)
        raise Exception('send_packet error')


def sendread_packet(pd, seq):
    send_packet(pd, seq)
    t0 = time.time()
    read = False
    while read is False:
        buf = read_next(pd)
        if buf[0:16] == SEQ_RETURN:
            read = True
            rbuf = bytes(buf)
        if (time.time() - t0) > TIMEOUT:
            raise Exception(f'sendread_packet: timeout, Data: {read}')
    return rbuf


def save(var, filename):
    path = _resolve_data_path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'wb') as f:
        np.save(f, var)


def unpack32(buf_list, offset=16):
    data = b''.join(buf_list)
    return struct.unpack('<' + 'I' * (len(data) >> 2), data)


def unpack16(buf_list, offset=16):
    data = b''.join(buf_list)
    return struct.unpack('<' + 'H' * (len(data) >> 1), data)


class PmcBackend:
    def __init__(self, dev_name, window_coefficients_csv):
        self.ebuf = ct.create_string_buffer(pcap.PCAP_ERRBUF_SIZE)
        self.dev_name = dev_name
        self.pd = None
        self.connect()
        self.t_acc = 500  # default
        self.wind_coefficients = load_window_coefficients(window_coefficients_csv)
        self.readout_32bit = True

    def calib_gain(self):
        self.write_reg_bits(160, 5, False)  # Disable gain manual codes
        self.write_reg_bits(160, 2, True)   # Enable gain cal

    def calib_offset(self):
        self.write_reg_bits(209, 5, 0b01, 0b11)  # Disable offset manual codes
        self.write_reg_bits(209, 4, True)        # Enable offs cal

    def calib_skew(self):
        # self.write_reg_bits(210,3,0b0000,0b0000)#Disable skew manual codes:
        self.write_reg(210, 1)
        self.write_reg(210, 0b10000111)

    def calib(self, skew=False, wait_between=5e-3):
        self.calib_gain()
        time.sleep(wait_between)
        self.calib_offset()
        time.sleep(wait_between)
        if skew:
            self.calib_skew()
            time.sleep(wait_between)
        self.reset_adc()

    def calib_pll(self):
        self.write_reg_bits(327, 0, False)
        self.write_reg_bits(327, 0, True)
        time.sleep(100e-3)
        if self.read_reg(331) == 1:
            return 'PLL not locked'
        band = self.read_reg(329) & 0b1111
        ndiv = (self.read_reg(336) >> 5) & 0b111111
        return f'PLL VCO band:{band}, NDIV:{ndiv}'

    def get_pll_stat(self):
        if self.read_reg(331) == 1:
            return 'PLL not locked'
        band = self.read_reg(329) & 0b1111
        ndiv = (self.read_reg(336) >> 5) & 0b111111
        return f'PLL VCO band:{band}, NDIV:{ndiv}'

    def connect(self, alternative_mode=True):
        # Open and configure a libpcap capture handle for the spectrometer link
        # In the Windows version alternative_mode=False.
        if self.pd is not None:
            pcap.close(self.pd)  # reconnect
        if alternative_mode is False:
            self.pd = pcap.open_live(
                self.dev_name,
                65535,
                pcap.PCAP_OPENFLAG_NOCAPTURE_LOCAL
                | pcap.PCAP_OPENFLAG_MAX_RESPONSIVENESS,
                500,
                self.ebuf,
            )
            print("Opened with open_live, pd:", self.pd)
        else:
            self.pd = pcap.create(self.dev_name, self.ebuf)
            print("Created pcap handle, pd:", self.pd)
            r = pcap.set_buffer_size(self.pd, 0xFFFFF)
            print("set_buffer_size:", r)
            r = pcap.set_immediate_mode(self.pd, 1)
            print("set_immediate_mode:", r)
            r = pcap.set_timeout(self.pd, -1)  # timeout in ms
            print("set_timeout:", r)
            r = pcap.activate(self.pd)
            print("activate:", r)
            r = pcap.setnonblock(self.pd, 1, self.ebuf)
            print("setnonblock:", r)
        fcode = pcap.bpf_program()
        netmask = pcap.bpf_u_int32()
        expression = 'ether dst FF:FF:FF:FF:FF:FF and ether src 1A:2B:3C:4D:5E:6F'
        cmdbuf = expression.encode("utf-8")
        pcap.compile(self.pd, ct.byref(fcode), cmdbuf, 1, netmask)
        pcap.setfilter(self.pd, ct.byref(fcode))
        return send_packet(self.pd, SEQ_ADDR + b'\xE0\x0F')  # connect to FPGA

    def disconnect(self):
        send_packet(self.pd, SEQ_ADDR + b'\xE0\x00')
        pcap.close(self.pd)

    def write_reg(self, reg, data):
        breg = reg.to_bytes(2, byteorder='big')
        bdat = data.to_bytes(2, byteorder='big')
        seq = SEQ_ADDR + b'\x10' + breg + bdat
        sendread_packet(self.pd, seq)  # returns typically b'\x02\x08' as payload

    def write_reg_bits(self, reg, start_bit, value, bitmask=0b1):
        reg_val = self.read_reg(reg)
        mask = 0xFFFF ^ (bitmask << start_bit)
        reg_val_new = (reg_val & mask) + ((value & bitmask) << start_bit)
        self.write_reg(reg, reg_val_new)

    def write_all(self, reg_vals):
        for i, rval in enumerate(reg_vals):
            self.write_reg(i, int(rval))

    def ping(self):
        buf = sendread_packet(self.pd, SEQ_ADDR + b'\x33')
        dv_pos = buf[19] & 0b100
        cal_select = buf[19] & 0b011
        return f'ping_counter:{buf[18]},dv_pos:{dv_pos},cal_select:{cal_select}'

    def _read_reg(self, reg, words=1):
        breg = reg.to_bytes(2, byteorder='big')
        bnum = words.to_bytes(1, byteorder='big')
        seq = SEQ_ADDR + b'\x11' + breg + bnum
        buf = sendread_packet(self.pd, seq)
        return buf[16:(16 + words * 2)]

    def read_reg(self, reg):
        global _i_debug, _dt_debug
        t0 = time.time()
        buf = self._read_reg(reg, 1)
        _dt_debug[_i_debug] = (time.time() - t0) * 1000
        _i_debug = (_i_debug + 1) % 256
        return int.from_bytes(buf, byteorder='big')

    def read_all(self):
        self.regs = [self.read_reg(i) for i in range(0, 512)]
        return self.regs

    def readburst32(self):
        buff = []
        for ii in range(0, 2):
            buf = sendread_packet(
                self.pd,
                SEQ_ADDR + b'\x17' + b'\x40\x00' + b'\x20\x01',
            )
            for i in range(0, 17):
                start = i * 1024
                transfer = 1024
                if i == 16:
                    transfer = 2
                if (i == 15) & (ii == 1):
                    transfer = 1022
                if (i == 16) & (ii == 1):
                    break
                bstartreg = start.to_bytes(3, byteorder='big')
                bnum = transfer.to_bytes(2, byteorder='big')
                seq = SEQ_ADDR + b'\x18' + bstartreg + bnum
                buf = sendread_packet(self.pd, seq)
                buff.append(bytes(buf[16:16 + transfer]))
        return unpack32(buff)

    def readburst16(self):
        buff = []
        buf = sendread_packet(
            self.pd,
            SEQ_ADDR + b'\x17' + b'\x40\x00' + b'\x20\x02',
        )  # readburst+start_reg+number
        for i in range(0, 16):
            start = i * 1024
            transfer = 1024
            bstartreg = start.to_bytes(3, byteorder='big')
            bnum = transfer.to_bytes(2, byteorder='big')
            seq = SEQ_ADDR + b'\x18' + bstartreg + bnum
            buf = sendread_packet(self.pd, seq)
            buff.append(bytes(buf[16:16 + transfer]))
        return unpack16(buff)

    def readburst(self):
        self.write_reg(12, 1)
        if self.readout_32bit:
            return self.readburst32()
        else:
            return self.readburst16()

    def read_adc(self, num=8192):  # number of samples per adc, max=8192
        self.write_reg(66, 0)
        self.write_reg(66, 1)
        if (self.read_reg(67) & 0b1) != 1:
            raise Exception('read_adc: not ready')
        self.write_reg(66, 0)
        self.write_reg(66, 0x8)
        adc_raw = [self._read_reg(8192, 128) for i in range(0, int(num / 128))]
        buf_ = struct.unpack('>' + 'H' * num, b''.join(adc_raw))  # reorder bytes 1/2
        adc_buf = b''.join([b.to_bytes(2, byteorder='little') for b in buf_])  # 2/2
        adc_q_a = struct.unpack('<' + 'Q' * int(num / 4), adc_buf)
        adc_q_b = struct.unpack('<' + 'Q' * (int(num / 4) - 1), adc_buf[7:-1])

        adc_q0 = adc_q_a[0:-1:2]
        adc_q1 = adc_q_b[0::2]

        adc0, adc1 = [], []
        for i in range(0, 10):
            adc0.append([(a >> (i * 6)) & 0b111111 for a in adc_q0])
            adc1.append([(a >> (i * 6 + 4)) & 0b111111 for a in adc_q1])

        return adc0 + adc1

    def reset_adc(self):
        # not as much as button in IDE
        self.write_reg_bits(226, 0, False)  # Reset ADC
        self.write_reg_bits(238, 0, False)  # Clk Gen rst
        self.write_reg_bits(226, 0, True)   # Unreset ADC
        self.write_reg_bits(238, 0, True)   # Unreset clk gen

    def reset_eth(self):
        # not clear if it does anything at all
        send_packet(self.pd, SEQ_ADDR + b'\x32')      # reset
        time.sleep(10e-3)
        send_packet(self.pd, SEQ_ADDR + b'\x35\x00')  # set back, tx_phase=0
        time.sleep(10e-3)

    def set_window_coefficients(self):
        global t0, t1, t2
        if len(self.wind_coefficients) != 513:
            raise Exception('Wrong number of coefficients, needs to be 513')
        t0 = time.time()
        for c in self.wind_coefficients:
            self.write_reg(20, c)
            self.write_reg(22, 0b100)

    def setup_pmcc(
        self,
        allregs,
        readout_32bit=True,
        bw='4GHz',
        int_time_ms=500,
        wind_bypass=False,
        autocal=False,
    ):
        if self.read_reg(0) != 6:
            raise Exception('setup_pmcc: connection error')
        self.write_reg(1, 0b101)  # reset DSP, ->single read

        self.write_all(allregs)
        self.set_bandwidth(bw)
        print(self.calib_pll())
        if self.read_reg(331) == 1:
            raise Exception('PLL not locked')
        if autocal:
            self.calib()
        self.wind_bypass = wind_bypass
        self.readout_32bit = readout_32bit
        if readout_32bit:
            self.set_32bit()
        else:
            self.set_16bit()
        self.t_acc = int_time_ms
        self.set_accum_time(int_time_ms)
        self.reset_adc()
        if self.wind_bypass is True:
            self.dsp_wind_bypass(True)
        else:
            self.dsp_wind_bypass(False)
            self.write_reg(22, 0b1010)  # reset window coefficients, clear errors
        self.write_reg(1, 0b110)  # set continuous readout and undo DSP reset
        if self.wind_coefficients != []:
            try:
                self.set_window_coefficients()
            except Exception:
                print('set_window_coefficients hiccup')
                time.sleep(100e-3)
                self.set_window_coefficients()
        self.write_reg(2, 1)  # start accumulating

    def set_accum_time(self, t_in_ms):
        num = round(t_in_ms * 488.281 / TIME_DIVIDER[self.bw])
        msb = (num >> 8)
        lsb = (num & 0xFF)
        self.write_reg(3, msb)
        self.write_reg(4, lsb)
        self.t_acc = t_in_ms

    def meas_spectra(self, n_spectra):
        if self.read_reg(331) == 1:
            raise Exception('PLL not locked')
        self.write_reg(12, 0b10)  # flush data queue
        data, t = [], [time.time()]
        i = 0
        try:
            while i < n_spectra:
                time.sleep(20e-3)
                try:
                    while not self.data_ready():
                        time.sleep(20e-3)
                except Exception:
                    print(
                        'meas_spectra:data_ready hiccup @'
                        + time.strftime('%H:%M:%S', time.localtime())
                    )
                    time.sleep(2000e-3)
                    while not self.data_ready():
                        time.sleep(100e-3)
                if time.time() < (t[0] + self.t_acc / 1000):
                    # not enough time elapsed, data might be corrupted
                    self.write_reg(12, 0b10)  # flush data queue
                    continue
                try:
                    _data = self.readburst()
                except Exception:
                    _data = []
                if len(_data) < 8192:
                    _data = []
                if _data != []:
                    data.append(_data)
                    t.append(time.time())
                    i += 1
                else:
                    print(
                        f'spectrum lost, current index:{i}, time:'
                        + time.strftime('%H:%M:%S', time.localtime())
                    )
                    time.sleep(1000e-3)
                    self.write_reg(12, 0b10)  # flush data queue
                if i % 25 == 0:
                    print(f'{i}/{n_spectra} spectra measured')
                # self.reset_eth()
                # send_packet(self.pd, SEQ_ADDR+b'\xFF') #cleanup FPGA
        except BaseException as err:
            print(err)
        return np.array(data, dtype=object), np.array(t)

    def set_32bit(self):
        self.write_reg_bits(5, 6, 0b11, 0b11)

    def set_16bit(self):
        self.write_reg_bits(5, 6, 0b10, 0b11)

    def clear_dsp(self):
        self.write_reg_bits(12, 1, 1)

    def reset_dsp(self):
        self.write_reg(1, 0b101)  # reset DSP, DSP enable, single read

    def data_ready(self):
        # if bit 0 of reg 24 indicates readiness
        return bool(self.read_reg(24) & 0x1)

    def start_accum(self):
        self.write_reg_bits(2, 0, 1)

    def dsp_wind_bypass(self, bypass=True):
        self.write_reg_bits(28, 7, bypass)

    def set_bandwidth(self, bw):
        self.bw = bw
        self.write_reg_bits(336, 1, BANDWIDTH[bw], 0b11)

    def adc_ref(self, fsr=5):
        self.write_reg(152, fsr)

    def vga_gain(self, val=0xF):
        self.write_reg_bits(265, 4, val, 0b1111)

    def vga_peak(self, val=0):
        self.write_reg_bits(265, 0, val, 0b1111)  # lowpass thing


