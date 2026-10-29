"""In-memory session storage; no persistent database is used."""

from typing import List

from models import Trial


class Session:
    def __init__(self) -> None:
        self.trials: List[Trial] = []

    def add_trial(self, trial: Trial) -> None:
        self.trials.append(trial)

    def clear(self) -> None:
        self.trials.clear()
