"""
Lightning Network Wallet Service
Provides abstraction for working with different LN wallet providers (LNbits, Alby, LND)
"""

from typing import Dict, Optional, Any
from dataclasses import dataclass
import logging
import requests
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


@dataclass
class LNInvoice:
    """Lightning Network invoice"""
    payment_request: str  # BOLT11 invoice string
    payment_hash: str
    amount_sats: int
    description: str
    expires_at: Optional[str] = None


class WalletProvider(ABC):
    """Abstract base class for Lightning wallet providers"""

    @abstractmethod
    def create_invoice(self, amount_sats: int, memo: str = "") -> LNInvoice:
        """Create a Lightning invoice"""
        pass

    @abstractmethod
    def check_invoice(self, payment_hash: str) -> Dict[str, Any]:
        """Check invoice payment status"""
        pass

    @abstractmethod
    def pay_invoice(self, bolt11: str) -> Dict[str, Any]:
        """Pay a BOLT11 Lightning invoice"""
        pass

    @abstractmethod
    def test_connection(self) -> Dict[str, Any]:
        """Test wallet connection and return balance/status info"""
        pass


class LNbitsProvider(WalletProvider):
    """LNbits wallet provider implementation"""

    def __init__(self, api_url: str, invoice_key: str, admin_key: str = ""):
        """
        Initialize LNbits provider.

        Args:
            api_url: LNbits instance URL (e.g., https://legend.lnbits.com)
            invoice_key: Invoice/Read key for creating invoices
            admin_key: Admin key for paying invoices (required for advertisers)
        """
        self.api_url = api_url.rstrip('/')
        self.invoice_key = invoice_key
        self.admin_key = admin_key

    def create_invoice(self, amount_sats: int, memo: str = "") -> LNInvoice:
        """Create invoice via LNbits API"""
        url = f"{self.api_url}/api/v1/payments"
        headers = {
            "X-Api-Key": self.invoice_key,
            "Content-Type": "application/json"
        }
        payload = {
            "out": False,  # Incoming payment
            "amount": amount_sats,
            "memo": memo,
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()

            return LNInvoice(
                payment_request=data['payment_request'],
                payment_hash=data['payment_hash'],
                amount_sats=amount_sats,
                description=memo,
            )
        except requests.RequestException as e:
            logger.error(f"LNbits API error: {e}")
            raise Exception(f"Failed to create invoice: {e}")

    def check_invoice(self, payment_hash: str) -> Dict[str, Any]:
        """Check invoice status via LNbits API"""
        url = f"{self.api_url}/api/v1/payments/{payment_hash}"
        headers = {"X-Api-Key": self.invoice_key}

        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"LNbits check invoice error: {e}")
            raise Exception(f"Failed to check invoice: {e}")

    def pay_invoice(self, bolt11: str) -> Dict[str, Any]:
        """Pay a BOLT11 invoice via LNbits API (requires admin_key)"""
        if not self.admin_key:
            raise ValueError("LNbits admin_key required to pay invoices")

        url = f"{self.api_url}/api/v1/payments"
        headers = {
            "X-Api-Key": self.admin_key,
            "Content-Type": "application/json"
        }
        payload = {
            "out": True,
            "bolt11": bolt11,
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            return {
                'payment_hash': data.get('payment_hash', ''),
                'checking_id': data.get('checking_id', ''),
            }
        except requests.RequestException as e:
            logger.error(f"LNbits pay_invoice error: {e}")
            raise Exception(f"Failed to pay invoice via LNbits: {e}")

    def test_connection(self) -> Dict[str, Any]:
        """Test LNbits connection by fetching wallet info"""
        url = f"{self.api_url}/api/v1/wallet"
        headers = {"X-Api-Key": self.invoice_key}

        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            return {
                'success': True,
                'provider': 'lnbits',
                'name': data.get('name', ''),
                'balance_sats': data.get('balance', 0) // 1000,  # LNbits returns msats
            }
        except requests.RequestException as e:
            logger.error(f"LNbits test_connection error: {e}")
            raise Exception(f"LNbits connection failed: {e}")


class AlbyProvider(WalletProvider):
    """Getalby.com wallet provider implementation"""

    def __init__(self, access_token: str):
        """
        Initialize Alby provider.

        Args:
            access_token: Alby OAuth access token (invoice permission)
        """
        self.api_url = "https://api.getalby.com"
        self.access_token = access_token

    def create_invoice(self, amount_sats: int, memo: str = "") -> LNInvoice:
        """Create invoice via Alby API"""
        url = f"{self.api_url}/invoices"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "amount": amount_sats,
            "description": memo,
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()

            return LNInvoice(
                payment_request=data['payment_request'],
                payment_hash=data['payment_hash'],
                amount_sats=amount_sats,
                description=memo,
            )
        except requests.RequestException as e:
            logger.error(f"Alby API error: {e}")
            raise Exception(f"Failed to create invoice: {e}")

    def check_invoice(self, payment_hash: str) -> Dict[str, Any]:
        """Check invoice status via Alby API"""
        url = f"{self.api_url}/invoices/{payment_hash}"
        headers = {"Authorization": f"Bearer {self.access_token}"}

        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Alby check invoice error: {e}")
            raise Exception(f"Failed to check invoice: {e}")

    def pay_invoice(self, bolt11: str) -> Dict[str, Any]:
        """Pay a BOLT11 invoice via Alby API"""
        url = f"{self.api_url}/payments/bolt11"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        payload = {"invoice": bolt11}

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            return {
                'payment_hash': data.get('payment_hash', ''),
                'payment_preimage': data.get('payment_preimage', ''),
            }
        except requests.RequestException as e:
            logger.error(f"Alby pay_invoice error: {e}")
            raise Exception(f"Failed to pay invoice via Alby: {e}")

    def test_connection(self) -> Dict[str, Any]:
        """Test Alby connection by fetching balance"""
        url = f"{self.api_url}/balance"
        headers = {"Authorization": f"Bearer {self.access_token}"}

        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 401:
                raise Exception("Invalid token or missing permissions. Required: balance:read, payments:send")
            if response.status_code == 403:
                raise Exception("Token lacks required permissions. Required: balance:read, payments:send")
            response.raise_for_status()
            data = response.json()
            return {
                'success': True,
                'provider': 'alby',
                'balance_sats': data.get('balance', 0),
            }
        except requests.ConnectionError:
            raise Exception("Cannot reach api.getalby.com")
        except requests.Timeout:
            raise Exception("Alby API timeout")
        except requests.RequestException as e:
            if "Invalid token" in str(e) or "missing permissions" in str(e) or "lacks required" in str(e):
                raise
            logger.error(f"Alby test_connection error: {e}")
            raise Exception(f"Alby connection failed: {e}")


def create_wallet_client(wallet_config: Dict[str, Any]) -> WalletProvider:
    """
    Factory function to create appropriate wallet provider client.

    Args:
        wallet_config: Configuration dict with provider info
            {
                "provider": "lnbits" | "alby" | "lnd",
                "api_url": "https://...",  # For LNbits/LND
                "invoice_key": "...",       # For LNbits
                "access_token": "...",      # For Alby
                "macaroon": "...",          # For LND
                "cert": "..."               # For LND
            }

    Returns:
        WalletProvider instance

    Raises:
        ValueError: If provider is unsupported or config is invalid
    """
    provider = wallet_config.get('provider')

    if not provider:
        raise ValueError("Missing 'provider' in wallet_config")

    if provider == 'lnbits':
        api_url = wallet_config.get('api_url')
        invoice_key = wallet_config.get('invoice_key')
        admin_key = wallet_config.get('admin_key', '')

        if not api_url or not invoice_key:
            raise ValueError("LNbits requires 'api_url' and 'invoice_key'")

        return LNbitsProvider(api_url=api_url, invoice_key=invoice_key, admin_key=admin_key)

    elif provider == 'alby':
        access_token = wallet_config.get('access_token')

        if not access_token:
            raise ValueError("Alby requires 'access_token'")

        return AlbyProvider(access_token=access_token)

    else:
        raise ValueError(f"Unsupported wallet provider: {provider}")


def send_payment_via_lnurl(ln_address: str, amount_sats: int, wallet_config: dict, comment: str = "") -> Dict[str, Any]:
    """
    Send payment to Lightning address via LNURL-pay protocol.

    Args:
        ln_address: Lightning address (user@domain.com)
        amount_sats: Amount in satoshis
        wallet_config: Decrypted wallet config of the advertiser (payer)
        comment: Optional payment comment

    Returns:
        Payment result dict with 'success', 'invoice', 'payment_hash'
    """
    try:
        # Parse Lightning address
        if '@' not in ln_address:
            raise ValueError("Invalid Lightning address format")

        username, domain = ln_address.split('@')

        # Step 1: Get LNURL metadata
        metadata_url = f"https://{domain}/.well-known/lnurlp/{username}"
        metadata_response = requests.get(metadata_url, timeout=10)
        metadata_response.raise_for_status()
        metadata = metadata_response.json()

        if metadata.get('tag') != 'payRequest':
            raise ValueError("Invalid LNURL-pay response")

        # Step 2: Request invoice from viewer's wallet
        callback_url = metadata['callback']
        amount_msat = amount_sats * 1000

        params = {'amount': amount_msat}
        if comment:
            params['comment'] = comment

        invoice_response = requests.get(callback_url, params=params, timeout=10)
        invoice_response.raise_for_status()
        invoice_data = invoice_response.json()

        if invoice_data.get('status') == 'ERROR':
            raise Exception(f"LNURL error: {invoice_data.get('reason')}")

        invoice_pr = invoice_data.get('pr')
        if not invoice_pr:
            raise Exception("No invoice returned from LNURL callback")

        # Step 3: Pay invoice using advertiser's wallet
        wallet_client = create_wallet_client(wallet_config)
        payment_result = wallet_client.pay_invoice(invoice_pr)

        logger.info(f"LNURL payment sent: {amount_sats} sats to {ln_address}")

        return {
            'success': True,
            'invoice': invoice_pr,
            'payment_hash': payment_result.get('payment_hash', ''),
        }

    except Exception as e:
        logger.error(f"LNURL payment failed: {e}")
        return {
            'success': False,
            'error': str(e)
        }
