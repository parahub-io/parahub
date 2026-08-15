"""
Lightning Network Wallet Service
Provides abstraction for working with different LN wallet providers (LNbits, Alby, LND)
"""

from typing import Dict, Optional, Any
from dataclasses import dataclass
from datetime import timedelta
import asyncio
import logging
import re
import requests
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class WalletRejectedError(Exception):
    """The payer's wallet answered and refused the payment.

    Distinct from a transport failure: the wallet is reachable, so its state
    (balance, permissions) is worth inspecting. An unreachable wallet tells us
    nothing and must not be probed again on the request path."""


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
            if not response.ok:
                detail = response.text[:200]
                logger.error(f"LNbits pay_invoice error: {response.status_code} {detail}")
                raise WalletRejectedError(f"LNbits rejected the payment ({response.status_code}): {detail}")
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
            if not response.ok:
                # Alby answers 400 for an empty/underfunded wallet too, so the
                # body is the only place the actual reason shows up.
                detail = response.text[:200]
                logger.error(f"Alby pay_invoice error: {response.status_code} {detail}")
                raise WalletRejectedError(f"Alby rejected the payment ({response.status_code}): {detail}")
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


class NWCProvider(WalletProvider):
    """Nostr Wallet Connect (NIP-47) — wallet-agnostic remote wallet.

    The advertiser's sats never come near us: we store only a connection string
    that authorises payment requests against a wallet they run or hold
    elsewhere. That is the property the whole payout design rests on — the
    platform holds neither funds nor the means of access to them.

    Works with any NIP-47 wallet (Alby Hub, self-hosted nodes, hosted wallets),
    so an advertiser is never tied to one provider's pricing.

    Encryption: NIP-04 only, which nostr-sdk negotiates for us. A wallet that
    speaks exclusively NIP-44 would need that added here.
    """

    # NIP-47 defines this error vocabulary. Seeing one of these codes means the
    # wallet answered and refused — as opposed to a relay timeout, where we
    # learned nothing and must not treat its state as known.
    WALLET_ERROR_CODES = (
        'INSUFFICIENT_BALANCE', 'PAYMENT_FAILED', 'QUOTA_EXCEEDED',
        'RESTRICTED', 'UNAUTHORIZED', 'NOT_IMPLEMENTED', 'RATE_LIMITED',
        'INTERNAL', 'OTHER',
    )
    # These codes are also everyday English words ("no other relays",
    # "internal error" from a relay), so only their exact on-the-wire
    # spelling counts as the wallet speaking.
    PROSE_WORD_CODES = ('INTERNAL', 'OTHER')

    def __init__(self, connection_uri: str, timeout_secs: int = 20):
        """
        Args:
            connection_uri: `nostr+walletconnect://...` string (carries the secret)
            timeout_secs: how long to wait for the wallet to answer via the relay
        """
        self.connection_uri = connection_uri
        self.timeout_secs = timeout_secs

    def _run(self, operation):
        """Run one NWC round-trip on a private event loop.

        nostr-sdk is async; ad payouts happen inside sync Django views, which
        run in a worker thread with no loop of its own. A client per call also
        keeps the relay connection from outliving the request — payouts are
        rare, so the reconnect is cheaper than a shared connection to babysit.
        """
        from nostr_sdk import NostrWalletConnect, NostrWalletConnectUri, NostrWalletConnectBuilder

        async def run():
            uri = NostrWalletConnectUri.parse(self.connection_uri)
            nwc = NostrWalletConnectBuilder(uri).timeout(
                timedelta(seconds=self.timeout_secs)
            ).build()
            try:
                return await operation(nwc)
            finally:
                try:
                    await nwc.client().shutdown()
                except Exception:
                    logger.debug("NWC client shutdown failed", exc_info=True)

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(run())
        raise Exception("NWC provider must be called from sync code, not inside a running event loop")

    def _classify(self, error: Exception, action: str) -> Exception:
        """Turn an nostr-sdk error into either a refusal or a transport failure.

        The error code is the only signal available — nostr-sdk surfaces every
        failure as one generic error — and wallets word it inconsistently
        ("INSUFFICIENT_BALANCE", "insufficient balance", "InsufficientBalance").
        Multi-word codes are distinctive enough to match with everything but
        letters stripped, which covers all three spellings. Single-word codes
        match as whole words only, and the ones that are everyday English
        words match solely in their exact code spelling — "try another relay"
        or "internal error" from a relay must not read as a wallet refusal.
        """
        message = str(error)
        upper = message.upper()
        squashed = re.sub(r'[^A-Z]', '', upper)
        for code in self.WALLET_ERROR_CODES:
            if '_' in code:
                matched = re.sub(r'[^A-Z]', '', code) in squashed
            elif code in self.PROSE_WORD_CODES:
                matched = re.search(rf'\b{code}\b', message) is not None
            else:
                matched = re.search(rf'\b{code}\b', upper) is not None
            if matched:
                return WalletRejectedError(f"NWC wallet refused the {action}: {message}")
        return Exception(f"NWC {action} failed: {message}")

    def create_invoice(self, amount_sats: int, memo: str = "") -> LNInvoice:
        """Create an invoice via NIP-47 `make_invoice`."""
        from nostr_sdk import MakeInvoiceRequest

        async def op(nwc):
            return await nwc.make_invoice(MakeInvoiceRequest(
                amount=amount_sats * 1000,  # NIP-47 speaks msats
                description=memo or None,
                description_hash=None,
                expiry=None,
            ))

        try:
            result = self._run(op)
        except Exception as e:
            raise self._classify(e, "invoice creation")

        return LNInvoice(
            payment_request=result.invoice,
            payment_hash=result.payment_hash or '',
            amount_sats=amount_sats,
            description=memo,
        )

    def check_invoice(self, payment_hash: str) -> Dict[str, Any]:
        """Look up an invoice via NIP-47 `lookup_invoice`."""
        from nostr_sdk import LookupInvoiceRequest

        async def op(nwc):
            return await nwc.lookup_invoice(LookupInvoiceRequest(
                payment_hash=payment_hash, invoice=None,
            ))

        try:
            result = self._run(op)
        except Exception as e:
            raise self._classify(e, "invoice lookup")

        return {
            'payment_hash': payment_hash,
            'paid': bool(getattr(result, 'settled_at', None)),
            'preimage': getattr(result, 'preimage', None),
        }

    def pay_invoice(self, bolt11: str) -> Dict[str, Any]:
        """Pay a BOLT11 invoice via NIP-47 `pay_invoice`."""
        from nostr_sdk import PayInvoiceRequest

        async def op(nwc):
            return await nwc.pay_invoice(PayInvoiceRequest(
                id=None, invoice=bolt11, amount=None,
            ))

        try:
            result = self._run(op)
        except Exception as e:
            error = self._classify(e, "payment")
            logger.error(f"NWC pay_invoice error: {e}")
            raise error

        return {
            'payment_hash': '',  # NIP-47 answers with the preimage, not the hash
            'payment_preimage': result.preimage,
            'fees_paid_msats': result.fees_paid,
        }

    def test_connection(self) -> Dict[str, Any]:
        """Fetch the wallet balance via NIP-47 `get_balance`."""
        async def op(nwc):
            return await nwc.get_balance()

        try:
            result = self._run(op)
        except Exception as e:
            logger.error(f"NWC test_connection error: {e}")
            raise self._classify(e, "balance check")

        return {
            'success': True,
            'provider': 'nwc',
            'balance_sats': result.balance // 1000,  # NIP-47 reports msats
        }


def create_wallet_client(wallet_config: Dict[str, Any]) -> WalletProvider:
    """
    Factory function to create appropriate wallet provider client.

    Args:
        wallet_config: Configuration dict with provider info
            {
                "provider": "nwc" | "lnbits" | "alby" | "lnd",
                "connection_uri": "nostr+walletconnect://...",  # For NWC
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

    if provider == 'nwc':
        connection_uri = wallet_config.get('connection_uri')

        if not connection_uri:
            raise ValueError("NWC requires 'connection_uri'")

        return NWCProvider(connection_uri=connection_uri)

    elif provider == 'lnbits':
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

    elif provider == 'spark':
        # Browser-paid rail: the advertiser's own Parahub Spark wallet pays
        # from their browser. The server holds no credentials for it at all,
        # so there is nothing to build a server-side client from.
        raise ValueError("The 'spark' provider pays from the advertiser's browser — no server-side client exists")

    else:
        raise ValueError(f"Unsupported wallet provider: {provider}")


def bolt11_amount_msat(invoice: str) -> Optional[int]:
    """Amount a wallet would pay for this BOLT11 invoice, in msats.

    The amount lives only in the invoice's human-readable part, and the hrp is
    covered by the invoice signature the paying wallet verifies — so reading
    the hrp is enough to know what will be paid, no full decode needed.
    Returns None for an amountless or unparseable invoice.
    """
    lowered = invoice.strip().lower()
    separator = lowered.rfind('1')  # bech32 data charset never contains '1'
    if separator <= 0:
        return None
    match = re.match(r'^ln[a-z]+?(\d+)([munp])?$', lowered[:separator])
    if not match:
        return None
    digits, multiplier = int(match.group(1)), match.group(2)
    if multiplier == 'p':
        # pico-bitcoin is 0.1 msat; BOLT11 requires the last digit to be 0
        return digits // 10 if digits % 10 == 0 else None
    msat_per_unit = {None: 10**11, 'm': 10**8, 'u': 10**5, 'n': 10**2}
    return digits * msat_per_unit[multiplier]


_BECH32_CHARSET = 'qpzry9x8gf2tvdw0s3jn54khce6mua7l'


def bolt11_payment_hash(invoice: str) -> Optional[str]:
    """Payment hash (hex) of a BOLT11 invoice, or None if unparseable.

    Walks the invoice's tagged fields for tag 'p' (52×5 bits → 256-bit hash).
    No checksum or signature verification: this reads invoices we resolved and
    stored ourselves, to check a preimage a payer claims — sha256(preimage)
    must equal this hash, which no honest-but-lazy payer can fake.
    """
    lowered = invoice.strip().lower()
    separator = lowered.rfind('1')
    if separator <= 0:
        return None
    try:
        data = [_BECH32_CHARSET.index(c) for c in lowered[separator + 1:-6]]
    except ValueError:
        return None
    # 7 chars of timestamp first; the last 104 chars are the signature
    pos, end = 7, len(data) - 104
    while pos + 3 <= end:
        tag = data[pos]
        length = data[pos + 1] * 32 + data[pos + 2]
        start = pos + 3
        if start + length > end:
            return None
        if tag == 1 and length == 52:  # 'p' = payment hash
            acc = bits = 0
            out = bytearray()
            for value in data[start:start + length]:
                acc = (acc << 5) | value
                bits += 5
                while bits >= 8:
                    bits -= 8
                    out.append((acc >> bits) & 0xFF)
            return bytes(out[:32]).hex()
        pos = start + length
    return None


def resolve_lnurl_invoice(ln_address: str, amount_sats: int, comment: str = "") -> str:
    """Ask a Lightning address for a BOLT11 invoice of exactly `amount_sats`.

    LNURL-pay steps 1-2 (metadata → callback → invoice), amount-verified per
    LUD-06: the receiver's server chose the invoice, so it is checked against
    the requested amount before anyone is allowed to pay it. Used both by the
    server-side payout path and by the browser-payer rail, where the browser
    cannot run LNURL itself (CORS) — the server only resolves an instruction
    here, it never touches the money.

    Returns the BOLT11 string; raises on any resolution problem.
    """
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

    # The receiver's server chose this invoice; verify it asks for exactly
    # what we offered before handing it to the payer's wallet (LUD-06) —
    # an inflated invoice would be paid as-is otherwise.
    invoice_msat = bolt11_amount_msat(invoice_pr)
    if invoice_msat != amount_msat:
        raise Exception(
            f"LNURL callback returned an invoice for {invoice_msat} msat "
            f"instead of the requested {amount_msat} msat"
        )

    return invoice_pr


def send_payment_via_lnurl(ln_address: str, amount_sats: int, wallet_config: dict, comment: str = "") -> Dict[str, Any]:
    """
    Send payment to Lightning address via LNURL-pay protocol.

    Args:
        ln_address: Lightning address (user@domain.com)
        amount_sats: Amount in satoshis
        wallet_config: Decrypted wallet config of the advertiser (payer)
        comment: Optional payment comment

    Returns:
        Payment result dict with 'success', 'invoice', 'payment_hash'. On
        failure it also carries 'stage': 'lnurl' when the receiver's address
        could not produce an invoice, 'pay' when the payer's wallet refused —
        the caller needs that to tell the viewer whose side is at fault — plus
        'rejected' when the payer's wallet answered and said no.
    """
    stage = 'lnurl'
    try:
        invoice_pr = resolve_lnurl_invoice(ln_address, amount_sats, comment)

        # Step 3: Pay invoice using advertiser's wallet
        stage = 'pay'
        wallet_client = create_wallet_client(wallet_config)
        payment_result = wallet_client.pay_invoice(invoice_pr)

        logger.info(f"LNURL payment sent: {amount_sats} sats to {ln_address}")

        return {
            'success': True,
            'invoice': invoice_pr,
            'payment_hash': payment_result.get('payment_hash', ''),
        }

    except Exception as e:
        logger.error(f"LNURL payment failed at stage '{stage}': {e}")
        return {
            'success': False,
            'stage': stage,
            'rejected': isinstance(e, WalletRejectedError),
            'error': str(e)
        }
