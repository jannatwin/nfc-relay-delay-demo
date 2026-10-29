"""CSV export for in-memory trials."""

import csv
import math
from pathlib import Path
from typing import Iterable

from devices.parser import sanitize_diagnostic
from models import Trial


def export_trials(trials: Iterable[Trial], path: str | Path) -> None:
    fields = ("session_id", "received_at", "source_unit", "route", "uid_display",
              "rtt_ms", "threshold_ms", "proof_valid", "secret_used", "decision", "reason")
    with Path(path).open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for trial in trials:
            row = vars(trial).copy()
            row["received_at"] = trial.received_at.isoformat()
            for key in ("source_unit", "route", "uid_display", "decision", "reason"):
                row[key] = sanitize_diagnostic(str(row[key]))
            for key in ("rtt_ms", "threshold_ms"):
                value = row[key]
                row[key] = value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else ""
            for key in ("proof_valid", "secret_used"):
                if row[key] is not True and row[key] is not False and row[key] is not None:
                    row[key] = ""
            writer.writerow(row)
