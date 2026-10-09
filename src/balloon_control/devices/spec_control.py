#!/usr/bin/env python3
import time

import libpcap as pcap
import matplotlib.pyplot as plt
import numpy as np
import spec_backend as pmc_backend

pmc = None

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

def plot_adc(adc, *args):
    indices = range(0, len(adc[0][:]))
    fig = plt.figure(1)
    for channel in adc:
        plt.plot(indices, channel, *args)
    fig.show()


def plot_hist(adc, nbins=32):
    fig = plt.figure()
    adc_merged = sum(adc, [])  # unnest
    plt.hist(adc_merged, nbins, range=(0, 63))
    fig.show()

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


def live_measurement(pmc_instance=None, bw=4, delay=0.5, normalize=True):
    if pmc_instance is None:
        if pmc is None:
            raise RuntimeError(
                "No pmc instance available. Create one first or call live_measurement(pmc_instance)."
            )
        pmc_instance = pmc

    plt.ion()

    fig, ax = plt.subplots()
    line, = ax.plot([], [])
    ax.set_xlabel("Frequency [MHz]")
    ax.set_ylabel("Power [dB]")
    ax.set_title("Live Spectrum")
    ax.grid(True)

    while True:
        try:
            data, timestamps = pmc_instance.meas_spectra(1)
            x_vals, y_vals = spectrum_xy(
                data,
                bw=bw,
                normalize=normalize,
            )

            line.set_data(x_vals, y_vals)
            ax.relim()
            ax.autoscale_view()
            plt.pause(delay)

        except KeyboardInterrupt:
            print("Live measurement stopped.")
            break
        except Exception as exc:
            print(f"Error during live measurement: {exc}")
            time.sleep(1)


if __name__ == "__main__":
    # dev_name = b'\\Device\\NPF_{8164B0EB-67A2-4A12-A97C-846787F14DD6}'  # Dell Laptop OSAS-B
    dev_name = b"eth0"  # Raspberry Pi

    print(pcap.lib_version())
    try:
        pmc = pmc_backend.PmcBackend(
            dev_name,
            window_coefficients_csv="config/wind_coeff_hamm.csv",
        )
    except Exception:
        raise RuntimeError(
            "Make sure to execute this from the project root and not from within src/"
        )
    # time.sleep(1)
    # pmc.connect()


