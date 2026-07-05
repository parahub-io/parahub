"""
Django signals for identity app.

Includes automatic WoT status sync via Verification post_save/post_delete.
Foundation members are added manually and do not require automatic verification.
"""

from django.db import transaction
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in
import logging

from identity.models import Profile, Verification
from geo.models import EstablishmentMembership


logger = logging.getLogger(__name__)


@receiver(user_logged_in)
def copy_oauth_credentials_to_session(sender, request, user, **kwargs):
    """
    Copy OAuth-generated credentials from user object to session.

    Django creates a new session on login for security, so credentials stored
    in the old session are lost. We temporarily store them on the user object
    in adapters.py and copy them to the new session here.
    """
    try:
        hna = getattr(user, '_oauth_generated_hna', None)
        password = getattr(user, '_oauth_generated_password', None)
        is_new = getattr(user, '_oauth_is_new_user', False)

        if hna and password:
            request.session['generated_hna'] = hna
            request.session['generated_password'] = password
            request.session['is_new_oauth_user'] = is_new
            request.session.set_expiry(1800)  # 30 minutes
            logger.info(f"[Login] Copied OAuth credentials to session for {user.username}, session_key: {request.session.session_key}")

            # Clean up user attributes
            delattr(user, '_oauth_generated_hna')
            delattr(user, '_oauth_generated_password')
            delattr(user, '_oauth_is_new_user')
    except Exception as e:
        logger.error(f"[Login] Failed to copy OAuth credentials to session: {e}")


@receiver(user_logged_in)
def sync_language_from_cookie(sender, request, user, **kwargs):
    """
    Sync user's preferred language from cookie to profile on login.

    This handles the case where user selects language before authentication,
    so their language preference is saved in cookie but not in database.
    """
    try:
        # Get user's profile
        profile = Profile.objects.filter(account=user).first()

        # Only sync if profile exists and preferred_language is empty
        if profile and not profile.preferred_language:
            # Try to get language from cookie
            lang_cookie = request.COOKIES.get('preferred_language')

            if lang_cookie and lang_cookie in ['en', 'es', 'fr', 'de', 'pt', 'ru']:
                profile.preferred_language = lang_cookie
                profile.save(update_fields=['preferred_language'])
                logger.info(f"[Login] Synced language from cookie for user {user.username}: {lang_cookie}")
    except Exception as e:
        logger.error(f"[Login] Failed to sync language from cookie: {e}")


@receiver(user_logged_in)
def create_matrix_user_on_login(sender, request, user, **kwargs):
    """
    Proactively create Matrix user on login to ensure they exist before chat usage.

    This runs asynchronously in background to avoid blocking the login process.
    Matrix user is created with deterministic password derived from account ID.

    IMPORTANT: Skip for new OAuth users who need to confirm username first!
    Matrix ID cannot be changed, so we must wait until username is finalized.
    """
    # Skip Matrix creation for new OAuth users who haven't confirmed username yet
    # Check both user attribute AND session flag (signal order is non-deterministic,
    # copy_oauth_credentials_to_session might have already moved flag to session)
    is_new_oauth_user = getattr(user, '_oauth_is_new_user', False)
    if not is_new_oauth_user:
        # Also check session - the other signal might have already copied it there
        is_new_oauth_user = request.session.get('is_new_oauth_user', False)

    if is_new_oauth_user:
        logger.info(f"[Login] Skipping Matrix creation for new OAuth user {user.username} - needs username confirmation")
        return

    from threading import Thread

    def create_matrix_user_background():
        try:
            # Import here to avoid circular dependency
            from parahub.endpoints.matrix_auth import _get_or_create_matrix_token

            # Attempt to create Matrix user
            token = _get_or_create_matrix_token(user.id)
            if token:
                logger.info(f"[Login] Matrix user created/verified for {user.username}")
            else:
                logger.warning(f"[Login] Failed to create Matrix user for {user.username}")
        except Exception as e:
            logger.error(f"[Login] Exception while creating Matrix user for {user.username}: {e}")

    # Run in background thread to not block login
    thread = Thread(target=create_matrix_user_background, daemon=True)
    thread.start()


@receiver(post_save, sender=EstablishmentMembership)
def log_foundation_member_added(sender, instance, created, **kwargs):
    """
    Log when a foundation member is added to Parahub - Associação.

    Foundation members do not receive automatic verifications - they can verify
    others immediately based on their legal status as Associados Fundadores.
    """
    # Only log new foundation member additions
    if not created or instance.membership_level != 'fundador':
        return

    # Check if this is PARAHUB establishment
    if instance.establishment.slug == 'parahub-associacao':
        logger.info(
            f'Foundation member added: {instance.profile.hna} '
            f'to {instance.establishment.name}. '
            f'This user can now verify others immediately (seed verifier).'
        )


@receiver(post_save, sender=Verification)
def sync_wot_status_on_verification_save(sender, instance, **kwargs):
    """Auto-update is_verified_wot when a Verification is created or modified."""
    try:
        instance.verified_profile.update_wot_status()
    except Exception as e:
        logger.error(f"Failed to sync WoT status on verification save: {e}")


@receiver(post_delete, sender=Verification)
def sync_wot_status_on_verification_delete(sender, instance, **kwargs):
    """Auto-update is_verified_wot when a Verification is deleted."""
    try:
        # Profile may have been cascade-deleted too
        if Profile.objects.filter(pk=instance.verified_profile_id).exists():
            instance.verified_profile.update_wot_status()
    except Exception as e:
        logger.error(f"Failed to sync WoT status on verification delete: {e}")


mailcow_logger = logging.getLogger('parahub.mailcow')


@receiver(post_save, sender='identity.Account')
def create_mailbox_on_registration(sender, instance, created, **kwargs):
    """
    Create a @parahub.io mailbox for new accounts when Mailcow integration is enabled.

    Runs in background thread so mailcow errors never block registration.
    """
    if not created:
        return

    from constance import config
    if not getattr(config, 'MAILCOW_ENABLED', False):
        return

    # Skip throwaway test/E2E accounts. They never read mail, and their mailboxes
    # would orphan in Mailcow: seed --reset / E2E teardown drop the Account but not
    # the Mailcow mailbox, so each run leaks a real mailbox. See PK/mail-system.md.
    if instance.username.startswith('e2etest') or (instance.email or '').endswith('@test.parahub.io'):
        return

    from threading import Thread

    def _create():
        try:
            from parahub.services.mailcow import MailcowService, encrypt_mail_password
            from identity.models import Account
            username = instance.username
            display_name = instance.get_full_name() or username
            if not MailcowService.mailbox_exists(username):
                result = MailcowService.create_mailbox(username, display_name)
                Account.objects.filter(pk=instance.pk).update(
                    mail_password=encrypt_mail_password(result['password'])
                )
                mailcow_logger.info(f'Mailbox created: {username}@parahub.io')
        except Exception as e:
            mailcow_logger.error(f'Failed to create mailbox for {instance.username}: {e}')

    Thread(target=_create, daemon=True).start()


# ---------------------------------------------------------------------------
# Reputation recalculation signals
# ---------------------------------------------------------------------------

def _recalc_reputation(profile_id):
    """Recalculate and persist reputation for a single profile (deferred via on_commit)."""
    try:
        from identity.reputation import calculate_reputation
        profile = Profile.objects.get(pk=profile_id)
        result = calculate_reputation(profile)
        Profile.objects.filter(pk=profile_id).update(reputation_score=result['total'])
    except Profile.DoesNotExist:
        pass
    except Exception as e:
        logger.error(f"Reputation recalc failed for {profile_id}: {e}")


def _schedule_recalc(profile_id):
    """Schedule reputation recalc after current transaction commits."""
    transaction.on_commit(lambda: _recalc_reputation(profile_id))


@receiver(post_save, sender='contracts.ContractReview')
@receiver(post_delete, sender='contracts.ContractReview')
def recalc_reputation_on_review(sender, instance, **kwargs):
    _schedule_recalc(instance.reviewed_id)


@receiver(post_save, sender='geo.EventParticipant')
@receiver(post_delete, sender='geo.EventParticipant')
def recalc_reputation_on_event_participation(sender, instance, **kwargs):
    _schedule_recalc(instance.profile_id)


@receiver(post_save, sender=EstablishmentMembership)
@receiver(post_delete, sender=EstablishmentMembership)
def recalc_reputation_on_membership(sender, instance, **kwargs):
    _schedule_recalc(instance.profile_id)


@receiver(post_save, sender='governance.PollVote')
@receiver(post_delete, sender='governance.PollVote')
def recalc_reputation_on_vote(sender, instance, **kwargs):
    _schedule_recalc(instance.voter_id)


@receiver(post_save, sender='governance.PollVoteDelegation')
@receiver(post_delete, sender='governance.PollVoteDelegation')
def recalc_reputation_on_delegation(sender, instance, **kwargs):
    _schedule_recalc(instance.delegate_id)


@receiver(post_save, sender='contracts.Contract')
def recalc_reputation_on_contract(sender, instance, **kwargs):
    _schedule_recalc(instance.creator_id)
    _schedule_recalc(instance.partner_id)


@receiver(post_save, sender='debts.Debt')
def recalc_reputation_on_debt(sender, instance, **kwargs):
    _schedule_recalc(instance.debtor_id)
