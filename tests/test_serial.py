"""Asynchronous serial adapter tests with mocked ports; no ESP32 is needed."""

import queue
import threading
import time
import unittest

from controller import AppController
from devices.parser import UnitAParser, UnitBParser, UnitCParser, sanitize_diagnostic
from devices.serial_adapter import UnitASerialAdapter, UnitBSerialAdapter, UnitCSerialAdapter
from services.diagnostics import DiagnosticLog


class FakeSerial:
    def __init__(self, chunks=()):
        self.chunks = list(chunks)
        self.closed = threading.Event()

    def readline(self):
        if self.chunks:
            return self.chunks.pop(0)
        self.closed.wait(0.01)
        return b""

    def close(self):
        self.closed.set()


def wait_for_event(events, predicate, timeout=1.5):
    deadline = time.monotonic() + timeout
    captured = []
    while time.monotonic() < deadline:
        try:
            event = events.get(timeout=0.05)
        except queue.Empty:
            continue
        captured.append(event)
        if predicate(event):
            return event, captured
    raise AssertionError(f"expected serial event not received; saw {captured!r}")


class SerialAdapterTests(unittest.TestCase):
    def test_each_unit_has_own_parser_and_only_candidate_classifications(self):
        self.assertEqual(UnitAParser().classify("Decision for card").kind, "decision-format-candidate")
        self.assertFalse(UnitAParser().classify("Decision for card").format_verified)
        self.assertEqual(UnitBParser().classify("PN532 ready").kind, "reader-ready-format-candidate")
        self.assertEqual(UnitCParser().classify("Relay status: connected").kind, "relay-status-format-candidate")

    def test_async_read_redacts_tokens_and_closes_without_writing(self):
        events = queue.Queue()
        fake = FakeSerial([b"PN532 ready\r\n",
                           b"secret=classroom uid=E4D93F02 HMAC=" + b"A" * 64 + b"\n",
                           b"\xff\n"])
        factory_calls = []

        def factory(port, baudrate, timeout):
            factory_calls.append((port, baudrate, timeout))
            return fake

        adapter = UnitBSerialAdapter("COM7", events, serial_factory=factory)
        adapter.connect()
        connected, _ = wait_for_event(events, lambda item: item.get("state") == "connected")
        self.assertEqual((connected["port"], connected["baudrate"]), ("COM7", 115200))
        data_event, _ = wait_for_event(events, lambda item: item.get("type") == "line")
        self.assertEqual(data_event["classification"], "reader-ready-format-candidate")
        safe_event, _ = wait_for_event(events, lambda item: item.get("type") == "line" and "secret" in item.get("message", ""))
        self.assertNotIn("classroom", safe_event["message"])
        self.assertNotIn("E4D93F02", safe_event["message"])
        self.assertNotIn("A" * 64, safe_event["message"])
        wait_for_event(events, lambda item: item.get("type") == "diagnostic")
        adapter.disconnect()
        adapter._thread.join(1)
        self.assertFalse(adapter.is_alive)
        self.assertTrue(fake.closed.is_set())
        self.assertEqual(factory_calls[0][:2], ("COM7", 115200))

    def test_permission_error_and_incomplete_line_are_diagnostics(self):
        events = queue.Queue()
        adapter = UnitASerialAdapter("COM9", events,
                                     serial_factory=lambda *_: (_ for _ in ()).throw(PermissionError("port busy")))
        adapter.connect(); adapter._thread.join(1)
        error, _ = wait_for_event(events, lambda item: item.get("type") == "error")
        self.assertIn("PermissionError", error["message"])
        wait_for_event(events, lambda item: item.get("type") == "status" and item.get("state") == "disconnected")

        fake = FakeSerial([b"partial without newline"])
        events = queue.Queue()
        adapter = UnitCSerialAdapter("COM10", events, serial_factory=lambda *_: fake)
        adapter.connect()
        incomplete, _ = wait_for_event(events, lambda item: item.get("type") == "diagnostic")
        self.assertIn("Incomplete serial line", incomplete["message"])
        adapter.disconnect(); adapter._thread.join(1)

    def test_controller_keeps_modes_separate_and_connects_units_independently(self):
        fakes = []

        def factory(port, baudrate, timeout):
            fake = FakeSerial()
            fakes.append((port, baudrate, fake))
            return fake

        controller = AppController(serial_factory=factory)
        with self.assertRaises(RuntimeError):
            controller.connect_serial("A", "COM4")
        controller.set_mode("hardware")
        controller.connect_serial("A", "COM4")
        controller.connect_serial("B", "COM5")
        wait_for_event(controller.serial_events,
                       lambda event: event.get("type") == "status" and event.get("unit") == "A" and event.get("state") == "connected")
        wait_for_event(controller.serial_events,
                       lambda event: event.get("type") == "status" and event.get("unit") == "B" and event.get("state") == "connected")
        self.assertEqual([(port, baud) for port, baud, _ in fakes], [("COM4", 115200), ("COM5", 115200)])
        with self.assertRaises(RuntimeError):
            controller.run_simulated_trial("direct")
        controller.disconnect_serial("A"); controller.disconnect_serial("B")
        for adapter in controller.serial_adapters.values():
            adapter._thread.join(1)
        controller.set_mode("simulation")
        self.assertTrue(controller.simulation_mode)

    def test_idle_read_timeout_is_not_a_response_and_duplicate_ports_are_rejected(self):
        fakes = []

        def factory(port, baudrate, timeout):
            fake = FakeSerial()
            fakes.append(fake)
            return fake

        controller = AppController(serial_factory=factory)
        controller.set_mode("hardware")
        with self.assertRaises(ValueError):
            controller.connect_serial("A", "")
        controller.connect_serial("A", "COM6")
        wait_for_event(controller.serial_events,
                       lambda event: event.get("state") == "connected" and event.get("unit") == "A")
        with self.assertRaises(ValueError):
            controller.connect_serial("B", "com6")
        time.sleep(0.03)
        self.assertEqual(controller.session.trials, [])
        self.assertTrue(controller.serial_adapters["A"].is_alive)
        controller.disconnect_serial("A")
        controller.serial_adapters["A"]._thread.join(1)

    def test_diagnostic_log_is_bounded_and_redacts(self):
        self.assertNotIn("mysecret", sanitize_diagnostic("secret=mysecret"))
        log = DiagnosticLog(max_entries=2)
        log.add("A", "first")
        log.add("A", "secret=do-not-keep")
        log.add("B", "third")
        self.assertEqual(len(log.entries), 2)
        self.assertNotIn("do-not-keep", " ".join(log.entries))


if __name__ == "__main__":
    unittest.main()
