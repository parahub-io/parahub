"""Mesh pass grants — the single entry point for extending a profile's
full-speed entitlement, shared by Lightning payments, achievements and
manual grants."""

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone


def grant_mesh_pass(profile, days: int, source: str = 'GRANT',
                    amount_sats: int = None, credit=None):
    """Extend (or start) `profile`'s mesh pass by `days`.

    Lightning flow passes its existing PENDING `credit` to mark applied;
    every other caller (achievements, staff grants) omits it and gets an
    APPLIED credit row created for the audit trail.
    """
    from .models import MeshPass, MeshPassCredit

    now = timezone.now()
    with transaction.atomic():
        mesh_pass, _ = MeshPass.objects.select_for_update().get_or_create(
            profile=profile,
            defaults={'expires_at': now, 'max_devices': settings.MESH_PASS_MAX_DEVICES},
        )
        base = mesh_pass.expires_at if mesh_pass.expires_at > now else now
        mesh_pass.expires_at = base + timedelta(days=days)
        mesh_pass.save(update_fields=['expires_at', 'updated_at'])

        if credit is not None:
            credit.status = MeshPassCredit.Status.APPLIED
            credit.applied_at = now
            credit.save(update_fields=['status', 'applied_at'])
        else:
            MeshPassCredit.objects.create(
                mesh_pass=mesh_pass, source=source, days=days,
                amount_sats=amount_sats,
                status=MeshPassCredit.Status.APPLIED, applied_at=now,
            )
    return mesh_pass


def ensure_mesh_pass_floor(profile, days: int, renew_below_days: int,
                           source: str = 'ACHIEVEMENT'):
    """Keep `profile`'s pass covering at least `days` ahead. Never shortens it.

    Unlike `grant_mesh_pass` (which always adds days) this is safe to call on a
    repeating signal such as a node heartbeat: the extension fires only once
    coverage drops below `renew_below_days`, so a node beating every 5 minutes
    writes one credit row per renewal cycle rather than one per beat. A longer
    expiry from a payment or a staff grant always wins.

    Returns the credit row when it extended, else None.
    """
    from .models import MeshPass, MeshPassCredit

    if days <= 0:
        return None

    now = timezone.now()
    threshold = now + timedelta(days=renew_below_days)

    # Unlocked pre-check: the overwhelmingly common call is a no-op, and this
    # keeps it to one indexed read on the heartbeat path.
    covered = MeshPass.objects.filter(profile=profile).values_list('expires_at', flat=True).first()
    if covered is not None and covered > threshold:
        return None

    target = now + timedelta(days=days)
    with transaction.atomic():
        mesh_pass, _ = MeshPass.objects.select_for_update().get_or_create(
            profile=profile,
            defaults={'expires_at': now, 'max_devices': settings.MESH_PASS_MAX_DEVICES},
        )
        # Re-check under the row lock: concurrent heartbeats from several nodes
        # of the same owner must produce one credit, not one each.
        if mesh_pass.expires_at > threshold:
            return None
        added = target - max(mesh_pass.expires_at, now)
        mesh_pass.expires_at = target
        mesh_pass.save(update_fields=['expires_at', 'updated_at'])
        return MeshPassCredit.objects.create(
            mesh_pass=mesh_pass, source=source,
            # Nearest whole day: rounding up would credit an extra day on every
            # renewal, so the credit rows would drift above real coverage.
            days=max(1, round(added.total_seconds() / 86400)),
            status=MeshPassCredit.Status.APPLIED, applied_at=now,
        )
