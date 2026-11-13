"""Merchant master: contract terms that change over time, and the daily snapshots
that report those changes (sometimes late, sometimes with gaps)."""

from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, time, timedelta

from ledger_recon.generator.bizdays import days_between
from ledger_recon.generator.config import GeneratorConfig
from ledger_recon.generator.truth import DefectLog

# Fictional names only.
_NAMES = [
    "Saffron Street Foods",
    "Kestrel Outdoor Gear",
    "Indigo Loom Textiles",
    "Northpeak Books",
    "Monsoon Home Decor",
    "Bluefin Electronics",
    "Tamarind Travel Co",
    "Cedarline Pharmacy",
    "Pixel Orchard Games",
    "Harbor Lane Apparel",
    "Copperleaf Coffee",
    "Riverbend Fitness",
    "Lotus Grid Energy",
    "Quillmark Stationery",
    "Sandstone Ceramics",
    "Velvet Tide Cosmetics",
    "Granite Peak Hardware",
    "Marigold Event Hire",
    "Silverfern Pet Supplies",
    "Tidewater Tickets",
    "Ashgrove Learning",
    "Brightkite Toys",
    "Coral Bay Rentals",
    "Driftwood Furniture",
    "Emberline Kitchenware",
    "Fableworks Studio",
    "Glasshouse Florists",
    "Hilltop Dairy",
    "Ironbark Tools",
    "Jadeview Opticals",
]

# (presentment, settlement, country, weight)
_CURRENCY_PROFILES: list[tuple[str, str, str, float]] = [
    ("INR", "INR", "IN", 0.70),
    ("USD", "USD", "US", 0.10),
    ("USD", "INR", "IN", 0.12),
    ("AED", "INR", "IN", 0.05),
    ("GBP", "INR", "IN", 0.03),
]

# Order matters: the first plan items go to the busiest merchants that get a change,
# so the fee-drift window is guaranteed to contain captures.
_CHANGE_PLAN: list[tuple[str, str]] = [
    ("FEE", "processor_lag"),
    ("FEE", "master_late"),
    ("FEE", "normal"),
    ("NAME", "normal"),
    ("LAG", "normal"),
    ("SUSPEND", "normal"),
]

PROCESSOR_FEE_LAG_DAYS = 3
MASTER_LATE_DAYS = 2


@dataclass(frozen=True)
class MerchantVersion:
    merchant_id: str
    legal_name: str
    country: str
    presentment_currency: str
    settlement_currency: str
    fee_bps: int
    settlement_lag_days: int
    status: str
    updated_at: datetime
    effective_from: date


@dataclass
class Merchant:
    merchant_id: str
    rank: int
    versions: list[MerchantVersion]
    # Day each version first shows up in the master snapshots. Normally equals
    # effective_from; later when the master is late.
    visible_from: list[date]
    # (from, until_exclusive, old_bps) when the processor keeps charging the old fee.
    processor_fee_override: tuple[date, date, int] | None = None
    change: tuple[str, str, date] | None = field(default=None)

    def on(self, d: date) -> MerchantVersion:
        current = self.versions[0]
        for v in self.versions:
            if v.effective_from <= d:
                current = v
        return current

    def visible_on(self, d: date) -> MerchantVersion:
        current = self.versions[0]
        for v, seen in zip(self.versions, self.visible_from, strict=True):
            if seen <= d:
                current = v
        return current

    def fee_bps_charged(self, d: date) -> int:
        """Fee the processor actually applies, which can lag the contract."""
        if self.processor_fee_override:
            start, until, old_bps = self.processor_fee_override
            if start <= d < until:
                return old_bps
        return self.on(d).fee_bps

    @property
    def presentment_currency(self) -> str:
        return self.versions[0].presentment_currency

    @property
    def settlement_currency(self) -> str:
        return self.versions[0].settlement_currency


def _at(d: date, hour: int) -> datetime:
    return datetime.combine(d, time(hour, 0), tzinfo=UTC)


def _pick_profile(rng: random.Random) -> tuple[str, str, str]:
    weights = [p[3] for p in _CURRENCY_PROFILES]
    pres, sett, country, _ = rng.choices(_CURRENCY_PROFILES, weights=weights, k=1)[0]
    return pres, sett, country


def build_merchants(cfg: GeneratorConfig, rng: random.Random, log: DefectLog) -> list[Merchant]:
    names = rng.sample(_NAMES, k=min(cfg.merchants, len(_NAMES)))
    while len(names) < cfg.merchants:
        names.append(f"Merchant {len(names) + 1:03d}")

    merchants: list[Merchant] = []
    for rank, name in enumerate(names):
        pres, sett, country = _pick_profile(rng)
        cross_border = pres != sett
        fee = rng.randrange(290, 355, 5) if cross_border else rng.randrange(175, 255, 5)
        base = MerchantVersion(
            merchant_id=f"M{rank + 1:04d}",
            legal_name=name,
            country=country,
            presentment_currency=pres,
            settlement_currency=sett,
            fee_bps=fee,
            settlement_lag_days=1 if rng.random() < 0.8 else 2,
            status="ACTIVE",
            updated_at=_at(cfg.start_date - timedelta(days=rng.randint(30, 400)), 9),
            effective_from=cfg.start_date,
        )
        merchants.append(Merchant(base.merchant_id, rank, [base], [cfg.start_date]))

    _apply_changes(cfg, rng, merchants, log)
    return merchants


def _apply_changes(
    cfg: GeneratorConfig, rng: random.Random, merchants: list[Merchant], log: DefectLog
) -> None:
    count = max(len(_CHANGE_PLAN), round(cfg.merchants * cfg.merchant_change_rate))
    count = min(count, len(merchants))
    chosen = sorted(rng.sample(range(len(merchants)), k=count))  # sorted by rank = by volume
    plan = [_CHANGE_PLAN[i % len(_CHANGE_PLAN)] for i in range(count)]

    for idx, (kind, variant) in zip(chosen, plan, strict=True):
        m = merchants[idx]
        old = m.versions[0]
        change_day = cfg.start_date + timedelta(days=rng.randint(5, cfg.days - 6))
        new = replace(old, effective_from=change_day, updated_at=_at(change_day, 9))

        if kind == "FEE":
            delta = rng.choice([-25, -15, 15, 25, 40])
            new = replace(new, fee_bps=max(100, old.fee_bps + delta))
        elif kind == "NAME":
            new = replace(new, legal_name=f"{old.legal_name} Pvt Ltd")
        elif kind == "LAG":
            new = replace(new, settlement_lag_days=2 if old.settlement_lag_days == 1 else 1)
        elif kind == "SUSPEND":
            new = replace(new, status="SUSPENDED")

        visible = change_day
        if variant == "master_late":
            visible = change_day + timedelta(days=MASTER_LATE_DAYS)
            log.add(
                "BACKDATED_MASTER_CHANGE",
                "merchant_master",
                {"merchant_id": m.merchant_id, "effective_from": change_day.isoformat()},
                f"fee {old.fee_bps}->{new.fee_bps} bps effective {change_day}, first appears "
                f"in snapshot {visible} with updated_at {new.updated_at:%Y-%m-%dT%H:%M:%SZ}",
                "silver SCD2: effective_from must come from updated_at, not snapshot_date",
            )
        if variant == "processor_lag":
            until = change_day + timedelta(days=PROCESSOR_FEE_LAG_DAYS)
            m.processor_fee_override = (change_day, until, old.fee_bps)

        m.versions.append(new)
        m.visible_from.append(visible)
        m.change = (kind, variant, change_day)


def snapshot_rows(
    cfg: GeneratorConfig, rng: random.Random, merchants: list[Merchant], log: DefectLog
) -> dict[date, list[dict[str, object]]]:
    days = days_between(cfg.start_date, cfg.end_date)
    cells = [(d, m.merchant_id) for d in days[1:] for m in merchants]
    k = max(1, round(len(cells) * cfg.snapshot_gap_rate)) if cfg.snapshot_gap_rate > 0 else 0
    gaps = set(rng.sample(cells, k=k))
    for d, mid in sorted(gaps):
        log.add(
            "SNAPSHOT_GAP",
            "merchant_master",
            {"merchant_id": mid, "snapshot_date": d.isoformat()},
            "merchant missing from one daily snapshot, present the day before and after",
            "silver SCD2: absence from one snapshot is not a deletion",
        )

    out: dict[date, list[dict[str, object]]] = {}
    for d in days:
        rows: list[dict[str, object]] = []
        for m in merchants:
            if (d, m.merchant_id) in gaps:
                continue
            v = m.visible_on(d)
            rows.append(
                {
                    "merchant_id": v.merchant_id,
                    "legal_name": v.legal_name,
                    "country": v.country,
                    "presentment_currency": v.presentment_currency,
                    "settlement_currency": v.settlement_currency,
                    "fee_bps": v.fee_bps,
                    "settlement_lag_days": v.settlement_lag_days,
                    "status": v.status,
                    "updated_at": v.updated_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
            )
        out[d] = rows
    return out


def change_rows(merchants: list[Merchant]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for m in merchants:
        if not m.change:
            continue
        kind, variant, day = m.change
        old, new = m.versions[0], m.versions[1]
        rows.append(
            {
                "merchant_id": m.merchant_id,
                "change_type": kind,
                "variant": variant,
                "effective_from": day.isoformat(),
                "visible_from": m.visible_from[1].isoformat(),
                "old_fee_bps": old.fee_bps,
                "new_fee_bps": new.fee_bps,
                "old_lag_days": old.settlement_lag_days,
                "new_lag_days": new.settlement_lag_days,
                "old_status": old.status,
                "new_status": new.status,
                "old_name": old.legal_name,
                "new_name": new.legal_name,
            }
        )
    return rows
