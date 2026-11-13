"""Deterministic, collision-free ids drawn from the run's RNG."""

from __future__ import annotations

import random


class IdFactory:
    def __init__(self, rng: random.Random) -> None:
        self._rng = rng
        self._seen: set[str] = set()

    def new(self, prefix: str) -> str:
        while True:
            candidate = f"{prefix}_{self._rng.getrandbits(48):012x}"
            if candidate not in self._seen:
                self._seen.add(candidate)
                return candidate
