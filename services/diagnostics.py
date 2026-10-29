"""Bounded, credential-redacted serial diagnostics."""

from collections import deque
from datetime import datetime

from devices.parser import sanitize_diagnostic


class DiagnosticLog:
    def __init__(self, max_entries: int = 250) -> None:
        self._entries = deque(maxlen=max_entries)

    @property
    def entries(self):
        return tuple(self._entries)

    def add(self, unit: str, message: str) -> None:
        safe = sanitize_diagnostic(message)
        self._entries.append(f"{datetime.now().strftime('%H:%M:%S')}  Unit {unit}  {safe}")
