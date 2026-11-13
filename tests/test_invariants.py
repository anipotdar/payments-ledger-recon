"""The scoreboard. Each test is a promise the platform makes. They start skipped
and get un-skipped as each weekend lands. CI shows how many are still open.

These run against tables exported from Databricks (or a local DuckDB build of
the same logic). Wire up the fixture when weekend 2 starts.
"""

from __future__ import annotations

import pytest

W1 = pytest.mark.skip(reason="weekend 1: bronze not built yet")
W2 = pytest.mark.skip(reason="weekend 2: ledger not built yet")
W3 = pytest.mark.skip(reason="weekend 3: reconciliation not built yet")
W4 = pytest.mark.skip(reason="weekend 4: hardening not done yet")


@W1
def test_bronze_replay_changes_nothing() -> None:
    """Loading the same landing files twice (including the resend) leaves row counts unchanged."""


@W1
def test_bronze_keeps_every_raw_line() -> None:
    """Bronze row count == lines in landing, duplicates included. Nothing is cleaned here."""


@W2
def test_silver_has_one_row_per_business_event() -> None:
    """Both duplicate kinds removed; no (payment_id, event_type) appears twice."""


@W2
def test_no_orphan_refunds() -> None:
    """Every refund and chargeback in silver has its capture, even when the refund arrived first."""


@W2
def test_ledger_sums_to_zero() -> None:
    """Sum of debits == sum of credits, per currency, per day, and overall."""


@W2
def test_every_entry_balances() -> None:
    """Each journal entry's legs net to zero on their own."""


@W2
def test_ledger_is_append_only() -> None:
    """Corrections are new reversing entries. No entry is ever updated or deleted."""


@W2
def test_scd2_has_no_overlaps_or_gaps() -> None:
    """Per merchant, versions tile time exactly; SNAPSHOT_GAP did not close a version."""


@W3
def test_every_bank_line_is_matched_or_a_break() -> None:
    """No statement line silently disappears from the recon output."""


@W3
def test_breaks_have_reason_codes() -> None:
    """Every break carries a reason code from the documented list, plus an age in days."""


@W4
def test_backfill_gives_same_answer() -> None:
    """Rebuilding all 30 days from scratch reproduces the ledger and breaks byte for byte."""


@W4
def test_every_seeded_defect_is_caught() -> None:
    """Join breaks and DQ failures to _truth/defects.jsonl. Report caught vs missed by type."""
