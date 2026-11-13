"""Daily FX mid rates, published on business days only (weekends have no row)."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ledger_recon.generator.bizdays import days_between, is_business_day

SIX_DP = Decimal("0.000001")
AED_USD_PEG = Decimal("3.6725")


@dataclass(frozen=True)
class FxRate:
    rate_date: date
    base_currency: str
    quote_currency: str
    mid_rate: Decimal


class FxTable:
    def __init__(self, rates: list[FxRate]) -> None:
        self._rates = rates
        self._index = {(r.rate_date, r.base_currency, r.quote_currency): r.mid_rate for r in rates}

    @property
    def rates(self) -> list[FxRate]:
        return list(self._rates)

    def rate(self, on: date, base: str, quote: str) -> Decimal:
        if base == quote:
            return Decimal(1)
        return self._index[(on, base, quote)]


def build_fx(rng: random.Random, start: date, end: date, holidays: tuple[date, ...]) -> FxTable:
    usd_inr = Decimal("88.40")
    gbp_inr = Decimal("116.20")
    rates: list[FxRate] = []
    for d in days_between(start, end):
        if not is_business_day(d, holidays):
            continue
        usd_inr = (usd_inr + Decimal(str(round(rng.gauss(0, 0.15), 4)))).quantize(SIX_DP)
        gbp_inr = (gbp_inr + Decimal(str(round(rng.gauss(0, 0.35), 4)))).quantize(SIX_DP)
        aed_inr = (usd_inr / AED_USD_PEG).quantize(SIX_DP)
        rates.append(FxRate(d, "USD", "INR", usd_inr))
        rates.append(FxRate(d, "AED", "INR", aed_inr))
        rates.append(FxRate(d, "GBP", "INR", gbp_inr))
    return FxTable(rates)
