"""
Push Notification Service
Handles sending Web Push (VAPID) and FCM (Firebase) notifications.
"""

import os
import logging
import json
from pywebpush import webpush, WebPushException
from notifications.models import PushSubscription, FCMDevice
from django.contrib.auth import get_user_model

User = get_user_model()
logger = logging.getLogger(__name__)

# ===== Firebase Admin SDK (lazy init) =====
_firebase_app = None


def _get_firebase_app():
    """Lazy-init Firebase Admin SDK. Returns app or None if not configured."""
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app

    try:
        import firebase_admin
        from firebase_admin import credentials

        cred_path = os.getenv(
            'FIREBASE_SERVICE_ACCOUNT',
            '/opt/parahub/.secrets/firebase-service-account.json',
        )
        if not os.path.exists(cred_path):
            logger.warning(f"Firebase service account not found at {cred_path}")
            return None

        cred = credentials.Certificate(cred_path)
        _firebase_app = firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK initialized")
        return _firebase_app
    except Exception as e:
        logger.error(f"Failed to initialize Firebase Admin SDK: {e}")
        return None


def send_fcm_notification(user, title: str, body: str, data: dict = None, url: str = None):
    """
    Send FCM push notification to all active FCM devices for a user.
    Uses DATA messages (not notification messages) so Capacitor can handle them
    programmatically — play siren, vibrate, show full-screen intent.
    """
    app = _get_firebase_app()
    if not app:
        return 0, 0

    devices = FCMDevice.objects.filter(user=user, is_active=True)
    if not devices.exists():
        return 0, 0

    from firebase_admin import messaging

    # FCM data message — all values must be strings
    fcm_data = {
        'title': title,
        'body': body,
        'url': url or '/',
    }
    if data:
        for k, v in data.items():
            fcm_data[k] = str(v) if not isinstance(v, str) else v

    success_count = 0
    failure_count = 0

    for device in devices:
        try:
            message = messaging.Message(
                data=fcm_data,
                token=device.token,
                android=messaging.AndroidConfig(
                    priority='high',  # Wake device from Doze
                ),
            )
            messaging.send(message)
            device.mark_success()
            success_count += 1
        except messaging.UnregisteredError:
            logger.info(f"FCM token expired for {user.username}, deactivating")
            device.is_active = False
            device.save(update_fields=['is_active'])
            failure_count += 1
        except Exception as e:
            logger.warning(f"FCM send failed for {user.username}: {e}")
            device.mark_failed()
            failure_count += 1

    return success_count, failure_count


def send_push_notification(user, title: str, body: str, data: dict = None, url: str = None):
    """
    Send push notification to all active subscriptions for a user.

    Args:
        user: Django User object
        title: Notification title
        body: Notification body text
        data: Optional dict of custom data
        url: Optional URL to open when notification is clicked

    Returns:
        tuple: (success_count, failure_count)
    """
    # Get VAPID credentials from environment
    vapid_private_key_pem = os.getenv('VAPID_PRIVATE_KEY_PEM', '')

    # Remove surrounding quotes if present (from .env file)
    if vapid_private_key_pem.startswith('"') and vapid_private_key_pem.endswith('"'):
        vapid_private_key_pem = vapid_private_key_pem[1:-1]

    # Replace literal \n with actual newlines
    vapid_private_key_pem = vapid_private_key_pem.replace('\\n', '\n')

    vapid_email = os.getenv('VAPID_ADMIN_EMAIL', 'admin@parahub.io')

    if not vapid_private_key_pem:
        logger.error("VAPID private key not configured in .env")
        return 0, 0

    # Load VAPID key using from_pem (correct method for PEM format)
    from py_vapid import Vapid
    try:
        vapid_instance = Vapid.from_pem(vapid_private_key_pem.encode())
    except Exception as e:
        logger.error(f"Failed to load VAPID key: {e}")
        return 0, 0

    # Get all active subscriptions for user
    subscriptions = PushSubscription.objects.filter(
        user=user,
        is_active=True
    )

    if not subscriptions.exists():
        logger.debug(f"No active subscriptions for user {user.email}")
        return 0, 0

    # Prepare notification payload
    payload = {
        'title': title,
        'body': body,
        'icon': '/logo.svg',
        'badge': '/logo.svg',
    }

    if url:
        payload['url'] = url

    if data:
        payload['data'] = data

    payload_json = json.dumps(payload)

    success_count = 0
    failure_count = 0

    # Send to all subscriptions
    for subscription in subscriptions:
        try:
            subscription_info = {
                'endpoint': subscription.endpoint,
                'keys': {
                    'p256dh': subscription.p256dh,
                    'auth': subscription.auth,
                }
            }

            # Send push notification using pre-loaded VAPID instance
            webpush(
                subscription_info=subscription_info,
                data=payload_json,
                vapid_private_key=vapid_instance,
                vapid_claims={
                    'sub': f'mailto:{vapid_email}',
                }
            )

            # Mark successful delivery
            subscription.mark_success()
            success_count += 1
            logger.info(f"Push sent successfully to {user.email} (subscription {subscription.id})")

        except WebPushException as e:
            logger.warning(f"Push failed for {user.email} (subscription {subscription.id}): {e}")

            # Handle specific error cases
            if e.response and e.response.status_code in [404, 410]:
                # Subscription no longer valid (expired or unsubscribed)
                logger.info(f"Subscription {subscription.id} is no longer valid, marking inactive")
                subscription.is_active = False
                subscription.save(update_fields=['is_active'])
            else:
                # Other errors - increment failure count
                subscription.mark_failed()

            failure_count += 1

        except Exception as e:
            logger.error(f"Unexpected error sending push to {user.email}: {e}", exc_info=True)
            subscription.mark_failed()
            failure_count += 1

    # Also send via FCM (Capacitor native app)
    fcm_success, fcm_failure = send_fcm_notification(user, title, body, data, url)
    success_count += fcm_success
    failure_count += fcm_failure

    logger.info(f"Push notification sent to {user.email}: {success_count} success, {failure_count} failures")
    return success_count, failure_count


def send_push_to_multiple_users(user_ids: list, title: str, body: str, data: dict = None, url: str = None):
    """
    Send push notification to multiple users.

    Args:
        user_ids: List of user IDs (or Profile IDs)
        title: Notification title
        body: Notification body text
        data: Optional dict of custom data
        url: Optional URL to open when notification is clicked

    Returns:
        dict: Statistics about sent notifications
    """
    total_success = 0
    total_failure = 0
    users_notified = 0

    users = User.objects.filter(id__in=user_ids)

    for user in users:
        success, failure = send_push_notification(user, title, body, data, url)
        if success > 0:
            users_notified += 1
        total_success += success
        total_failure += failure

    return {
        'users_notified': users_notified,
        'total_users': users.count(),
        'success_count': total_success,
        'failure_count': total_failure,
    }


# ===== Notification dispatch =====

# Maps a notification type → the preference category that gates it.
TYPE_TO_CATEGORY = {
    'partner_added': 'social',
    'verification_received': 'social',
    'new_contract': 'contracts',
    'contract_signed': 'contracts',
    'new_debt': 'contracts',
    'new_poll': 'governance',
    'delegation_received': 'governance',
    'poll_closing_soon': 'governance',
    'incoming_call': 'calls',
    'new_booking': 'rental',
    'booking_confirmed': 'rental',
    'booking_cancelled': 'rental',
    'new_subscriber': 'subscriptions',
    'subscription_expiring': 'subscriptions',
}


def _should_notify(user, notification_type: str) -> bool:
    """Check if user has enabled this notification category."""
    from identity.models import Profile

    category = TYPE_TO_CATEGORY.get(notification_type)
    if not category:
        return True  # Unknown type = always send

    profile = Profile.objects.filter(account=user, is_primary=True).first()
    if not profile:
        return True

    prefs = profile.notification_prefs or {}
    return prefs.get(category, True)  # Default = enabled


def _serialize(notif) -> dict:
    """Shape a Notification for the WS payload and the feed API."""
    return {
        'id': notif.id,
        'object_type': 'notification',
        'type': notif.type,
        'category': notif.category,
        'title': notif.title,
        'body': notif.body,
        'url': notif.url,
        'data': notif.data,
        'read': notif.read_at is not None,
        'created_at': notif.created_at.isoformat() if notif.created_at else None,
    }


def emit_notification(user, *, type, title, body, url='', category=None, data=None):
    """Single dispatch point for a user-facing notification.

    Persists an in-app Notification (the feed + unread-badge source of truth),
    pushes it live over the recipient's ``user:{id}`` WS channel (instant toast +
    badge bump for open clients), then fans out to Web Push + FCM.

    Returns the (success, failure) push counts so the legacy ``notify_*`` callers
    keep their return contract; returns (0, 0) when the recipient muted the
    category."""
    if not _should_notify(user, type):
        return 0, 0

    from notifications.models import Notification

    data = data or {}
    notif = Notification.objects.create(
        recipient=user,
        type=type,
        category=category or TYPE_TO_CATEGORY.get(type, ''),
        title=title,
        body=body,
        url=url or '',
        data=data,
    )

    # Live in-app: instant toast + badge bump for any client that's open.
    try:
        from parahub.services.ws_publish import ws_publish
        ws_publish(f'user:{user.id}', {
            'type': 'notification.new',
            'notification': _serialize(notif),
        })
    except Exception:
        logger.exception('emit_notification: ws_publish failed')

    # Off-device alert.
    return send_push_notification(
        user, title, body,
        data={**data, 'type': type, 'notification_id': notif.id},
        url=url,
    )


# ===== Activity log (the actor's OWN first-class actions) =====
#
# Separate stream from Notification: outgoing (you did it), immutable, never
# unread, never pushed off-device. Written from notifications.signals (post_save
# on the source models) and merged into the /feed by the API. See the Activity
# model docstring for the design rationale.

def _pick_lang(profile) -> str:
    """Actor's preferred language for rendering the log line; defaults to 'en'."""
    return getattr(profile, 'preferred_language', None) or 'en'


def _serialize_activity(act) -> dict:
    """Shape an Activity for the WS payload and the feed API.

    Same shape as ``_serialize`` (so the frontend renders one list), but
    ``object_type='activity'`` and ``read`` is always True — own actions are
    never unread and never bump the bell badge."""
    return {
        'id': act.id,
        'object_type': 'activity',
        'type': act.verb,
        'category': act.category,
        'title': act.title,
        'body': act.body,
        'url': act.url,
        'data': act.data,
        'read': True,
        'created_at': act.created_at.isoformat() if act.created_at else None,
    }


def record_activity(actor, *, verb, obj, title, body, url='', category='', data=None,
                     publish=True, created_ts=None):
    """Append one row to the actor's activity log + (optionally) push it live.

    ``actor`` is the Account (User); ``obj`` is the canonical object created by the
    action (PollVote / Verification / Item / Contract) — stored as a GenericFK
    pointer, not a copy. The WS push fires on transaction commit so the row is
    durable before any client reacts (and so it works whether or not the caller is
    inside a transaction). Never raises into the caller's signal — failures are
    logged and swallowed.

    ``publish=False`` skips the WS push — used by the backfill command so a
    one-time historical import doesn't fan out thousands of live events.

    ``created_ts`` (a datetime) backdates the row to the original action time: the
    ULID id is minted from it (so feed ordering is chronological) and ``created_at``
    is overridden past ``auto_now_add`` (so "when" is accurate). Live callers leave
    it None — the row is born now, which is correct."""
    from notifications.models import Activity
    from django.contrib.contenttypes.models import ContentType
    from django.db import transaction

    data = data or {}
    ct = ContentType.objects.get_for_model(obj) if obj is not None else None

    create_kwargs = dict(
        actor=actor,
        verb=verb,
        category=category,
        content_type=ct,
        object_id=(getattr(obj, 'id', '') or ''),
        title=title,
        body=body,
        url=url or '',
        data=data,
    )
    if created_ts is not None:
        from ulid import ULID
        create_kwargs['id'] = str(ULID.from_datetime(created_ts))

    act = Activity.objects.create(**create_kwargs)

    if created_ts is not None:
        # auto_now_add stamps created_at = now on insert regardless of input;
        # override it post-insert so the historical timestamp sticks.
        Activity.objects.filter(pk=act.id).update(created_at=created_ts)
        act.created_at = created_ts

    if not publish:
        return act

    def _publish():
        try:
            from parahub.services.ws_publish import ws_publish
            ws_publish(f'user:{actor.id}', {
                'type': 'activity.new',
                'activity': _serialize_activity(act),
            })
        except Exception:
            logger.exception('record_activity: ws_publish failed')

    transaction.on_commit(_publish)
    return act


# Predefined notification types for common events

def notify_new_contract(user, contract):
    """Send notification for new contract"""
    if not _should_notify(user, 'new_contract'):
        return 0, 0
    from identity.models import Profile

    # Get profile for display name
    profile = Profile.objects.filter(account=user).first()
    if not profile:
        return 0, 0

    # Get language preference
    lang = profile.preferred_language if profile else 'en'

    # Determine if user is buyer or seller
    is_buyer = contract.buyer_id == profile.id

    # Get display name from related Profile objects
    if is_buyer:
        other_party = contract.seller.display_name or contract.seller.local_name or f"User {contract.seller_id[:8]}"
    else:
        other_party = contract.buyer.display_name or contract.buyer.local_name or f"User {contract.buyer_id[:8]}"

    # Localized messages
    titles = {
        'en': "New Contract",
        'ru': "Новый контракт",
        'pt': "Novo Contrato",
        'es': "Nuevo Contrato",
        'fr': "Nouveau Contrat",
        'de': "Neuer Vertrag"
    }

    bodies = {
        'en': f"You have a new contract with {other_party}",
        'ru': f"У вас новый контракт с {other_party}",
        'pt': f"Você tem um novo contrato com {other_party}",
        'es': f"Tienes un nuevo contrato con {other_party}",
        'fr': f"Vous avez un nouveau contrat avec {other_party}",
        'de': f"Sie haben einen neuen Vertrag mit {other_party}"
    }

    title = titles.get(lang, titles['en'])
    body = bodies.get(lang, bodies['en'])
    url = f"/contracts/{contract.id}"

    return emit_notification(
        user,
        type='new_contract',
        title=title,
        body=body,
        data={'contract_id': contract.id},
        url=url
    )


def notify_new_debt(user, debt):
    """Send notification for new debt"""
    if not _should_notify(user, 'new_debt'):
        return 0, 0
    from identity.models import Profile

    profile = Profile.objects.filter(account=user).first()
    if not profile:
        return 0, 0

    # Get language preference
    lang = profile.preferred_language if profile else 'en'

    # Determine if user is creditor or debtor
    is_creditor = debt.creditor_id == profile.id

    # Get display name from related Profile objects
    if is_creditor:
        other_party = debt.debtor.display_name or debt.debtor.local_name or f"User {debt.debtor_id[:8]}"
    else:
        other_party = debt.creditor.display_name or debt.creditor.local_name or f"User {debt.creditor_id[:8]}"

    # Localized messages
    if is_creditor:
        titles = {
            'en': "New Debt Recorded",
            'ru': "Новый долг записан",
            'pt': "Nova Dívida Registrada",
            'es': "Nueva Deuda Registrada",
            'fr': "Nouvelle Dette Enregistrée",
            'de': "Neue Schuld erfasst"
        }
        bodies = {
            'en': f"{other_party} owes you {debt.amount} {debt.currency}",
            'ru': f"{other_party} должен вам {debt.amount} {debt.currency}",
            'pt': f"{other_party} deve a você {debt.amount} {debt.currency}",
            'es': f"{other_party} te debe {debt.amount} {debt.currency}",
            'fr': f"{other_party} vous doit {debt.amount} {debt.currency}",
            'de': f"{other_party} schuldet Ihnen {debt.amount} {debt.currency}"
        }
    else:
        titles = {
            'en': "New Debt",
            'ru': "Новый долг",
            'pt': "Nova Dívida",
            'es': "Nueva Deuda",
            'fr': "Nouvelle Dette",
            'de': "Neue Schuld"
        }
        bodies = {
            'en': f"You owe {other_party} {debt.amount} {debt.currency}",
            'ru': f"Вы должны {other_party} {debt.amount} {debt.currency}",
            'pt': f"Você deve a {other_party} {debt.amount} {debt.currency}",
            'es': f"Debes a {other_party} {debt.amount} {debt.currency}",
            'fr': f"Vous devez à {other_party} {debt.amount} {debt.currency}",
            'de': f"Sie schulden {other_party} {debt.amount} {debt.currency}"
        }

    title = titles.get(lang, titles['en'])
    body = bodies.get(lang, bodies['en'])
    url = f"/debts"

    return emit_notification(
        user,
        type='new_debt',
        title=title,
        body=body,
        data={'debt_id': debt.id},
        url=url
    )


def notify_contract_signed(user, contract):
    """Send notification when contract is signed"""
    if not _should_notify(user, 'contract_signed'):
        return 0, 0
    from identity.models import Profile

    # Get recipient's profile for language preference
    recipient_profile = Profile.objects.filter(account=user).first()
    lang = recipient_profile.preferred_language if recipient_profile else 'en'

    # Localized messages
    titles = {
        'en': "Contract Signed",
        'ru': "Контракт подписан",
        'pt': "Contrato Assinado",
        'es': "Contrato Firmado",
        'fr': "Contrat Signé",
        'de': "Vertrag unterschrieben"
    }

    bodies = {
        'en': "Contract has been signed by all parties",
        'ru': "Контракт подписан всеми сторонами",
        'pt': "O contrato foi assinado por todas as partes",
        'es': "El contrato ha sido firmado por todas las partes",
        'fr': "Le contrat a été signé par toutes les parties",
        'de': "Der Vertrag wurde von allen Parteien unterzeichnet"
    }

    title = titles.get(lang, titles['en'])
    body = bodies.get(lang, bodies['en'])
    url = f"/contracts/{contract.id}"

    return emit_notification(
        user,
        type='contract_signed',
        title=title,
        body=body,
        data={'contract_id': contract.id},
        url=url
    )


def notify_partner_added(user, partner_profile):
    """Send notification when someone adds you as partner"""
    if not _should_notify(user, 'partner_added'):
        return 0, 0
    from identity.models import Profile

    # Get recipient's profile for language preference
    recipient_profile = Profile.objects.filter(account=user).first()
    lang = recipient_profile.preferred_language if recipient_profile else 'en'

    # Get display name of partner who added you
    display_name = partner_profile.display_name or partner_profile.local_name or partner_profile.hna

    # Localized messages
    titles = {
        'en': "New Partner",
        'ru': "Новый партнёр",
        'pt': "Novo Parceiro",
        'es': "Nuevo Socio",
        'fr': "Nouveau Partenaire",
        'de': "Neuer Partner"
    }

    bodies = {
        'en': f"{display_name} added you to their partners",
        'ru': f"{display_name} добавил вас в партнёры",
        'pt': f"{display_name} adicionou você aos parceiros",
        'es': f"{display_name} te agregó a sus socios",
        'fr': f"{display_name} vous a ajouté à ses partenaires",
        'de': f"{display_name} hat Sie zu seinen Partnern hinzugefügt"
    }

    title = titles.get(lang, titles['en'])
    body = bodies.get(lang, bodies['en'])
    url = f"/u/{partner_profile.id}"

    return emit_notification(
        user,
        type='partner_added',
        title=title,
        body=body,
        data={'partner_id': partner_profile.id},
        url=url
    )


def notify_verification_received(user, verifier_profile):
    """Send notification when someone verifies you"""
    if not _should_notify(user, 'verification_received'):
        return 0, 0
    from identity.models import Profile

    # Get recipient's profile for language preference
    recipient_profile = Profile.objects.filter(account=user).first()
    lang = recipient_profile.preferred_language if recipient_profile else 'en'

    # Get display name of verifier
    display_name = verifier_profile.display_name or verifier_profile.local_name or verifier_profile.hna

    # Localized messages
    titles = {
        'en': "New Verification",
        'ru': "Новая верификация",
        'pt': "Nova Verificação",
        'es': "Nueva Verificación",
        'fr': "Nouvelle Vérification",
        'de': "Neue Verifizierung"
    }

    bodies = {
        'en': f"{display_name} has verified you in Web of Trust",
        'ru': f"{display_name} верифицировал вас в Web of Trust",
        'pt': f"{display_name} verificou você na Web of Trust",
        'es': f"{display_name} te ha verificado en Web of Trust",
        'fr': f"{display_name} vous a vérifié dans Web of Trust",
        'de': f"{display_name} hat Sie im Web of Trust verifiziert"
    }

    title = titles.get(lang, titles['en'])
    body = bodies.get(lang, bodies['en'])
    url = f"/u/{verifier_profile.id}"

    return emit_notification(
        user,
        type='verification_received',
        title=title,
        body=body,
        data={'verifier_id': verifier_profile.id},
        url=url
    )


def notify_new_poll(user, poll, creator_profile):
    """Send notification when user is added as eligible voter in a new poll"""
    if not _should_notify(user, 'new_poll'):
        return 0, 0
    from identity.models import Profile

    # Get recipient's profile for language preference
    recipient_profile = Profile.objects.filter(account=user).first()
    lang = recipient_profile.preferred_language if recipient_profile else 'en'

    # Get display name of poll creator
    creator_name = creator_profile.display_name or creator_profile.local_name or creator_profile.hna

    # Localized messages
    titles = {
        'en': "New Poll",
        'ru': "Новое голосование",
        'pt': "Nova Votação",
        'es': "Nueva Votación",
        'fr': "Nouveau Sondage",
        'de': "Neue Abstimmung"
    }

    bodies = {
        'en': f"{creator_name} created a poll: {poll.title}",
        'ru': f"{creator_name} создал голосование: {poll.title}",
        'pt': f"{creator_name} criou uma votação: {poll.title}",
        'es': f"{creator_name} creó una votación: {poll.title}",
        'fr': f"{creator_name} a créé un sondage : {poll.title}",
        'de': f"{creator_name} hat eine Abstimmung erstellt: {poll.title}"
    }

    title = titles.get(lang, titles['en'])
    body = bodies.get(lang, bodies['en'])
    url = f"/governance/polls/{poll.id}"

    return emit_notification(
        user,
        type='new_poll',
        title=title,
        body=body,
        data={'poll_id': poll.id, 'creator_id': creator_profile.id},
        url=url
    )


def notify_delegation_received(user, poll, delegator_profile):
    """Send notification when someone delegates their vote to you"""
    if not _should_notify(user, 'delegation_received'):
        return 0, 0
    from identity.models import Profile

    recipient_profile = Profile.objects.filter(account=user).first()
    lang = recipient_profile.preferred_language if recipient_profile else 'en'

    delegator_name = delegator_profile.display_name or delegator_profile.local_name or delegator_profile.hna

    titles = {
        'en': "Vote Delegated to You",
        'ru': "Вам делегирован голос",
        'pt': "Voto Delegado a Você",
        'es': "Voto Delegado a Ti",
        'fr': "Vote Délégué à Vous",
        'de': "Stimme an Sie delegiert",
    }

    bodies = {
        'en': f"{delegator_name} delegated their vote to you in: {poll.title}",
        'ru': f"{delegator_name} делегировал вам голос в: {poll.title}",
        'pt': f"{delegator_name} delegou o voto a você em: {poll.title}",
        'es': f"{delegator_name} te delegó su voto en: {poll.title}",
        'fr': f"{delegator_name} vous a délégué son vote dans : {poll.title}",
        'de': f"{delegator_name} hat seine Stimme an Sie delegiert in: {poll.title}",
    }

    title = titles.get(lang, titles['en'])
    body = bodies.get(lang, bodies['en'])
    url = f"/governance/polls/{poll.id}"

    return emit_notification(
        user,
        type='delegation_received',
        title=title,
        body=body,
        data={'poll_id': poll.id, 'delegator_id': delegator_profile.id},
        url=url
    )


def notify_poll_closing_soon(user, poll, hours_left: int):
    """Send notification when a poll is closing soon and user hasn't voted"""
    if not _should_notify(user, 'poll_closing_soon'):
        return 0, 0
    from identity.models import Profile

    recipient_profile = Profile.objects.filter(account=user).first()
    lang = recipient_profile.preferred_language if recipient_profile else 'en'

    titles = {
        'en': "Poll Closing Soon",
        'ru': "Голосование скоро завершится",
        'pt': "Votação Encerrando em Breve",
        'es': "Votación Cerrando Pronto",
        'fr': "Sondage Bientôt Clos",
        'de': "Abstimmung endet bald",
    }

    bodies = {
        'en': f'"{poll.title}" closes in {hours_left}h — you haven\'t voted yet',
        'ru': f'«{poll.title}» завершится через {hours_left}ч — вы ещё не проголосовали',
        'pt': f'"{poll.title}" encerra em {hours_left}h — você ainda não votou',
        'es': f'"{poll.title}" cierra en {hours_left}h — aún no has votado',
        'fr': f'"{poll.title}" ferme dans {hours_left}h — vous n\'avez pas encore voté',
        'de': f'„{poll.title}“ endet in {hours_left}h — Sie haben noch nicht abgestimmt',
    }

    title = titles.get(lang, titles['en'])
    body = bodies.get(lang, bodies['en'])
    url = f"/governance/polls/{poll.id}"

    return emit_notification(
        user,
        type='poll_closing_soon',
        title=title,
        body=body,
        data={'poll_id': poll.id},
        url=url
    )


def notify_incoming_call(user, caller_profile, room_name: str):
    """
    Send notification for incoming video call.

    Uses special options:
    - requireInteraction: true (notification stays until dismissed)
    - Long vibration pattern for attention
    - tag: incoming-call (replaces previous call notifications)
    """
    if not _should_notify(user, 'incoming_call'):
        return 0, 0
    from identity.models import Profile

    # Get recipient's profile for language preference
    recipient_profile = Profile.objects.filter(account=user).first()
    lang = recipient_profile.preferred_language if recipient_profile else 'en'

    # Get display name of caller
    caller_name = caller_profile.display_name or caller_profile.local_name or caller_profile.hna

    # Localized messages
    titles = {
        'en': "Incoming Call",
        'ru': "Входящий звонок",
        'pt': "Chamada Recebida",
        'es': "Llamada Entrante",
        'fr': "Appel Entrant",
        'de': "Eingehender Anruf"
    }

    bodies = {
        'en': f"{caller_name} is calling you",
        'ru': f"{caller_name} звонит вам",
        'pt': f"{caller_name} está ligando para você",
        'es': f"{caller_name} te está llamando",
        'fr': f"{caller_name} vous appelle",
        'de': f"{caller_name} ruft Sie an"
    }

    title = titles.get(lang, titles['en'])
    body = bodies.get(lang, bodies['en'])
    url = f"/call?room={room_name}"

    return emit_notification(
        user,
        type='incoming_call',
        title=title,
        body=body,
        data={
            'caller_id': caller_profile.id,
            'caller_name': caller_name,
            'room_name': room_name,
            'requireInteraction': True,
            'vibrate': [300, 100, 300, 100, 300],  # Long pattern for calls
            'tag': 'incoming-call'
        },
        url=url
    )


# ===== Rental booking notifications =====

def _booking_period(booking) -> str:
    """Compact, locale-neutral period string in the bookable's timezone."""
    from zoneinfo import ZoneInfo
    try:
        tz = ZoneInfo(booking.bookable.timezone)
    except Exception:
        tz = ZoneInfo('UTC')
    s = booking.start.astimezone(tz)
    e = booking.end.astimezone(tz)
    if s.date() == e.date():
        return f"{s:%Y-%m-%d %H:%M}–{e:%H:%M}"
    return f"{s:%Y-%m-%d %H:%M} → {e:%Y-%m-%d %H:%M}"


def _renter_name(booking) -> str:
    r = booking.renter
    if r is None:  # walk-in / manual booking → the external client name
        return booking.external_renter_name or 'Someone'
    return r.display_name or r.local_name or getattr(r, 'hna', '') or 'Someone'


def notify_new_booking(user, booking):
    """Notify an item manager (owner/admin) that a new booking arrived.

    REQUEST-mode bookings arrive as REQUESTED (the manager must approve);
    AUTO-mode arrive as CONFIRMED (already booked) — both are worth a ping."""
    if not _should_notify(user, 'new_booking'):
        return 0, 0
    from identity.models import Profile

    recipient = Profile.objects.filter(account=user).first()
    lang = recipient.preferred_language if recipient else 'en'
    item = booking.bookable.item
    name = _renter_name(booking)
    period = _booking_period(booking)

    if booking.status == 'REQUESTED':
        titles = {
            'en': "New booking request", 'ru': "Новый запрос на бронь",
            'pt': "Novo pedido de reserva", 'es': "Nueva solicitud de reserva",
            'fr': "Nouvelle demande de réservation", 'de': "Neue Buchungsanfrage",
        }
        bodies = {
            'en': f"{name} requested “{item.title}” · {period}",
            'ru': f"{name} запросил «{item.title}» · {period}",
            'pt': f"{name} pediu “{item.title}” · {period}",
            'es': f"{name} solicitó «{item.title}» · {period}",
            'fr': f"{name} a demandé « {item.title} » · {period}",
            'de': f"{name} hat „{item.title}“ angefragt · {period}",
        }
    else:
        titles = {
            'en': "New booking", 'ru': "Новая бронь",
            'pt': "Nova reserva", 'es': "Nueva reserva",
            'fr': "Nouvelle réservation", 'de': "Neue Buchung",
        }
        bodies = {
            'en': f"{name} booked “{item.title}” · {period}",
            'ru': f"{name} забронировал «{item.title}» · {period}",
            'pt': f"{name} reservou “{item.title}” · {period}",
            'es': f"{name} reservó «{item.title}» · {period}",
            'fr': f"{name} a réservé « {item.title} » · {period}",
            'de': f"{name} hat „{item.title}“ gebucht · {period}",
        }

    title = titles.get(lang, titles['en'])
    body = bodies.get(lang, bodies['en'])
    url = f"/rental/{item.slug or item.id}"
    return emit_notification(
        user, type='new_booking', title=title, body=body,
        data={'booking_id': booking.id, 'item_id': item.id},
        url=url,
    )


def notify_booking_confirmed(user, booking):
    """Notify the renter that their REQUESTED booking was approved."""
    if not _should_notify(user, 'booking_confirmed'):
        return 0, 0
    from identity.models import Profile

    recipient = Profile.objects.filter(account=user).first()
    lang = recipient.preferred_language if recipient else 'en'
    item = booking.bookable.item
    period = _booking_period(booking)

    titles = {
        'en': "Booking confirmed", 'ru': "Бронь подтверждена",
        'pt': "Reserva confirmada", 'es': "Reserva confirmada",
        'fr': "Réservation confirmée", 'de': "Buchung bestätigt",
    }
    bodies = {
        'en': f"Your booking of “{item.title}” is confirmed · {period}",
        'ru': f"Ваша бронь «{item.title}» подтверждена · {period}",
        'pt': f"A sua reserva de “{item.title}” foi confirmada · {period}",
        'es': f"Tu reserva de «{item.title}» está confirmada · {period}",
        'fr': f"Votre réservation de « {item.title} » est confirmée · {period}",
        'de': f"Deine Buchung von „{item.title}“ ist bestätigt · {period}",
    }
    title = titles.get(lang, titles['en'])
    body = bodies.get(lang, bodies['en'])
    return emit_notification(
        user, type='booking_confirmed', title=title, body=body,
        data={'booking_id': booking.id, 'item_id': item.id},
        url="/market/my?tab=bookings",
    )


def notify_booking_cancelled(user, booking):
    """Notify the counterpart that a booking was cancelled.

    Direction is inferred from the recipient: if `user` is the renter the
    manager cancelled it; otherwise the renter cancelled and a manager is told."""
    if not _should_notify(user, 'booking_cancelled'):
        return 0, 0
    from identity.models import Profile

    recipient = Profile.objects.filter(account=user).first()
    lang = recipient.preferred_language if recipient else 'en'
    item = booking.bookable.item
    period = _booking_period(booking)
    to_renter = booking.renter.account_id == user.id
    reason = (booking.cancel_note or '').strip()

    titles = {
        'en': "Booking cancelled", 'ru': "Бронь отменена",
        'pt': "Reserva cancelada", 'es': "Reserva cancelada",
        'fr': "Réservation annulée", 'de': "Buchung storniert",
    }
    if to_renter:
        bodies = {
            'en': f"Your booking of “{item.title}” was cancelled · {period}",
            'ru': f"Ваша бронь «{item.title}» отменена · {period}",
            'pt': f"A sua reserva de “{item.title}” foi cancelada · {period}",
            'es': f"Tu reserva de «{item.title}» fue cancelada · {period}",
            'fr': f"Votre réservation de « {item.title} » a été annulée · {period}",
            'de': f"Deine Buchung von „{item.title}“ wurde storniert · {period}",
        }
    else:
        name = _renter_name(booking)
        bodies = {
            'en': f"{name} cancelled their booking of “{item.title}” · {period}",
            'ru': f"{name} отменил бронь «{item.title}» · {period}",
            'pt': f"{name} cancelou a reserva de “{item.title}” · {period}",
            'es': f"{name} canceló su reserva de «{item.title}» · {period}",
            'fr': f"{name} a annulé sa réservation de « {item.title} » · {period}",
            'de': f"{name} hat die Buchung von „{item.title}“ storniert · {period}",
        }
    title = titles.get(lang, titles['en'])
    body = bodies.get(lang, bodies['en'])
    if reason:
        body = f"{body} — {reason}"
    url = "/market/my?tab=bookings" if to_renter else f"/rental/{item.slug or item.id}"
    return emit_notification(
        user, type='booking_cancelled', title=title, body=body,
        data={'booking_id': booking.id, 'item_id': item.id},
        url=url,
    )


def notify_ad_payment_issue(user, *, campaign, amount_sats, error=None):
    """Persistent alert when an ad-view reward did NOT reach the viewer.

    The claim screen only shows an ephemeral (~1.5s) toast, so a failed or
    pending payout would otherwise vanish silently — leaving the viewer
    believing they were paid. This is a money alert, so its ``type`` is kept
    out of ``TYPE_TO_CATEGORY`` on purpose: ``_should_notify`` returns True for
    unknown types, i.e. it can never be muted by a category preference. The
    ``ads`` category is only carried for the feed icon."""
    from identity.models import Profile

    recipient = Profile.objects.filter(account=user).first()
    lang = recipient.preferred_language if recipient else 'en'
    name = campaign.name

    titles = {
        'en': "Ad reward not received",
        'ru': "Награда за рекламу не получена",
        'pt': "Recompensa de anúncio não recebida",
        'es': "Recompensa de anuncio no recibida",
        'fr': "Récompense publicitaire non reçue",
        'de': "Werbe-Belohnung nicht erhalten",
    }
    bodies = {
        'en': f"You earned {amount_sats} sats for “{name}” but the payout didn't reach your wallet. Check your Lightning address.",
        'ru': f"Вы заработали {amount_sats} сат за «{name}», но выплата не дошла до кошелька. Проверьте Lightning-адрес.",
        'pt': f"Você ganhou {amount_sats} sats por “{name}”, mas o pagamento não chegou à sua carteira. Verifique o seu endereço Lightning.",
        'es': f"Ganaste {amount_sats} sats por «{name}», pero el pago no llegó a tu billetera. Revisa tu dirección Lightning.",
        'fr': f"Vous avez gagné {amount_sats} sats pour « {name} », mais le paiement n'est pas arrivé dans votre portefeuille. Vérifiez votre adresse Lightning.",
        'de': f"Sie haben {amount_sats} Sats für „{name}“ verdient, aber die Auszahlung hat Ihre Wallet nicht erreicht. Prüfen Sie Ihre Lightning-Adresse.",
    }
    title = titles.get(lang, titles['en'])
    body = bodies.get(lang, bodies['en'])
    return emit_notification(
        user,
        type='ad_payment_issue',
        title=title,
        body=body,
        category='ads',
        data={'campaign_id': campaign.id, 'amount_sats': amount_sats, 'error': error or ''},
        url='/profile#lightning',
    )


# ===== Recurring-support (subscription) notifications =====

def notify_new_subscriber(user, subscriber_profile):
    """Tell a recipient that someone started supporting them (first cycle only)."""
    if not _should_notify(user, 'new_subscriber'):
        return 0, 0
    from identity.models import Profile

    recipient_profile = Profile.objects.filter(account=user).first()
    lang = recipient_profile.preferred_language if recipient_profile else 'en'
    name = subscriber_profile.display_name or subscriber_profile.local_name or subscriber_profile.hna

    titles = {
        'en': "New supporter",
        'ru': "Новый сторонник",
        'pt': "Novo apoiante",
        'es': "Nuevo seguidor",
        'fr': "Nouveau soutien",
        'de': "Neuer Unterstützer",
    }
    bodies = {
        'en': f"{name} is now supporting you monthly",
        'ru': f"{name} теперь поддерживает вас ежемесячно",
        'pt': f"{name} agora apoia você mensalmente",
        'es': f"{name} ahora te apoya mensualmente",
        'fr': f"{name} vous soutient désormais chaque mois",
        'de': f"{name} unterstützt Sie jetzt monatlich",
    }
    title = titles.get(lang, titles['en'])
    body = bodies.get(lang, bodies['en'])
    url = f"/u/{subscriber_profile.local_name or subscriber_profile.id}"
    return emit_notification(
        user,
        type='new_subscriber',
        title=title,
        body=body,
        data={'subscriber_id': subscriber_profile.id},
        url=url,
    )


def notify_subscription_expiring(user, subscription, days_left: int):
    """Remind a subscriber their monthly support is about to lapse — one tap renews."""
    if not _should_notify(user, 'subscription_expiring'):
        return 0, 0
    from identity.models import Profile

    subscriber_profile = Profile.objects.filter(account=user).first()
    lang = subscriber_profile.preferred_language if subscriber_profile else 'en'
    recipient = subscription.recipient
    name = recipient.display_name or recipient.local_name or recipient.hna

    titles = {
        'en': "Support expiring soon",
        'ru': "Поддержка скоро закончится",
        'pt': "Apoio a expirar em breve",
        'es': "El apoyo expira pronto",
        'fr': "Le soutien expire bientôt",
        'de': "Unterstützung läuft bald ab",
    }
    bodies = {
        'en': f"Your monthly support for {name} ends in {days_left}d — tap to renew",
        'ru': f"Ваша ежемесячная поддержка {name} закончится через {days_left}д — нажмите, чтобы продлить",
        'pt': f"O seu apoio mensal a {name} termina em {days_left}d — toque para renovar",
        'es': f"Tu apoyo mensual a {name} termina en {days_left}d — toca para renovar",
        'fr': f"Votre soutien mensuel à {name} se termine dans {days_left}j — appuyez pour renouveler",
        'de': f"Ihre monatliche Unterstützung für {name} endet in {days_left}T — zum Verlängern tippen",
    }
    title = titles.get(lang, titles['en'])
    body = bodies.get(lang, bodies['en'])
    url = f"/u/{recipient.local_name or recipient.id}"
    return emit_notification(
        user,
        type='subscription_expiring',
        title=title,
        body=body,
        data={'subscription_id': subscription.id, 'recipient_id': recipient.id},
        url=url,
    )
