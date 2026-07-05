from django.db import migrations
from django.db.models import F


def backfill_actor_ulid(apps, schema_editor):
    """Snapshot existing actor FK ids into actor_ulid so Merkle chain verification
    (which now reads the snapshot, not the live FK) reproduces historical hashes."""
    PollAuditLog = apps.get_model('governance', 'PollAuditLog')
    PollAuditLog.objects.filter(actor__isnull=False).update(actor_ulid=F('actor_id'))


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('governance', '0003_poll_ballot_mode_poll_civic_destination_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_actor_ulid, noop),
    ]
