"""Projector-friendly Tkinter dashboard; all interactions remain simulated."""

import csv
import math
import queue
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

from controller import AppController
from services.csv_export import export_trials
from services.simulation import summarize_trials


NAVY = "#10243a"
BLUE = "#164e78"
PALE = "#f3f6fa"
INK = "#172b3e"
MUTED = "#536579"


class DemoApp:
    PAGES = ("Live Demo", "Trials & Chart", "Cards", "Settings")

    def __init__(self, controller: AppController | None = None) -> None:
        self.controller = controller or AppController()
        self.root = tk.Tk()
        self.root.title("NFC Relay Delay Demo")
        self.root.geometry("1180x800")
        self.root.minsize(960, 680)
        self.root.configure(bg=PALE)
        self.style = ttk.Style(self.root)
        self.style.configure("TButton", padding=(12, 9), font=("Segoe UI", 10, "bold"))
        self.style.configure("Treeview", rowheight=30, font=("Segoe UI", 10))
        self.style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
        self.current_page = None
        self._build_shell()
        self.show_page("Live Demo")
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.after(100, self._poll_serial_events)

    def _build_shell(self) -> None:
        header = tk.Frame(self.root, bg=NAVY, height=78)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="NFC RELAY DELAY DEMO", bg=NAVY, fg="white",
                 font=("Segoe UI", 19, "bold")).pack(side="left", padx=24)
        self.mode_banner = tk.Label(header, text="", bg="#ffe5b4", fg="#552e00",
                                    font=("Segoe UI", 11, "bold"), padx=14, pady=8)
        self.mode_banner.pack(side="right", padx=20, pady=15)

        body = tk.Frame(self.root, bg=PALE)
        body.pack(fill="both", expand=True)
        self.nav = tk.Frame(body, bg=NAVY, width=220)
        self.nav.pack(side="left", fill="y")
        self.nav.pack_propagate(False)
        tk.Label(self.nav, text="NAVIGATION", bg=NAVY, fg="#c9d7e5",
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=20, pady=(24, 12))
        self.nav_buttons = {}
        for page in self.PAGES:
            b = tk.Button(self.nav, text=page, command=lambda p=page: self.show_page(p),
                          anchor="w", padx=20, pady=14, bd=0, cursor="hand2",
                          bg=NAVY, fg="white", activebackground=BLUE, activeforeground="white",
                          font=("Segoe UI", 12, "bold"))
            b.pack(fill="x", padx=10, pady=3)
            self.nav_buttons[page] = b
        self.content = tk.Frame(body, bg=PALE)
        self.content.pack(side="left", fill="both", expand=True, padx=24, pady=20)
        self.content_root = self.content

    def _clear(self):
        for child in self.content_root.winfo_children():
            child.destroy()

    def _heading(self, title: str, subtitle: str):
        tk.Label(self.content, text=title, bg=PALE, fg=INK,
                 font=("Segoe UI", 23, "bold")).pack(anchor="w")
        tk.Label(self.content, text=subtitle, bg=PALE, fg=MUTED,
                 font=("Segoe UI", 11), wraplength=900, justify="left").pack(anchor="w", pady=(4, 18))

    def _card(self, parent, title, fill="white"):
        frame = tk.Frame(parent, bg=fill, highlightbackground="#d4dde7", highlightthickness=1)
        tk.Label(frame, text=title, bg=fill, fg=INK, font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=(13, 8))
        return frame

    def show_page(self, name: str) -> None:
        if name not in self.PAGES:
            raise ValueError(f"unknown page: {name}")
        if self.current_page == "Settings":
            self.root.unbind_all("<MouseWheel>")
        self.current_page = name
        self.content = self.content_root
        self._refresh_mode_banner()
        for page, button in self.nav_buttons.items():
            button.configure(bg=BLUE if page == name else NAVY)
        self._clear()
        {"Live Demo": self._live_page, "Trials & Chart": self._trials_page,
         "Cards": self._cards_page, "Settings": self._settings_page}[name]()

    def _live_page(self):
        self._heading("Live Demo", "SIMULATION VALUES are illustrative examples, not measurements from Unit A. Hardware mode remains read-only until its firmware messages are verified.")
        devices = tk.Frame(self.content, bg=PALE)
        devices.pack(fill="x", pady=(0, 14))
        self.device_card_widgets = {}
        for code, title, detail in (("A", "Unit A · Verifier", "Verifier simulation state"),
                                    ("B", "Unit B · Reader", "Reader simulation state"),
                                    ("C", "Unit C · Relay", "Relay simulation state")):
            card = self._card(devices, title)
            card.pack(side="left", fill="both", expand=True, padx=(0, 10))
            status_label = tk.Label(card, text="", bg="white", fg=INK, font=("Segoe UI", 15, "bold"))
            status_label.pack(anchor="w", padx=16)
            detail_label = tk.Label(card, text="", bg="white", fg=MUTED, font=("Segoe UI", 10))
            detail_label.pack(anchor="w", padx=16, pady=(4, 14))
            self.device_card_widgets[code] = (status_label, detail_label)
            if self.controller.simulation_mode:
                status = self.controller.simulation.devices[code]
                ttk.Button(card, text="Simulate disconnect" if status.connected else "Simulate reconnect",
                           command=lambda unit=code, connected=not status.connected: self._toggle_device(unit, connected)).pack(anchor="w", padx=14, pady=(0, 12))
        self._refresh_device_status_widgets()

        controls = self._card(self.content, "TRIAL CONTROLS")
        controls.pack(fill="x", pady=(0, 14))
        row = tk.Frame(controls, bg="white"); row.pack(fill="x", padx=14, pady=(0, 12))
        self.trial_buttons = []
        for label, callback in (("Direct Trial", lambda: self._run_simulated("direct")),
                                ("Relay Trial", lambda: self._run_simulated("relay")),
                                ("Run Configured Route", lambda: self._run_simulated(self.controller.simulation.selected_route)),
                                ("Calibration", self._toggle_calibration),
                                ("Stop", self._stop)):
            button = ttk.Button(row, text=label, command=callback)
            button.pack(side="left", padx=5)
            self.trial_buttons.append(button)
        self.calibration_label = tk.Label(row, text="Calibration: OFF", bg="white", fg=MUTED, font=("Segoe UI", 10, "bold"))
        self.calibration_label.pack(side="right", padx=8)
        self.calibration_label.configure(text="Calibration: ON" if self.controller.calibration_enabled else "Calibration: OFF")
        self._update_simulation_controls()
        tk.Label(controls, text=(f"Simulation configuration · threshold {self.controller.threshold_ms:g} ms · "
                                 f"route {self.controller.simulation.selected_route.title()} · "
                                 f"relay delay {self.controller.simulation.relay_delay_ms_per_hop} ms/hop"),
                 bg="white", fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", padx=20, pady=(0, 10))

        trial = self.controller.latest_trial
        card_title = ("LATEST DECISION · SIMULATED EXAMPLE" if self.controller.simulation_mode
                      else "HARDWARE MODE · UNVERIFIED SERIAL TEXT")
        result = self._card(self.content, card_title)
        result.pack(fill="both", expand=True)
        self.result_panel = result
        self._render_decision(trial)

    def _render_decision(self, trial):
        panel = self.result_panel
        for widget in panel.winfo_children()[1:]: widget.destroy()
        missing_units = []
        if not trial:
            if self.controller.simulation_mode:
                needed = ("A", "B", "C") if self.controller.simulation.selected_route == "relay" else ("A", "B")
                missing_units = [unit for unit in needed if not self.controller.simulation.devices[unit].connected]
            else:
                missing_units = [unit for unit, state in self.controller.serial_states.items() if state != "connected"]
        if missing_units:
            text = "DEVICE DISCONNECTED"
            reason = "Unavailable: " + ", ".join(f"Unit {unit}" for unit in missing_units) + ". No decision or RTT is available."
            color = "#46586a"
            trial = None
        elif not trial:
            if not self.controller.simulation_mode:
                text, reason, color = "WAITING FOR CARD", "Serial data is diagnostic only until the firmware message format is verified. No decision or RTT is inferred.", "#46586a"
            elif self.controller.simulation_running:
                text, reason, color = "WAITING FOR CARD", "No simulated trial has been run yet.", "#46586a"
            else:
                text, reason, color = "SIMULATION STOPPED", "The simulator is stopped. New simulated trials are disabled.", "#46586a"
        else:
            palette = {"granted": ("ACCESS GRANTED", "#176b3a"), "denied": ("ACCESS DENIED", "#9b2424"),
                       "relay_suspected": ("RELAY DELAY SUSPECTED", "#8a4b08"), "error": ("ERROR", "#46586a")}
            text, color = palette.get(trial.decision, ("ERROR", "#46586a"))
            reason = trial.reason
        tk.Label(panel, text=text, bg="white", fg=color, font=("Segoe UI", 25, "bold")).pack(anchor="w", padx=18, pady=(3, 4))
        tk.Label(panel, text=reason, bg="white", fg=INK, font=("Segoe UI", 13), wraplength=850, justify="left").pack(anchor="w", padx=18, pady=(0, 12))
        values = [
            ("UID", trial.uid_display if trial else "—"), ("Source unit", trial.source_unit if trial else "—"),
            ("Route · simulated", trial.route.title() if trial else "—"),
            ("Wi-Fi challenge-response RTT · simulated", f"{trial.rtt_ms:g} ms" if trial and self._valid_rtt(trial.rtt_ms) else "—"),
            ("Configured threshold", f"{trial.threshold_ms:g} ms" if trial and trial.threshold_ms is not None else "—"),
            ("Proof status", self._truth(trial.proof_valid) if trial else "—"),
            ("Secret status", ("Used" if trial.secret_used else "Not used") if trial and trial.secret_used is not None else "—"),
            ("App receive time", trial.received_at.strftime("%Y-%m-%d %H:%M:%S") if trial else "—"),
        ]
        grid = tk.Frame(panel, bg="white"); grid.pack(fill="x", padx=14, pady=(0, 12))
        for i, (label, value) in enumerate(values):
            cell = tk.Frame(grid, bg="#f3f6fa"); cell.grid(row=i // 4, column=i % 4, sticky="ew", padx=4, pady=4)
            tk.Label(cell, text=label, bg="#f3f6fa", fg=MUTED, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=9, pady=(7, 1))
            tk.Label(cell, text=value, bg="#f3f6fa", fg=INK, font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=9, pady=(0, 7))
            grid.grid_columnconfigure(i % 4, weight=1)
        tk.Label(panel, text="Illustrative local data only. No desktop timing is used to calculate verifier RTT.", bg="white", fg=MUTED,
                 font=("Segoe UI", 9, "italic")).pack(anchor="w", padx=18, pady=(0, 12))

    @staticmethod
    def _truth(value):
        return "Valid" if value is True else "Invalid" if value is False else "Unknown"

    def _run_simulated(self, route):
        if not self.controller.simulation_mode or not self.controller.simulation_running:
            return
        try:
            self.controller.run_simulated_trial(route)
        except (RuntimeError, ValueError) as exc:
            messagebox.showerror("Simulated trial unavailable", str(exc), parent=self.root)
            return
        self.show_page("Live Demo")

    def _toggle_device(self, unit, connected):
        self.controller.set_simulated_device_connected(unit, connected)
        self.show_page("Live Demo")

    def _toggle_calibration(self):
        value = self.controller.toggle_calibration()
        self.calibration_label.configure(text="Calibration: ON" if value else "Calibration: OFF")
        if hasattr(self, "calibration_var"):
            self.calibration_var.set(value)

    def _update_simulation_controls(self):
        if not hasattr(self, "trial_buttons"):
            return
        running = self.controller.simulation_running
        direct_ready = all(self.controller.simulation.devices[u].connected for u in ("A", "B"))
        relay_ready = all(self.controller.simulation.devices[u].connected for u in ("A", "B", "C"))
        configured_ready = relay_ready if self.controller.simulation.selected_route == "relay" else direct_ready
        enabled = (self.controller.simulation_mode and direct_ready,
                   self.controller.simulation_mode and relay_ready,
                   self.controller.simulation_mode and configured_ready,
                   self.controller.simulation_mode, self.controller.simulation_mode and running)
        for button, can_run in zip(self.trial_buttons, enabled):
            button.configure(state="normal" if running and can_run else "disabled")

    def _stop(self):
        self.controller.stop_simulation()
        self.show_page("Live Demo")

    def _trials_page(self):
        self._heading("Trials & Chart", "Simulation rows are clearly marked. RTT shown here is illustrative and is not reported by connected firmware.")
        toolbar = tk.Frame(self.content, bg=PALE); toolbar.pack(fill="x", pady=(0, 10))
        ttk.Button(toolbar, text="Export CSV", command=self._export_csv).pack(side="left", padx=(0, 8))
        ttk.Button(toolbar, text="Clear Session", command=self._clear_session).pack(side="left")
        table_card = self._card(self.content, "SESSION TRIALS · SIMULATED")
        table_card.pack(fill="both", expand=True)
        columns = ("time", "path", "reader", "rtt", "threshold", "decision", "proof")
        headings = ("App time", "Path", "Reader", "RTT · simulated", "Threshold · configured", "Decision · simulated", "Proof / secret")
        table_wrap = tk.Frame(table_card, bg="white")
        table_wrap.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        table = ttk.Treeview(table_wrap, columns=columns, show="headings", height=8)
        for key, heading, width in zip(columns, headings, (165, 95, 100, 100, 100, 190, 145)):
            table.heading(key, text=heading); table.column(key, width=width, anchor="w")
        vertical = ttk.Scrollbar(table_wrap, orient="vertical", command=table.yview)
        horizontal = ttk.Scrollbar(table_wrap, orient="horizontal", command=table.xview)
        table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        table.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        table_wrap.grid_rowconfigure(0, weight=1)
        table_wrap.grid_columnconfigure(0, weight=1)
        self.trial_table = table
        self._refresh_trials()
        chart = self._card(self.content, "DIRECT VS RELAY RTT · SIMULATED EXAMPLES")
        chart.pack(fill="x", pady=(12, 0))
        tk.Label(chart, text="Illustrative simulator output only · not measurements reported by Unit A",
                 bg="white", fg="#8a4b08", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=16)
        tk.Label(chart, text="Small sample counts or overlapping direct and relay ranges make the comparison inconclusive.",
                 bg="white", fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", padx=16)
        self.chart_canvas = tk.Canvas(chart, height=170, bg="white", highlightthickness=0)
        self.chart_canvas.pack(fill="x", padx=12, pady=4)
        self.chart_canvas.bind("<Configure>", lambda _event: self._draw_comparison())
        self.stats_label = tk.Label(chart, text="", bg="white", fg=INK, font=("Segoe UI", 10), justify="left")
        self.stats_label.pack(anchor="w", padx=16, pady=(0, 12))
        self._draw_comparison()

    def _refresh_trials(self):
        if not hasattr(self, "trial_table") or not self.trial_table.winfo_exists(): return
        self.trial_table.delete(*self.trial_table.get_children())
        for trial in self.controller.session.trials:
            rtt = f"{trial.rtt_ms:g} ms" if self._valid_rtt(trial.rtt_ms) else "—"
            self.trial_table.insert("", "end", values=(trial.received_at.strftime("%H:%M:%S"), trial.route.title(),
                "Unit B", rtt,
                f"{trial.threshold_ms:g} ms" if trial.threshold_ms is not None else "—",
                f"SIMULATED · {trial.decision.replace('_', ' ').title()}",
                f"{self._truth(trial.proof_valid)} / {'used' if trial.secret_used else 'not used'}"))

    def _draw_comparison(self):
        if not hasattr(self, "chart_canvas") or not self.chart_canvas.winfo_exists():
            return
        canvas = self.chart_canvas
        canvas.delete("all")
        samples = self.controller.session.trials
        threshold = self.controller.threshold_ms
        summary = summarize_trials(samples, threshold)
        width = max(360, canvas.winfo_width())
        left, right, top, bottom = 78, width - 24, 22, 132
        values = [trial.rtt_ms for trial in samples if self._valid_rtt(trial.rtt_ms)]
        maximum = max([threshold, *values], default=threshold)
        scale_max = max(20.0, maximum * 1.15)
        canvas.create_line(left, bottom, right, bottom, fill="#8998a8")
        canvas.create_text(8, 43, text="DIRECT", anchor="w", fill=INK, font=("Segoe UI", 9, "bold"))
        canvas.create_text(8, 93, text="RELAY", anchor="w", fill=INK, font=("Segoe UI", 9, "bold"))
        canvas.create_text(left, 148, text="0 ms", anchor="w", fill=MUTED)
        canvas.create_text(right, 148, text=f"{scale_max:.0f} ms", anchor="e", fill=MUTED)
        threshold_x = left + (right - left) * min(threshold / scale_max, 1.0)
        canvas.create_line(threshold_x, top, threshold_x, bottom, fill="#a44125", dash=(5, 3), width=2)
        canvas.create_text(min(threshold_x + 4, right - 70), 8, text=f"Threshold {threshold:g} ms", anchor="w", fill="#8a2525", font=("Segoe UI", 9, "bold"))
        if not values:
            canvas.create_text((left + right) / 2, 78, text="No simulated RTT samples yet", fill=MUTED, font=("Segoe UI", 12))
        else:
            offsets = {"direct": 0, "relay": 0}
            for trial in samples:
                if not self._valid_rtt(trial.rtt_ms) or trial.route not in offsets:
                    continue
                offsets[trial.route] += 1
                x = left + (right - left) * trial.rtt_ms / scale_max
                base_y = 43 if trial.route == "direct" else 93
                y = base_y + ((offsets[trial.route] - 1) % 5 - 2) * 5
                color = "#206c45" if trial.route == "direct" else "#c17818"
                canvas.create_oval(x - 5, y - 5, x + 5, y + 5, fill=color, outline="")
        def fmt(value): return "—" if value is None else f"{value:g} ms"
        route_stats = summary["by_route"]
        self.stats_label.configure(text=(
            f"All paths: {summary['sample_count']} samples · min {fmt(summary['minimum'])} · "
            f"median {fmt(summary['median'])} · max {fmt(summary['maximum'])} · "
            f"configured threshold {threshold:g} ms\n"
            f"Direct: n={route_stats['direct']['sample_count']} · min {fmt(route_stats['direct']['minimum'])} · "
            f"median {fmt(route_stats['direct']['median'])} · max {fmt(route_stats['direct']['maximum'])}     "
            f"Relay: n={route_stats['relay']['sample_count']} · min {fmt(route_stats['relay']['minimum'])} · "
            f"median {fmt(route_stats['relay']['median'])} · max {fmt(route_stats['relay']['maximum'])}"
        ))

    def _export_csv(self):
        path = filedialog.asksaveasfilename(parent=self.root, title="Export simulated session", defaultextension=".csv",
                                            filetypes=(("CSV files", "*.csv"),))
        if path:
            try:
                export_trials(self.controller.session.trials, path)
            except (OSError, csv.Error, ValueError) as exc:
                self.controller.diagnostics.add("CSV", f"Export failed: {type(exc).__name__}: {exc}")
                messagebox.showerror("Export failed", f"Could not write the CSV file.\n{exc}", parent=self.root)
                return
            messagebox.showinfo("Export complete", "The in-memory simulated session was exported as CSV.", parent=self.root)

    @staticmethod
    def _valid_rtt(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0

    def _clear_session(self):
        if messagebox.askyesno("Clear session?", "Remove all trials from this in-memory session?", parent=self.root):
            self.controller.session.clear()
            self.controller.latest_trial = None
            self.show_page("Trials & Chart")

    def _cards_page(self):
        self._heading("Cards", "Workflow guidance from the design brief. Actions below change local demo status only; no card is read or provisioned.")
        tk.Label(self.content, text="Hardware enrollment, erase, and provisioning are unavailable until their firmware commands are verified.",
                 bg=PALE, fg="#8a2525", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 10))
        card = self._card(self.content, "UNIT A ENROLLMENT WORKFLOW"); card.pack(fill="x", pady=(0, 14))
        steps = (("N", "Enroll as normal, then tap the card."),
                 ("S", "Enroll as simulated suspicious, then tap the card."),
                 ("P", "Provision a supported MIFARE Classic card secret at Unit A’s local reader."),
                 ("L", "List enrollment and check whether a secret is provisioned."),
                 ("X", "Erase enrollment. Confirm before proceeding."))
        for code, description in steps:
            tk.Label(card, text=f"{code}   {description}", bg="white", fg=INK, anchor="w",
                     font=("Segoe UI", 12), wraplength=850, justify="left").pack(fill="x", padx=18, pady=6)
        tk.Label(card, text="Never enter or display a card secret here. The dashboard stores no secret, PSK, or HMAC.",
                 bg="white", fg="#8a2525", font=("Segoe UI", 11, "bold"), wraplength=850, justify="left").pack(anchor="w", padx=18, pady=12)
        actions = self._card(self.content, "LOCAL DEMO ACTIONS"); actions.pack(fill="x")
        row = tk.Frame(actions, bg="white"); row.pack(fill="x", padx=12, pady=(0, 10))
        for index, (label, action) in enumerate((
                ("Simulate N enrollment", lambda: self._card_action("N")),
                ("Simulate S enrollment", lambda: self._card_action("S")),
                ("Simulate secret status", lambda: self._card_action("P")),
                ("List demo status", lambda: self._card_action("L")),
                ("Erase demo enrollment", self._erase_demo))):
            ttk.Button(row, text=label, command=action).grid(row=index // 3, column=index % 3,
                                                              sticky="w", padx=4, pady=5)
        self.cards_status = tk.Label(actions, text=self.controller.card_status, bg="white", fg=MUTED, font=("Segoe UI", 10, "bold"))
        self.cards_status.pack(anchor="w", padx=18, pady=(0, 12))

    def _card_action(self, action):
        self.cards_status.configure(text=self.controller.card_action(action))

    def _erase_demo(self):
        if messagebox.askyesno("Erase demo enrollment?", "Clear the local simulated enrollment status? No hardware command will be sent.", parent=self.root):
            self.cards_status.configure(text=self.controller.erase_demo_enrollment())

    def _settings_page(self):
        canvas = tk.Canvas(self.content_root, bg=PALE, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.content_root, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        inner = tk.Frame(canvas, bg=PALE)
        inner_window = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(inner_window, width=event.width))
        self.settings_canvas = canvas
        self.content = inner
        canvas.bind_all("<MouseWheel>", lambda event, target=canvas: self._scroll_settings(event, target))
        self._heading("Settings", "Choose simulation or read-only hardware monitoring. The firmware command and response contract is unavailable, so this app sends no serial commands.")
        mode_card = self._card(self.content, "OPERATING MODE"); mode_card.pack(fill="x", pady=(0, 12))
        self.mode_var = tk.StringVar(value=self.controller.active_mode)
        row = tk.Frame(mode_card, bg="white"); row.pack(fill="x", padx=16, pady=(0, 12))
        ttk.Radiobutton(row, text="Simulation mode", value="simulation", variable=self.mode_var,
                        command=lambda: self._change_mode("simulation")).pack(side="left", padx=(0, 20))
        ttk.Radiobutton(row, text="Hardware mode (read only)", value="hardware", variable=self.mode_var,
                        command=lambda: self._change_mode("hardware")).pack(side="left")
        ports = self._card(self.content, "USB SERIAL PORTS · 115200 BAUD"); ports.pack(fill="x", pady=(0, 12))
        self.port_vars = {}
        self.port_combos = {}
        self.serial_row_widgets = {}
        available_ports = self._available_ports()
        for unit, label in (("A", "Unit A · Verifier"), ("B", "Unit B · Reader"), ("C", "Unit C · Relay")):
            row = tk.Frame(ports, bg="white"); row.pack(fill="x", padx=16, pady=5)
            tk.Label(row, text=label, bg="white", fg=INK, width=18, anchor="w", font=("Segoe UI", 10, "bold")).pack(side="left")
            port = tk.StringVar(value=self.controller.serial_ports[unit])
            self.port_vars[unit] = port
            port.trace_add("write", lambda *_args, u=unit, value=port: self.controller.serial_ports.__setitem__(u, value.get()))
            combo = ttk.Combobox(row, textvariable=port, values=available_ports, width=12)
            combo.pack(side="left", padx=4); self.port_combos[unit] = combo
            ttk.Combobox(row, values=("115200",), state="readonly", width=8).pack(side="left", padx=4)
            connect = ttk.Button(row, text="Connect", command=lambda u=unit: self._connect_device(u))
            connect.pack(side="left", padx=4)
            disconnect = ttk.Button(row, text="Disconnect", command=lambda u=unit: self._disconnect_device(u))
            disconnect.pack(side="left", padx=4)
            status_label = tk.Label(row, text="", bg="white", fg=MUTED, font=("Segoe UI", 9, "bold"), anchor="w")
            status_label.pack(side="left", padx=7, fill="x", expand=True)
            self.serial_row_widgets[unit] = (connect, disconnect, status_label)
        port_actions = tk.Frame(ports, bg="white"); port_actions.pack(fill="x", padx=16, pady=(4, 10))
        ttk.Button(port_actions, text="Refresh COM ports", command=self._refresh_port_lists).pack(side="left")
        tk.Label(port_actions, text="Select a different COM port for each board. Connection only reads serial text.",
                 bg="white", fg=MUTED, font=("Segoe UI", 9)).pack(side="left", padx=12)
        tk.Label(ports, text="Serial reads use a 250 ms timeout; idle polls are normal and do not count as responses.",
                 bg="white", fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", padx=16, pady=(0, 8))
        self._refresh_serial_rows()

        controls = self._card(self.content, "SIMULATION CONFIGURATION PREVIEW · VALUES ARE NOT SENT TO BOARDS"); controls.pack(fill="x")
        grid = tk.Frame(controls, bg="white"); grid.pack(fill="x", padx=16, pady=(0, 12))
        self.threshold = tk.StringVar(value=f"{self.controller.threshold_ms:g}")
        tk.Label(grid, text="Simulation threshold (ms)", bg="white", fg=INK).grid(row=0, column=0, sticky="w", pady=7)
        self.threshold_entry = ttk.Entry(grid, textvariable=self.threshold, width=12)
        self.threshold_entry.grid(row=0, column=1, sticky="w", padx=12)
        self.calibration_var = tk.BooleanVar(value=self.controller.calibration_enabled)
        ttk.Checkbutton(grid, text="Calibration mode (simulation)", variable=self.calibration_var,
                        command=lambda: self.controller.set_calibration(self.calibration_var.get())).grid(row=1, column=0, sticky="w", pady=7)
        self.secret_var = tk.BooleanVar(value=self.controller.simulation.require_secret_mode)
        ttk.Checkbutton(grid, text="Require-secret scenario (simulation only)", variable=self.secret_var,
                        command=lambda: self.controller.set_require_secret(self.secret_var.get())).grid(row=1, column=1, sticky="w", pady=7)
        tk.Label(grid, text="Simulated relay delay per hop", bg="white", fg=INK).grid(row=2, column=0, sticky="w", pady=7)
        ttk.Button(grid, text="−  10 ms per hop", command=lambda: self._delay(-10)).grid(row=2, column=1, sticky="w", padx=12)
        ttk.Button(grid, text="+  10 ms per hop", command=lambda: self._delay(10)).grid(row=2, column=2, sticky="w", padx=6)
        self.delay_label = tk.Label(grid, text=f"Simulated relay delay: {self.controller.simulation.relay_delay_ms_per_hop} ms per hop", bg="white", fg=INK, font=("Segoe UI", 10, "bold"))
        self.delay_label.grid(row=2, column=3, sticky="w", padx=10)
        self.route_var = tk.StringVar(value=self.controller.simulation.selected_route.title())
        tk.Label(grid, text="Configured simulation route", bg="white", fg=INK).grid(row=3, column=0, sticky="w", pady=7)
        ttk.Radiobutton(grid, text="Direct", value="Direct", variable=self.route_var,
                        command=lambda: self.controller.set_simulation_route(self.route_var.get().lower())).grid(row=3, column=1, sticky="w", padx=12)
        ttk.Radiobutton(grid, text="Relay", value="Relay", variable=self.route_var,
                        command=lambda: self.controller.set_simulation_route(self.route_var.get().lower())).grid(row=3, column=2, sticky="w")
        ttk.Button(grid, text="Save local preview", command=self._save_settings).grid(row=4, column=0, sticky="w", pady=(12, 4))
        self.settings_message = tk.Label(grid, text="", bg="white", fg=BLUE, font=("Segoe UI", 10, "bold"))
        self.settings_message.grid(row=4, column=1, columnspan=3, sticky="w", padx=12)
        self.diagnostic_card = self._card(self.content, "BOUNDED SERIAL DIAGNOSTICS · CREDENTIAL VALUES REDACTED")
        self.diagnostic_card.pack(fill="both", expand=True, pady=(12, 0))
        log_wrap = tk.Frame(self.diagnostic_card, bg="white"); log_wrap.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.diagnostic_text = tk.Text(log_wrap, height=7, wrap="word", state="disabled", font=("Consolas", 9),
                                       bg="#f8fafc", fg=INK)
        scroll = ttk.Scrollbar(log_wrap, orient="vertical", command=self.diagnostic_text.yview)
        self.diagnostic_text.configure(yscrollcommand=scroll.set)
        self.diagnostic_text.pack(side="left", fill="both", expand=True); scroll.pack(side="right", fill="y")
        self._refresh_diagnostics()

    @staticmethod
    def _scroll_settings(event, canvas):
        try:
            if canvas.winfo_exists():
                canvas.yview_scroll(-int(event.delta / 120), "units")
        except tk.TclError:
            pass

    def _available_ports(self):
        try:
            from serial.tools import list_ports
            return tuple(port.device for port in list_ports.comports())
        except (ImportError, OSError):
            return ()

    def _refresh_port_lists(self):
        ports = self._available_ports()
        for combo in self.port_combos.values():
            combo.configure(values=ports)
        if not ports:
            self.controller.diagnostics.add("USB", "No COM ports discovered (or PySerial port discovery unavailable).")
            self._refresh_diagnostics()

    def _change_mode(self, mode):
        self.controller.set_mode(mode)
        self.show_page("Settings")

    def _connect_device(self, unit):
        if self.controller.active_mode != "hardware":
            return
        try:
            port = self.port_vars[unit].get()
            self.controller.connect_serial(unit, port, 115200)
        except (ValueError, RuntimeError) as exc:
            self.controller.serial_states[unit] = "error"
            self.controller.serial_errors[unit] = str(exc)
            self.controller.diagnostics.add(unit, str(exc))
        self._refresh_serial_rows()
        self._refresh_diagnostics()

    def _disconnect_device(self, unit):
        self.controller.disconnect_serial(unit)
        if self.controller.serial_states[unit] not in ("disconnected", "error"):
            self.controller.serial_states[unit] = "disconnecting"
        self._refresh_serial_rows()

    def _refresh_serial_rows(self):
        for unit, (connect, disconnect, label) in self.serial_row_widgets.items():
            mode_is_hardware = self.controller.active_mode == "hardware"
            state = self.controller.serial_states[unit]
            connect.configure(state="normal" if mode_is_hardware and state in ("disconnected", "error") else "disabled")
            disconnect.configure(state="normal" if mode_is_hardware and state in ("connecting", "connected", "disconnecting") else "disabled")
            details = self.controller.serial_errors.get(unit, "")
            label.configure(text=(f"{state.upper()} · {details}" if details else state.upper()),
                            fg="#176b3a" if state == "connected" else "#8a2525" if state == "error" else MUTED)

    def _refresh_device_status_widgets(self):
        for unit, (status_label, detail_label) in getattr(self, "device_card_widgets", {}).items():
            try:
                if not status_label.winfo_exists():
                    continue
            except tk.TclError:
                continue
            if self.controller.simulation_mode:
                status = self.controller.simulation.devices[unit]
                status_label.configure(text="SIMULATED READY" if status.ready else "SIMULATED DISCONNECTED",
                                        fg="#176b3a" if status.ready else "#8a2525")
                detail_label.configure(text="Simulator state · no USB hardware connection")
            else:
                status = self.controller.hardware_status[unit]
                state = self.controller.serial_states[unit]
                label = "CONNECTED · READINESS UNVERIFIED" if state == "connected" else state.upper()
                status_label.configure(text=label, fg="#176b3a" if state == "connected" else "#8a2525" if state == "error" else MUTED)
                last = status.last_message_at.strftime("%H:%M:%S") if status.last_message_at else "none yet"
                detail_label.configure(text=f"{self.controller.serial_ports[unit] or 'No port selected'} · last line: {last}")

    def _poll_serial_events(self):
        changed_status = False
        while True:
            try:
                event = self.controller.serial_events.get_nowait()
            except queue.Empty:
                break
            unit, kind = event.get("unit", "?"), event.get("type")
            if kind == "status":
                state = event.get("state", "disconnected")
                if state == "connected":
                    self.controller.serial_states[unit] = "connected"
                    self.controller.serial_errors[unit] = ""
                    self.controller.hardware_status[unit].connected = True
                    self.controller.hardware_status[unit].ready = False
                    self.controller.diagnostics.add(unit, f"Serial connected on {event.get('port')} at {event.get('baudrate')} baud; readiness is unverified.")
                elif state in ("operator-disconnect", "disconnected"):
                    self.controller.serial_states[unit] = "error" if self.controller.serial_errors.get(unit) else "disconnected"
                    self.controller.hardware_status[unit].connected = False
                    self.controller.hardware_status[unit].ready = False
                    self.controller.diagnostics.add(unit, "Serial connection closed.")
                elif state == "connecting":
                    self.controller.serial_states[unit] = "connecting"
                changed_status = True
            elif kind == "error":
                self.controller.serial_errors[unit] = event.get("message", "Serial error")
                self.controller.serial_states[unit] = "error"
                self.controller.diagnostics.add(unit, self.controller.serial_errors[unit])
                changed_status = True
            elif kind == "line":
                self.controller.hardware_status[unit].last_message_at = datetime.now()
                self.controller.diagnostics.add(unit, f"{event.get('classification', 'unclassified')}: {event.get('message', '')}")
                changed_status = True
            else:
                self.controller.diagnostics.add(unit, event.get("message", "Serial diagnostic event"))
        self._refresh_serial_rows_if_visible()
        self._refresh_diagnostics_if_visible()
        if changed_status:
            self._refresh_device_status_widgets()
        self.root.after(100, self._poll_serial_events)

    def _refresh_serial_rows_if_visible(self):
        if hasattr(self, "serial_row_widgets"):
            try:
                if self.current_page == "Settings": self._refresh_serial_rows()
            except tk.TclError:
                pass

    def _refresh_diagnostics_if_visible(self):
        if self.current_page == "Settings": self._refresh_diagnostics()

    def _refresh_diagnostics(self):
        if not hasattr(self, "diagnostic_text") or not self.diagnostic_text.winfo_exists():
            return
        self.diagnostic_text.configure(state="normal")
        self.diagnostic_text.delete("1.0", "end")
        for entry in self.controller.diagnostics.entries:
            self.diagnostic_text.insert("end", entry + "\n")
        self.diagnostic_text.configure(state="disabled")
        self.diagnostic_text.see("end")

    def _refresh_mode_banner(self):
        if self.controller.simulation_mode:
            self.mode_banner.configure(text="SIMULATION MODE · no serial ports accessed", bg="#ffe5b4", fg="#552e00")
        else:
            self.mode_banner.configure(text="HARDWARE MODE · read-only serial monitoring", bg="#d8eaff", fg="#103c64")

    def _close(self):
        self.controller.shutdown_serial()
        self.root.destroy()

    def _delay(self, change):
        value = self.controller.adjust_relay_delay(change)
        self.delay_label.configure(text=f"Simulated relay delay: {value} ms per hop")

    def _settings_toggle_calibration(self):
        value = self.controller.toggle_calibration()
        self.calibration_var.set(value)

    def _save_settings(self):
        try:
            value = float(self.threshold.get())
            if not math.isfinite(value) or value <= 0: raise ValueError
        except ValueError:
            messagebox.showerror("Invalid threshold", "Enter a positive threshold in milliseconds.", parent=self.root)
            return
        self.controller.configure_threshold(value)
        self.settings_message.configure(text=f"Saved locally · {value:g} ms · configured {self.route_var.get()} route · not sent")

    def run(self) -> None:
        self.root.mainloop()
