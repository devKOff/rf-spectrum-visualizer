import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

import matplotlib

matplotlib.use("TkAgg")

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from scanner import NRF24SpectrumScanner


class SpectrumVisualizer:

    def __init__(self, root):

        self.root = root
        self.root.title(
            "nRF24L01 RF Spectrum Visualizer"
        )

        self.root.geometry("1100x750")

        self.scanner = None

        self.scanning = False
        self.scan_thread = None

        self.current_channel = 0
        self.current_frequency = 2400

        self.scan_count = 0
        self.scan_start_time = None

        # --------------------------------------------------
        # Main frame
        # --------------------------------------------------

        main_frame = ttk.Frame(root)
        main_frame.pack(
            fill=tk.BOTH,
            expand=True,
            padx=10,
            pady=10
        )

        # --------------------------------------------------
        # Control frame
        # --------------------------------------------------

        control_frame = ttk.Frame(main_frame)
        control_frame.pack(
            fill=tk.X,
            pady=(0, 10)
        )

        self.start_button = ttk.Button(
            control_frame,
            text="Start Scan",
            command=self.start_scan
        )

        self.start_button.pack(
            side=tk.LEFT,
            padx=5
        )

        self.stop_button = ttk.Button(
            control_frame,
            text="Stop Scan",
            command=self.stop_scan,
            state=tk.DISABLED
        )

        self.stop_button.pack(
            side=tk.LEFT,
            padx=5
        )

        self.clear_button = ttk.Button(
            control_frame,
            text="Clear",
            command=self.clear_graph
        )

        self.clear_button.pack(
            side=tk.LEFT,
            padx=5
        )

        # --------------------------------------------------
        # Information labels
        # --------------------------------------------------

        info_frame = ttk.Frame(main_frame)
        info_frame.pack(
            fill=tk.X,
            pady=(0, 10)
        )

        self.status_label = ttk.Label(
            info_frame,
            text="Status: Ready"
        )

        self.status_label.pack(
            side=tk.LEFT,
            padx=10
        )

        self.frequency_label = ttk.Label(
            info_frame,
            text="Frequency: -- MHz"
        )

        self.frequency_label.pack(
            side=tk.LEFT,
            padx=10
        )

        self.channel_label = ttk.Label(
            info_frame,
            text="Channel: --"
        )

        self.channel_label.pack(
            side=tk.LEFT,
            padx=10
        )

        self.rate_label = ttk.Label(
            info_frame,
            text="Sweep rate: -- sweeps/s"
        )

        self.rate_label.pack(
            side=tk.LEFT,
            padx=10
        )

        # --------------------------------------------------
        # Figure
        # --------------------------------------------------

        self.figure = Figure(
            figsize=(10, 7),
            dpi=90
        )

        self.ax_spectrum = self.figure.add_subplot(
            211
        )

        self.ax_waterfall = self.figure.add_subplot(
            212
        )

        # --------------------------------------------------
        # Spectrum graph
        # --------------------------------------------------

        self.frequencies = [
            2400 + i
            for i in range(126)
        ]

        self.activity = [
            0.0
            for _ in range(126)
        ]

        self.line, = self.ax_spectrum.plot(
            self.frequencies,
            self.activity,
            linewidth=1.5
        )

        self.ax_spectrum.set_title(
            "nRF24L01 2.4 GHz RF Activity"
        )

        self.ax_spectrum.set_xlabel(
            "Frequency (MHz)"
        )

        self.ax_spectrum.set_ylabel(
            "Relative RF Activity"
        )

        self.ax_spectrum.set_xlim(
            2400,
            2525
        )

        self.ax_spectrum.set_ylim(
            0,
            1
        )

        self.ax_spectrum.grid(
            True,
            alpha=0.3
        )

        # --------------------------------------------------
        # Waterfall
        # --------------------------------------------------

        self.waterfall_rows = []

        self.waterfall_image = self.ax_waterfall.imshow(
            [[0.0] * 126],
            aspect="auto",
            interpolation="nearest",
            origin="lower",
            extent=[
                2400,
                2525,
                0,
                1
            ],
            vmin=0,
            vmax=1
        )

        self.ax_waterfall.set_title(
            "RF Activity Waterfall"
        )

        self.ax_waterfall.set_xlabel(
            "Frequency (MHz)"
        )

        self.ax_waterfall.set_ylabel(
            "Time / Sweep"
        )

        self.ax_waterfall.set_xlim(
            2400,
            2525
        )

        # --------------------------------------------------
        # Canvas
        # --------------------------------------------------

        self.canvas = FigureCanvasTkAgg(
            self.figure,
            master=main_frame
        )

        self.canvas.get_tk_widget().pack(
            fill=tk.BOTH,
            expand=True
        )

        # --------------------------------------------------
        # Waterfall settings
        # --------------------------------------------------

        self.max_waterfall_rows = 80

        # --------------------------------------------------
        # Closing
        # --------------------------------------------------

        self.root.protocol(
            "WM_DELETE_WINDOW",
            self.on_close
        )

    # ======================================================
    # Start scanning
    # ======================================================

    def start_scan(self):

        if self.scanning:
            return

        try:

            self.scanner = NRF24SpectrumScanner(
                ce_pin=25,
                csn_pin=8,

                # Five measurements per channel.
                samples_per_channel=5,

                # 1 ms listening time per measurement.
                dwell_time=0.001
            )

            self.scanner.initialize()

        except Exception as error:

            messagebox.showerror(
                "Radio Error",
                str(error)
            )

            return

        self.scanning = True

        self.scan_count = 0
        self.scan_start_time = time.monotonic()

        self.start_button.config(
            state=tk.DISABLED
        )

        self.stop_button.config(
            state=tk.NORMAL
        )

        self.status_label.config(
            text="Status: Scanning"
        )

        self.scan_thread = threading.Thread(
            target=self.scan_loop,
            daemon=True
        )

        self.scan_thread.start()

    # ======================================================
    # Scanner thread
    # ======================================================

    def scan_loop(self):

        while self.scanning:

            try:

                activity = self.scanner.scan()

                if not self.scanning:
                    break

                self.root.after(
                    0,
                    self.update_graph,
                    activity
                )

            except Exception as error:

                self.root.after(
                    0,
                    self.scan_error,
                    str(error)
                )

                break

    # ======================================================
    # Update GUI
    # ======================================================

    def update_graph(self, activity):

        if not self.scanning:
            return

        self.activity = activity

        self.line.set_ydata(
            self.activity
        )

        # ----------------------------------------------
        # Find strongest channel
        # ----------------------------------------------

        max_activity = max(
            self.activity
        )

        strongest_channel = self.activity.index(
            max_activity
        )

        strongest_frequency = (
            2400 +
            strongest_channel
        )

        self.current_channel = (
            strongest_channel
        )

        self.current_frequency = (
            strongest_frequency
        )

        self.frequency_label.config(
            text=(
                f"Strongest: "
                f"{strongest_frequency} MHz"
            )
        )

        self.channel_label.config(
            text=(
                f"Channel: "
                f"{strongest_channel}"
            )
        )

        # ----------------------------------------------
        # Waterfall
        # ----------------------------------------------

        self.waterfall_rows.append(
            activity.copy()
        )

        if len(self.waterfall_rows) > self.max_waterfall_rows:

            self.waterfall_rows.pop(0)

        self.waterfall_image.set_data(
            self.waterfall_rows
        )

        self.waterfall_image.set_extent(
            [
                2400,
                2525,
                0,
                max(
                    1,
                    len(self.waterfall_rows)
                )
            ]
        )

        self.ax_waterfall.set_ylim(
            0,
            max(
                1,
                len(self.waterfall_rows)
            )
        )

        # ----------------------------------------------
        # Sweep rate
        # ----------------------------------------------

        self.scan_count += 1

        elapsed = (
            time.monotonic()
            - self.scan_start_time
        )

        if elapsed > 0:

            rate = (
                self.scan_count /
                elapsed
            )

            self.rate_label.config(
                text=(
                    f"Sweep rate: "
                    f"{rate:.2f} sweeps/s"
                )
            )

        self.canvas.draw_idle()

    # ======================================================
    # Scan error
    # ======================================================

    def scan_error(self, error):

        self.scanning = False

        self.start_button.config(
            state=tk.NORMAL
        )

        self.stop_button.config(
            state=tk.DISABLED
        )

        self.status_label.config(
            text="Status: Error"
        )

        messagebox.showerror(
            "Scanner Error",
            error
        )

    # ======================================================
    # Stop
    # ======================================================

    def stop_scan(self):

        if not self.scanning:
            return

        self.scanning = False

        if self.scanner:

            self.scanner.stop()

        self.start_button.config(
            state=tk.NORMAL
        )

        self.stop_button.config(
            state=tk.DISABLED
        )

        self.status_label.config(
            text="Status: Stopped"
        )

    # ======================================================
    # Clear
    # ======================================================

    def clear_graph(self):

        self.activity = [
            0.0
            for _ in range(126)
        ]

        self.waterfall_rows.clear()

        self.line.set_ydata(
            self.activity
        )

        self.waterfall_image.set_data(
            [[0.0] * 126]
        )

        self.waterfall_image.set_extent(
            [
                2400,
                2525,
                0,
                1
            ]
        )

        self.ax_waterfall.set_ylim(
            0,
            1
        )

        self.canvas.draw_idle()

        self.frequency_label.config(
            text="Strongest: -- MHz"
        )

        self.channel_label.config(
            text="Channel: --"
        )

    # ======================================================
    # Close application
    # ======================================================

    def on_close(self):

        self.scanning = False

        if self.scanner:

            self.scanner.stop()

        self.root.destroy()


def main():

    root = tk.Tk()

    app = SpectrumVisualizer(
        root
    )

    root.mainloop()


if __name__ == "__main__":
    main()