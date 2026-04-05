"""
LNURL-pay endpoints for Lightning Network payments
Provides user@parahub.io addresses without custodial wallet
"""

from ninja import Router
from django.shortcuts import get_object_or_404
from django.http import JsonResponse, Http404
from django.conf import settings
from typing import Optional
import logging
import hashlib
import hmac

from identity.models import Profile
from ads.models import AdsProfile
from ads.crypto_utils import decrypt_wallet_config
from ads.ln_wallet_service import create_wallet_client
from parahub.ratelimit import ratelimit

logger = logging.getLogger(__name__)

# Create LNURL router (no auth - public endpoint)
lnurl_router = Router()


@lnurl_router.get("/.well-known/lnurlp/{username}")
@ratelimit(group='lnurl:metadata', key='ip', rate='30/m')
def lnurl_pay_metadata(request, username: str):
    """
    LNURL-pay metadata endpoint.
    Returns information about the Lightning address.

    Spec: https://github.com/lnurl/luds/blob/luds/06.md
    """
    try:
        # Find profile by HNA (Human-Navigable Alias)
        profile = Profile.objects.get(hna=username)

        # Check if user has ads profile with Lightning address configured
        if not profile.ln_address:
            raise Http404("User has no Lightning wallet configured")

        try:
            ads_profile = AdsProfile.objects.get(profile=profile)
        except AdsProfile.DoesNotExist:
            raise Http404("User has no advertising profile")

        # Build callback URL for actual payment
        callback_url = f"{settings.SITE_URL}/api/v1/lnurl/pay/{username}/callback"

        # LNURL-pay metadata response
        return {
            "tag": "payRequest",
            "callback": callback_url,
            "minSendable": 1000,  # 1 satoshi minimum (in millisatoshis)
            "maxSendable": 100000000,  # 100k sats max (in millisatoshis)
            "metadata": f'[["text/plain", "Payment to {username}@parahub.io"]]',
            "commentAllowed": 255,
        }

    except Profile.DoesNotExist:
        raise Http404(f"User @{username} not found")


@lnurl_router.get("/pay/{username}/callback")
@ratelimit(group='lnurl:callback', key='ip', rate='20/m')
def lnurl_pay_callback(request, username: str):
    """
    LNURL-pay callback endpoint.
    Generates Lightning invoice for payment.

    Query params:
    - amount: millisatoshis to pay
    - comment: optional payment comment

    Phase 3 Implementation:
    1. Get user's ln_wallet_config (LNbits API key, Alby token, LND macaroon)
    2. Connect to user's actual wallet
    3. Request invoice from user's wallet
    4. Return invoice to payer

    Current: Returns placeholder response for testing
    """
    amount_msat = request.GET.get('amount')
    comment = request.GET.get('comment', '')

    if not amount_msat:
        return JsonResponse({
            "status": "ERROR",
            "reason": "Missing required parameter: amount"
        }, status=400)

    try:
        amount_sats = int(amount_msat) // 1000

        # Find user
        profile = Profile.objects.get(hna=username)
        ads_profile = AdsProfile.objects.get(profile=profile)

        if not profile.ln_address and not ads_profile.ln_wallet_config:
            return JsonResponse({
                "status": "ERROR",
                "reason": "User has no Lightning wallet configured"
            }, status=400)

        # Create invoice via user's wallet provider
        if ads_profile.ln_wallet_config:
            try:
                wallet_config = decrypt_wallet_config(ads_profile.ln_wallet_config)
                wallet_client = create_wallet_client(wallet_config)
                invoice = wallet_client.create_invoice(
                    amount_sats=amount_sats,
                    memo=f"Parahub payment to {username}: {comment}" if comment else f"Payment to {username}@parahub.io"
                )

                return JsonResponse({
                    "pr": invoice.payment_request,
                    "successAction": {
                        "tag": "message",
                        "message": f"Payment of {amount_sats} sats sent to {username}!"
                    },
                    "routes": []
                })
            except Exception as e:
                logger.error(f"LNURL callback invoice creation failed for {username}: {e}")
                return JsonResponse({
                    "status": "ERROR",
                    "reason": "Failed to create invoice from wallet"
                }, status=500)
        else:
            # User has ln_address but no wallet_config — can't create invoice on their behalf
            return JsonResponse({
                "status": "ERROR",
                "reason": "User wallet does not support direct invoice creation"
            }, status=400)

    except Profile.DoesNotExist:
        return JsonResponse({
            "status": "ERROR",
            "reason": f"User @{username} not found"
        }, status=404)
    except AdsProfile.DoesNotExist:
        return JsonResponse({
            "status": "ERROR",
            "reason": "User has no advertising profile"
        }, status=404)
    except ValueError as e:
        return JsonResponse({
            "status": "ERROR",
            "reason": str(e)
        }, status=400)
