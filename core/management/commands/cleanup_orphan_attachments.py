"""
Report (and optionally delete) orphaned polymorphic attachments.

Attachments reference hosts by bare ULID (no FK), so hosts deleted before the
core pre_delete fan-out existed left rows behind. An id counts as live if it
exists in ANY model with a 26-char CharField pk — not just the registered
ATTACHMENT_HOSTS — so an attachment on an unregistered host type is never
misread as an orphan.

Dry-run by default; --apply deletes content attachments (photo/file storage
blobs included). ObjectShare/ObjectDistribution orphans are ALWAYS report-only:
financial records need a human decision.

    python3 manage.py cleanup_orphan_attachments [--apply]
"""

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import models

from core.models import (
    Like, ObjectComment, ObjectDistribution, ObjectFile, ObjectPhoto,
    ObjectShare, ObjectVideo,
)

CHUNK = 500


class Command(BaseCommand):
    help = 'Report/delete attachment rows whose host object no longer exists'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Delete orphaned content attachments (default: report only)')

    def handle(self, *args, **options):
        host_models = [
            m for m in apps.get_models()
            if m._meta.managed
            and isinstance(m._meta.pk, models.CharField)
            and m._meta.pk.max_length == 26
        ]
        self.stdout.write(f'Checking ids against {len(host_models)} ULID-pk models')

        def live_ids(ids):
            ids = list(ids)
            found = set()
            for model in host_models:
                remaining = [i for i in ids if i not in found]
                if not remaining:
                    break
                for off in range(0, len(remaining), CHUNK):
                    chunk = remaining[off:off + CHUNK]
                    found.update(model.objects.filter(pk__in=chunk).values_list('pk', flat=True))
            return found

        specs = [
            (ObjectPhoto, 'object_id', 'content'),
            (ObjectFile, 'object_id', 'content'),
            (ObjectComment, 'object_id', 'content'),
            (ObjectVideo, 'object_id', 'content'),
            (Like, 'target_id', 'content'),
            (ObjectShare, 'object_id', 'financial'),
            (ObjectDistribution, 'object_id', 'financial'),
        ]

        for model, id_field, kind in specs:
            referenced = set(model.objects.values_list(id_field, flat=True).distinct())
            if not referenced:
                self.stdout.write(f'{model.__name__}: 0 rows')
                continue
            orphan_ids = referenced - live_ids(referenced)
            qs = model.objects.filter(**{f'{id_field}__in': orphan_ids})
            n = qs.count()
            self.stdout.write(
                f'{model.__name__}: {n} orphaned rows '
                f'({len(orphan_ids)} dead ids of {len(referenced)} referenced)'
            )
            for oid in sorted(orphan_ids):
                self.stdout.write(f'  dead host {oid}')
            if not n or not options['apply']:
                continue
            if kind == 'financial':
                self.stdout.write(self.style.WARNING(
                    f'  {model.__name__} is financial — left untouched, resolve manually'))
                continue
            if model is ObjectPhoto:
                for photo in qs:
                    photo.image.delete(save=False)
                    photo.delete()
            elif model is ObjectFile:
                for f in qs:
                    f.file.delete(save=False)
                    f.delete()
            else:
                qs.delete()
            self.stdout.write(self.style.SUCCESS(f'  deleted {n}'))

        if not options['apply']:
            self.stdout.write('Dry run — pass --apply to delete content orphans')
