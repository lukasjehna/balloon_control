#!/usr/bin/env python3
import time
import libpcap as pcap
import matplotlib.pyplot as plt
import numpy as np
import spectrometer_backend as pmc_backend

#Test this first. The working version is on the raspberry pi.
#sudo python3 -i src/devices/spectrometer_control.py
#init_default_pmc()
#setup_default_pmcc()
#livesurement()

pmc = None

def init_default_pmc(
    dev_name=b"eth0",
    window_coefficients_csv="config/wind_coeff_hamm.csv",
):
    global pmc
    pmc = pmc_backend.PmcBackend(
        dev_name,
        window_coefficients_csv=window_coefficients_csv,
    )
    return pmc

def setup_default_pmcc(
    pmc_instance=None,
    allregs_file="config/allregs.bin",
    bw="2GHz",
    int_time_ms=500,
):
    if pmc_instance is None:
        if pmc is None:
            raise RuntimeError(
                "No pmc instance available. Create one first or call setup_pmcc(pmc_instance)."
            )
        pmc_instance = pmc

    allregs = pmc_backend.load(allregs_file)
    pmc_instance.setup_pmcc(
        allregs,
        bw=bw,
        int_time_ms=int_time_ms,
    )

def spectrum_xy(data, bw=4, normalize=False, floor=1e-12):
    spectrum_sum = np.sum(data, axis=0)
    spectrum = np.array(spectrum_sum, dtype=float)

    if normalize:
        norm = np.max(spectrum)
        if norm <= 0:
            norm = 1.0
    else:
        norm = 1.0

    spectrum = spectrum / norm
    spectrum = np.maximum(spectrum, floor)

    freqs = np.linspace(0, bw * 1000, len(spectrum))
    y_vals = 20 * np.log10(spectrum)

    return freqs, y_vals


def adc_hist_data(adc):
    return sum(adc, [])


def plot_spectrum(data, bw=4, fig_num=2, normalize=False):
    x_vals, y_vals = spectrum_xy(data, bw=bw, normalize=normalize)

    fig = plt.figure(fig_num)
    plt.clf()
    plt.plot(x_vals, y_vals)
    plt.xlabel("Frequency [MHz]")
    plt.ylabel("Power [dB]")
    plt.title("Spectrum")
    plt.grid(True)
    fig.show()


def plot_hist(adc, nbins=32):
    fig = plt.figure()
    adc_merged = adc_hist_data(adc)
    plt.hist(adc_merged, nbins, range=(0, 63))
    plt.xlabel("ADC value")
    plt.ylabel("Counts")
    plt.title("ADC Histogram")
    plt.grid(True)
    fig.show()


def live_measurement(pmc_instance=None, bw=4, delay=0.5, normalize=True, nbins=32):
    if pmc_instance is None:
        if pmc is None:
            raise RuntimeError(
                "No pmc instance available. Create one first or call live_measurement(pmc_instance)."
            )
        pmc_instance = pmc

    plt.ion()

    fig, (ax_spec, ax_hist) = plt.subplots(
        2, 1, figsize=(10, 8), gridspec_kw={"height_ratios": [2, 1]}
    )

    line, = ax_spec.plot([], [])
    ax_spec.set_xlabel("Frequency [MHz]")
    ax_spec.set_ylabel("Power [dB]")
    ax_spec.set_title("Live Spectrum")
    ax_spec.grid(True)

    ax_hist.set_xlabel("ADC value")
    ax_hist.set_ylabel("Counts")
    ax_hist.set_title("ADC Histogram")
    ax_hist.grid(True)

    while True:
        try:
            data, timestamps = pmc_instance.meas_spectra(1)
            x_vals, y_vals = spectrum_xy(data, bw=bw, normalize=normalize)

            line.set_data(x_vals, y_vals)
            ax_spec.relim()
            ax_spec.autoscale_view()

            adc = pmc_instance.read_adc()
            adc_merged = adc_hist_data(adc)

            ax_hist.cla()
            ax_hist.hist(adc_merged, nbins, range=(0, 63))
            ax_hist.set_xlabel("ADC value")
            ax_hist.set_ylabel("Counts")
            ax_hist.set_title("ADC Histogram")
            ax_hist.grid(True)

            fig.tight_layout()
            plt.pause(delay)

        except KeyboardInterrupt:
            print("Live measurement stopped.")
            break
        except Exception as exc:
            print(f"Error during live measurement: {exc}")
            time.sleep(1)