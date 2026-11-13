"""Processor webhooks: the same truth, delivered with duplicates, late,
out of order, occasionally not at all, and with a mid-period schema change."""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from ledger_recon.generator.config import GeneratorConfig
from ledger_recon.generator.ids import IdFactory
from ledger_recon.generator.payments import CAPTURE, CHARGEBACK, REFUND, Activity
from ledger_recon.generator.truth import DefectLog

OLD_API = "2026-06-01"

_EVENT_TYPE = {
    CAPTURE: "payment.captured",
    REFUND: "refund.succeeded",
    CHARGEBACK: "chargeback.debited",
}


@dataclass(frozen=True)
class Event:
    event_id: str
    event_type: str
    created_at: datetime
    delivered_at: datetime
    api_version: str
    activity: Activity

    def as_dict(self) -> dict[str, object]:
        a = self.activity
        data: dict[str, object] = {
            "payment_id": a.payment_id,
            "merchant_id": a.merchant_id,
            "amount_minor": a.amount_minor,
            "currency": a.currency,
        }
        if a.kind == CAPTURE:
            data["order_id"] = a.order_id
            data["fee_minor"] = a.fee_minor
            if self.api_version != OLD_API:
                data["payment_method"] = a.payment_method
        elif a.kind == REFUND:
            data["refund_id"] = a.activity_id
        else:
            data["chargeback_id"] = a.activity_id
            data["fee_minor"] = a.fee_minor
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "api_version": self.api_version,
            "created_at": _ts(self.created_at),
            "delivered_at": _ts(self.delivered_at),
            "data": data,
        }


def _ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _k(n: int, rate: float, available: int) -> int:
    if rate <= 0 or available == 0:
        return 0
    return min(available, max(1, round(n * rate)))


def build_events(
    cfg: GeneratorConfig,
    rng: random.Random,
    acts: list[Activity],
    ids: IdFactory,
    log: DefectLog,
) -> list[Event]:
    new_api = cfg.schema_change_date.isoformat()
    events: list[Event] = []
    for a in acts:
        api = new_api if a.activity_date >= cfg.schema_change_date else OLD_API
        delivered = a.occurred_at + timedelta(seconds=rng.randrange(1, 300))
        events.append(Event(ids.new("evt"), _EVENT_TYPE[a.kind], a.occurred_at, delivered, api, a))

    log.add(
        "SCHEMA_CHANGE",
        "processor",
        {"api_version": new_api},
        f"from {new_api} payment.captured events carry a new field data.payment_method",
        "bronze: schema evolution handled without dropping or failing rows",
    )

    touched: set[str] = set()
    by_payment: dict[str, list[int]] = {}
    for i, e in enumerate(events):
        by_payment.setdefault(e.activity.payment_id, []).append(i)

    # 1. Missing capture: processor never sends it, bank still pays it out.
    lonely_captures = [
        i
        for i, e in enumerate(events)
        if e.activity.kind == CAPTURE and len(by_payment[e.activity.payment_id]) == 1
    ]
    n_caps = sum(1 for e in events if e.activity.kind == CAPTURE)
    missing = set(
        rng.sample(lonely_captures, k=_k(n_caps, cfg.missing_event_rate, len(lonely_captures)))
    )
    for i in sorted(missing):
        e = events[i]
        touched.add(e.event_id)
        log.add(
            "MISSING_EVENT",
            "processor",
            {
                "payment_id": e.activity.payment_id,
                "merchant_id": e.activity.merchant_id,
                "activity_date": e.activity.activity_date.isoformat(),
            },
            f"capture of {e.activity.amount_minor} {e.activity.currency} never delivered; "
            "bank payout still includes it",
            "recon: bank payout higher than ledger expectation for that merchant and date",
        )

    # 2. Out of order: a refund arrives before the capture it reverses.
    refunds = [i for i, e in enumerate(events) if e.activity.kind == REFUND and i not in missing]
    n_refunds = len(refunds)
    for ri in sorted(rng.sample(refunds, k=_k(n_refunds, cfg.out_of_order_rate, n_refunds))):
        refund = events[ri]
        ci = by_payment[refund.activity.payment_id][0]
        capture = events[ci]
        if ci in missing or capture.event_id in touched:
            continue
        new_delivery = refund.delivered_at + timedelta(seconds=rng.randrange(600, 6 * 3600))
        events[ci] = replace(capture, delivered_at=new_delivery)
        touched.update({capture.event_id, refund.event_id})
        log.add(
            "OUT_OF_ORDER",
            "processor",
            {
                "capture_event_id": capture.event_id,
                "refund_event_id": refund.event_id,
                "payment_id": refund.activity.payment_id,
            },
            "refund delivered before the capture it reverses",
            "silver: order by created_at (event time), not delivered_at; no orphan refunds",
        )

    # 3. Late arrival: delivered 2 to 5 days after it happened.
    untouched = [i for i, e in enumerate(events) if i not in missing and e.event_id not in touched]
    for i in sorted(rng.sample(untouched, k=_k(len(events), cfg.late_rate, len(untouched)))):
        e = events[i]
        delay = timedelta(seconds=rng.randrange(2 * 86400, 5 * 86400))
        events[i] = replace(e, delivered_at=e.created_at + delay)
        touched.add(e.event_id)
        log.add(
            "LATE_ARRIVAL",
            "processor",
            {"event_id": e.event_id},
            f"created {_ts(e.created_at)}, delivered {_ts(e.created_at + delay)}",
            "silver/recon: late event lands in the right activity date; earlier days re-reconciled",
        )

    # 4. Exact duplicate: same event_id redelivered.
    untouched = [i for i, e in enumerate(events) if i not in missing and e.event_id not in touched]
    dupes: list[Event] = []
    for i in sorted(rng.sample(untouched, k=_k(len(events), cfg.duplicate_rate, len(untouched)))):
        e = events[i]
        again = e.delivered_at + timedelta(seconds=rng.randrange(30, 6 * 3600))
        dupes.append(replace(e, delivered_at=again))
        touched.add(e.event_id)
        log.add(
            "DUPLICATE_DELIVERY",
            "processor",
            {"event_id": e.event_id},
            "same event_id delivered twice",
            "silver: dedup on event_id",
        )

    # 5. Duplicate with a fresh event_id: processor retried and minted a new id.
    caps = [
        i
        for i, e in enumerate(events)
        if e.activity.kind == CAPTURE and i not in missing and e.event_id not in touched
    ]
    for i in sorted(rng.sample(caps, k=_k(n_caps, cfg.duplicate_new_id_rate, len(caps)))):
        e = events[i]
        twin = replace(
            e,
            event_id=ids.new("evt"),
            delivered_at=e.delivered_at + timedelta(seconds=rng.randrange(60, 2 * 3600)),
        )
        dupes.append(twin)
        touched.add(e.event_id)
        log.add(
            "DUPLICATE_NEW_EVENT_ID",
            "processor",
            {
                "original_event_id": e.event_id,
                "duplicate_event_id": twin.event_id,
                "payment_id": e.activity.payment_id,
            },
            "same capture sent twice under different event_ids",
            "silver: dedup on business key (payment_id, event_type), not only event_id",
        )

    kept = [e for i, e in enumerate(events) if i not in missing] + dupes
    kept.sort(key=lambda e: (e.delivered_at, e.event_id))
    return kept
