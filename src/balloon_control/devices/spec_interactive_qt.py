#!/usr/bin/env python3
"""
Standalone PyQt6 GUI for the PMC Spectrometer on Raspberry Pi 4.
Decouples libpcap Ethernet I/O from the Qt main event loop and preserves
binary compatibility with the legacy .spec file format.
"""

import struct
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from matplotlib.backends.backend_qtagg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT as NavigationToolbar,
)
from matplotlib.collections import LineCollection
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from balloon_control.devices import spec_backend as pmc_backend


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S")


def save_spec(
    d: list[Any] | np.ndarray,
    t: list[float] | np.ndarray,
    out_dir: str | Path,
    t_acc: float | None = None,
    bw: str | float | None = None,
) -> dict[str, Any]:
    """
    Writes spectra and timestamps to disk matching the backend .spec binary format.
    Uses vectorized NumPy big-endian casting to eliminate Python-level struct loops.
    """
    out_path = Path(out_dir)
    _ensure_dir(out_path)
    ts = _ts()
    fn = out_path / f"{ts}.spec"
    
    # Prevent file overwrite if flushed twice within the same 1-second boundary
    counter = 1
    while fn.exists():
        fn = out_path / f"{ts}_{counter:02d}.spec"
        counter += 1

    header = (
        f"number of spectra: {len(d)}, "
        f"integration time: {t_acc}ms, bandwidth: {bw}\n"
    )

    t_arr = np.asarray(t, dtype=">f8")
    # Clip to signed 32-bit integer bounds to avoid OverflowError on saturated 32-bit unsigned bins
    d_arr = np.clip(np.asarray(d, dtype=np.int64), -2147483648, 2147483647).astype(">i4")

    with open(fn, "wb") as f:
        f.write(header.encode("ascii"))
        f.write(t_arr.tobytes())
        f.write(d_arr.tobytes())

    return {
        "file": str(fn),
        "n_spectra": len(d),
        "int_time_ms": t_acc,
        "bandwidth": bw,
    }


class InitWorker(QThread):
    """Executes blocking libpcap initialization and FPGA register writes off the GUI thread."""
    finished_init = pyqtSignal(bool, str, float, int)

    def __init__(self, pmc: pmc_backend.PmcBackend, bw_str: str, int_time_ms: int) -> None:
        super().__init__()
        self.pmc = pmc
        self.bw_str = bw_str
        self.int_time_ms = int_time_ms

    def run(self) -> None:
        try:
            self.pmc.connect()
            allregs = pmc_backend.load("config/allregs.bin")
            self.pmc.setup_pmcc(
                allregs,
                readout_32bit=True,
                bw=self.bw_str,
                int_time_ms=self.int_time_ms,
            )
            bw_ghz = float(self.bw_str.replace("GHz", ""))
            self.finished_init.emit(
                True,
                f"Initialized ({self.bw_str}, {self.int_time_ms} ms)",
                bw_ghz,
                self.int_time_ms,
            )
        except Exception as exc:
            self.finished_init.emit(False, f"Initialization failed: {exc}", 0.0, 0)


class AcquisitionWorker(QThread):
    """
    Continuous background hardware polling thread.
    Pauses safely on a threading.Event without dropping the libpcap handle.
    """
    spectrum_ready = pyqtSignal(np.ndarray, float, float)  # raw_bins (int64), t_start, t_end
    error_occurred = pyqtSignal(str)

    def __init__(self, pmc: pmc_backend.PmcBackend, poll_delay: float = 0.05) -> None:
        super().__init__()
        self.pmc = pmc
        self.poll_delay = poll_delay
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # Start in paused state

    def set_paused(self, paused: bool) -> None:
        if paused:
            self._pause_event.set()
        else:
            self._pause_event.clear()

    def stop(self) -> None:
        self._stop_event.set()
        self._pause_event.set()

    def run(self) -> None:
        while not self._stop_event.is_set():
            if self._pause_event.is_set():
                time.sleep(0.05)
                continue

            try:
                data, timestamps = self.pmc.meas_spectra(1)
                # Discard in-flight packet if user paused/stopped mid-accumulation
                if self._pause_event.is_set() or self._stop_event.is_set():
                    continue

                if len(data) == 0:
                    time.sleep(self.poll_delay)
                    continue

                raw_spec = np.asarray(data[0], dtype=np.int64)
                t_start = float(timestamps[0])
                t_end = float(timestamps[-1])
                self.spectrum_ready.emit(raw_spec, t_start, t_end)

            except Exception as exc:
                self.error_occurred.emit(str(exc))
                time.sleep(1.0)


class SpectrometerWindow(QMainWindow):
    def __init__(
        self,
        dev_name: bytes = b"eth0",
        out_dir: str | Path = "data/spectra",
        floor: float = 1e-12,
    ) -> None:
        super().__init__()
        self.setWindowTitle("PMC Spectrometer Control & Live Telemetry")
        self.resize(1150, 750)

        self.dev_name = dev_name
        self.out_dir = Path(out_dir)
        self.floor = floor

        self.pmc: pmc_backend.PmcBackend | None = None
        self.acq_worker: AcquisitionWorker | None = None
        self.init_worker: InitWorker | None = None

        # Hardware & state parameters
        self.is_initialized: bool = False
        self.is_running: bool = False
        self.logging_enabled: bool = False

        self.bw_str: str = "2GHz"
        self.bw_ghz: float = 2.0
        self.int_time_ms: int = 500

        # Spectral display buffers
        self.current_spectrum: np.ndarray | None = None
        self.running_average: np.ndarray | None = None
        self.history: list[np.ndarray] = []
        self.n_spectra: int = 0
        self.max_history: int = 150

        # Display configuration
        self.display_mode: str = "current"  # 'current', 'average', 'history'
        self.x_mode: str = "frequency"      # 'frequency', 'bins'
        self.y_mode: str = "linear"         # 'linear', 'log', 'dBm'

        # Logging cache: stores raw unscaled spectra and unix timestamps
        # For N spectra, PmcBackend.meas_spectra produces N+1 timestamps: [t_0, t_1, ..., t_N]
        self.cache_d: list[np.ndarray] = []
        self.cache_t: list[float] = []

        self._build_ui()
        self._init_plot()

    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # --- Top Control Panel ---
        ctrl_layout = QHBoxLayout()

        # 1. Hardware Initialization Group
        hw_group = QGroupBox("Hardware Setup")
        hw_layout = QHBoxLayout(hw_group)

        hw_layout.addWidget(QLabel("BW:"))
        self.combo_bw = QComboBox()
        self.combo_bw.addItems(["1GHz", "2GHz", "4GHz", "8GHz"])
        self.combo_bw.setCurrentText(self.bw_str)
        hw_layout.addWidget(self.combo_bw)

        hw_layout.addWidget(QLabel("Int. Time:"))
        self.spin_int_time = QSpinBox()
        self.spin_int_time.setRange(10, 10000)
        self.spin_int_time.setSingleStep(50)
        self.spin_int_time.setSuffix(" ms")
        self.spin_int_time.setValue(self.int_time_ms)
        hw_layout.addWidget(self.spin_int_time)

        self.btn_init = QPushButton("Initialize")
        self.btn_init.clicked.connect(self._on_initialize_clicked)
        hw_layout.addWidget(self.btn_init)
        ctrl_layout.addWidget(hw_group)

        # 2. Acquisition & Logging Group
        acq_group = QGroupBox("Acquisition & Logging")
        acq_layout = QHBoxLayout(acq_group)

        self.btn_run_pause = QPushButton("Start")
        self.btn_run_pause.setEnabled(False)
        self.btn_run_pause.clicked.connect(self._on_run_pause_clicked)
        acq_layout.addWidget(self.btn_run_pause)

        self.chk_logging = QCheckBox("Enable Logging")
        self.chk_logging.toggled.connect(self._on_logging_toggled)
        acq_layout.addWidget(self.chk_logging)

        self.lbl_cache = QLabel("Cached: 0")
        acq_layout.addWidget(self.lbl_cache)
        ctrl_layout.addWidget(acq_group)

        # 3. View & Display Group
        view_group = QGroupBox("Display Controls")
        view_layout = QHBoxLayout(view_group)

        view_layout.addWidget(QLabel("Mode (d):"))
        self.combo_display = QComboBox()
        self.combo_display.addItems(["current", "average", "history"])
        self.combo_display.currentTextChanged.connect(self._on_display_mode_changed)
        view_layout.addWidget(self.combo_display)

        view_layout.addWidget(QLabel("X-Axis (x):"))
        self.combo_x = QComboBox()
        self.combo_x.addItems(["frequency", "bins"])
        self.combo_x.currentTextChanged.connect(self._on_x_mode_changed)
        view_layout.addWidget(self.combo_x)

        view_layout.addWidget(QLabel("Y-Scale (y):"))
        self.combo_y = QComboBox()
        self.combo_y.addItems(["linear", "log", "dBm"])
        self.combo_y.currentTextChanged.connect(self._on_y_mode_changed)
        view_layout.addWidget(self.combo_y)

        self.btn_clear = QPushButton("Clear Avg (c)")
        self.btn_clear.clicked.connect(self._clear_buffers)
        view_layout.addWidget(self.btn_clear)

        ctrl_layout.addWidget(view_group)
        main_layout.addLayout(ctrl_layout)

        # --- Matplotlib Canvas & Interactive Toolbar ---
        self.fig = Figure(figsize=(9, 6), tight_layout=True)
        self.canvas = FigureCanvas(self.fig)
        self.canvas.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.canvas.setFocus()
        self.toolbar = NavigationToolbar(self.canvas, self)

        main_layout.addWidget(self.toolbar)
        main_layout.addWidget(self.canvas, stretch=1)

        # --- Status Bar ---
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Hardware uninitialized. Configure BW and Integration Time, then click Initialize.")

    def _init_plot(self) -> None:
        self.ax = self.fig.add_subplot(111)
        self.ax.grid(True)

        (self.line_current,) = self.ax.plot([], [], label="Current", color="blue", zorder=3)
        (self.line_average,) = self.ax.plot([], [], label="Running Avg", color="red", linewidth=1.5, zorder=3)

        self.line_collection = LineCollection([], colors="black", alpha=0.15, linewidths=0.8, zorder=1)
        self.ax.add_collection(self.line_collection)

        self._update_plot_labels()

    # --- Hardware Initialization & Acquisition State Machine ---

    def _on_initialize_clicked(self) -> None:
        if self.is_running:
            # Transition Running -> Paused before re-initializing hardware
            self._set_running_state(False)

        self.bw_str = self.combo_bw.currentText()
        self.int_time_ms = self.spin_int_time.value()

        self.btn_init.setEnabled(False)
        self.btn_run_pause.setEnabled(False)
        self.combo_bw.setEnabled(False)
        self.spin_int_time.setEnabled(False)
        self.status_bar.showMessage(f"Initializing spectrometer ({self.bw_str}, {self.int_time_ms} ms)...")

        try:
            if self.pmc is None:
                self.pmc = pmc_backend.PmcBackend(
                    self.dev_name,
                    window_coefficients_csv="config/wind_coeff_hamm.csv",
                )
        except Exception as exc:
            self._handle_init_result(False, f"Backend creation failed: {exc}", 0.0, 0)
            return

        self.init_worker = InitWorker(self.pmc, self.bw_str, self.int_time_ms)
        self.init_worker.finished_init.connect(self._handle_init_result)
        self.init_worker.start()

    def _handle_init_result(self, success: bool, msg: str, bw_ghz: float, int_time_ms: int) -> None:
        self.btn_init.setEnabled(True)
        self.combo_bw.setEnabled(True)
        self.spin_int_time.setEnabled(True)
        self.status_bar.showMessage(msg)

        if not success:
            QMessageBox.critical(self, "Hardware Initialization Error", msg)
            return

        self.is_initialized = True
        self.bw_ghz = bw_ghz
        self.int_time_ms = int_time_ms
        self._clear_buffers()
        self._update_plot_labels()

        if self.acq_worker is None:
            self.acq_worker = AcquisitionWorker(self.pmc)
            self.acq_worker.spectrum_ready.connect(self._on_spectrum_received)
            self.acq_worker.error_occurred.connect(self._on_acquisition_error)
            self.acq_worker.start()

        self.btn_run_pause.setEnabled(True)

    def _on_run_pause_clicked(self) -> None:
        self._set_running_state(not self.is_running)

    def _set_running_state(self, run: bool) -> None:
        if not self.is_initialized or self.acq_worker is None:
            return

        was_running = self.is_running
        self.is_running = run
        self.acq_worker.set_paused(not run)

        if run:
            self.btn_run_pause.setText("Pause")
            self.btn_init.setEnabled(False)
            self.combo_bw.setEnabled(False)
            self.spin_int_time.setEnabled(False)
            self.status_bar.showMessage(f"Acquisition RUNNING ({self.bw_str}, {self.int_time_ms} ms)")
        else:
            self.btn_run_pause.setText("Start")
            self.btn_init.setEnabled(True)
            self.combo_bw.setEnabled(True)
            self.spin_int_time.setEnabled(True)
            self.status_bar.showMessage("Acquisition PAUSED. Plot inspection active.")
            
            # Requirement: Flush cache on transition from Running -> Paused
            if was_running:
                self._flush_cache(reason="Running -> Paused")

    def _on_logging_toggled(self, checked: bool) -> None:
        was_logging = self.logging_enabled
        self.logging_enabled = checked

        # Requirement: Flush cache when Logging is toggled Enabled -> Disabled while running
        if was_logging and not checked and self.is_running:
            self._flush_cache(reason="Logging Disabled while Running")

    # --- Data Ingestion & Cache Flushing ---

    def _on_spectrum_received(self, raw_spec: np.ndarray, t_start: float, t_end: float) -> None:
        if not self.is_running:
            return

        # Cache raw integer bins and timestamps if logging is active
        if self.logging_enabled:
            if not self.cache_t:
                self.cache_t.append(t_start)
            self.cache_t.append(t_end)
            self.cache_d.append(raw_spec.copy())
            self.lbl_cache.setText(f"Cached: {len(self.cache_d)}")

        # Compute physical power representation for display
        amplitude = raw_spec.astype(np.float64)
        spectrum = np.maximum(amplitude ** 2, self.floor)

        if self.current_spectrum is not None and self.current_spectrum.shape != spectrum.shape:
            self._clear_buffers()

        self.current_spectrum = spectrum
        self.n_spectra += 1

        if self.running_average is None or self.n_spectra == 1:
            self.running_average = spectrum.copy()
        else:
            self.running_average += (spectrum - self.running_average) / self.n_spectra

        self.history.append(spectrum)
        if len(self.history) > self.max_history:
            self.history.pop(0)

        self._redraw_canvas(autoscale=True)

    def _on_acquisition_error(self, err_msg: str) -> None:
        self.status_bar.showMessage(f"[Hardware I/O Fault] {err_msg}")

    def _flush_cache(self, reason: str = "") -> None:
        """Writes cached spectra to disk and clears the cache. Skips if cache is empty."""
        if not self.cache_d:
            return

        try:
            meta = save_spec(
                d=self.cache_d,
                t=self.cache_t,
                out_dir=self.out_dir,
                t_acc=self.int_time_ms,
                bw=self.bw_str,
            )
            self.status_bar.showMessage(
                f"[{reason}] Saved {meta['n_spectra']} spectra to {meta['file']}"
            )
        except Exception as exc:
            self.status_bar.showMessage(f"[Disk Write Error] Failed to save .spec file: {exc}")
            QMessageBox.warning(self, "Disk Write Error", f"Failed to save spectra:\n{exc}")
        finally:
            self.cache_d.clear()
            self.cache_t.clear()
            self.lbl_cache.setText("Cached: 0")

    # --- Plotting & Interactive Inspection ---

    def _apply_y_scale(self, y_data: np.ndarray) -> np.ndarray:
        if self.y_mode == "linear":
            return y_data
        elif self.y_mode == "log":
            return np.log10(y_data)
        return 10.0 * np.log10(y_data)

    def _update_plot_labels(self) -> None:
        unit_x = f"Frequency [MHz] (BW: {self.bw_ghz} GHz)" if self.x_mode == "frequency" else "Bin Index"
        self.ax.set_xlabel(unit_x)

        if self.y_mode == "linear":
            self.ax.set_ylabel("Power (Linear)")
        elif self.y_mode == "log":
            self.ax.set_ylabel("Power (Log10)")
        else:
            self.ax.set_ylabel("Power [dBm]")

        self.ax.set_title(
            f"x: {self.x_mode} | y: {self.y_mode} | d: {self.display_mode} | "
            f"N_avg: {self.n_spectra}"
        )
        self.ax.legend(
            handles=[self.line_average] if self.display_mode == "average" else [self.line_current],
            loc="upper right",
        )
        self.canvas.draw_idle()

    def _redraw_canvas(self, autoscale: bool = False) -> None:
        if self.current_spectrum is None:
            self.canvas.draw_idle()
            return

        curr_spec = self.current_spectrum
        n_bins = len(curr_spec)
        x_vals = (
            np.linspace(0.0, self.bw_ghz * 1000.0, n_bins)
            if self.x_mode == "frequency"
            else np.arange(n_bins, dtype=np.float64)
        )

        self.line_current.set_visible(False)
        self.line_average.set_visible(False)
        self.line_collection.set_visible(False)

        if self.display_mode == "current":
            self.line_current.set_data(x_vals, self._apply_y_scale(curr_spec))
            self.line_current.set_color("blue")
            self.line_current.set_visible(True)

        elif self.display_mode == "average" and self.running_average is not None:
            self.line_average.set_data(x_vals, self._apply_y_scale(self.running_average))
            self.line_average.set_visible(True)

        elif self.display_mode == "history":
            segments = [np.column_stack([x_vals, self._apply_y_scale(h)]) for h in self.history]
            self.line_collection.set_segments(segments)
            self.line_collection.set_visible(True)

            self.line_current.set_data(x_vals, self._apply_y_scale(curr_spec))
            self.line_current.set_color("red")
            self.line_current.set_visible(True)

        # Preserve manual zoom/pan state if user is actively inspecting with the toolbar
        if autoscale and not self.toolbar.mode:
            self.ax.relim()
            self.ax.autoscale_view()

        self._update_plot_labels()

    def _on_display_mode_changed(self, mode: str) -> None:
        self.display_mode = mode
        self._redraw_canvas(autoscale=True)

    def _on_x_mode_changed(self, mode: str) -> None:
        self.x_mode = mode
        self._redraw_canvas(autoscale=True)
        # Reset toolbar view history on axis coordinate system change
        self.toolbar.update()

    def _on_y_mode_changed(self, mode: str) -> None:
        self.y_mode = mode
        self._redraw_canvas(autoscale=True)
        self.toolbar.update()

    def _clear_buffers(self) -> None:
        self.n_spectra = 0
        self.history.clear()
        self.running_average = (
            self.current_spectrum.copy() if self.current_spectrum is not None else None
        )
        if self.current_spectrum is not None:
            self.n_spectra = 1
            self.history.append(self.current_spectrum.copy())
        self._redraw_canvas(autoscale=True)

    # --- Keyboard Shortcuts & Application Lifecycle ---

    def keyPressEvent(self, event: Any) -> None:
        key = event.text().lower()
        if key == "x":
            new_x = "bins" if self.x_mode == "frequency" else "frequency"
            self.combo_x.setCurrentText(new_x)
        elif key == "y":
            modes = ["linear", "log", "dBm"]
            self.combo_y.setCurrentText(modes[(modes.index(self.y_mode) + 1) % len(modes)])
        elif key == "d":
            modes = ["current", "average", "history"]
            self.combo_display.setCurrentText(modes[(modes.index(self.display_mode) + 1) % len(modes)])
        elif key == "c":
            self._clear_buffers()
        elif key == " ":
            if self.btn_run_pause.isEnabled():
                self._on_run_pause_clicked()
        elif key == "q":
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        # Stop background acquisition thread
        if self.acq_worker is not None:
            self.acq_worker.stop()
            self.acq_worker.wait(2000)

        if self.init_worker is not None and self.init_worker.isRunning():
            self.init_worker.wait(2000)

        # Requirement: Automatically flush any remaining cached spectra on application close
        self._flush_cache(reason="Application Close")

        # Cleanly close libpcap descriptor
        if self.pmc is not None and self.pmc.pd is not None:
            try:
                self.pmc.disconnect()
            except Exception:
                pass

        event.accept()


def main() -> None:
    app = QApplication(sys.argv)
    window = SpectrometerWindow(dev_name=b"eth0", out_dir="data/spectra")
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()