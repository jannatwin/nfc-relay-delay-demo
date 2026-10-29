"""Application coordination for local-only demo interactions."""

import math
import queue

from devices.serial_adapter import UnitASerialAdapter, UnitBSerialAdapter, UnitCSerialAdapter
from models import DeviceStatus
from services.diagnostics import DiagnosticLog
from services.session import Session
from services.simulation import SimulationService


class AppController:
    def __init__(self, simulation=None, serial_factory=None) -> None:
        self.session = Session()
        self.simulation = simulation or SimulationService()
        self.active_mode = "simulation"
        self.serial_factory = serial_factory
        self.serial_events = queue.Queue()
        self.serial_adapters = {}
        self.serial_ports = {unit: "" for unit in ("A", "B", "C")}
        self.hardware_status = {unit: DeviceStatus(unit=unit) for unit in ("A", "B", "C")}
        self.serial_states = {unit: "disconnected" for unit in ("A", "B", "C")}
        self.serial_errors = {unit: "" for unit in ("A", "B", "C")}
        self.diagnostics = DiagnosticLog(max_entries=250)
        self.latest_trial = None
        self.card_status = "No demo enrollment recorded."
        self._next_session_id = 1
        self.threshold_ms = 60.0

    @property
    def calibration_enabled(self) -> bool:
        return self.simulation.calibration_enabled

    @property
    def simulation_running(self) -> bool:
        return self.simulation.running

    @property
    def simulation_mode(self) -> bool:
        return self.active_mode == "simulation"

    def set_mode(self, mode: str) -> None:
        if mode not in ("simulation", "hardware"):
            raise ValueError("mode must be simulation or hardware")
        if mode == "simulation":
            for adapter in self.serial_adapters.values():
                adapter.disconnect()
        self.active_mode = mode

    def connect_serial(self, unit: str, port: str, baudrate: int = 115200) -> None:
        if self.active_mode != "hardware":
            raise RuntimeError("Switch to hardware mode before connecting serial devices")
        if unit not in ("A", "B", "C"):
            raise ValueError("unit must be A, B, or C")
        port = port.strip()
        if not port:
            raise ValueError("Select a COM port first")
        for other_unit, other_port in self.serial_ports.items():
            if other_unit != unit and other_port.casefold() == port.casefold() and self.serial_states[other_unit] in ("connecting", "connected", "disconnecting"):
                raise ValueError(f"{port} is already connected to Unit {other_unit}")
        current = self.serial_adapters.get(unit)
        if current is not None and current.is_alive:
            raise RuntimeError(f"Unit {unit} already has an active serial connection")
        adapter_type = {"A": UnitASerialAdapter, "B": UnitBSerialAdapter, "C": UnitCSerialAdapter}[unit]
        options = {"baudrate": baudrate}
        if self.serial_factory is not None:
            options["serial_factory"] = self.serial_factory
        adapter = adapter_type(port, self.serial_events, **options)
        self.serial_adapters[unit] = adapter
        self.serial_ports[unit] = port
        self.serial_states[unit] = "connecting"
        self.serial_errors[unit] = ""
        self.serial_events.put({"type": "status", "unit": unit, "state": "connecting", "port": port})
        adapter.connect()

    def disconnect_serial(self, unit: str) -> None:
        adapter = self.serial_adapters.get(unit)
        if adapter is not None:
            adapter.disconnect()

    def shutdown_serial(self) -> None:
        for adapter in self.serial_adapters.values():
            adapter.disconnect()

    def run_simulated_trial(self, route: str):
        """Create and store an explicitly simulated (never measured) trial."""
        if not self.simulation_mode:
            raise RuntimeError("Switch to simulation mode before running simulated trials")
        trial = self.simulation.generate_trial(session_id=self._next_session_id, route=route,
                                               threshold_ms=self.threshold_ms)
        self._next_session_id += 1
        self.session.add_trial(trial)
        self.latest_trial = trial
        return trial

    def toggle_calibration(self) -> bool:
        return self.simulation.set_calibration(not self.calibration_enabled)

    def set_calibration(self, enabled: bool) -> bool:
        return self.simulation.set_calibration(enabled)

    def set_require_secret(self, enabled: bool) -> bool:
        return self.simulation.set_require_secret(enabled)

    def set_simulation_route(self, route: str) -> str:
        return self.simulation.set_route(route)

    def adjust_relay_delay(self, change_ms: int) -> int:
        return self.simulation.adjust_relay_delay(change_ms)

    def set_simulated_device_connected(self, unit: str, connected: bool):
        return self.simulation.set_device_connected(unit, connected)

    def configure_threshold(self, threshold_ms: float) -> float:
        if not math.isfinite(threshold_ms) or threshold_ms <= 0:
            raise ValueError("threshold must be positive")
        self.threshold_ms = float(threshold_ms)
        return self.threshold_ms

    def stop_simulation(self) -> None:
        self.simulation.stop()
        self.latest_trial = None

    def card_action(self, action: str) -> str:
        messages = {
            "N": "Simulated normal enrollment recorded. No card was read.",
            "S": "Simulated suspicious enrollment recorded. No card was read.",
            "P": "Demo status only: secret provision status is not known. No secret was entered or stored.",
            "L": self.card_status,
        }
        if action not in messages:
            raise ValueError("unsupported demo card action")
        if action in ("N", "S"):
            self.card_status = messages[action]
        return messages[action]

    def erase_demo_enrollment(self) -> str:
        self.card_status = "Local simulated enrollment cleared. No hardware command was sent."
        return self.card_status
