"""
EUR→sats quoting for fiat-priced ticket types.

Rate source: currency.ExchangeRate BTC row (updated daily by
`update_exchange_rates`, BTC via CoinGecko). The charging path
(strict=True) refuses to quote from a missing or stale rate; the
display path returns an approximation or None.
"""
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from django.utils import timezone

SATS_PER_BTC = Decimal(100_000_000)
MAX_RATE_AGE = timedelta(hours=48)


class RateUnavailable(Exception):
    """BTC/EUR rate missing, non-positive, or too stale to charge against."""


def sats_per_eur(strict: bool = False) -> Optional[Decimal]:
    """Sats per 1 EUR. strict=True raises RateUnavailable instead of returning None."""
    from currency.models import ExchangeRate
    try:
        row = ExchangeRate.objects.get(currency='BTC')
    except ExchangeRate.DoesNotExist:
        if strict:
            raise RateUnavailable("BTC/EUR exchange rate not available")
        return None
    if row.rate_to_eur <= 0:
        if strict:
            raise RateUnavailable("BTC/EUR exchange rate invalid")
        return None
    if strict and timezone.now() - row.updated_at > MAX_RATE_AGE:
        raise RateUnavailable("BTC/EUR exchange rate is stale")
    # rate_to_eur: 1 EUR = X BTC
    return row.rate_to_eur * SATS_PER_BTC


def eur_to_sats(eur: Decimal, rate: Optional[Decimal] = None, strict: bool = False) -> Optional[int]:
    """Convert a EUR amount to sats, optionally with a pre-fetched rate."""
    if rate is None:
        rate = sats_per_eur(strict=strict)
    if rate is None:
        return None
    return int((Decimal(eur) * rate).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
