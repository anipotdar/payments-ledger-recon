from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from ledger_recon.generator import GeneratorConfig, generate

SMALL = GeneratorConfig(seed=7, days=20, merchants=10, payments_per_day=80)


@dataclass
class Run:
    root: Path
    manifest: dict[str, object]

    @property
    def landing(self) -> Path:
        return self.root / "landing"

    def defects(self, defect_type: str | None = None) -> list[dict[str, object]]:
        lines = (self.root / "_truth" / "defects.jsonl").read_text().splitlines()
        rows = [json.loads(x) for x in lines]
        return [r for r in rows if defect_type is None or r["defect_type"] == defect_type]

    def events(self) -> list[dict[str, object]]:
        out: list[dict[str, object]] = []
        for f in sorted((self.landing / "processor_events").rglob("*.jsonl")):
            out.extend(json.loads(x) for x in f.read_text().splitlines())
        return out

    def statement_lines(self, include_resends: bool = False) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        for f in sorted((self.landing / "bank_statements").rglob("*.csv")):
            if "_resend" in f.name and not include_resends:
                continue
            with f.open(newline="") as fh:
                out.extend(csv.DictReader(fh))
        return out


@pytest.fixture(scope="session")
def run(tmp_path_factory: pytest.TempPathFactory) -> Run:
    root = tmp_path_factory.mktemp("gen")
    return Run(root, generate(SMALL, root))
