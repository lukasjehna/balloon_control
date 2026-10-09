#!/usr/bin/env python3
import time
import matplotlib.pyplot as plt
import numpy as np
import spectrometer_backend as pmc_backend

def interactive_live_measurement(pmc_instance, bw=2, delay=0.5, floor=1e-12):
    plt.ion()
    fig, ax = plt.subplots()
    line, = ax.plot([], [])
    
    # State configuration for interactive toggles
    state = {
        'x_mode': 'frequency',  # 'frequency' (default) or 'bins'
        'y_mode': 'linear',     # 'linear' (default), 'log', or 'db'
        'bw': bw
    }

    def update_labels():
        if state['x_mode'] == 'frequency':
            ax.set_xlabel(f"Frequency [MHz] (BW: {state['bw']} GHz)")
        else:
            ax.set_xlabel("Bin Index")

        if state['y_mode'] == 'linear':
            ax.set_ylabel("Power (Linear)")
        elif state['y_mode'] == 'log':
            ax.set_ylabel("Power (Log10)")
        else:
            ax.set_ylabel("Power [dB]")
            
        ax.set_title(
            f"Live Spectrum | X: {state['x_mode']} | Y: {state['y_mode']}\n"
            "[Press 'x' to toggle X-axis, 'y' to cycle Y-axis]"
        )
        fig.canvas.draw_idle()

    def on_key(event):
        if event.key == 'x':
            state['x_mode'] = 'bins' if state['x_mode'] == 'frequency' else 'frequency'
            print(f"[Control] X-axis switched to: {state['x_mode']}")
            update_labels()
        elif event.key == 'y':
            modes = ['linear', 'log', 'db']
            curr_idx = modes.index(state['y_mode'])
            state['y_mode'] = modes[(curr_idx + 1) % len(modes)]
            print(f"[Control] Y-axis switched to: {state['y_mode']}")
            update_labels()

    fig.canvas.mpl_connect('key_press_event', on_key)
    update_labels()
    ax.grid(True)

    while True:
        try:
            data, timestamps = pmc_instance.meas_spectra(1)
            if len(data) == 0:
                time.sleep(delay)
                continue

            spectrum_sum = np.sum(data, axis=0)
            spectrum = np.array(spectrum_sum, dtype=float)
            spectrum = np.maximum(spectrum, floor)

            # Compute X-axis values
            if state['x_mode'] == 'frequency':
                x_vals = np.linspace(0, state['bw'] * 1000, len(spectrum))
            else:
                x_vals = np.arange(len(spectrum))

            # Compute Y-axis values based on selected scale
            if state['y_mode'] == 'linear':
                y_vals = spectrum
            elif state['y_mode'] == 'log':
                y_vals = np.log10(spectrum)
            else:  # 'db'
                y_vals = 20 * np.log10(spectrum)

            line.set_data(x_vals, y_vals)
            ax.relim()
            ax.autoscale_view()
            plt.pause(delay)

        except KeyboardInterrupt:
            print("\nLive measurement stopped by user.")
            break
        except Exception as exc:
            print(f"Error during live measurement: {exc}")
            time.sleep(1)

def main():
    dev_name = b"eth0"  # Adjust interface name if needed (e.g., for Raspberry Pi)

    print(f"Initializing PmcBackend on device: {dev_name.decode()}")
    pmc = pmc_backend.PmcBackend(
        dev_name,
        window_coefficients_csv="config/wind_coeff_hamm.csv",
    )

    try:
        print("Connecting to FPGA...")
        pmc.connect()
        
        print("Loading registers and configuring PMCC (2GHz, 500ms integration)...")
        allregs = pmc_backend.load('config/allregs.bin')
        pmc.setup_pmcc(allregs, bw='2GHz', int_time_ms=500)
        
        print("Starting interactive live measurement... Focus the plot window and use 'x' / 'y' keys.")
        interactive_live_measurement(pmc_instance=pmc, bw=2)

    finally:
        print("Disconnecting...")
        try:
            pmc.disconnect()
        except Exception:
            pass

if __name__ == "__main__":
    main()