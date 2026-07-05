"""
Central pre_delete fan-out for polymorphic (object_id-keyed) attachments.

Universal attachments (ObjectPhoto/File/Comment/Video, Like) reference their
host by bare ULID — no FK, so the database cannot cascade them. Without this
fan-out, deleting a host silently strands its attachment rows (and the photo/
file blobs on disk) forever.

Financial attachments (ObjectShare, ObjectDistribution) are the opposite
case: they represent other people's money and must never vanish together
with the host. Deleting a host that still has active shares or any
distribution history is refused with ProtectedError — deactivate/resolve
them explicitly first.
"""

import logging

from django.apps import apps
from django.db.models import ProtectedError
from django.db.models.signals import pre_delete

logger = logging.getLogger(__name__)

# Host models that receive universal attachments. An object_id is a bare ULID
# (attach endpoints accept any 26-char id), so this registry — not the schema —
# defines whose deletion fans out.
ATTACHMENT_HOSTS = [
    'market.Item',
    'geo.Establishment',
    'geo.Event',
    'geo.WorldObject',
    'identity.Profile',
    'cms.Post',
    'cms.SitePage',
    'energy.EnergyCell',
    'iot.Property',
]


def delete_attachments(sender, instance, **kwargs):
    from core.models import (
        Like, ObjectComment, ObjectDistribution, ObjectFile, ObjectPhoto,
        ObjectShare, ObjectVideo,
    )

    oid = instance.pk

    active_shares = ObjectShare.objects.filter(object_id=oid, is_active=True)
    distributions = ObjectDistribution.objects.filter(object_id=oid)
    if active_shares.exists() or distributions.exists():
        raise ProtectedError(
            f"{sender.__name__} {oid} still has active investment shares or "
            f"distribution history; deactivate/resolve them before deleting.",
            set(active_shares) | set(distributions),
        )

    # Per-instance .delete() so FileField storage blobs go with the rows.
    for photo in ObjectPhoto.objects.filter(object_id=oid):
        photo.image.delete(save=False)
        photo.delete()
    for f in ObjectFile.objects.filter(object_id=oid):
        f.file.delete(save=False)
        f.delete()

    ObjectComment.objects.filter(object_id=oid).delete()
    # DB row only — the PeerTube video belongs to its uploader's account.
    ObjectVideo.objects.filter(object_id=oid).delete()
    Like.objects.filter(target_id=oid).delete()
    # Inactive shares are resolved history and follow their host.
    ObjectShare.objects.filter(object_id=oid).delete()


def connect_attachment_fanout():
    for label in ATTACHMENT_HOSTS:
        pre_delete.connect(
            delete_attachments,
            sender=apps.get_model(label),
            dispatch_uid=f'core.attachments.{label}',
        )
