"""The generator is the answer key, so it gets tested like production code."""

from __future__ import annotations

import csv
import hashlib
from datetime import date, datetime
from pathlib import Path

from conftest import SMALL, Run

from ledger_recon.generator import generate
from ledger_recon.generator.bank import net_presentment
from ledger_recon.generator.bizdays import add_business_days
from ledger_recon.generator.money import convert, fee_from_bps
from ledger_recon.generator.payments import CAPTURE, CHARGEBACK, REFUND, Activity
from ledger_recon.generator.run import release

ALL_TYPES = {
    "BACKDATED_MASTER_CHANGE",
    "BANK_CHARGE",
    "DUPLICATE_DELIVERY",
    "DUPLICATE_NEW_EVENT_ID",
    "FEE_DRIFT",
    "FILE_RESEND",
    "LATE_ARRIVAL",
    "MISSING_EVENT",
    "MISSING_PAYOUT",
    "MISSING_REFERENCE",
    "OUT_OF_ORDER",
    "SCHEMA_CHANGE",
    "SETTLEMENT_DELAYED",
    "SNAPSHOT_GAP",
}


def _ts(s: object) -> datetime:
    return datetime.strptime(str(s), "%Y-%m-%dT%H:%M:%SZ")


def _tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(root.rglob("*")):
        if f.is_file():
            h.update(str(f.relative_to(root)).encode())
            h.update(f.read_bytes())
    return h.hexdigest()


# --- determinism -------------------------------------------------------------


def test_same_seed_same_bytes(tmp_path: Path) -> None:
    generate(SMALL, tmp_path / "a")
    generate(SMALL, tmp_path / "b")
    assert _tree_hash(tmp_path / "a") == _tree_hash(tmp_path / "b")


def test_every_defect_type_is_planted(run: Run) -> None:
    assert {d["defect_type"] for d in run.defects()} == ALL_TYPES


# --- money -------------------------------------------------------------------


def test_fee_rounds_half_up() -> None:
    assert fee_from_bps(10000, 175) == 175
    assert fee_from_bps(2, 2500) == 1  # 0.5 rounds up


def test_convert_applies_spread() -> None:
    from decimal import Decimal

    assert convert(10000, Decimal("88"), 0) == 880000
    assert convert(10000, Decimal("88"), 35) == 876920


def test_net_is_gross_less_reversals_and_fees() -> None:
    t = datetime(2026, 10, 5, 10)
    acts = [
        Activity(CAPTURE, "p1", "p1", "o1", "M1", t, 10000, "INR", 200, "card"),
        Activity(CAPTURE, "p2", "p2", "o2", "M1", t, 5000, "INR", 100, "upi"),
        Activity(REFUND, "r1", "p1", "o1", "M1", t, 3000, "INR", 0, "card"),
        Activity(CHARGEBACK, "c1", "p2", "o2", "M1", t, 5000, "INR", 500, "upi"),
    ]
    assert net_presentment(acts) == 10000 + 5000 - 3000 - 5000 - 200 - 100 - 500


def test_business_days_skip_weekend_and_holiday() -> None:
    hol = (date(2026, 10, 2),)
    assert add_business_days(date(2026, 10, 1), 1, hol) == date(2026, 10, 5)  # Thu -> Mon
    assert add_business_days(date(2026, 10, 9), 2, hol) == date(2026, 10, 13)  # Fri -> Tue


# --- processor defects -------------------------------------------------------


def test_exact_duplicates_share_event_id(run: Run) -> None:
    ids = [e["event_id"] for e in run.events()]
    for d in run.defects("DUPLICATE_DELIVERY"):
        keys = d["keys"]
        assert isinstance(keys, dict)
        assert ids.count(keys["event_id"]) == 2


def test_new_id_duplicates_share_payment(run: Run) -> None:
    by_id = {e["event_id"]: e for e in run.events()}
    for d in run.defects("DUPLICATE_NEW_EVENT_ID"):
        keys = d["keys"]
        assert isinstance(keys, dict)
        a, b = by_id[keys["original_event_id"]], by_id[keys["duplicate_event_id"]]
        assert a["data"] == b["data"]
        assert a["event_type"] == b["event_type"] == "payment.captured"


def test_late_events_arrive_at_least_two_days_late(run: Run) -> None:
    by_id = {e["event_id"]: e for e in run.events()}
    for d in run.defects("LATE_ARRIVAL"):
        keys = d["keys"]
        assert isinstance(keys, dict)
        e = by_id[keys["event_id"]]
        assert (_ts(e["delivered_at"]) - _ts(e["created_at"])).total_seconds() >= 2 * 86400


def test_out_of_order_refund_beats_capture(run: Run) -> None:
    by_id = {e["event_id"]: e for e in run.events()}
    for d in run.defects("OUT_OF_ORDER"):
        keys = d["keys"]
        assert isinstance(keys, dict)
        cap, ref = by_id[keys["capture_event_id"]], by_id[keys["refund_event_id"]]
        assert _ts(ref["delivered_at"]) < _ts(cap["delivered_at"])
        assert _ts(ref["created_at"]) > _ts(cap["created_at"])


def test_missing_captures_are_absent(run: Run) -> None:
    pays = {
        e["data"]["payment_id"]  # type: ignore[index]
        for e in run.events()
        if e["event_type"] == "payment.captured"
    }
    for d in run.defects("MISSING_EVENT"):
        keys = d["keys"]
        assert isinstance(keys, dict)
        assert keys["payment_id"] not in pays


def test_schema_change_adds_field_only_after_cutover(run: Run) -> None:
    cutover = SMALL.schema_change_date
    for e in run.events():
        if e["event_type"] != "payment.captured":
            continue
        data = e["data"]
        assert isinstance(data, dict)
        after = _ts(e["created_at"]).date() >= cutover
        assert ("payment_method" in data) == after


def test_files_partitioned_by_arrival_not_event_time(run: Run) -> None:
    for f in (run.landing / "processor_events").rglob("*.jsonl"):
        day = f.parent.name.split("=")[1]
        for line in f.read_text().splitlines():
            assert f'"delivered_at":"{day}T' in line


# --- bank defects ------------------------------------------------------------


def test_no_statement_on_non_business_days(run: Run) -> None:
    for line in run.statement_lines():
        d = date.fromisoformat(line["value_date"])
        assert d.weekday() < 5 and d not in SMALL.holidays


def test_missing_payouts_absent_and_references_otherwise_unique(run: Run) -> None:
    refs = [x["reference"] for x in run.statement_lines() if x["reference"]]
    assert len(refs) == len(set(refs))
    for d in run.defects("MISSING_PAYOUT"):
        keys = d["keys"]
        assert isinstance(keys, dict)
        assert keys["reference"] not in refs


def test_resend_file_is_identical_to_original(run: Run) -> None:
    for d in run.defects("FILE_RESEND"):
        keys = d["keys"]
        assert isinstance(keys, dict)
        part = run.landing / "bank_statements" / f"statement_date={keys['statement_date']}"
        files = sorted(part.glob("*.csv"))
        assert len(files) == 2
        assert files[0].read_bytes() == files[1].read_bytes()


# --- merchant master ---------------------------------------------------------


def test_backdated_change_visible_late_with_old_updated_at(run: Run) -> None:
    for d in run.defects("BACKDATED_MASTER_CHANGE"):
        keys = d["keys"]
        assert isinstance(keys, dict)
        mid, eff = keys["merchant_id"], keys["effective_from"]
        snap = run.landing / "merchant_master" / f"snapshot_date={eff}" / "merchants.csv"
        with snap.open(newline="") as fh:
            row = next(r for r in csv.DictReader(fh) if r["merchant_id"] == mid)
        assert not row["updated_at"].startswith(eff)  # still the old version on that day


def test_snapshot_gap_is_a_single_day(run: Run) -> None:
    for d in run.defects("SNAPSHOT_GAP"):
        keys = d["keys"]
        assert isinstance(keys, dict)
        snap = run.landing / "merchant_master" / f"snapshot_date={keys['snapshot_date']}"
        assert keys["merchant_id"] not in (snap / "merchants.csv").read_text()


# --- release -----------------------------------------------------------------


def test_release_is_incremental(run: Run, tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    first = release(run.root, SMALL.start_date, inbox)
    again = release(run.root, SMALL.start_date, inbox)
    later = release(run.root, SMALL.end_date, inbox)
    assert first and not again and later
    for f in inbox.rglob("*"):
        if f.is_file():
            assert date.fromisoformat(f.parent.name.split("=")[1]) <= SMALL.end_date
