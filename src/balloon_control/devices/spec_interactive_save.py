To stop the interactive measurement gracefully—ensuring the hardware connection is properly closed and any spectra captured during the session are saved to disk—you can implement an explicit exit key (such as **`q`**) alongside `KeyboardInterrupt` handling.

Below is the updated script that accumulates spectra while running, saves them automatically upon a graceful exit (via **`q`** or **`Ctrl+C`**), and safely disconnects the FPGA.

```python
#!/usr/bin/env python3
import time
import matplotlib.pyplot as plt
import numpy as np
import spectrometer_backend as pmc_backend

def interactive_live_measurement(pmc_instance, bw=2, delay=0.5, floor=1e-12):
    plt.ion()
    fig, ax = plt.subplots()
    line, = ax.plot([], [])
    
    state = {
        'x_mode': 'frequency',  # 'frequency' or 'bins'
        'y_mode': 'linear',     # 'linear', 'log', or 'db'
        'bw': bw,
        'running': True
    }

    accumulated_spectra = []
    accumulated_timestamps = []

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
            "[Press 'x': toggle X | 'y': cycle Y | 'q': save & quit]"
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
        elif event.key == 'q':
            print("\n[Control] Quit signal received via 'q' key.")
            state['running'] = False

    fig.canvas.mpl_connect('key_press_event', on_key)
    update_labels()
    ax.grid(True)

    while state['running']:
        try:
            data, timestamps = pmc_instance.meas_spectra(1)
            if len(data) == 0:
                time.sleep(delay)
                continue

            # Accumulate data for saving upon exit
            accumulated_spectra.append(data[0])
            accumulated_timestamps.append(timestamps[0])

            spectrum_sum = np.sum(data, axis=0)
            spectrum = np.array(spectrum_sum, dtype=float)
            spectrum = np.maximum(spectrum, floor)

            if state['x_mode'] == 'frequency':
                x_vals = np.linspace(0, state['bw'] * 1000, len(spectrum))
            else:
                x_vals = np.arange(len(spectrum))

            if state['y_mode'] == 'linear':
                y_vals = spectrum
            elif state['y_mode'] == 'log':
                y_vals = np.log10(spectrum)
            else:
                y_vals = 20 * np.log10(spectrum)

            line.set_data(x_vals, y_vals)
            ax.relim()
            ax.autoscale_view()
            plt.pause(delay)

        except KeyboardInterrupt:
            print("\n[Control] Interrupted by user (Ctrl+C).")
            break
        except Exception as exc:
            print(f"Error during live measurement: {exc}")
            time.sleep(1)

    plt.ioff()
    return np.array(accumulated_spectra, dtype=object), np.array(accumulated_timestamps)

def main():
    dev_name = b"eth0"  # Target interface

    pmc = pmc_backend.PmcBackend(
        dev_name,
        window_coefficients_csv="config/wind_coeff_hamm.csv",
    )

    try:
        pmc.connect()
        allregs = pmc_backend.load('config/allregs.bin')
        pmc.setup_pmcc(allregs, bw='2GHz', int_time_ms=500)
        
        print("Starting interactive live measurement. Press 'q' in the plot window or Ctrl+C in terminal to exit.")
        spectra, timestamps = interactive_live_measurement(pmc_instance=pmc, bw=2)

        # Save accumulated data if any spectra were captured
        if len(spectra) > 0:
            timestamp_str = time.strftime("%Y%m%d-%H%M%S")
            filename = f"data/live_session_{timestamp_str}.npy"
            print(f"Saving {len(spectra)} spectra to {filename}...")
            pmc_backend.save(spectra, filename)
        else:
            print("No spectra collected to save.")

    finally:
        print("Disconnecting hardware safely...")
        try:
            pmc.disconnect()
        except Exception:
            pass

if __name__ == "__main__":
    main()

```