"""Deterministic-capable local simulation; never communicates with hardware."""

import math
import random
from datetime import datetime
from statistics import median
from typing import Iterable, Optional

from models import DeviceStatus, Trial


class SimulationService:
    def __init__(self, rng=None, *, initial_delay_ms_per_hop: int = 30) -> None:
        # Passing random.Random(seed) makes test fixtures repeatable.
        self.rng = rng if rng is not None else random.Random()
        self.enabled = True
        self.running = True
        self.calibration_enabled = False
        self.require_secret_mode = False
        self.selected_route = "direct"
        self.relay_delay_ms_per_hop = max(0, int(initial_delay_ms_per_hop))
        self.devices = {unit: DeviceStatus(unit=unit, connected=True, ready=True)
                        for unit in ("A", "B", "C")}

    def set_device_connected(self, unit: str, connected: bool) -> DeviceStatus:
        if unit not in self.devices:
            raise ValueError("unit must be A, B, or C")
        status = self.devices[unit]
        status.connected = bool(connected)
        status.ready = bool(connected)
        status.last_message_at = datetime.now() if connected else None
        return status

    def set_calibration(self, enabled: bool) -> bool:
        self.calibration_enabled = bool(enabled)
        return self.calibration_enabled

    def set_require_secret(self, enabled: bool) -> bool:
        self.require_secret_mode = bool(enabled)
        return self.require_secret_mode

    def set_route(self, route: str) -> str:
        if route not in ("direct", "relay"):
            raise ValueError("route must be direct or relay")
        self.selected_route = route
        return self.selected_route

    def adjust_relay_delay(self, change_ms: int) -> int:
        self.relay_delay_ms_per_hop = max(0, self.relay_delay_ms_per_hop + int(change_ms))
        return self.relay_delay_ms_per_hop

    def stop(self) -> None:
        self.running = False

    def generate_trial(self, *, session_id: int, route: str, threshold_ms: float,
                       received_at: Optional[datetime] = None) -> Trial:
        if not self.running:
            raise RuntimeError("simulation has been stopped")
        if route not in ("direct", "relay"):
            raise ValueError("route must be direct or relay")
        if not math.isfinite(threshold_ms) or threshold_ms <= 0:
            raise ValueError("threshold_ms must be a positive finite number")
        required = ("A", "B", "C") if route == "relay" else ("A", "B")
        missing = [unit for unit in required if not self.devices[unit].connected]
        if missing:
            return Trial(session_id=session_id, received_at=received_at or datetime.now(),
                         source_unit="simulation", route=route, uid_display="••••••••",
                         threshold_ms=threshold_ms, decision="error",
                         reason="Simulated trial unavailable: " + ", ".join(f"Unit {u}" for u in missing) +
                                " disconnected in the simulator.")
        base = self.rng.uniform(34.0, 54.0) if route == "direct" else self.rng.uniform(38.0, 56.0)
        rtt_ms = round(base + (self.relay_delay_ms_per_hop if route == "relay" else 0), 1)
        proof_valid = self.rng.random() >= 0.08
        secret_used = True if self.require_secret_mode else self.rng.choice((True, False))
        calibration_note = "Calibration demonstration enabled. " if self.calibration_enabled else ""
        if not proof_valid:
            decision = "denied"
            reason = calibration_note + "Simulated credential proof failed. This is example data, not a verifier result."
        elif rtt_ms > threshold_ms:
            decision = "relay_suspected"
            reason = (calibration_note + f"Simulated RTT {rtt_ms:g} ms exceeded {threshold_ms:g} ms. "
                      "A high Wi-Fi RTT is not proof of an NFC relay.")
        else:
            decision = "granted"
            reason = (calibration_note + f"Simulated proof passed and RTT {rtt_ms:g} ms was within "
                      f"the {threshold_ms:g} ms threshold.")
        return Trial(session_id=session_id, received_at=received_at or datetime.now(),
                     source_unit="Unit B (simulated)", route=route, uid_display="••••••••",
                     rtt_ms=rtt_ms, threshold_ms=float(threshold_ms), proof_valid=proof_valid,
                     secret_used=secret_used, decision=decision, reason=reason)


def summarize_trials(trials: Iterable[Trial], configured_threshold_ms: Optional[float] = None) -> dict:
    """Return robust overall and per-route statistics, including for empty input."""
    values = list(trials)
    by_route = {}
    for route in ("direct", "relay"):
        samples = [t.rtt_ms for t in values if t.route == route and _valid_rtt(t.rtt_ms)]
        by_route[route] = _summary(samples)
    all_samples = [t.rtt_ms for t in values if _valid_rtt(t.rtt_ms)]
    return {"sample_count": len(all_samples), "minimum": min(all_samples) if all_samples else None,
            "median": median(all_samples) if all_samples else None,
            "maximum": max(all_samples) if all_samples else None,
            "configured_threshold_ms": configured_threshold_ms, "by_route": by_route}


def _summary(samples: list[float]) -> dict:
    return {"sample_count": len(samples), "minimum": min(samples) if samples else None,
            "median": median(samples) if samples else None,
            "maximum": max(samples) if samples else None}


def _valid_rtt(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0
