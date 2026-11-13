"""Integer minor-unit arithmetic. No floats touch an amount."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

# Flat chargeback fee per presentment currency, in minor units.
CHARGEBACK_FEE_MINOR: dict[str, int] = {"INR": 50000, "USD": 1500, "AED": 5500, "GBP": 1200}

# Incoming-credit charge some bank lines carry: Rs 25 + 18% GST.
BANK_CHARGE_INR_MINOR = 2950


def fee_from_bps(amount_minor: int, bps: int) -> int:
    """Processor fee, rounded half up to the minor unit."""
    return int((Decimal(amount_minor) * bps / Decimal(10000)).quantize(Decimal(1), ROUND_HALF_UP))


def convert(amount_minor: int, rate: Decimal, spread_bps: int) -> int:
    """Bank conversion: mid rate less spread, rounded half up (away from zero)."""
    factor = rate * (Decimal(1) - Decimal(spread_bps) / Decimal(10000))
    return int((Decimal(amount_minor) * factor).quantize(Decimal(1), ROUND_HALF_UP))
