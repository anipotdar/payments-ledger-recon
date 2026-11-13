"""Orchestrates one generator run and writes the landing zone plus ground truth.

Layout (every source is partitioned by the date it would arrive):

    <out>/landing/processor_events/arrival_date=YYYY-MM-DD/events_HH.jsonl
    <out>/landing/bank_statements/statement_date=YYYY-MM-DD/statement_YYYYMMDD.csv
    <out>/landing/merchant_master/snapshot_date=YYYY-MM-DD/merchants.csv
    <out>/landing/fx_rates/rate_date=YYYY-MM-DD/fx_rates.csv
    <out>/_truth/defects.jsonl
    <out>/_truth/merchant_changes.csv
    <out>/_truth/manifest.json
"""

from __future__ import annotations

import csv
import json
import random
import shutil
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from ledger_recon import __version__
from ledger_recon.generator.bank import apply_bank_defects, compute_payouts, statement_rows
from ledger_recon.generator.config import GeneratorConfig
from ledger_recon.generator.fx import build_fx
from ledger_recon.generator.ids import IdFactory
from ledger_recon.generator.merchants import build_merchants, change_rows, snapshot_rows
from ledger_recon.generator.payments import generate_activities
from ledger_recon.generator.processor import Event, build_events
from ledger_recon.generator.truth import DefectLog

FX_TAIL_DAYS = 20


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        if not rows:
            return
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="\n", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n")


def _event_files(events: list[Event]) -> dict[tuple[date, int], list[dict[str, object]]]:
    """Four files per arrival day, one per 6-hour delivery window."""
    files: dict[tuple[date, int], list[dict[str, object]]] = defaultdict(list)
    for e in events:
        files[(e.delivered_at.date(), (e.delivered_at.hour // 6) * 6)].append(e.as_dict())
    return files


def generate(cfg: GeneratorConfig, out: Path) -> dict[str, object]:
    rng = random.Random(cfg.seed)
    ids = IdFactory(rng)
    log = DefectLog()

    landing = out / "landing"
    truth = out / "_truth"
    for p in (landing, truth):
        if p.exists():
            shutil.rmtree(p)

    merchants = build_merchants(cfg, rng, log)
    fx = build_fx(rng, cfg.start_date, cfg.end_date + timedelta(days=FX_TAIL_DAYS), cfg.holidays)
    acts = generate_activities(cfg, rng, merchants, ids, log)
    events = build_events(cfg, rng, acts, ids, log)
    payouts = compute_payouts(acts, merchants, fx, cfg.holidays, cfg.fx_spread_bps)
    lines = apply_bank_defects(cfg, rng, payouts, fx, merchants, log)
    snapshots = snapshot_rows(cfg, rng, merchants, log)
    statements = statement_rows(lines)

    # Processor events
    for (day, hour), rows in sorted(_event_files(events).items()):
        _write_jsonl(
            landing / "processor_events" / f"arrival_date={day}" / f"events_{hour:02d}.jsonl",
            rows,
        )

    # Bank statements, plus re-sent copies of some files
    for day, rows in statements.items():
        _write_csv(
            landing / "bank_statements" / f"statement_date={day}" / f"statement_{day:%Y%m%d}.csv",
            rows,
        )
    resend_days = sorted(rng.sample(sorted(statements), k=min(cfg.resend_files, len(statements))))
    for day in resend_days:
        name = f"statement_{day:%Y%m%d}_resend.csv"
        _write_csv(landing / "bank_statements" / f"statement_date={day}" / name, statements[day])
        log.add(
            "FILE_RESEND",
            "bank",
            {"statement_date": day.isoformat(), "file": name},
            f"statement for {day} delivered twice under a different file name",
            "bronze: loading the same lines twice changes nothing (idempotent on line identity)",
        )

    # Merchant master snapshots
    for day, rows in snapshots.items():
        _write_csv(landing / "merchant_master" / f"snapshot_date={day}" / "merchants.csv", rows)

    # FX rates
    fx_by_day: dict[date, list[dict[str, object]]] = defaultdict(list)
    for r in fx.rates:
        fx_by_day[r.rate_date].append(
            {
                "rate_date": r.rate_date.isoformat(),
                "base_currency": r.base_currency,
                "quote_currency": r.quote_currency,
                "mid_rate": str(r.mid_rate),
            }
        )
    for day, rows in sorted(fx_by_day.items()):
        _write_csv(landing / "fx_rates" / f"rate_date={day}" / "fx_rates.csv", rows)

    # Ground truth
    _write_jsonl(truth / "defects.jsonl", [d.as_dict() for d in log.items])
    _write_csv(truth / "merchant_changes.csv", change_rows(merchants))
    manifest: dict[str, object] = {
        "generator_version": __version__,
        "config": cfg.as_dict(),
        "rows": {
            "activities_truth": len(acts),
            "processor_events": len(events),
            "bank_statement_lines": sum(len(r) for r in statements.values()),
            "merchant_snapshot_rows": sum(len(r) for r in snapshots.values()),
            "fx_rates": len(fx.rates),
        },
        "defects": log.counts(),
    }
    (truth / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def release(data: Path, through: date, inbox: Path | None = None) -> list[Path]:
    """Copy every landing partition dated <= `through` into the inbox.

    Lets you replay the period one day at a time, the way files would really
    arrive, so incremental loads, late data and backfills can be exercised.
    Already-released files are left alone.
    """
    src_root = data / "landing"
    dst_root = inbox or (data / "inbox")
    copied: list[Path] = []
    for part in sorted(src_root.glob("*/*=*")):
        _, value = part.name.split("=", 1)
        if date.fromisoformat(value) > through:
            continue
        for f in sorted(part.iterdir()):
            target = dst_root / part.parent.name / part.name / f.name
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target)
            copied.append(target)
    return copied
