"""Bank statement: one netted payout line per merchant per activity date, in the
settlement currency, with timing, reference and amount problems."""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date

from ledger_recon.generator.bizdays import add_business_days
from ledger_recon.generator.config import GeneratorConfig
from ledger_recon.generator.fx import FxTable
from ledger_recon.generator.merchants import Merchant
from ledger_recon.generator.money import BANK_CHARGE_INR_MINOR, convert
from ledger_recon.generator.payments import CAPTURE, Activity
from ledger_recon.generator.truth import DefectLog

ACCOUNTS = {"INR": "ACC-INR-0001", "USD": "ACC-USD-0001"}


@dataclass(frozen=True)
class Payout:
    reference: str
    merchant_id: str
    activity_date: date
    value_date: date
    account_id: str
    currency: str
    amount_minor: int  # signed, settlement currency. Negative = bank debit.
    narrative: str


def payout_reference(merchant_id: str, activity_date: date) -> str:
    return f"PO-{merchant_id}-{activity_date:%Y%m%d}"


def net_presentment(acts: list[Activity]) -> int:
    """Gross captures less refunds, chargebacks and every processor fee."""
    total = 0
    for a in acts:
        total += a.amount_minor if a.kind == CAPTURE else -a.amount_minor
        total -= a.fee_minor
    return total


def compute_payouts(
    acts: list[Activity],
    merchants: list[Merchant],
    fx: FxTable,
    holidays: tuple[date, ...],
    spread_bps: int,
) -> list[Payout]:
    by_id = {m.merchant_id: m for m in merchants}
    groups: dict[tuple[str, date], list[Activity]] = defaultdict(list)
    for a in acts:
        groups[(a.merchant_id, a.activity_date)].append(a)

    payouts: list[Payout] = []
    for (mid, day), group in sorted(groups.items()):
        m = by_id[mid]
        net = net_presentment(group)
        if net == 0:
            continue
        value_date = add_business_days(day, m.on(day).settlement_lag_days, holidays)
        sett = m.settlement_currency
        if sett != m.presentment_currency:
            net = convert(net, fx.rate(value_date, m.presentment_currency, sett), spread_bps)
        ref = payout_reference(mid, day)
        payouts.append(
            Payout(ref, mid, day, value_date, ACCOUNTS[sett], sett, net, _narrative(sett, net, ref))
        )
    return payouts


def _narrative(currency: str, amount: int, ref: str) -> str:
    rail = "NEFT" if currency == "INR" else "SWIFT"
    if amount >= 0:
        return f"{rail} CR ACQ SETTLEMENT {ref}"
    return f"{rail} DR ACQ RECOVERY {ref}"


def _k(n: int, rate: float, available: int) -> int:
    if rate <= 0 or available == 0:
        return 0
    return min(available, max(1, round(n * rate)))


def apply_bank_defects(
    cfg: GeneratorConfig,
    rng: random.Random,
    payouts: list[Payout],
    fx: FxTable,
    merchants: list[Merchant],
    log: DefectLog,
) -> list[Payout]:
    by_id = {m.merchant_id: m for m in merchants}
    lines = list(payouts)
    n = len(lines)
    touched: set[int] = set()

    def pick(rate: float, eligible: list[int]) -> list[int]:
        chosen = sorted(rng.sample(eligible, k=_k(n, rate, len(eligible))))
        touched.update(chosen)
        return chosen

    free = [i for i in range(n) if i not in touched]
    missing = set(pick(cfg.missing_payout_rate, free))
    for i in sorted(missing):
        p = lines[i]
        log.add(
            "MISSING_PAYOUT",
            "bank",
            {"reference": p.reference},
            f"expected {p.amount_minor} {p.currency} on {p.value_date}, never credited",
            "recon: break NOT_IN_BANK that keeps ageing",
        )

    free = [i for i in range(n) if i not in touched]
    for i in pick(cfg.delayed_payout_rate, free):
        p = lines[i]
        late = add_business_days(p.value_date, 1, cfg.holidays)
        amount = p.amount_minor
        m = by_id[p.merchant_id]
        if m.settlement_currency != m.presentment_currency:
            # Bank converts on the day it actually receives the funds.
            ratio = fx.rate(late, m.presentment_currency, m.settlement_currency) / fx.rate(
                p.value_date, m.presentment_currency, m.settlement_currency
            )
            amount = int(round(amount * ratio))
        lines[i] = replace(p, value_date=late, amount_minor=amount)
        log.add(
            "SETTLEMENT_DELAYED",
            "bank",
            {
                "reference": p.reference,
                "expected_value_date": p.value_date.isoformat(),
                "actual_value_date": late.isoformat(),
            },
            "payout landed one business day after contract terms",
            "recon: timing break on day 1 that clears on day 2; ageing shows it",
        )

    free = [
        i
        for i in range(n)
        if i not in touched
        and lines[i].currency == "INR"
        and lines[i].amount_minor > BANK_CHARGE_INR_MINOR
    ]
    for i in pick(cfg.bank_charge_rate, free):
        p = lines[i]
        lines[i] = replace(p, amount_minor=p.amount_minor - BANK_CHARGE_INR_MINOR)
        log.add(
            "BANK_CHARGE",
            "bank",
            {"reference": p.reference},
            f"bank deducted {BANK_CHARGE_INR_MINOR} minor (Rs 25 + 18% GST) from the credit",
            "recon: amount break with a known, explainable reason code",
        )

    free = [i for i in range(n) if i not in touched]
    for i in pick(cfg.missing_reference_rate, free):
        p = lines[i]
        lines[i] = replace(p, reference="", narrative=p.narrative.rsplit(" ", 1)[0])
        log.add(
            "MISSING_REFERENCE",
            "bank",
            {"reference": p.reference},
            "statement line has no payout reference",
            "recon: fall back to account + value date + amount matching",
        )

    return [p for i, p in enumerate(lines) if i not in missing]


def statement_rows(lines: list[Payout]) -> dict[date, list[dict[str, object]]]:
    by_day: dict[date, list[Payout]] = defaultdict(list)
    for p in lines:
        by_day[p.value_date].append(p)
    out: dict[date, list[dict[str, object]]] = {}
    for day, group in sorted(by_day.items()):
        group.sort(key=lambda p: (p.account_id, p.merchant_id, p.activity_date))
        out[day] = [
            {
                "account_id": p.account_id,
                "statement_date": day.isoformat(),
                "line_no": n,
                "value_date": p.value_date.isoformat(),
                "direction": "CR" if p.amount_minor >= 0 else "DR",
                "amount_minor": abs(p.amount_minor),
                "currency": p.currency,
                "reference": p.reference,
                "narrative": p.narrative,
            }
            for n, p in enumerate(group, start=1)
        ]
    return out
