#!/usr/bin/env python3
import struct
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np

try:
    import spec_backend as pmc_backend
except ImportError:
    import spec_backend as pmc_backend


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _ts() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def save_spec(
    d: List[Any] | np.ndarray,
    t: List[float] | np.ndarray,
    out_dir: str | Path,
    t_acc: int | float | None = None,
    bw: str | int | float | None = None,
) -> Dict[str, Any]:
    """Writes spectra and timestamps to disk matching the backend .spec binary format."""
    out_path = Path(out_dir)
    _ensure_dir(out_path)
    ts = _ts()
    fn = out_path / f"{ts}.spec"

    # Human-readable header followed by big-endian binary payload
    header = (
        f"number of spectra: {len(d)}, "
        f"integration time: {t_acc}ms, bandwidth: {bw}\n"
    )

    with open(fn, "wb") as f:
        f.write(header.encode("ascii"))
        # Pack times (floats) as big-endian doubles ('>d')
        f.write(struct.pack(">" + "d" * len(t), *t))
        # Pack raw spectrum bins as big-endian signed 32-bit integers ('>l')
        for d_ in d:
            f.write(struct.pack(">" + "l" * len(d_), *[int(x) for x in d_]))

    return {
        "file": str(fn),
        "n_spectra": len(d),
        "int_time_ms": t_acc,
        "bandwidth": bw,
    }


def interactive_live_measurement(
    pmc_instance: Any, bw: float = 2.0, delay: float = 0.5, floor: float = 1e-12
) -> Tuple[List[Any], List[float]]:
    plt.ion()
    fig, ax = plt.subplots()
    (line,) = ax.plot([], [])

    state = {
        "x_mode": "frequency",  # 'frequency' or 'bins'
        "y_mode": "linear",     # 'linear', 'log', or 'db'
        "bw": bw,
        "running": True,
    }

    accumulated_spectra: List[Any] = []
    accumulated_timestamps: List[float] = []

    def update_labels() -> None:
        if state["x_mode"] == "frequency":
            ax.set_xlabel(f"Frequency [MHz] (BW: {state['bw']} GHz)")
        else:
            ax.set_xlabel("Bin Index")

        if state["y_mode"] == "linear":
            ax.set_ylabel("Power (Linear)")
        elif state["y_mode"] == "log":
            ax.set_ylabel("Power (Log10)")
        else:
            ax.set_ylabel("Power [dB]")

        ax.set_title(
            f"Live Spectrum | X: {state['x_mode']} | Y: {state['y_mode']}\n"
            "[Press 'x': toggle X | 'y': cycle Y | 'q': save & quit]"
        )
        fig.canvas.draw_idle()

    def on_key(event: Any) -> None:
        if event.key == "x":
            state["x_mode"] = "bins" if state["x_mode"] == "frequency" else "frequency"
            print(f"[Control] X-axis switched to: {state['x_mode']}")
            update_labels()
        elif event.key == "y":
            modes = ["linear", "log", "db"]
            curr_idx = modes.index(state["y_mode"])
            state["y_mode"] = modes[(curr_idx + 1) % len(modes)]
            print(f"[Control] Y-axis switched to: {state['y_mode']}")
            update_labels()
        elif event.key == "q":
            print("\n[Control] Quit signal received via 'q' key.")
            state["running"] = False

    fig.canvas.mpl_connect("key_press_event", on_key)
    update_labels()
    ax.grid(True)

    while state["running"]:
        try:
            data, timestamps = pmc_instance.meas_spectra(1)
            if len(data) == 0:
                time.sleep(delay)
                continue

            # Maintain time continuity: preserve batch start t[0], then append completion times
            if not accumulated_timestamps:
                accumulated_timestamps.append(float(timestamps[0]))
            accumulated_timestamps.append(float(timestamps[-1]))
            accumulated_spectra.append(data[0])

            spectrum_sum = np.sum(data, axis=0)
            spectrum = np.array(spectrum_sum, dtype=float)
            spectrum = np.maximum(spectrum, floor)

            if state["x_mode"] == "frequency":
                x_vals = np.linspace(0, state["bw"] * 1000, len(spectrum))
            else:
                x_vals = np.arange(len(spectrum))

            if state["y_mode"] == "linear":
                y_vals = spectrum
            elif state["y_mode"] == "log":
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
    return accumulated_spectra, accumulated_timestamps


def main() -> None:
    dev_name = b"eth0"

    pmc = pmc_backend.PmcBackend(
        dev_name,
        window_coefficients_csv="config/wind_coeff_hamm.csv",
    )

    try:
        pmc.connect()
        allregs = pmc_backend.load("config/allregs.bin")
        pmc.setup_pmcc(allregs, bw="2GHz", int_time_ms=500)

        print("Starting interactive live measurement. Press 'q' in plot or Ctrl+C to exit.")
        spectra, timestamps = interactive_live_measurement(pmc_instance=pmc, bw=2.0)

        if len(spectra) > 0:
            t_acc = getattr(pmc, "t_acc", None)
            bw = getattr(pmc, "bw", None)
            res = save_spec(
                d=spectra,
                t=timestamps,
                out_dir="data",
                t_acc=t_acc,
                bw=bw,
            )
            print(
                f"Saved {res['n_spectra']} spectra to {res['file']} "
                f"(t_acc: {res['int_time_ms']} ms, bw: {res['bandwidth']})"
            )
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