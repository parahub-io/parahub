"""
Barter Signals
Auto-sync PostgreSQL changes to Neo4j graph
"""

from django.db.models.signals import post_save, post_delete, pre_delete
from django.dispatch import receiver
from django.core.cache import cache
from django.db import transaction
from market.models import Item
from taxonomy.models import Category
from identity.models import Profile
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


@receiver(post_save, sender=Profile)
def sync_profile_to_neo4j(sender, instance, created, **kwargs):
    """Sync Profile (User) to Neo4j when created/updated"""
    profile_pk = instance.pk

    def do_sync():
        try:
            profile = Profile.objects.get(pk=profile_pk)
            graph_service.sync_user_to_graph(profile)
            logger.info(f"Synced profile {profile_pk} to Neo4j")
        except Profile.DoesNotExist:
            logger.warning(f"Profile {profile_pk} deleted before Neo4j sync completed")
        except Exception as e:
            logger.error(f"Failed to sync profile {profile_pk} to Neo4j: {e}")

    transaction.on_commit(lambda: threading.Thread(target=do_sync, daemon=True).start())


@receiver(post_save, sender=Category)
def sync_category_to_neo4j(sender, instance, created, **kwargs):
    """Sync Category to Neo4j when created/updated"""
    category_pk = instance.pk

    def do_sync():
        try:
            category = Category.objects.get(pk=category_pk)
            graph_service.sync_category_to_graph(category)
            logger.info(f"Synced category {category_pk} to Neo4j")
        except Category.DoesNotExist:
            logger.warning(f"Category {category_pk} deleted before Neo4j sync completed")
        except Exception as e:
            logger.error(f"Failed to sync category {category_pk} to Neo4j: {e}")

    transaction.on_commit(lambda: threading.Thread(target=do_sync, daemon=True).start())


@receiver(post_save, sender=Item)
def sync_item_to_neo4j(sender, instance, created, **kwargs):
    """
    Sync Item to Neo4j when created/updated

    Only sync if:
    - Item is active
    - Item has owner and category
    - Item type is CREDIT or DEBIT
    """
    # Invalidate barter cache synchronously (fast Redis op)
    if instance.owner_id:
        _invalidate_barter_cache(instance.owner_id)

    # Capture values for guard checks in the deferred thread
    item_pk = instance.pk
    is_active = instance.is_active
    owner_id = instance.owner_id
    category_id = instance.category_id
    item_type = instance.type

    def do_sync():
        if not is_active:
            if not created:
                try:
                    graph_service.delete_item_from_graph(item_pk)
                    logger.info(f"Deleted inactive item {item_pk} from Neo4j")
                except Exception as e:
                    logger.error(f"Failed to delete item {item_pk} from Neo4j: {e}")
            return

        if not owner_id or not category_id:
            logger.warning(f"Skipping Neo4j sync for item {item_pk}: missing owner or category")
            return

        if item_type not in ['CREDIT', 'DEBIT']:
            logger.warning(f"Skipping Neo4j sync for item {item_pk}: invalid type {item_type}")
            return

        try:
            item = Item.objects.get(pk=item_pk)
            graph_service.sync_item_to_graph(item)
            logger.info(f"Synced item {item_pk} to Neo4j")
        except Item.DoesNotExist:
            logger.warning(f"Item {item_pk} deleted before Neo4j sync completed")
        except Exception as e:
            logger.error(f"Failed to sync item {item_pk} to Neo4j: {e}")

    transaction.on_commit(lambda: threading.Thread(target=do_sync, daemon=True).start())


@receiver(pre_delete, sender=Item)
def delete_item_from_neo4j(sender, instance, **kwargs):
    """Remove Item from Neo4j when deleted"""
    if instance.owner_id:
        _invalidate_barter_cache(instance.owner_id)

    item_pk = instance.pk

    def do_delete():
        try:
            graph_service.delete_item_from_graph(item_pk)
            logger.info(f"Deleted item {item_pk} from Neo4j")
        except Exception as e:
            logger.error(f"Failed to delete item {item_pk} from Neo4j: {e}")

    transaction.on_commit(lambda: threading.Thread(target=do_delete, daemon=True).start())
