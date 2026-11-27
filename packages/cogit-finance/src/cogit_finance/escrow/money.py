"""Money in integer minor units. No floats anywhere (SPEC §10.1)."""

from __future__ import annotations

BPS = 10_000


def _whole(name: str, value: object) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer of minor units or basis points")
    return value


def fee_minor(price_minor: int, fee_bps: int) -> int:
    """The fee, rounded half up to the cent: ``(price * bps + 5000) div 10000``."""
    price = _whole("price_minor", price_minor)
    bps = _whole("fee_bps", fee_bps)
    if price < 0 or not 0 <= bps <= BPS:
        raise ValueError("price_minor must be >= 0 and fee_bps within 0..10000")
    return (price * bps + BPS // 2) // BPS


def split(price_minor: int, fee_bps: int) -> tuple[int, int]:
    """``(payout_minor, fee_minor)``: the fee is taken from the seller's payout."""
    fee = fee_minor(price_minor, fee_bps)
    return price_minor - fee, fee
