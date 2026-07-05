"""
Django signals for the contracts app: live WebSocket updates to both parties.

Reputation recalculation on Contract/ContractReview saves stays in
identity/signals.py (lazy 'contracts.*' senders) next to the other
cross-app reputation triggers.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
import logging

from contracts.models import Contract


logger = logging.getLogger(__name__)


@receiver(post_save, sender=Contract)
def notify_contract_update(sender, instance, created, **kwargs):
    """
    Send WebSocket notifications to both parties when contract is created/updated
    """
    # Build contract data for WebSocket
    contract_data = {
        'id': instance.id,
        'object_type': 'contract',
        'creator_id': instance.creator_id,
        'creator_display_name': instance.creator.display_name or instance.creator.hna or '',
        'partner_id': instance.partner_id,
        'partner_display_name': instance.partner.display_name or instance.partner.hna or '',
        'arbiter_id': instance.arbiter_id,
        'arbiter_display_name': instance.arbiter.display_name or instance.arbiter.hna or '' if instance.arbiter else None,
        'title': instance.title,
        'file_sha256': instance.file_sha256,
        'status': instance.status,
        'creator_signed_at': instance.creator_signed_at.isoformat() if instance.creator_signed_at else None,
        'partner_signed_at': instance.partner_signed_at.isoformat() if instance.partner_signed_at else None,
        'creator_completed_at': instance.creator_completed_at.isoformat() if instance.creator_completed_at else None,
        'partner_completed_at': instance.partner_completed_at.isoformat() if instance.partner_completed_at else None,
        'created_at': instance.created_at.isoformat(),
        'updated_at': instance.updated_at.isoformat(),
    }

    from parahub.services.ws_publish import ws_publish
    event_type = "contract.updated" if not created else "contract.created"
    payload = {"type": event_type, "contract": contract_data}

    ws_publish(f"user:{instance.creator.account_id}", payload)
    ws_publish(f"user:{instance.partner.account_id}", payload)
