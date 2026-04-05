"""
Management command to update exchange rates from Frankfurter API
Usage: python manage.py update_exchange_rates
"""

from django.core.management.base import BaseCommand
from django.core.cache import cache
from currency.models import ExchangeRate
from decimal import Decimal
import requests
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Update exchange rates from Frankfurter API (https://www.frankfurter.app)'

    def handle(self, *args, **options):
        """
        Fetch latest exchange rates from Frankfurter API.
        Rates are relative to EUR (base currency).
        """
        self.stdout.write('Fetching exchange rates from Frankfurter API...')

        # Currencies to fetch
        currencies = ['USD', 'RUB', 'GBP', 'BTC']

        try:
            # Frankfurter API: get latest rates with EUR as base
            # Note: Frankfurter doesn't support BTC, so we'll handle it separately
            url = 'https://api.frankfurter.app/latest'
            params = {
                'from': 'EUR',
                'to': ','.join([c for c in currencies if c != 'BTC'])
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Update rates in database
            updated_count = 0
            for currency_code, rate in data['rates'].items():
                rate_decimal = Decimal(str(rate))

                ExchangeRate.objects.update_or_create(
                    currency=currency_code,
                    defaults={'rate_to_eur': rate_decimal}
                )

                self.stdout.write(
                    self.style.SUCCESS(f'✓ Updated {currency_code}: 1 EUR = {rate_decimal} {currency_code}')
                )
                updated_count += 1

                # Clear cache for this currency
                # Note: Django Redis cache doesn't have delete_pattern, we'll rely on TTL expiry

            # Handle RUB and BTC separately (using CoinGecko API)
            # Frankfurter doesn't support RUB or BTC
            try:
                crypto_url = 'https://api.coingecko.com/api/v3/simple/price'
                crypto_params = {
                    'ids': 'bitcoin',
                    'vs_currencies': 'eur,rub'
                }
                crypto_response = requests.get(crypto_url, params=crypto_params, timeout=10)
                crypto_response.raise_for_status()
                crypto_data = crypto_response.json()

                # BTC: Convert 1 EUR = X BTC
                eur_per_btc = Decimal(str(crypto_data['bitcoin']['eur']))
                btc_per_eur = Decimal('1.0') / eur_per_btc

                ExchangeRate.objects.update_or_create(
                    currency='BTC',
                    defaults={'rate_to_eur': btc_per_eur}
                )

                self.stdout.write(
                    self.style.SUCCESS(f'✓ Updated BTC: 1 EUR = {btc_per_eur:.8f} BTC')
                )
                updated_count += 1

                # RUB: Convert 1 EUR = X RUB
                # CoinGecko gives us BTC price in RUB, so we need to calculate
                # 1 BTC = Y RUB, 1 BTC = Z EUR, therefore 1 EUR = (Y/Z) RUB
                rub_per_btc = Decimal(str(crypto_data['bitcoin']['rub']))
                rub_per_eur = rub_per_btc / eur_per_btc

                ExchangeRate.objects.update_or_create(
                    currency='RUB',
                    defaults={'rate_to_eur': rub_per_eur}
                )

                self.stdout.write(
                    self.style.SUCCESS(f'✓ Updated RUB: 1 EUR = {rub_per_eur:.2f} RUB')
                )
                updated_count += 1

            except Exception as crypto_error:
                self.stdout.write(
                    self.style.WARNING(f'⚠ Failed to update BTC/RUB rates: {crypto_error}')
                )
                logger.warning(f'Crypto/RUB rate update failed: {crypto_error}')

            self.stdout.write(
                self.style.SUCCESS(f'\n✓ Successfully updated {updated_count} exchange rates')
            )

            # Log update
            logger.info(f'Exchange rates updated successfully: {updated_count} currencies')

        except requests.RequestException as e:
            self.stdout.write(
                self.style.ERROR(f'✗ Failed to fetch exchange rates: {e}')
            )
            logger.error(f'Exchange rate update failed: {e}', exc_info=True)
            raise

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'✗ Unexpected error: {e}')
            )
            logger.error(f'Unexpected error during exchange rate update: {e}', exc_info=True)
            raise
