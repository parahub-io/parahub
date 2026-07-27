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
