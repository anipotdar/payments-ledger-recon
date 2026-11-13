"""What actually happened: captures, refunds and chargebacks. This is the truth
the three sources each report a distorted view of."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from ledger_recon.generator.bizdays import days_between
from ledger_recon.generator.config import GeneratorConfig
from ledger_recon.generator.ids import IdFactory
from ledger_recon.generator.merchants import Merchant
from ledger_recon.generator.money import CHARGEBACK_FEE_MINOR, fee_from_bps
from ledger_recon.generator.truth import DefectLog

CAPTURE = "CAPTURE"
REFUND = "REFUND"
CHARGEBACK = "CHARGEBACK"

# Median ticket size in minor units, per presentment currency.
_MEDIAN_MINOR = {"INR": 120000, "USD": 4500, "AED": 15000, "GBP": 3500}
_MIN_MINOR = {"INR": 1000, "USD": 100, "AED": 500, "GBP": 100}
_METHODS = ["card", "upi", "netbanking", "wallet"]


@dataclass(frozen=True)
class Activity:
    kind: str
    activity_id: str
    payment_id: str
    order_id: str
    merchant_id: str
    occurred_at: datetime
    amount_minor: int  # always positive; kind decides the sign
    currency: str
    fee_minor: int  # capture fee or chargeback fee charged by the processor
    payment_method: str

    @property
    def activity_date(self) -> date:
        return self.occurred_at.date()


def _ticket(rng: random.Random, currency: str) -> int:
    raw = _MEDIAN_MINOR[currency] * rng.lognormvariate(0, 0.9)
    return max(_MIN_MINOR[currency], int(round(raw)))


def _random_time(rng: random.Random, d: date) -> datetime:
    return datetime.combine(d, time(0, 0), tzinfo=UTC) + timedelta(seconds=rng.randrange(0, 86400))


def generate_activities(
    cfg: GeneratorConfig,
    rng: random.Random,
    merchants: list[Merchant],
    ids: IdFactory,
    log: DefectLog,
) -> list[Activity]:
    end_of_period = datetime.combine(cfg.end_date, time(23, 59, 59), tzinfo=UTC)
    weights = [1 / (m.rank + 1) ** 0.8 for m in merchants]
    acts: list[Activity] = []

    for d in days_between(cfg.start_date, cfg.end_date):
        volume = cfg.payments_per_day * (0.6 if d.weekday() >= 5 else 1.0)
        n = int(volume * rng.uniform(0.8, 1.2))
        active = [
            (m, w) for m, w in zip(merchants, weights, strict=True) if m.on(d).status == "ACTIVE"
        ]
        pool = [m for m, _ in active]
        pool_w = [w for _, w in active]

        for _ in range(n):
            m = rng.choices(pool, weights=pool_w, k=1)[0]
            cur = m.presentment_currency
            amount = _ticket(rng, cur)
            at = _random_time(rng, d)
            payment_id = ids.new("pay")
            order_id = ids.new("ord")
            method = rng.choice(_METHODS)
            acts.append(
                Activity(
                    CAPTURE,
                    payment_id,
                    payment_id,
                    order_id,
                    m.merchant_id,
                    at,
                    amount,
                    cur,
                    fee_from_bps(amount, m.fee_bps_charged(d)),
                    method,
                )
            )

            roll = rng.random()
            if roll < cfg.refund_rate:
                refund_at = at + timedelta(seconds=rng.randrange(2 * 3600, 10 * 86400))
                if refund_at <= end_of_period:
                    partial = rng.random() < 0.4
                    refund_amt = int(amount * rng.uniform(0.2, 0.8)) if partial else amount
                    acts.append(
                        Activity(
                            REFUND,
                            ids.new("re"),
                            payment_id,
                            order_id,
                            m.merchant_id,
                            refund_at,
                            max(1, refund_amt),
                            cur,
                            0,
                            method,
                        )
                    )
            elif roll < cfg.refund_rate + cfg.chargeback_rate:
                cb_at = at + timedelta(seconds=rng.randrange(5 * 86400, 25 * 86400))
                if cb_at <= end_of_period:
                    acts.append(
                        Activity(
                            CHARGEBACK,
                            ids.new("cb"),
                            payment_id,
                            order_id,
                            m.merchant_id,
                            cb_at,
                            amount,
                            cur,
                            CHARGEBACK_FEE_MINOR[cur],
                            method,
                        )
                    )

    acts.sort(key=lambda a: (a.occurred_at, a.activity_id))
    _log_fee_drift(merchants, acts, log)
    return acts


def _log_fee_drift(merchants: list[Merchant], acts: list[Activity], log: DefectLog) -> None:
    for m in merchants:
        if not m.processor_fee_override:
            continue
        start, until, old_bps = m.processor_fee_override
        affected = [
            a.payment_id
            for a in acts
            if a.kind == CAPTURE
            and a.merchant_id == m.merchant_id
            and start <= a.activity_date < until
        ]
        log.add(
            "FEE_DRIFT",
            "processor",
            {"merchant_id": m.merchant_id, "from": start.isoformat(), "until": until.isoformat()},
            f"contract moved to {m.on(start).fee_bps} bps on {start} but processor charged "
            f"{old_bps} bps until {until}; {len(affected)} captures affected",
            "recon: capture fee vs contract fee effective on capture date (point-in-time join)",
        )
