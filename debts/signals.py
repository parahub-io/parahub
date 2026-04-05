"""
Debts Signals
Auto-sync PostgreSQL debts to Neo4j graph as virtual items
Send WebSocket notifications for real-time updates
"""

from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.core.cache import cache
from django.db import transaction
from debts.models import Debt, DebtRepayment
from barter.graph_service import BarterGraphService
import logging
import threading

logger = logging.getLogger(__name__)

graph_service = BarterGraphService()


def _invalidate_barter_cache(profile_id: str):
    """Bump cache version to invalidate all barter chain keys for a profile"""
    version_key = f"barter:version:{profile_id}"
    try:
        cache.incr(version_key)
    except ValueError:
        cache.set(version_key, 1, timeout=None)


@receiver(post_save, sender=Debt)
def sync_debt_to_neo4j(sender, instance, created, **kwargs):
    """
    Sync Debt to Neo4j when created/updated
    Send WebSocket notifications to both parties
    Send Web Push notifications on new debt creation
    """
    # Invalidate barter cache for both parties
    _invalidate_barter_cache(instance.debtor_id)
    _invalidate_barter_cache(instance.creditor_id)

    # Build debt data for WebSocket
    debt_data = {
        'id': instance.id,
        'object_type': 'debt',
        'creditor_id': instance.creditor_id,
        'creditor_display_name': instance.creditor.display_name or instance.creditor.hna or '',
        'debtor_id': instance.debtor_id,
        'debtor_display_name': instance.debtor.display_name or instance.debtor.hna or '',
        'amount': float(instance.amount),
        'remaining_amount': float(instance.remaining_amount),
        'currency': instance.currency,
        'status': instance.status,
        'description': instance.description,
        'percent_settled': float(instance.percent_settled),
        'confirmed_by_creditor_at': instance.confirmed_by_creditor_at.isoformat() if instance.confirmed_by_creditor_at else None,
        'confirmed_by_debtor_at': instance.confirmed_by_debtor_at.isoformat() if instance.confirmed_by_debtor_at else None,
        'created_at': instance.created_at.isoformat(),
        'updated_at': instance.updated_at.isoformat(),
    }

    # ALWAYS send WebSocket notification (even for settled debts)
    from parahub.services.ws_publish import ws_publish
    event_type = "debt.updated" if not created else "debt.created"
    payload = {"type": event_type, "debt": debt_data}

    ws_publish(f"user:{instance.creditor.account_id}", payload)
    ws_publish(f"user:{instance.debtor.account_id}", payload)

    # Send Web Push notifications on new debt creation
    if created:
        from notifications.services import notify_new_debt

        # Notify creditor (person who is owed)
        try:
            notify_new_debt(instance.creditor.account, instance)
            logger.info(f"Sent Web Push to creditor for debt {instance.id}")
        except Exception as e:
            logger.error(f"Failed to send Web Push to creditor: {e}")

        # Notify debtor (person who owes)
        try:
            notify_new_debt(instance.debtor.account, instance)
            logger.info(f"Sent Web Push to debtor for debt {instance.id}")
        except Exception as e:
            logger.error(f"Failed to send Web Push to debtor: {e}")

    # Defer Neo4j sync to after transaction commits (non-blocking)
    debt_id = instance.id
    is_active = instance.is_active
    has_debtor = instance.debtor_id is not None
    has_creditor = instance.creditor_id is not None
    remaining_amount = instance.remaining_amount

    def do_neo4j_sync():
        if not is_active:
            if not created:
                try:
                    graph_service.delete_debt_from_graph(debt_id)
                    logger.info(f"Deleted inactive debt {debt_id} from Neo4j")
                except Exception as e:
                    logger.error(f"Failed to delete debt {debt_id} from Neo4j: {e}")
            return

        if not has_debtor or not has_creditor:
            logger.warning(f"Skipping Neo4j sync for debt {debt_id}: missing debtor or creditor")
            return

        if remaining_amount <= 0:
            logger.warning(f"Skipping Neo4j sync for debt {debt_id}: zero remaining_amount")
            return

        try:
            debt = Debt.objects.get(pk=debt_id)
            graph_service.sync_debt_to_graph(debt)
            logger.info(f"Synced debt {debt_id} to Neo4j")
        except Debt.DoesNotExist:
            logger.warning(f"Debt {debt_id} deleted before Neo4j sync completed")
        except Exception as e:
            logger.error(f"Failed to sync debt {debt_id} to Neo4j: {e}")

    transaction.on_commit(lambda: threading.Thread(target=do_neo4j_sync, daemon=True).start())


@receiver(pre_delete, sender=Debt)
def delete_debt_from_neo4j(sender, instance, **kwargs):
    """Remove Debt from Neo4j when deleted"""
    _invalidate_barter_cache(instance.debtor_id)
    _invalidate_barter_cache(instance.creditor_id)

    debt_id = instance.id

    def do_delete():
        try:
            graph_service.delete_debt_from_graph(debt_id)
            logger.info(f"Deleted debt {debt_id} from Neo4j")
        except Exception as e:
            logger.error(f"Failed to delete debt {debt_id} from Neo4j: {e}")

    transaction.on_commit(lambda: threading.Thread(target=do_delete, daemon=True).start())


@receiver(post_save, sender=DebtRepayment)
def handle_debt_repayment(sender, instance, created, **kwargs):
    """
    When repayment is created, update debt in Neo4j
    """
    if created:
        _invalidate_barter_cache(instance.debt.debtor_id)
        _invalidate_barter_cache(instance.debt.creditor_id)

        debt_id = instance.debt_id

        def do_sync():
            try:
                debt = Debt.objects.get(pk=debt_id)
                if debt.is_active:
                    graph_service.sync_debt_to_graph(debt)
                    logger.info(f"Updated debt {debt_id} in Neo4j after repayment")
                else:
                    graph_service.delete_debt_from_graph(debt_id)
                    logger.info(f"Deleted fully settled debt {debt_id} from Neo4j")
            except Debt.DoesNotExist:
                logger.warning(f"Debt {debt_id} deleted before Neo4j sync after repayment")
            except Exception as e:
                logger.error(f"Failed to update debt {debt_id} in Neo4j after repayment: {e}")

        transaction.on_commit(lambda: threading.Thread(target=do_sync, daemon=True).start())
