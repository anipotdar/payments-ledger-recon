"""Ground truth for scoring: every planted defect, with where it should be caught."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class Defect:
    defect_id: str
    defect_type: str
    source: str
    keys: dict[str, str]
    detail: str
    expected_catch: str

    def as_dict(self) -> dict[str, object]:
        return {
            "defect_id": self.defect_id,
            "defect_type": self.defect_type,
            "source": self.source,
            "keys": self.keys,
            "detail": self.detail,
            "expected_catch": self.expected_catch,
        }


class DefectLog:
    def __init__(self) -> None:
        self._items: list[Defect] = []

    def add(
        self,
        defect_type: str,
        source: str,
        keys: dict[str, str],
        detail: str,
        expected_catch: str,
    ) -> None:
        defect_id = f"D{len(self._items) + 1:04d}"
        self._items.append(Defect(defect_id, defect_type, source, keys, detail, expected_catch))

    @property
    def items(self) -> list[Defect]:
        return list(self._items)

    def counts(self) -> dict[str, int]:
        return dict(sorted(Counter(d.defect_type for d in self._items).items()))
