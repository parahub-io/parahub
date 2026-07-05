"""Recurring-support API — subscribe to a profile, renew, cancel, inspect status.

Non-custodial: the client sends the Lightning payment directly to the recipient's
wallet, then reports the completed cycle here. The backend only keeps the
relationship + cycle ledger and gates restricted content on a live subscription.
"""
import logging
from typing import Optional

from django.utils import timezone
from ninja import Router
from ninja.errors import HttpError
from pydantic import BaseModel

from parahub.auth import ProfileAuth, OptionalProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from identity.models import Profile
from finance.models import Subscription
from finance import services as sub_services

logger = logging.getLogger(__name__)

subscriptions_router = Router()

MIN_AMOUNT_SATS = 1


# --- Schemas ---

class SubscribeRequest(BaseModel):
    recipient_id: str
    amount_sats: int
    ln_payment_hash: str = ''


class SubscriptionOut(BaseModel):
    id: str
    object_type: str = 'subscription'
    subscriber_id: str
    recipient_id: str
    recipient_local_name: str = ''
    recipient_display_name: Optional[str] = None
    recipient_avatar: Optional[str] = None
    amount_sats: int
    status: str
    is_live: bool
    started_at: str
    expires_at: str
    last_paid_at: Optional[str] = None
    cancelled_at: Optional[str] = None


class SubscriptionStatusOut(BaseModel):
    recipient_id: str
    subscriber_count: int
    is_subscriber: bool = False
    subscription: Optional[SubscriptionOut] = None


# --- Helpers ---

def _serialize(sub: Subscription) -> dict:
    r = sub.recipient
    return {
        'id': sub.id,
        'subscriber_id': sub.subscriber_id,
        'recipient_id': sub.recipient_id,
        'recipient_local_name': r.local_name if r else '',
        'recipient_display_name': (r.display_name or None) if r else None,
        'recipient_avatar': (r.avatar.url if (r and r.avatar) else None),
        'amount_sats': sub.amount_sats,
        'status': sub.status,
        'is_live': sub.is_live,
        'started_at': sub.started_at.isoformat() if sub.started_at else '',
        'expires_at': sub.expires_at.isoformat() if sub.expires_at else '',
        'last_paid_at': sub.last_paid_at.isoformat() if sub.last_paid_at else None,
        'cancelled_at': sub.cancelled_at.isoformat() if sub.cancelled_at else None,
    }


# --- Endpoints ---

@subscriptions_router.post("/", auth=ProfileAuth(), response={200: SubscriptionOut, 400: dict})
@ratelimit(group='subs:subscribe', key=user_or_ip, rate='30/m', method='POST')
def subscribe_or_renew(request, data: SubscribeRequest):
    """Start a recurring support to a profile, or renew an existing one.

    The client has already paid this cycle to the recipient's wallet; we record it
    and push the access window forward by one cycle. Same endpoint serves the first
    subscribe and every monthly renewal."""
    subscriber: Profile = request.auth

    if data.amount_sats < MIN_AMOUNT_SATS:
        raise HttpError(400, "Amount must be positive")

    recipient = Profile.objects.filter(id=data.recipient_id).select_related('account').first()
    if not recipient:
        raise HttpError(404, "Recipient not found")
    if recipient.id == subscriber.id:
        raise HttpError(400, "Cannot subscribe to yourself")
    if not (recipient.spark_address or recipient.ln_address):
        raise HttpError(400, "Recipient cannot receive payments yet")

    sub, is_new = sub_services.start_or_renew(
        subscriber, recipient, data.amount_sats, ln_payment_hash=data.ln_payment_hash,
    )

    if is_new and recipient.account_id:
        try:
            from notifications.services import notify_new_subscriber
            notify_new_subscriber(recipient.account, subscriber)
        except Exception:
            logger.exception("notify_new_subscriber failed")

    return _serialize(sub)


@subscriptions_router.post("/{subscription_id}/cancel/", auth=ProfileAuth(), response={200: SubscriptionOut, 403: dict, 404: dict})
@ratelimit(group='subs:cancel', key=user_or_ip, rate='30/m', method='POST')
def cancel_subscription(request, subscription_id: str):
    """Stop renewals. Access stays until the paid period ends."""
    subscriber: Profile = request.auth
    sub = Subscription.objects.filter(id=subscription_id).select_related('recipient').first()
    if not sub:
        raise HttpError(404, "Subscription not found")
    if sub.subscriber_id != subscriber.id:
        raise HttpError(403, "Not your subscription")
    sub_services.cancel(sub)
    return _serialize(sub)


@subscriptions_router.get("/my/", auth=ProfileAuth())
@ratelimit(group='subs:my', key=user_or_ip, rate='60/m')
def my_subscriptions(request):
    """The caller's outbound subscriptions (who they support)."""
    subscriber: Profile = request.auth
    subs = (
        Subscription.objects
        .filter(subscriber=subscriber)
        .exclude(status=Subscription.Status.LAPSED)
        .select_related('recipient')
        .order_by('-expires_at')
    )
    return {'subscriptions': [_serialize(s) for s in subs]}


@subscriptions_router.get("/inbound/", auth=ProfileAuth())
@ratelimit(group='subs:inbound', key=user_or_ip, rate='60/m')
def inbound_subscriptions(request):
    """The caller's inbound subscriptions (who supports them) + monthly total."""
    recipient: Profile = request.auth
    subs = (
        Subscription.objects
        .filter(recipient=recipient, status=Subscription.Status.ACTIVE)
        .select_related('subscriber')
        .order_by('-expires_at')
    )
    live = [s for s in subs if s.is_live]
    monthly_total = sum(s.amount_sats for s in live)
    return {
        'subscriber_count': len(live),
        'monthly_total_sats': monthly_total,
        'subscribers': [
            {
                'subscription_id': s.id,
                'subscriber_id': s.subscriber_id,
                'subscriber_local_name': s.subscriber.local_name if s.subscriber else '',
                'subscriber_display_name': (s.subscriber.display_name or None) if s.subscriber else None,
                'subscriber_avatar': (s.subscriber.avatar.url if (s.subscriber and s.subscriber.avatar) else None),
                'amount_sats': s.amount_sats,
                'since': s.started_at.isoformat() if s.started_at else '',
            }
            for s in live
        ],
    }


@subscriptions_router.get("/status/{recipient_id}/", auth=OptionalProfileAuth())
@ratelimit(group='subs:status', key=user_or_ip, rate='120/m')
def subscription_status(request, recipient_id: str):
    """Public subscriber count for a profile + (if authed) the caller's own status.

    Drives the subscribe button state, the "you support X" line, and content
    locks on the frontend."""
    recipient = Profile.objects.filter(id=recipient_id).first()
    if not recipient:
        raise HttpError(404, "Profile not found")

    subscriber_count = Subscription.objects.filter(
        recipient=recipient,
        status=Subscription.Status.ACTIVE,
        expires_at__gt=timezone.now(),
    ).count()

    out = {
        'recipient_id': recipient.id,
        'subscriber_count': subscriber_count,
        'is_subscriber': False,
        'subscription': None,
    }

    viewer = getattr(request, 'auth_profile', None)
    if viewer and viewer.id != recipient.id:
        sub = Subscription.objects.filter(
            subscriber=viewer, recipient=recipient,
        ).select_related('recipient').first()
        if sub:
            out['subscription'] = _serialize(sub)
            out['is_subscriber'] = sub.is_live

    return out
