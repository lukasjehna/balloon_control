import socket
import time
import os
import sys
import signal
import json
import argparse
import numpy as np
sys.path.append(os.path.join(os.path.dirname(__file__), 'src')) # Add src/ to path
from devices import led_control
os.umask(0o000) #no default restriction for files

chopper=5001
receiver=5002
gyro=5003
pressure=5004
spectrometer=5005
temperature=5006
telemetry=5007
SOCKET_TYPE={'UDP':socket.SOCK_DGRAM,'TCP':socket.SOCK_STREAM}
TIMEOUT = 10
SPECTROMETER_TIMEOUT = 30
IP= '127.0.0.1'

DEFAULT_F_RX_GHZ_LIST = [235.960]
DEFAULT_BW = "2GHz"
DEFAULT_INT_MS = 500
DEFAULT_N_SPECTRA = 20
DEFAULT_N_ITERATIONS = 90 # 4000
DEFAULT_SETTLE_TIME_S = 2.1
DEFAULT_OUT_DIR = "data/"

ports = {
    chopper: "chopper",
    receiver: "receiver",
    gyro: "gyro",
    pressure: "pressure",
    spectrometer: "spectrometer",
    temperature: "temperature",
    telemetry: "telemetry",
}

# Global flag set by Ctrl+C
_stop_requested = False
#print("To use main.py directly without systemd start the udp-servers directly with start_udp_servers.sh.")
def _sigint_handler(signum, frame):
    """
    Signal handler for SIGINT (Ctrl+C).
    It does NOT abort the program immediately, but asks the
    hot/cold loop to finish the current iteration and then stop.
    """
    global _stop_requested
    print("Ctrl+C detected: will stop after the current hot/cold cycle.")
    _stop_requested = True

class UdpCommandError(RuntimeError):
    pass


def _cmd_preview(command, max_len=120):
    try:
        s = command.decode("utf-8", errors="replace").strip()
    except Exception:
        s = repr(command)
    return s if len(s) <= max_len else s[:max_len] + "..."


def cmd(port, command, ip=IP, noansw=0, answerTerminated=True, packetlen=1024,
        timeout=TIMEOUT, socketType='UDP'):
    try:
        pname = ports.get(port, str(port))
    except Exception:
        pname = str(port)

    cmd_preview = _cmd_preview(command)
    proto = SOCKET_TYPE.get(socketType, socket.SOCK_DGRAM)
    answ = b''

    with socket.socket(socket.AF_INET, proto) as s:
        s.settimeout(timeout)

        try:
            if socketType == 'UDP':
                s.sendto(command, (ip, port))
            else:
                s.connect((ip, port))
                s.sendall(command)
        except Exception as exc:
            raise UdpCommandError(
                f"cmd send error to {pname}({port}) cmd='{cmd_preview}': {exc}"
            ) from exc

        if noansw:
            return b''

        try:
            data = s.recv(packetlen)
            if not data:
                raise UdpCommandError(
                    f"empty reply from {pname}({port}) cmd='{cmd_preview}'"
                )
            answ += data

            if answerTerminated:
                while answ and answ[-1] != 10:
                    try:
                        data = s.recv(packetlen)
                        if not data:
                            raise UdpCommandError(
                                f"incomplete reply from {pname}({port}) "
                                f"cmd='{cmd_preview}', received={answ!r}"
                            )
                        answ += data
                    except socket.timeout as exc:
                        raise UdpCommandError(
                            f"incomplete terminated reply from {pname}({port}) "
                            f"cmd='{cmd_preview}', received={answ!r}"
                        ) from exc
            else:
                while len(answ) < packetlen:
                    try:
                        data = s.recv(packetlen - len(answ))
                        if not data:
                            break
                        answ += data
                    except socket.timeout:
                        break

        except socket.timeout as exc:
            raise UdpCommandError(
                f"socket timeout on {pname}({port}) cmd='{cmd_preview}', received={answ!r}"
            ) from exc
        except UdpCommandError:
            raise
        except Exception as exc:
            raise UdpCommandError(
                f"cmd recv error from {pname}({port}) cmd='{cmd_preview}': {exc}"
            ) from exc

    try:
        txt = answ.decode("utf-8", errors="replace").strip()
        if txt.startswith("{"):
            payload = json.loads(txt)
            if isinstance(payload, dict) and payload.get("status") == "err":
                raise UdpCommandError(
                    f"server error from {pname}({port}) cmd='{cmd_preview}': "
                    f"{payload.get('error', payload)}"
                )
    except json.JSONDecodeError:
        pass

    return answ



def chopper_set(angle):
    # Reuse your cmd() with socketType='UDP'
    return cmd(chopper, f"{angle:.1f}\n".encode(), socketType='UDP')

def receiver_set(f):
    # Reuse your cmd() with socketType='UDP'
    return cmd(receiver, f"{f:.1f}\n".encode(), socketType='UDP')

def gyro_start_continuous():
    return cmd(gyro, b"START\n", socketType='UDP')

def gyro_stop_continuous():
    return cmd(gyro, b"STOP\n", socketType='UDP')

def gyro_read():
    # Ask the gyro UDP server for a one-shot reading. 
    return cmd(gyro, b"READ\n", socketType='UDP')

def pressure_read():
    # Ask the pressure UDP server for a one-shot reading. 
    return cmd(pressure, b"READ\n", socketType='UDP')

def pressure_start_continuous():
    return cmd(pressure, b"START\n", socketType='UDP')

def pressure_stop_continuous():
    return cmd(pressure, b"STOP\n", socketType='UDP')

def temperature_read():
    # Ask the pressure UDP server for a one-shot reading. 
    return cmd(temperature, b"READ\n", socketType='UDP')

def temperature_start_continuous():
    return cmd(temperature, b"START\n", socketType='UDP')

def temperature_stop_continuous():
    return cmd(temperature, b"STOP\n", socketType='UDP')

def read_telemetry():
    raw = cmd(telemetry, b"READ\n")
    # Expecting a JSON line like {"timestamp": "...", "cpu_temp_c": ..., ...}\n
    return json.loads(raw.decode("ascii"))


def start_continuous_telemetry():
    """
    Tell the system telemetry server to start background CSV logging.
    """
    cmd(telemetry, b"START\n", noansw=1)


def stop_continuous_telemetry():
    """
    Tell the system telemetry server to stop background CSV logging.
    """
    cmd(telemetry, b"STOP\n", noansw=1)

def spectrometer_control(buf, timeout=SPECTROMETER_TIMEOUT): 
    return cmd(spectrometer,buf.encode('utf-8'), timeout=timeout, socketType='UDP')
#buf message form:
#INIT 2 GHz 500

def spectrometer_connect():
    return spectrometer_control("CONN")

def spectrometer_init(bw="2GHz", int_ms=500):
    return spectrometer_control(f"INIT {bw} {int_ms}")

def spectrometer_adc(out_dir="data/"):
    return spectrometer_control(f"ADC {out_dir}")

def spectrometer_meas(n_spectra=1, out_dir="data/"):
    return spectrometer_control(f"MEAS {n_spectra} {out_dir}")

def spectrometer_meas_repeated(n_cycles=1, n_spectra_per_per_cycle=1, out_dir="data/", wait_s=1.0):
    for i in range(n_cycles):
        spectrometer_meas(n_spectra=n_spectra_per_per_cycle, out_dir=out_dir)
        if _stop_requested:
            print("Stop requested, ending spectromter_meas_repeated loop.")
            print("Stop requested, ending spectrometer_meas_repeated loop.")

        if i < n_cycles - 1:
            time.sleep(wait_s)

def spectrometer_create_timestamp_dir(out_root="data/"):
    return spectrometer_control(f"DIR {out_root}")

def spectrometer_write_header(
    out_dir,
    f_rx_ghz,
    bw,
    n_iterations,
    int_ms,
    n_spectra=None,
):
    """
    Ask the spectrometer server to write a header CSV into out_dir
    containing f_RX, bandwidth, n_iterations, integration time, and n_spectra.
    """
    parts = [f"HEAD {out_dir}"]
    # Number of spectra per iteration
    if n_spectra is not None:
        parts.append(str(int(n_spectra)))
    else:
        parts.append("None")

    # f_rx_ghz, bw, n_iterations, int_ms
    parts.append(f"{float(f_rx_ghz):.6f}")
    parts.append(str(bw))
    parts.append(str(int(n_iterations)))
    parts.append(str(int(int_ms)))

    cmd_str = " ".join(parts)
    return spectrometer_control(cmd_str)

def spectrometer_hot_cold(n_spectra, out_dir, tag):
    tag = str(tag).lower()
    return spectrometer_control(f"HOTCOLD {int(n_spectra)} {out_dir} {tag}")

def generate_linear_scan(start_ghz=225, stop_ghz=255, step_ghz=0.5):
    return np.arange(start_ghz, stop_ghz + step_ghz / 2, step_ghz).round(6).tolist()

def generate_center_scan(center_ghz=235.71, start_ghz=0.01, step_ghz=0.01, points_per_sideband=20):
    usb = [round(center_ghz - start_ghz - i * step_ghz, 6)
           for i in range(points_per_sideband)]
    lsb = [round(center_ghz + start_ghz + i * step_ghz, 6)
           for i in range(points_per_sideband)]
    return usb + lsb

def start_background_measurements():
    print("Starting background measurements (gyro, pressure, temperature, telemetry).")
    gyro_start_continuous()
    pressure_start_continuous()
    temperature_start_continuous()
    start_continuous_telemetry()

def stop_background_measurements():
    print("Stopping background measurements (gyro, pressure, temperature, telemetry).")
    gyro_stop_continuous()
    pressure_stop_continuous()
    temperature_stop_continuous()
    stop_continuous_telemetry()

# takes the first frequency from the list.
def run_hot_cold_cycles(
    freq_ghz=DEFAULT_F_RX_GHZ_LIST[0],
    bw=DEFAULT_BW,
    int_ms=DEFAULT_INT_MS,
    n_spectra=DEFAULT_N_SPECTRA,
    n_iterations=DEFAULT_N_ITERATIONS,
    settle_time_s=DEFAULT_SETTLE_TIME_S,
    out_dir=DEFAULT_OUT_DIR,
    connect=True,
    initialize=True,
):
    """
    Perform gas spectroscopy hot/cold cycles with the chopper.
    Ctrl+C (SIGINT) will be caught and converted into a request to stop
    """

    print(
        f"Starting gas spectroscopy: f={freq_ghz} GHz, "
        f"n_spectra={n_spectra}, iterations={n_iterations}, "
        f"settle={settle_time_s} s, out_dir='{out_dir}'"
    )

    print(f"Setting receiver frequency to {freq_ghz} GHz")
    receiver_set(freq_ghz)

    if connect:
        print("Open and configure a libpcap capture handle for the spectrometer link")
        spectrometer_connect()
    else:
        print("Skipping spectrometer connect (connect=False).")    

    if initialize:
        print(f"Initialize spectrometer with bw={bw} and int_ms={int_ms}.")
        spectrometer_init(bw=bw, int_ms=int_ms)
    else:
        print("Skipping spectrometer init (initialize=False).")

    print(f"Creating session directory under '{out_dir}'")
    dir_resp = spectrometer_create_timestamp_dir(out_dir)
    try:
        dir_info = json.loads(dir_resp.decode("ascii"))
    except Exception as exc:
        raise RuntimeError(f"Failed to parse DIR response: {dir_resp!r}") from exc

    if dir_info.get("status") != "ok":
        raise RuntimeError(f"DIR command failed: {dir_info}")

    session_dir = dir_info["session_dir"]
    print(f"Using session directory: {session_dir}")

    print(
        f"Writing header CSV in '{session_dir}' "
        f"(n_spectra={n_spectra})"
    )

    spectrometer_write_header(
        out_dir=session_dir,
        f_rx_ghz=freq_ghz,
        bw=bw,
        n_iterations=n_iterations,
        int_ms=int_ms,
        n_spectra=n_spectra,
    )

    # 5) Perform hot–cold cycles with tagged measurements
    cycle = 0
    while cycle < n_iterations and not _stop_requested:
        cycle += 1

        # HOT
        print(f"Cycle {cycle}/{n_iterations}: HOT position (0 deg)")
        chopper_set(10)
        time.sleep(settle_time_s)
        try:
            spectrometer_hot_cold(n_spectra=n_spectra,
                                    out_dir=session_dir,
                                    tag="hot")
        except Exception as e:
            print(f"Error during HOT measurement: {e}. Reinitializing and retrying...")
            try:
                spectrometer_connect()
                time.sleep(1.0)
                spectrometer_init(bw=bw, int_ms=int_ms)
                time.sleep(settle_time_s)
                spectrometer_hot_cold(n_spectra=n_spectra,
                                        out_dir=session_dir,
                                        tag="hot")
            except Exception as retry_e:
                print(f"Retry failed: {retry_e}. Skipping this cycle.")
                continue

        if _stop_requested:
            break

        # COLD
        print(f"Cycle {cycle}/{n_iterations}: COLD position (45 deg)")
        chopper_set(65)
        time.sleep(settle_time_s)
        try:
            spectrometer_hot_cold(n_spectra=n_spectra,
                                    out_dir=session_dir,
                                    tag="cold")
        except Exception as e:
            print(f"Error during COLD measurement: {e}. Reinitializing and retrying...")
            try:
                spectrometer_connect()
                time.sleep(1.0)
                spectrometer_init(bw=bw, int_ms=int_ms)
                time.sleep(settle_time_s)
                spectrometer_hot_cold(n_spectra=n_spectra,
                                        out_dir=session_dir,
                                        tag="cold")
            except Exception as retry_e:
                print(f"Retry failed: {retry_e}. Skipping this cycle.")
                continue

    if _stop_requested:
        print("Stop requested: exiting after the last completed hot/cold cycle.")
    else:
        print("Gas spectroscopy hot/cold cycles completed.")
 

def parse_args():
    epilog = (
        "Examples:\n"
        " Use scripts/run_services.sh to use systemd.\n"
        " Use scripts/start_udp_servers.sh and then python3 main.py to run without systemd.\n"
        " python3 main.py --led --background --spectrometer"
        " python3 main.py --spectrometer --f-rx-ghz 235.71 236.00 237.5"
        " python3 main.py --spectrometer --linear-scan 225.0 255.0 0.5\n"
        " python3 main.py --spectrometer --center-scan 235.710 0.01 0.01 20\n"
        " use sudo fuser -k ****/udp to kill a process from another shell\n"
    )
    parser = argparse.ArgumentParser(
        description="Start LED control, background measurements, and/or spectrometer. Also set spectrometer parameters like frequency, bandwidth, integration time, and number of spectra/iterations. Ctrl+C will stop the spectrometer after the current hot/cold cycle finishes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=epilog,
    )

    parser.add_argument("--led", action="store_true", help="Use the LED.")

    parser.add_argument("--spectrometer", action="store_true", help="run gas spectroscopy hot/cold measurement sequence.")

    parser.add_argument("--background", action="store_true",help="Run pressure, temperature, gyro and telemetry background measurements.")

    parser.add_argument("--f-rx-ghz", type=float, nargs="+", default=DEFAULT_F_RX_GHZ_LIST, help="Set one or more receiver frequencies in GHz (default:%(default)s).")

    parser.add_argument("--bw", type=str, default=DEFAULT_BW, help="Spectrometer bandwidth string (default: %(default)s).")

    parser.add_argument("--int-ms", type=int, default=DEFAULT_INT_MS, help="Integration time in ms (default: %(default)s).")

    parser.add_argument("--n-spectra", type=int, default=DEFAULT_N_SPECTRA, help="Spectra per hot/cold phase (default: %(default)s).")
    parser.add_argument("--n-iterations", type=int, default=DEFAULT_N_ITERATIONS, help="Number of hot/cold cycles (default: %(default)s).")

    parser.add_argument("--settle-time", type=float, default=DEFAULT_SETTLE_TIME_S, help="Chopper settle time in seconds (default: %(default)s).")

    parser.add_argument("--out-dir", type=str, default=DEFAULT_OUT_DIR, help="Output directory root on spectrometer side (default: %(default)s).")

    scan_group = parser.add_mutually_exclusive_group()
    scan_group.add_argument("--linear-scan", nargs=3, type=float, metavar=("START_GHZ", "STOP_GHZ", "STEP_GHZ"), help="Linear frequency scan in GHz: START STOP STEP." )
    scan_group.add_argument("--center-scan", nargs=4, type=float, metavar=("CENTER_GHZ", "START_GHZ", "STEP_GHZ", "POINTS_PER_SIDEBAND"), help=
            "Sideband scan around CENTER_GHZ. Provide CENTER_GHZ, START_GHZ (offset from center in GHz), STEP_GHZ, and POINTS_PER_SIDEBAND. ")

    return parser.parse_args()

def main():
    global _stop_requested
    args = parse_args()

    if getattr(args, "linear_scan", None):
        start_ghz, stop_ghz, step_ghz = args.linear_scan
        args.f_rx_ghz  = generate_linear_scan(start_ghz, stop_ghz, step_ghz)
    elif getattr(args, "center_scan", None):
        center_ghz, start_ghz, step_ghz, points_per_sideband = args.center_scan
        args.f_rx_ghz  = generate_center_scan(center_ghz, start_ghz, step_ghz, points_per_sideband)

    _stop_requested = False
    original_sigint = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, _sigint_handler)

    red_pwm = green_pwm = blue_pwm = None
    background_started = False
    spectrometer_started = False

    try:
        if args.led:
            try:
                red_pwm, green_pwm, blue_pwm = led_control.init_leds()
                led_control.set_color(red_pwm, green_pwm, blue_pwm, 0.2, 0.2, 0.2)
            except Exception as e:
                print(f"Error initializing LEDs: {e}")

        if args.background:
            try:
                start_background_measurements()
                background_started = True
            except Exception as e:
                print(f"Error starting background measurements: {e}")

        if args.spectrometer:
            try:
                freq_list = [float(f) for f in args.f_rx_ghz ]

                print("Connecting spectrometer once before frequency loop.")
                spectrometer_connect()
                print(f"Initializing spectrometer once: bw={args.bw}, int_ms={args.int_ms}.")
                #time.sleep(5)
                spectrometer_init(bw=args.bw, int_ms=args.int_ms)
                spectrometer_started = True

                for i, f_ghz in enumerate(freq_list, start=1):
                    if _stop_requested:
                        print("Stop requested, ending frequency loop.")
                        break

                    print(f"\n=== Frequency {i}/{len(freq_list)}: {f_ghz} GHz ===")
                    run_hot_cold_cycles(
                        freq_ghz=f_ghz,
                        bw=args.bw,
                        int_ms=args.int_ms,
                        n_spectra=args.n_spectra,
                        n_iterations=args.n_iterations,
                        settle_time_s=args.settle_time,
                        out_dir=args.out_dir,
                        connect=False,
                        initialize=False,
                    )
            except Exception as e:
                print(f"Error in spectrometer measurement: {e}")

        if not (args.led or args.background or args.spectrometer):
            print("No action specified.")

    finally:
        if background_started:
            try:
                stop_background_measurements()
            except Exception as e:
                print(f"Error stopping background measurements: {e}")

        if all(pwm is not None for pwm in (red_pwm, green_pwm, blue_pwm)):
            try:
                led_control.cleanup(red_pwm, green_pwm, blue_pwm)
            except Exception as e:
                print(f"Error cleaning up LEDs: {e}")

        signal.signal(signal.SIGINT, original_sigint)
    

if __name__ == "__main__":
    main()

