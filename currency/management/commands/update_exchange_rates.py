"""
Management command to update exchange rates.

Two independent upstreams:
  - Frankfurter (fiat: USD, GBP)
  - CoinGecko (BTC, RUB)

Usage: python manage.py update_exchange_rates
"""

from django.core.management.base import BaseCommand, CommandError
from currency.models import ExchangeRate
from decimal import Decimal
import time
import requests
import logging

logger = logging.getLogger(__name__)

FRANKFURTER_URL = 'https://api.frankfurter.app/latest'
COINGECKO_URL = 'https://api.coingecko.com/api/v3/simple/price'

# A single transient ReadTimeout used to leave the BTC rate stale for a whole
# day; EUR-priced tickets refuse to charge past 48h (tickets/pricing.py), so a
# two-run outage takes ticket sales down. Retry before giving up.
HTTP_TIMEOUT = 20
RETRY_DELAYS = (5, 15)


class Command(BaseCommand):
    help = 'Update exchange rates from Frankfurter (fiat) and CoinGecko (BTC/RUB)'

    def handle(self, *args, **options):
        fiat_count = self._run_step('fiat', self._update_fiat)
        crypto_count = self._run_step('BTC/RUB', self._update_crypto)

        updated = fiat_count + crypto_count
        if updated:
            self.stdout.write(self.style.SUCCESS(f'\n✓ Successfully updated {updated} exchange rates'))
            logger.info(f'Exchange rates updated successfully: {updated} currencies')

        # Only a total blackout is a failure — one upstream down must not hide
        # the other's fresh rates behind a non-zero exit.
        if not updated:
            raise CommandError('All exchange rate upstreams failed — no rates updated')

        return None

    def _run_step(self, label, step):
        """Run one upstream update; log and swallow its failure, return rows written."""
        try:
            return step()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Failed to update {label} rates: {e}'))
            logger.error(f'Exchange rate update failed ({label}): {e}', exc_info=True)
            return 0

    def _fetch_json(self, url, params, label):
        """GET with retries — transient timeouts are the common failure here."""
        last_error = None
        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                response = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
                response.raise_for_status()
                return response.json()
            except requests.RequestException as e:
                last_error = e
                if attempt < len(RETRY_DELAYS):
                    delay = RETRY_DELAYS[attempt]
                    self.stdout.write(self.style.WARNING(
                        f'⚠ {label} attempt {attempt + 1} failed ({e}); retrying in {delay}s'
                    ))
                    time.sleep(delay)
        raise last_error

    def _store(self, currency, rate, display):
        ExchangeRate.objects.update_or_create(currency=currency, defaults={'rate_to_eur': rate})
        self.stdout.write(self.style.SUCCESS(f'✓ Updated {currency}: 1 EUR = {display} {currency}'))

    def _update_fiat(self):
        """Frankfurter: EUR-based fiat rates."""
        self.stdout.write('Fetching fiat rates from Frankfurter API...')
        data = self._fetch_json(FRANKFURTER_URL, {'from': 'EUR', 'to': 'USD,GBP'}, 'Frankfurter')

        count = 0
        for currency_code, rate in data['rates'].items():
            self._store(currency_code, Decimal(str(rate)), rate)
            count += 1
        return count

    def _update_crypto(self):
        """CoinGecko: BTC and RUB (Frankfurter carries neither)."""
        self.stdout.write('Fetching BTC/RUB rates from CoinGecko API...')
        data = self._fetch_json(
            COINGECKO_URL, {'ids': 'bitcoin', 'vs_currencies': 'eur,rub'}, 'CoinGecko'
        )

        eur_per_btc = Decimal(str(data['bitcoin']['eur']))
        rub_per_btc = Decimal(str(data['bitcoin']['rub']))

        btc_per_eur = Decimal('1.0') / eur_per_btc
        self._store('BTC', btc_per_eur, f'{btc_per_eur:.8f}')

        # CoinGecko prices BTC in both currencies, so RUB/EUR falls out of the ratio.
        rub_per_eur = rub_per_btc / eur_per_btc
        self._store('RUB', rub_per_eur, f'{rub_per_eur:.2f}')

        return 2
