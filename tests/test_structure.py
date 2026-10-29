"""Headless smoke tests for the initial project structure."""

import csv
import math
import random
import tempfile
import tkinter as tk
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import DemoApp
from controller import AppController
from devices.parser import UnitAParser
from models import DeviceStatus, Trial
from services.csv_export import export_trials
from services.session import Session
from services.simulation import SimulationService, summarize_trials


class StructureSmokeTests(unittest.TestCase):
    def test_navigation_and_simulation_are_declared(self):
        self.assertEqual(DemoApp.PAGES, ("Live Demo", "Trials & Chart", "Cards", "Settings"))
        self.assertTrue(AppController().simulation_mode)

    def test_simulated_trials_and_session_clear(self):
        controller = AppController(SimulationService(rng=random.Random(0)))
        direct = controller.run_simulated_trial("direct")
        relay = controller.run_simulated_trial("relay")
        self.assertEqual((direct.decision, relay.decision), ("granted", "relay_suspected"))
        self.assertEqual(len(controller.session.trials), 2)
        self.assertIn("Simulated", relay.reason)
        controller.session.clear()
        self.assertEqual(controller.session.trials, [])

    def test_card_workflow_never_accepts_or_persists_secret(self):
        controller = AppController()
        message = controller.card_action("P")
        self.assertIn("No secret was entered or stored", message)
        self.assertIn("Simulated normal enrollment", controller.card_action("N"))
        self.assertIn("cleared", controller.erase_demo_enrollment())

    def test_models_services_and_unverified_parser_import(self):
        self.assertFalse(DeviceStatus("A").connected)
        self.assertEqual(UnitAParser().classify("unverified firmware line").kind, "unclassified")
        self.assertEqual(Session().trials, [])
        self.assertTrue(callable(export_trials))
        self.assertEqual(Trial.__name__, "Trial")

    def test_simulation_fixture_is_reproducible_and_records_fields(self):
        first = SimulationService(rng=random.Random(25))
        second = SimulationService(rng=random.Random(25))
        a = first.generate_trial(session_id=1, route="direct", threshold_ms=60)
        b = second.generate_trial(session_id=1, route="direct", threshold_ms=60)
        self.assertEqual((a.rtt_ms, a.proof_valid, a.secret_used, a.decision),
                         (b.rtt_ms, b.proof_valid, b.secret_used, b.decision))
        self.assertTrue(30 <= a.rtt_ms <= 60)
        self.assertEqual(a.uid_display, "••••••••")
        self.assertEqual(a.threshold_ms, 60)
        self.assertEqual(first.devices["A"].ready, True)
        self.assertEqual(first.devices["B"].ready, True)
        self.assertEqual(first.devices["C"].ready, True)

    def test_relay_delay_calibration_disconnect_and_stop(self):
        simulation = SimulationService(rng=random.Random(2), initial_delay_ms_per_hop=0)
        direct = simulation.generate_trial(session_id=1, route="direct", threshold_ms=100)
        simulation.adjust_relay_delay(20)
        relay = simulation.generate_trial(session_id=2, route="relay", threshold_ms=100)
        self.assertGreaterEqual(relay.rtt_ms, 20)
        self.assertTrue(simulation.set_calibration(True))
        simulation.set_device_connected("C", False)
        unavailable = simulation.generate_trial(session_id=3, route="relay", threshold_ms=100)
        self.assertEqual(unavailable.decision, "error")
        self.assertTrue(simulation.set_calibration(True))
        simulation.stop()
        with self.assertRaises(RuntimeError):
            simulation.generate_trial(session_id=4, route="direct", threshold_ms=100)

    def test_controller_updates_simulated_connection_states_and_stops(self):
        controller = AppController(SimulationService(rng=random.Random(7)))
        controller.set_simulated_device_connected("B", False)
        unavailable = controller.run_simulated_trial("direct")
        self.assertEqual(unavailable.decision, "error")
        controller.stop_simulation()
        with self.assertRaises(RuntimeError):
            controller.run_simulated_trial("direct")

    def test_statistics_cover_populated_and_empty_datasets(self):
        summary = summarize_trials([], configured_threshold_ms=60)
        self.assertEqual(summary["sample_count"], 0)
        self.assertIsNone(summary["minimum"])
        self.assertIsNone(summary["median"])
        self.assertIsNone(summary["maximum"])
        controller = AppController(SimulationService(rng=random.Random(3)))
        controller.run_simulated_trial("direct")
        controller.run_simulated_trial("relay")
        summary = summarize_trials(controller.session.trials, 60)
        self.assertEqual(summary["sample_count"], 2)
        self.assertEqual(summary["configured_threshold_ms"], 60)
        self.assertEqual(summary["by_route"]["direct"]["sample_count"], 1)
        self.assertEqual(summary["by_route"]["relay"]["sample_count"], 1)

    def test_statistics_compute_route_min_median_max_and_ignore_missing_rtt(self):
        now = datetime(2026, 1, 1)
        trials = [
            Trial(1, now, "A", "direct", rtt_ms=10, threshold_ms=60),
            Trial(2, now, "A", "direct", rtt_ms=20, threshold_ms=60),
            Trial(3, now, "A", "direct", rtt_ms=40, threshold_ms=60),
            Trial(4, now, "B", "relay", rtt_ms=90, threshold_ms=60),
            Trial(5, now, "B", "relay", rtt_ms=None, threshold_ms=60, decision="error"),
            Trial(6, now, "A", "direct", rtt_ms=math.nan, threshold_ms=60, decision="error"),
        ]
        summary = summarize_trials(trials, configured_threshold_ms=60)
        self.assertEqual(summary["by_route"]["direct"],
                         {"sample_count": 3, "minimum": 10, "median": 20, "maximum": 40})
        self.assertEqual(summary["by_route"]["relay"],
                         {"sample_count": 1, "minimum": 90, "median": 90, "maximum": 90})
        self.assertEqual(summary["sample_count"], 4)

    def test_simulation_settings_are_effective_and_secrets_never_persist(self):
        simulation = SimulationService(rng=random.Random(8), initial_delay_ms_per_hop=0)
        simulation.set_route("relay")
        simulation.set_require_secret(True)
        simulation.set_calibration(True)
        trial = simulation.generate_trial(session_id=1, route=simulation.selected_route, threshold_ms=120)
        self.assertEqual(trial.secret_used, True)
        self.assertIn("Calibration demonstration", trial.reason)
        self.assertFalse(hasattr(trial, "card_secret"))

    def test_csv_export_contains_required_fields_and_redacts_sensitive_text(self):
        trial = Trial(session_id=7, received_at=datetime(2026, 2, 3, 4, 5, 6),
                      source_unit="Unit A", route="direct", rtt_ms=42.5,
                      threshold_ms=60, proof_valid=True, secret_used=True,
                      decision="granted", reason="secret=topsecret HMAC=" + "F" * 64)
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as folder:
            path = Path(folder) / "session.csv"
            export_trials([trial], path)
            contents = path.read_text(encoding="utf-8")
            self.assertNotIn("topsecret", contents)
            self.assertNotIn("F" * 64, contents)
            with path.open(encoding="utf-8", newline="") as input_file:
                rows = list(csv.DictReader(input_file))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["route"], "direct")
        self.assertEqual(rows[0]["rtt_ms"], "42.5")
        self.assertEqual(rows[0]["threshold_ms"], "60")
        self.assertEqual(rows[0]["proof_valid"], "True")
        self.assertEqual(rows[0]["secret_used"], "True")
        self.assertEqual(rows[0]["received_at"], "2026-02-03T04:05:06")
        self.assertIn("decision", rows[0])
        malformed = Trial(8, datetime(2026, 2, 3), "Unit A", "direct",
                          rtt_ms="secret=do-not-export", threshold_ms=60)
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as folder:
            path = Path(folder) / "safe.csv"
            export_trials([malformed], path)
            safe_contents = path.read_text(encoding="utf-8")
            with path.open(encoding="utf-8", newline="") as input_file:
                safe_rows = list(csv.DictReader(input_file))
        self.assertEqual(safe_rows[0]["rtt_ms"], "")
        self.assertNotIn("do-not-export", safe_contents)
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as folder:
            empty_path = Path(folder) / "empty.csv"
            export_trials([], empty_path)
            with empty_path.open(encoding="utf-8", newline="") as input_file:
                self.assertEqual(list(csv.DictReader(input_file)), [])

    def test_csv_export_failure_propagates_as_file_error_for_ui_handling(self):
        trial = AppController(SimulationService(rng=random.Random(4))).run_simulated_trial("direct")
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as folder:
            with self.assertRaises(OSError):
                export_trials([trial], Path(folder) / "missing" / "session.csv")

    def test_csv_export_ui_handles_write_failure(self):
        app_stub = SimpleNamespace(root=object(), controller=AppController())
        with patch("app.filedialog.asksaveasfilename", return_value="blocked.csv"), \
             patch("app.export_trials", side_effect=PermissionError("file is open")), \
             patch("app.messagebox.showerror") as show_error:
            DemoApp._export_csv(app_stub)
        show_error.assert_called_once()
        self.assertTrue(any("Export failed" in item for item in app_stub.controller.diagnostics.entries))

    def test_tk_settings_preserve_ports_and_keep_hardware_read_only(self):
        try:
            dashboard = DemoApp(AppController(SimulationService(rng=random.Random(9))))
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        try:
            dashboard.root.withdraw()
            dashboard.show_page("Settings")
            dashboard.port_vars["A"].set("COM17")
            self.assertEqual(dashboard.controller.serial_ports["A"], "COM17")
            self.assertIn("disabled", dashboard.serial_row_widgets["A"][0].state())
            dashboard._change_mode("hardware")
            self.assertEqual(dashboard.controller.active_mode, "hardware")
            self.assertNotIn("disabled", dashboard.serial_row_widgets["A"][0].state())
            self.assertEqual(dashboard.controller.session.trials, [])
            dashboard.show_page("Trials & Chart")
            dashboard.root.update_idletasks()
        finally:
            dashboard.root.destroy()

    def test_tk_repeated_trials_do_not_duplicate_live_page_widgets(self):
        try:
            dashboard = DemoApp(AppController(SimulationService(rng=random.Random(10))))
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        try:
            dashboard.root.withdraw()
            initial_widget_count = len(dashboard.content_root.winfo_children())
            dashboard._run_simulated("direct")
            self.assertEqual(len(dashboard.content_root.winfo_children()), initial_widget_count)
            dashboard._run_simulated("relay")
            self.assertEqual(len(dashboard.content_root.winfo_children()), initial_widget_count)
            self.assertEqual([trial.route for trial in dashboard.controller.session.trials], ["direct", "relay"])
        finally:
            dashboard.root.destroy()


if __name__ == "__main__":
    unittest.main()
