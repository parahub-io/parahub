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


# ===== Notification preference check =====

def _should_notify(user, notification_type: str) -> bool:
    """Check if user has enabled this notification category."""
    from identity.models import Profile

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
    }

    category = TYPE_TO_CATEGORY.get(notification_type)
    if not category:
        return True  # Unknown type = always send

    profile = Profile.objects.filter(account=user, is_primary=True).first()
    if not profile:
        return True

    prefs = profile.notification_prefs or {}
    return prefs.get(category, True)  # Default = enabled


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
        'fr': "Nouveau Contrat"
    }

    bodies = {
        'en': f"You have a new contract with {other_party}",
        'ru': f"У вас новый контракт с {other_party}",
        'pt': f"Você tem um novo contrato com {other_party}",
        'es': f"Tienes un nuevo contrato con {other_party}",
        'fr': f"Vous avez un nouveau contrat avec {other_party}"
    }

    title = titles.get(lang, titles['en'])
    body = bodies.get(lang, bodies['en'])
    url = f"/contracts/{contract.id}"

    return send_push_notification(
        user,
        title,
        body,
        data={'contract_id': contract.id, 'type': 'new_contract'},
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
            'fr': "Nouvelle Dette Enregistrée"
        }
        bodies = {
            'en': f"{other_party} owes you {debt.amount} {debt.currency}",
            'ru': f"{other_party} должен вам {debt.amount} {debt.currency}",
            'pt': f"{other_party} deve a você {debt.amount} {debt.currency}",
            'es': f"{other_party} te debe {debt.amount} {debt.currency}",
            'fr': f"{other_party} vous doit {debt.amount} {debt.currency}"
        }
    else:
        titles = {
            'en': "New Debt",
            'ru': "Новый долг",
            'pt': "Nova Dívida",
            'es': "Nueva Deuda",
            'fr': "Nouvelle Dette"
        }
        bodies = {
            'en': f"You owe {other_party} {debt.amount} {debt.currency}",
            'ru': f"Вы должны {other_party} {debt.amount} {debt.currency}",
            'pt': f"Você deve a {other_party} {debt.amount} {debt.currency}",
            'es': f"Debes a {other_party} {debt.amount} {debt.currency}",
            'fr': f"Vous devez à {other_party} {debt.amount} {debt.currency}"
        }

    title = titles.get(lang, titles['en'])
    body = bodies.get(lang, bodies['en'])
    url = f"/debts"

    return send_push_notification(
        user,
        title,
        body,
        data={'debt_id': debt.id, 'type': 'new_debt'},
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
        'fr': "Contrat Signé"
    }

    bodies = {
        'en': "Contract has been signed by all parties",
        'ru': "Контракт подписан всеми сторонами",
        'pt': "O contrato foi assinado por todas as partes",
        'es': "El contrato ha sido firmado por todas las partes",
        'fr': "Le contrat a été signé par toutes les parties"
    }

    title = titles.get(lang, titles['en'])
    body = bodies.get(lang, bodies['en'])
    url = f"/contracts/{contract.id}"

    return send_push_notification(
        user,
        title,
        body,
        data={'contract_id': contract.id, 'type': 'contract_signed'},
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
        'fr': "Nouveau Partenaire"
    }

    bodies = {
        'en': f"{display_name} added you to their partners",
        'ru': f"{display_name} добавил вас в партнёры",
        'pt': f"{display_name} adicionou você aos parceiros",
        'es': f"{display_name} te agregó a sus socios",
        'fr': f"{display_name} vous a ajouté à ses partenaires"
    }

    title = titles.get(lang, titles['en'])
    body = bodies.get(lang, bodies['en'])
    url = f"/u/{partner_profile.id}"

    return send_push_notification(
        user,
        title,
        body,
        data={'partner_id': partner_profile.id, 'type': 'partner_added'},
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
        'fr': "Nouvelle Vérification"
    }

    bodies = {
        'en': f"{display_name} has verified you in Web of Trust",
        'ru': f"{display_name} верифицировал вас в Web of Trust",
        'pt': f"{display_name} verificou você na Web of Trust",
        'es': f"{display_name} te ha verificado en Web of Trust",
        'fr': f"{display_name} vous a vérifié dans Web of Trust"
    }

    title = titles.get(lang, titles['en'])
    body = bodies.get(lang, bodies['en'])
    url = f"/u/{verifier_profile.id}"

    return send_push_notification(
        user,
        title,
        body,
        data={'verifier_id': verifier_profile.id, 'type': 'verification_received'},
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

    return send_push_notification(
        user,
        title,
        body,
        data={'poll_id': poll.id, 'type': 'new_poll', 'creator_id': creator_profile.id},
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
    }

    bodies = {
        'en': f"{delegator_name} delegated their vote to you in: {poll.title}",
        'ru': f"{delegator_name} делегировал вам голос в: {poll.title}",
        'pt': f"{delegator_name} delegou o voto a você em: {poll.title}",
        'es': f"{delegator_name} te delegó su voto en: {poll.title}",
        'fr': f"{delegator_name} vous a délégué son vote dans : {poll.title}",
    }

    title = titles.get(lang, titles['en'])
    body = bodies.get(lang, bodies['en'])
    url = f"/governance/polls/{poll.id}"

    return send_push_notification(
        user,
        title,
        body,
        data={'poll_id': poll.id, 'delegator_id': delegator_profile.id, 'type': 'delegation_received'},
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
    }

    bodies = {
        'en': f'"{poll.title}" closes in {hours_left}h — you haven\'t voted yet',
        'ru': f'«{poll.title}» завершится через {hours_left}ч — вы ещё не проголосовали',
        'pt': f'"{poll.title}" encerra em {hours_left}h — você ainda não votou',
        'es': f'"{poll.title}" cierra en {hours_left}h — aún no has votado',
        'fr': f'"{poll.title}" ferme dans {hours_left}h — vous n\'avez pas encore voté',
    }

    title = titles.get(lang, titles['en'])
    body = bodies.get(lang, bodies['en'])
    url = f"/governance/polls/{poll.id}"

    return send_push_notification(
        user,
        title,
        body,
        data={'poll_id': poll.id, 'type': 'poll_closing_soon'},
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

    return send_push_notification(
        user,
        title,
        body,
        data={
            'type': 'incoming_call',
            'caller_id': caller_profile.id,
            'caller_name': caller_name,
            'room_name': room_name,
            'requireInteraction': True,
            'vibrate': [300, 100, 300, 100, 300],  # Long pattern for calls
            'tag': 'incoming-call'
        },
        url=url
    )
