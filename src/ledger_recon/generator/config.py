"""Generator settings. Every run with the same config produces identical bytes."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta


@dataclass(frozen=True)
class GeneratorConfig:
    seed: int = 42
    start_date: date = date(2026, 10, 1)
    days: int = 30
    merchants: int = 25
    payments_per_day: int = 150

    # Payment lifecycle
    refund_rate: float = 0.06
    chargeback_rate: float = 0.008

    # Merchant master
    merchant_change_rate: float = 0.30
    snapshot_gap_rate: float = 0.004

    # Processor defects (share of eligible events)
    duplicate_rate: float = 0.02
    duplicate_new_id_rate: float = 0.005
    late_rate: float = 0.03
    out_of_order_rate: float = 0.25
    missing_event_rate: float = 0.002

    # Bank defects (share of payouts)
    delayed_payout_rate: float = 0.05
    missing_payout_rate: float = 0.01
    missing_reference_rate: float = 0.03
    bank_charge_rate: float = 0.04
    resend_files: int = 1

    # FX: bank converts at mid minus this spread
    fx_spread_bps: int = 35

    # Bank holidays (weekends are always non-business days)
    holidays: tuple[date, ...] = field(default=(date(2026, 10, 2),))

    def __post_init__(self) -> None:
        if self.days < 14:
            raise ValueError("days must be >= 14 so merchant changes and late data fit")
        if self.merchants < 6:
            raise ValueError("merchants must be >= 6 so every change type is covered")

    @property
    def end_date(self) -> date:
        """Last day of activity (inclusive)."""
        return self.start_date + timedelta(days=self.days - 1)

    @property
    def schema_change_date(self) -> date:
        """From this day the processor sends a newer API version with an extra field."""
        return self.start_date + timedelta(days=int(self.days * 0.6))

    def as_dict(self) -> dict[str, object]:
        raw = asdict(self)
        raw["start_date"] = self.start_date.isoformat()
        raw["holidays"] = [d.isoformat() for d in self.holidays]
        return raw
