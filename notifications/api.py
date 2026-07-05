"""
Push Notifications API Endpoints
Django Ninja REST API for Web Push notifications management
"""

from ninja import Router, Schema
from ninja.errors import HttpError
from typing import List, Optional
from datetime import datetime
from django.utils import timezone
from parahub.auth import ProfileAuth
from notifications.models import PushSubscription, FCMDevice, Notification, Activity
from notifications.services import _serialize, _serialize_activity
from parahub.ratelimit import ratelimit, user_or_ip
import logging

logger = logging.getLogger(__name__)

router = Router(tags=["Push Notifications"])


# Schemas
class PushSubscriptionRequest(Schema):
    """Browser push subscription data from PushManager API"""
    endpoint: str
    keys: dict  # Contains p256dh and auth keys


class PushSubscriptionResponse(Schema):
    id: str
    object_type: str = 'push_subscription'
    endpoint: str
    is_active: bool
    created_at: datetime


class VapidPublicKeyResponse(Schema):
    """VAPID public key for client-side subscription"""
    public_key: str


@router.get('/vapid-public-key/', response=VapidPublicKeyResponse)
@ratelimit(group='notifications:vapid_key', key='ip', rate='30/m')
def get_vapid_public_key(request):
    """
    Get VAPID public key for client-side push subscription.
    This endpoint is public (no auth required) as the key is needed before user subscribes.
    """
    import os
    public_key = os.getenv('VAPID_PUBLIC_KEY', '')

    if not public_key:
        raise HttpError(500, "VAPID public key not configured")

    return {'public_key': public_key}


@router.post('/subscribe/', response=PushSubscriptionResponse, auth=ProfileAuth())
@ratelimit(group='notifications:subscribe', key=user_or_ip, rate='10/m', method='POST')
def subscribe_push(request, data: PushSubscriptionRequest):
    """
    Subscribe to push notifications.
    Creates or updates push subscription for the authenticated user.
    """
    profile = request.auth_profile
    user = profile.account

    # Extract keys from subscription data
    p256dh = data.keys.get('p256dh', '')
    auth = data.keys.get('auth', '')

    if not p256dh or not auth:
        raise HttpError(400, "Missing required keys: p256dh and auth")

    # Get user agent from request
    user_agent = request.META.get('HTTP_USER_AGENT', '')

    # Check if subscription already exists
    subscription, created = PushSubscription.objects.update_or_create(
        endpoint=data.endpoint,
        defaults={
            'user': user,
            'p256dh': p256dh,
            'auth': auth,
            'user_agent': user_agent,
            'is_active': True,
            'failed_count': 0,
        }
    )

    logger.info(f"Push subscription {'created' if created else 'updated'} for user {user.email}")

    return {
        'id': subscription.id,
        'endpoint': subscription.endpoint,
        'is_active': subscription.is_active,
        'created_at': subscription.created_at,
    }


@router.delete('/unsubscribe/', auth=ProfileAuth())
@ratelimit(group='notifications:unsubscribe', key=user_or_ip, rate='10/m', method='DELETE')
def unsubscribe_push(request, endpoint: str):
    """
    Unsubscribe from push notifications.
    Deletes the push subscription for the given endpoint.
    """
    profile = request.auth_profile
    user = profile.account

    try:
        subscription = PushSubscription.objects.get(
            user=user,
            endpoint=endpoint
        )
        subscription.delete()
        logger.info(f"Push subscription deleted for user {user.email}")
        return {'success': True, 'message': 'Unsubscribed successfully'}
    except PushSubscription.DoesNotExist:
        raise HttpError(404, "Subscription not found")


@router.get('/subscriptions/', response=List[PushSubscriptionResponse], auth=ProfileAuth())
@ratelimit(group='notifications:list', key=user_or_ip, rate='60/m')
def list_subscriptions(request):
    """
    List all active push subscriptions for the authenticated user.
    """
    profile = request.auth_profile
    user = profile.account

    subscriptions = PushSubscription.objects.filter(
        user=user,
        is_active=True
    )

    return [
        {
            'id': sub.id,
            'endpoint': sub.endpoint,
            'is_active': sub.is_active,
            'created_at': sub.created_at,
        }
        for sub in subscriptions
    ]


# ===== FCM (Firebase Cloud Messaging) for Capacitor native app =====

class FCMTokenRequest(Schema):
    token: str
    platform: str = 'android'  # android | ios


@router.post('/fcm/register/', response={200: dict}, auth=ProfileAuth())
@ratelimit(group='notifications:fcm_register', key=user_or_ip, rate='10/m', method='POST')
def register_fcm_token(request, data: FCMTokenRequest):
    """
    Register FCM device token from Capacitor native app.
    Called on app start and when token refreshes.
    """
    user = request.auth_profile.account

    device, created = FCMDevice.objects.update_or_create(
        token=data.token,
        defaults={
            'user': user,
            'platform': data.platform,
            'is_active': True,
            'failed_count': 0,
        },
    )

    logger.info(f"FCM token {'registered' if created else 'updated'} for {user.username} ({data.platform})")
    return {'success': True, 'device_id': device.id}


@router.post('/fcm/unregister/', response={200: dict}, auth=ProfileAuth())
@ratelimit(group='notifications:fcm_unregister', key=user_or_ip, rate='10/m', method='POST')
def unregister_fcm_token(request, data: FCMTokenRequest):
    """Unregister FCM device token (on logout or app uninstall)."""
    FCMDevice.objects.filter(token=data.token).update(is_active=False)
    return {'success': True}


# ===== In-app notification feed (persistent history + unread badge) =====

class NotificationSchema(Schema):
    id: str
    object_type: str = 'notification'
    type: str
    category: str = ''
    title: str
    body: str = ''
    url: str = ''
    data: dict = {}
    read: bool = False
    created_at: Optional[str] = None


class UnreadCountResponse(Schema):
    count: int


class MarkReadRequest(Schema):
    ids: List[str]


@router.get('/feed', response=List[NotificationSchema], auth=ProfileAuth())
@ratelimit(group='notifications:feed', key=user_or_ip, rate='120/m')
def notification_feed(
    request,
    limit: int = 30,
    before: Optional[str] = None,
    category: Optional[str] = None,
    source: str = 'all',
    unread: bool = False,
):
    """Newest-first page of the caller's feed.

    Two orthogonal axes:
      - ``source``: ``all`` (default — incoming + your own, merged) | ``incoming``
        (things others did to you) | ``mine`` (your own first-class actions).
      - ``unread``: when true, keep only unread items. ``Activity`` (your own
        actions) is never "unread", so it drops out of any unread view —
        ``mine`` + ``unread`` is empty, and ``all`` + ``unread`` collapses to
        unread incoming.

    Cursor by ULID id (`before` = the last id of the previous page → `id__lt`).
    ULIDs are globally time-sortable, so a single `before` cursor is valid across
    both tables and `-id` ordering is chronological."""
    user = request.auth_profile.account
    limit = max(1, min(limit, 100))

    def notifications_qs():
        q = Notification.objects.filter(recipient=user)
        if unread:
            q = q.filter(read_at__isnull=True)
        if category:
            q = q.filter(category=category)
        if before:
            q = q.filter(id__lt=before)
        return q.order_by('-id')

    def activity_qs():
        q = Activity.objects.filter(actor=user)
        if category:
            q = q.filter(category=category)
        if before:
            q = q.filter(id__lt=before)
        return q.order_by('-id')

    if source == 'incoming':
        return [_serialize(n) for n in notifications_qs()[:limit]]

    if source == 'mine':
        if unread:  # your own actions are never unread
            return []
        return [_serialize_activity(a) for a in activity_qs()[:limit]]

    # all: pull up to `limit` from each stream, merge by ULID id, take the top.
    merged = [_serialize(n) for n in notifications_qs()[:limit]]
    if not unread:  # activity is never unread → omit it from the unread view
        merged += [_serialize_activity(a) for a in activity_qs()[:limit]]
    merged.sort(key=lambda x: x['id'], reverse=True)
    return merged[:limit]


@router.get('/unread-count', response=UnreadCountResponse, auth=ProfileAuth())
@ratelimit(group='notifications:unread', key=user_or_ip, rate='120/m')
def unread_count(request):
    """Count of unread notifications — drives the nav bell badge."""
    user = request.auth_profile.account
    count = Notification.objects.filter(recipient=user, read_at__isnull=True).count()
    return {'count': count}


@router.post('/mark-read', response={200: dict}, auth=ProfileAuth())
@ratelimit(group='notifications:mark_read', key=user_or_ip, rate='120/m', method='POST')
def mark_read(request, data: MarkReadRequest):
    """Mark the given notifications read (recipient-scoped)."""
    user = request.auth_profile.account
    if not data.ids:
        return {'updated': 0}
    updated = Notification.objects.filter(
        recipient=user, id__in=data.ids, read_at__isnull=True,
    ).update(read_at=timezone.now())
    return {'updated': updated}


@router.post('/mark-all-read', response={200: dict}, auth=ProfileAuth())
@ratelimit(group='notifications:mark_all_read', key=user_or_ip, rate='30/m', method='POST')
def mark_all_read(request):
    """Mark every unread notification read for the caller."""
    user = request.auth_profile.account
    updated = Notification.objects.filter(
        recipient=user, read_at__isnull=True,
    ).update(read_at=timezone.now())
    return {'updated': updated}
