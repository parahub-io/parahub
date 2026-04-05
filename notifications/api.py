"""
Push Notifications API Endpoints
Django Ninja REST API for Web Push notifications management
"""

from ninja import Router, Schema
from ninja.errors import HttpError
from typing import List, Optional
from datetime import datetime
from parahub.auth import ProfileAuth
from notifications.models import PushSubscription, FCMDevice
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
