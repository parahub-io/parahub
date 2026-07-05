"""
Signal handlers for automatic audit log creation.

Auto-publishes PGP keys and creates pending OpenTimestamps proofs when contracts/debts are signed.
Actual OTS stamping happens in batches via batch_ots_stamp management command (every 10 min).
"""
import hashlib
import json
import logging
from typing import Optional

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError
from asgiref.sync import async_to_sync

from identity.models import Profile, Verification
from contracts.models import Contract
from debts.models import Debt
from geo.models import Establishment
from parahub.background import spawn

from .services import PGPKeyringService, ProofExportService
from .matrix_service import matrix_service

logger = logging.getLogger(__name__)


def _create_pending_proof(obj, data_to_timestamp: dict) -> Optional['TimestampProof']:
    """
    Create a pending TimestampProof (ots_proof=NULL, batch=NULL).
    Will be stamped in the next batch_ots_stamp run.
    """
    from .models import TimestampProof
    data_json = json.dumps(data_to_timestamp, sort_keys=True, ensure_ascii=False)
    data_hash = hashlib.sha256(data_json.encode('utf-8')).hexdigest()
    ct = ContentType.objects.get_for_model(obj)
    try:
        return TimestampProof.objects.create(
            content_type=ct,
            object_id=obj.id,
            data_hash=data_hash,
            data_json=data_json,
            ots_proof=None,
            batch=None,
        )
    except IntegrityError:
        return None  # Duplicate — proof already exists


@receiver(post_save, sender=Profile)
def publish_pgp_key(sender, instance, created, **kwargs):
    """
    Auto-publish PGP public key to Git repository when profile is created or key is updated.
    """
    if not instance.pgp_public_key:
        return

    try:
        keyring_service = PGPKeyringService()
        publication = keyring_service.publish_key(instance)

        if publication:
            logger.info(f"Published PGP key for profile {instance.id[:8]}: {publication.fingerprint[:16]}")
        else:
            logger.debug(f"PGP key already published for profile {instance.id[:8]}")

    except Exception as e:
        logger.error(f"Failed to publish PGP key for profile {instance.id[:8]}: {e}")


@receiver(post_save, sender=Contract)
def create_contract_timestamp(sender, instance, created, **kwargs):
    """
    Create OpenTimestamps proof when contract is signed by both parties (SIGNED status).
    """
    if instance.status != Contract.Status.SIGNED:
        return

    if not settings.OPENTIMESTAMPS_ENABLED:
        logger.debug("OpenTimestamps disabled, skipping timestamp creation")
        return

    try:
        data_to_timestamp = {
            'id': instance.id,
            'object_type': 'contract',
            'created_at': instance.creator_signed_at.isoformat(),
            'partner_signed_at': instance.partner_signed_at.isoformat() if instance.partner_signed_at else None,
            'creator_id': instance.creator_id,
            'partner_id': instance.partner_id,
            'arbiter_id': instance.arbiter_id,
            'title': instance.title,
            'file_sha256': instance.file_sha256,
            'signatures': {
                'creator': instance.creator_signature,
                'partner': instance.partner_signature,
            }
        }

        proof = _create_pending_proof(instance, data_to_timestamp)

        if proof:
            logger.info(f"Created pending OTS proof for contract {instance.id[:8]}: {proof.data_hash[:16]}...")
        else:
            logger.debug(f"OTS proof already exists for contract {instance.id[:8]}")

    except Exception as e:
        logger.error(f"Error creating pending proof for contract {instance.id[:8]}: {e}")


@receiver(post_save, sender=Debt)
def create_debt_timestamp(sender, instance, created, **kwargs):
    """
    Create OpenTimestamps proof when debt is active (both parties confirmed).
    """
    if instance.status != 'active':
        return

    if not settings.OPENTIMESTAMPS_ENABLED:
        logger.debug("OpenTimestamps disabled, skipping timestamp creation")
        return

    try:
        data_to_timestamp = {
            'id': instance.id,
            'object_type': 'debt',
            'created_at': instance.created_at.isoformat(),
            'creditor_id': instance.creditor_id,
            'debtor_id': instance.debtor_id,
            'amount': str(instance.amount),
            'currency': instance.currency,
            'description': instance.description,
            'due_date': instance.due_date.isoformat() if instance.due_date else None,
            'confirmed_by_creditor_at': instance.confirmed_by_creditor_at.isoformat() if instance.confirmed_by_creditor_at else None,
            'confirmed_by_debtor_at': instance.confirmed_by_debtor_at.isoformat() if instance.confirmed_by_debtor_at else None,
            'signatures': {
                'creditor': getattr(instance, 'creditor_signature', None),
                'debtor': getattr(instance, 'debtor_signature', None),
            }
        }

        proof = _create_pending_proof(instance, data_to_timestamp)

        if proof:
            logger.info(f"Created pending OTS proof for debt {instance.id[:8]}: {proof.data_hash[:16]}...")
        else:
            logger.debug(f"OTS proof already exists for debt {instance.id[:8]}")

    except Exception as e:
        logger.error(f"Error creating pending proof for debt {instance.id[:8]}: {e}")


@receiver(post_save, sender=Verification)
def create_verification_timestamp(sender, instance, created, **kwargs):
    """
    Create OpenTimestamps proof for new WoT verifications.
    """
    if not created:
        return

    if not settings.OPENTIMESTAMPS_ENABLED:
        return

    try:
        data_to_timestamp = {
            'id': instance.id,
            'object_type': 'verification',
            'verified_at': instance.verified_at.isoformat() if instance.verified_at else None,
            'verifier_id': instance.verifier_id,
            'verified_profile_id': instance.verified_profile_id,
            'verification_method': instance.verification_method,
            'signature': instance.signature,
        }

        proof = _create_pending_proof(instance, data_to_timestamp)

        if proof:
            logger.info(f"Created pending OTS proof for verification {instance.id[:8]}")
        else:
            logger.debug(f"OTS proof already exists for verification {instance.id[:8]}")

    except Exception as e:
        logger.error(f"Error creating pending proof for verification {instance.id[:8]}: {e}")


# ── Federation: Organization registry ──────────────────────────────────

@receiver(post_save, sender=Establishment)
def register_organization_in_registry(sender, instance, created, **kwargs):
    """
    Register new organizations in the federation registry git repo.
    Commits a JSON record to organizations/{ulid}.json.
    """
    if not created:
        return

    if not getattr(settings, 'FEDERATION_ENABLED', False):
        return

    def _register():
        try:
            from .registry import RegistryService
            registry = RegistryService()
            commit = registry.register_organization(instance)

            if commit:
                # Create OTS proof for the registry record
                data_to_timestamp = {
                    'id': instance.id,
                    'object_type': 'establishment',
                    'name': instance.name,
                    'node': getattr(settings, 'FEDERATION_DOMAIN', 'parahub.io'),
                    'created_at': instance.created_at.isoformat(),
                    'owner_id': instance.owner_id,
                }
                _create_pending_proof(instance, data_to_timestamp)

                # Broadcast to federation WS
                from parahub.services.ws_publish import ws_publish
                ws_publish('feed:federation', {
                    'type': 'registry_update',
                    'domain': getattr(settings, 'FEDERATION_DOMAIN', 'parahub.io'),
                    'commit': commit,
                    'records': [{
                        'type': 'organization',
                        'ulid': instance.id,
                        'name': instance.name,
                        'action': 'created',
                    }],
                })

                logger.info(f"Registered organization {instance.id[:8]} in federation registry")
        except Exception as e:
            logger.error(f"Failed to register organization {instance.id[:8]} in registry: {e}")

    # Run on the shared background pool to avoid blocking the HTTP response
    spawn(_register)


def _send_verification_notifications(instance_id: str, verified_profile_id: str, verifier_id: str):
    """Send Matrix notifications in background thread to avoid blocking the signal."""
    from identity.models import Profile, Verification
    try:
        instance = Verification.objects.select_related('verified_profile', 'verifier').get(id=instance_id)

        # Send to verified profile's system room
        async_to_sync(matrix_service.send_to_system_room)(
            profile=instance.verified_profile,
            content={
                'msgtype': 'm.parahub.verification.received',
                'body': f"Вы получили верификацию от {instance.verifier.hna}",
                'verification': {
                    'id': instance.id,
                    'timestamp': instance.verified_at.isoformat() if instance.verified_at else None,
                    'verifier_name': instance.verifier.hna,
                    'verifier_id': instance.verifier_id,
                    'type': instance.verification_method,
                },
                'instructions': 'Сохраните это сообщение как доказательство верификации'
            }
        )

        # Send to verifier's system room
        async_to_sync(matrix_service.send_to_system_room)(
            profile=instance.verifier,
            content={
                'msgtype': 'm.parahub.verification.issued',
                'body': f"Вы верифицировали {instance.verified_profile.hna}",
                'verification': {
                    'id': instance.id,
                    'timestamp': instance.verified_at.isoformat() if instance.verified_at else None,
                    'verified_name': instance.verified_profile.hna,
                    'verified_id': instance.verified_profile_id,
                    'type': instance.verification_method,
                }
            }
        )

        logger.info(f"Sent verification notifications for {instance_id[:8]} to Matrix")

    except Exception as e:
        logger.error(f"Failed to send verification notification to Matrix: {e}")


@receiver(post_save, sender=Verification)
def notify_verification_to_matrix(sender, instance, created, **kwargs):
    """
    Send verification notification to both parties' Matrix system rooms.
    Runs in a background thread to avoid blocking the HTTP response.
    """
    if not created:
        return

    spawn(_send_verification_notifications,
          instance.id, instance.verified_profile_id, instance.verifier_id)


@receiver(post_save, sender=Contract)
def email_contract_proof(sender, instance, created, **kwargs):
    """Email contract proof summary to both parties when signed."""
    if instance.status != Contract.Status.SIGNED:
        return

    contract_id = instance.id
    creator_id = instance.creator_id
    partner_id = instance.partner_id
    spawn(_send_contract_email, contract_id, creator_id, partner_id)


def _send_contract_email(contract_id, creator_id, partner_id):
    from django.core.mail import send_mail
    from django.conf import settings as s

    try:
        contract = Contract.objects.select_related(
            'creator__account', 'partner__account',
        ).get(id=contract_id)

        recipients = []
        for profile in (contract.creator, contract.partner):
            email = getattr(profile.account, 'email', None)
            if email:
                recipients.append(email)

        if not recipients:
            logger.debug(f"Contract {contract_id[:8]}: no recipient emails, skipping")
            return

        subject = f"Contract signed: {contract.title}"
        body = (
            f"Contract \"{contract.title}\" has been signed by both parties.\n\n"
            f"Contract ID: {contract.id}\n"
            f"File SHA256: {contract.file_sha256}\n"
            f"Creator: {contract.creator.hna}\n"
            f"Partner: {contract.partner.hna}\n"
            f"Signed at: {contract.updated_at}\n\n"
            f"This is an automated proof notification from ParaHub."
        )
        send_mail(subject, body, s.DEFAULT_FROM_EMAIL, recipients, fail_silently=True)
        logger.info(f"Sent contract proof email for {contract_id[:8]} to {len(recipients)} recipient(s)")
    except Exception as e:
        logger.error(f"Failed to send contract proof email for {contract_id[:8]}: {e}")


@receiver(post_save, sender=Debt)
def email_debt_proof(sender, instance, created, **kwargs):
    """Email debt confirmation to creditor and debtor when active."""
    if instance.status != 'ACTIVE':
        return

    debt_id = instance.id
    creditor_id = instance.creditor_id
    debtor_id = instance.debtor_id
    spawn(_send_debt_email, debt_id, creditor_id, debtor_id)


def _send_debt_email(debt_id, creditor_id, debtor_id):
    from django.core.mail import send_mail
    from django.conf import settings as s

    try:
        debt = Debt.objects.select_related(
            'creditor__account', 'debtor__account',
        ).get(id=debt_id)

        recipients = []
        for profile in (debt.creditor, debt.debtor):
            email = getattr(profile.account, 'email', None)
            if email:
                recipients.append(email)

        if not recipients:
            logger.debug(f"Debt {debt_id[:8]}: no recipient emails, skipping")
            return

        subject = f"Debt confirmed: {debt.amount} {debt.currency}"
        body = (
            f"A debt of {debt.amount} {debt.currency} has been confirmed.\n\n"
            f"Debt ID: {debt.id}\n"
            f"Creditor: {debt.creditor.hna}\n"
            f"Debtor: {debt.debtor.hna}\n"
            f"Amount: {debt.amount} {debt.currency}\n"
            f"Description: {debt.description or '—'}\n"
            f"Confirmed at: {debt.updated_at}\n\n"
            f"This is an automated proof notification from ParaHub."
        )
        send_mail(subject, body, s.DEFAULT_FROM_EMAIL, recipients, fail_silently=True)
        logger.info(f"Sent debt proof email for {debt_id[:8]} to {len(recipients)} recipient(s)")
    except Exception as e:
        logger.error(f"Failed to send debt proof email for {debt_id[:8]}: {e}")
