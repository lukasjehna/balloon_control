#!/usr/bin/env python3
import threading
import time
from typing import Any

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import spec_backend as pmc_backend
from matplotlib.collections import LineCollection
from matplotlib.widgets import Button

# Suppress window raising to avoid stealing foreground focus on render ticks
mpl.rcParams["figure.raise_window"] = False


class SpectrometerState:
    """Thread-safe state container for concurrent acquisition and rendering."""
    def __init__(self, bw: float):
        self.lock = threading.Lock()
        self.running: bool = True
        self.current_spectrum: np.ndarray | None = None
        self.running_average: np.ndarray | None = None
        self.history: list[np.ndarray] = []
        self.n_spectra: int = 0
        self.max_history: int = 150  # Cap geometry buffer to prevent GUI memory exhaustion

        self.display_mode: str = 'current'  # 'current', 'average', 'history'
        self.x_mode: str = 'frequency'
        self.y_mode: str = 'linear'
        self.bw: float = bw
        self.trigger_autoscale: bool = True  # Flag to trigger one-shot axis rescale


def acquisition_worker(
    pmc_instance: Any, state: SpectrometerState, delay: float, floor: float
) -> None:
    """Background hardware polling. Isolates blocking network/bus I/O from the GUI event loop."""
    while state.running:
        try:
            data, _ = pmc_instance.meas_spectra(1)
            if len(data) == 0:
                time.sleep(delay)
                continue

            spectrum_sum = np.sum(data, axis=0)
            spectrum = np.array(spectrum_sum, dtype=float)
            spectrum = np.maximum(spectrum, floor)

            with state.lock:
                # Discretization bounds check: reset buffers if spectrometer bin count changes
                if state.current_spectrum is not None and state.current_spectrum.shape != spectrum.shape:
                    print(f"\n[Warning] Bin geometry shifted from {state.current_spectrum.shape} to {spectrum.shape}. Purging state.")
                    state.n_spectra = 0
                    state.history.clear()
                    state.running_average = None

                state.current_spectrum = spectrum
                state.n_spectra += 1

                # Recursive moving average (A_n = A_{n-1} + (S_n - A_{n-1}) / n)
                if state.running_average is None or state.n_spectra == 1:
                    state.running_average = spectrum.copy()
                else:
                    state.running_average += (spectrum - state.running_average) / state.n_spectra

                # FIFO persistence buffer for waterfall/history mode
                state.history.append(spectrum)
                if len(state.history) > state.max_history:
                    state.history.pop(0)

        except Exception as exc:
            print(f"[Acquisition Fault] Hardware I/O error: {exc}")
            time.sleep(1.0)


def interactive_live_measurement(
    pmc_instance: Any, bw: float = 2.0, delay: float = 0.5, floor: float = 1e-12
) -> None:
    state = SpectrometerState(bw=bw)

    plt.ion()
    fig, ax = plt.subplots()
    # Reserve top margin for GUI buttons
    plt.subplots_adjust(top=0.88)

    # Instantiate persistent matplotlib plot objects
    line_current, = ax.plot([], [], label='Current', color='blue', zorder=3)
    line_average, = ax.plot([], [], label='Running Avg', color='red', linewidth=1.5, zorder=3)
    line_collection = LineCollection([], colors='black', alpha=0.15, linewidths=0.8, zorder=1)
    ax.add_collection(line_collection)

    # UI Autoscale Button
    ax_btn = plt.axes([0.80, 0.91, 0.12, 0.05])
    btn_autoscale = Button(ax_btn, 'Autoscale', color='#e0e0e0', hovercolor='#c0c0c0')

    def request_autoscale(event: Any = None) -> None:
        with state.lock:
            state.trigger_autoscale = True

    btn_autoscale.on_clicked(request_autoscale)

    def update_labels() -> None:
        unit_x = f"Frequency [MHz] (BW: {state.bw} GHz)" if state.x_mode == 'frequency' else "Bin Index"
        ax.set_xlabel(unit_x)

        if state.y_mode == 'linear':
            ax.set_ylabel("Power (Linear)")
        elif state.y_mode == 'log':
            ax.set_ylabel("Power (Log10)")
        else:
            ax.set_ylabel("Power [dB]")

        ax.set_title(
            f"Live | X: {state.x_mode} | Y: {state.y_mode} | Mode: {state.display_mode}\n"
            f"[a/Btn: Autoscale | d: Mode | x: X-axis | y: Y-axis | c: Clear Avg | q: Quit]",
            y=1.08,
        )

        ax.legend(
            handles=[line_average] if state.display_mode == 'average' else [line_current],
            loc='upper right'
        )
        fig.canvas.draw_idle()

    def on_key(event: Any) -> None:
        with state.lock:
            if event.key == 'a':
                state.trigger_autoscale = True
            elif event.key == 'x':
                state.x_mode = 'bins' if state.x_mode == 'frequency' else 'frequency'
                state.trigger_autoscale = True
                update_labels()
            elif event.key == 'y':
                modes = ['linear', 'log', 'db']
                curr_idx = modes.index(state.y_mode)
                state.y_mode = modes[(curr_idx + 1) % len(modes)]
                state.trigger_autoscale = True
                update_labels()
            elif event.key == 'd':
                modes = ['current', 'average', 'history']
                curr_idx = modes.index(state.display_mode)
                state.display_mode = modes[(curr_idx + 1) % len(modes)]
                state.trigger_autoscale = True
                print(f"[Control] Display mode switched to: {state.display_mode}")
                update_labels()
            elif event.key == 'c':
                state.n_spectra = 0
                state.history.clear()
                state.running_average = None
                state.trigger_autoscale = True
                print("[Control] Averages and history buffers cleared.")
            elif event.key == 'q':
                state.running = False

    fig.canvas.mpl_connect('key_press_event', on_key)
    update_labels()
    ax.grid(True)

    acq_thread = threading.Thread(
        target=acquisition_worker,
        args=(pmc_instance, state, delay, floor),
        daemon=True
    )
    acq_thread.start()

    def apply_y_scale(y_data: np.ndarray) -> np.ndarray:
        if state.y_mode == 'linear':
            return y_data
        elif state.y_mode == 'log':
            return np.log10(y_data)
        return 20 * np.log10(y_data)

    while state.running:
        try:
            with state.lock:
                if state.current_spectrum is None:
                    fig.canvas.flush_events()
                    time.sleep(delay)
                    continue

                curr_spec = state.current_spectrum.copy()
                avg_spec = state.running_average.copy() if state.running_average is not None else None
                hist_specs = list(state.history)
                x_mode, d_mode = state.x_mode, state.display_mode
                should_autoscale = state.trigger_autoscale
                state.trigger_autoscale = False

            n_bins = len(curr_spec)
            x_vals = np.linspace(0, state.bw * 1000, n_bins) if x_mode == 'frequency' else np.arange(n_bins)

            line_current.set_visible(False)
            line_average.set_visible(False)
            line_collection.set_visible(False)

            if d_mode == 'current':
                line_current.set_data(x_vals, apply_y_scale(curr_spec))
                line_current.set_color('blue')
                line_current.set_visible(True)

            elif d_mode == 'average' and avg_spec is not None:
                line_average.set_data(x_vals, apply_y_scale(avg_spec))
                line_average.set_visible(True)

            elif d_mode == 'history':
                segments = [np.column_stack([x_vals, apply_y_scale(h)]) for h in hist_specs]
                line_collection.set_segments(segments)
                line_collection.set_visible(True)

                line_current.set_data(x_vals, apply_y_scale(curr_spec))
                line_current.set_color('red')
                line_current.set_visible(True)

            # Autoscale only on deliberate trigger (button press, key 'a', or mode change)
            # This preserves manual zoom/pan levels during live acquisition
            if should_autoscale:
                ax.relim()
                ax.autoscale_view()

            fig.canvas.draw_idle()
            fig.canvas.flush_events()
            time.sleep(delay)

        except KeyboardInterrupt:
            print("\n[Control] SIGINT trapped. Initiating clean shutdown.")
            state.running = False
            break
        except BaseException as exc:
            print(f"[GUI Render Fault] {exc}")
            time.sleep(delay)

    acq_thread.join(timeout=2.0)
    plt.ioff()


def main() -> None:
    dev_name = b"eth0"

    print(f"Initializing PmcBackend on device: {dev_name.decode()}")
    pmc = pmc_backend.PmcBackend(
        dev_name,
        window_coefficients_csv="config/wind_coeff_hamm.csv",
    )

    try:
        print("Connecting to FPGA...")
        pmc.connect()

        allregs = pmc_backend.load('config/allregs.bin')
        pmc.setup_pmcc(allregs, bw='2GHz', int_time_ms=500)

        print("Starting interactive live measurement. Focus plot window to use shortcuts.")
        interactive_live_measurement(pmc_instance=pmc, bw=2.0)

    finally:
        print("Disconnecting hardware link...")
        try:
            pmc.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    main()