from django.db import models
from django.core.cache import cache
from decimal import Decimal


class ExchangeRate(models.Model):
    """
    Exchange rates storage for currency conversion.
    Rates are stored relative to EUR as base currency.
    """
    currency = models.CharField(max_length=3, primary_key=True, help_text="ISO 4217 currency code")
    rate_to_eur = models.DecimalField(
        max_digits=18,
        decimal_places=8,
        help_text="Exchange rate: 1 EUR = X currency"
    )
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        db_table = 'currency_exchange_rates'

    def __str__(self):
        return f"1 EUR = {self.rate_to_eur} {self.currency}"

    @classmethod
    def get_rate(cls, from_currency: str, to_currency: str) -> Decimal:
        """
        Get exchange rate from one currency to another.
        Uses Redis cache for performance.

        Args:
            from_currency: Source currency code (e.g., 'USD')
            to_currency: Target currency code (e.g., 'EUR')

        Returns:
            Exchange rate as Decimal
        """
        if from_currency == to_currency:
            return Decimal('1.0')

        # Try cache first
        cache_key = f'exchange_rate:{from_currency}:{to_currency}'
        cached_rate = cache.get(cache_key)
        if cached_rate is not None:
            return Decimal(str(cached_rate))

        # Calculate rate through EUR as intermediary
        # 1 from_currency = X EUR
        # 1 EUR = Y to_currency
        # Therefore: 1 from_currency = X * Y to_currency

        if from_currency == 'EUR':
            # Direct conversion from EUR
            to_rate = cls.objects.get(currency=to_currency)
            rate = to_rate.rate_to_eur
        elif to_currency == 'EUR':
            # Direct conversion to EUR
            from_rate = cls.objects.get(currency=from_currency)
            rate = Decimal('1.0') / from_rate.rate_to_eur
        else:
            # Conversion through EUR
            from_rate = cls.objects.get(currency=from_currency)
            to_rate = cls.objects.get(currency=to_currency)

            # from -> EUR -> to
            eur_amount = Decimal('1.0') / from_rate.rate_to_eur
            rate = eur_amount * to_rate.rate_to_eur

        # Cache for 25 hours (rates update daily at 3 AM UTC)
        cache.set(cache_key, float(rate), 90000)  # 25 hours

        return rate

    @classmethod
    def convert(cls, amount: Decimal, from_currency: str, to_currency: str) -> Decimal:
        """
        Convert amount from one currency to another.

        Args:
            amount: Amount to convert
            from_currency: Source currency code
            to_currency: Target currency code

        Returns:
            Converted amount as Decimal
        """
        if amount is None or amount == 0:
            return Decimal('0.0')

        rate = cls.get_rate(from_currency, to_currency)
        return amount * rate
