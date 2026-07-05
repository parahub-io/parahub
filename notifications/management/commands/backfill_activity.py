"""
Backfill the Activity log from existing first-class actions.

The Activity log is written going forward by notifications.signals, so it would
otherwise start empty at deploy. This one-time (idempotent) pass walks the source
tables (PollVote / Verification / Item / Contract) and creates the missing
Activity rows, so the full history shows up in the feed.

Idempotent: skips any object that already has an Activity row pointing at it
(content_type + object_id). Safe to re-run. WS push is suppressed (publish=False)
so re-importing thousands of rows doesn't fan out live events.

    python3 manage.py backfill_activity            # all builders
    python3 manage.py backfill_activity --dry-run
    python3 manage.py backfill_activity --only voted,verified
"""
from django.core.management.base import BaseCommand
from django.contrib.contenttypes.models import ContentType

from notifications.models import Activity
from notifications.services import record_activity
from notifications.signals import ACTIVITY_BUILDERS


class Command(BaseCommand):
    help = "Backfill Activity log rows from existing PollVote/Verification/Item/Contract"

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help="Count what would be created, write nothing")
        parser.add_argument('--only', type=str, default='',
                            help="Comma-separated verbs to limit to (voted,verified,listed_item,created_contract)")

    def handle(self, *args, **opts):
        dry = opts['dry_run']
        only = {v.strip() for v in opts['only'].split(',') if v.strip()}

        grand_created = grand_skipped = grand_failed = 0

        for model, builder, ts_attr in ACTIVITY_BUILDERS:
            ct = ContentType.objects.get_for_model(model)
            existing = set(
                Activity.objects.filter(content_type=ct)
                .values_list('object_id', flat=True)
            )

            created = skipped = failed = 0
            label = model.__name__

            for obj in model.objects.all().iterator(chunk_size=500):
                if obj.id in existing:
                    skipped += 1
                    continue
                try:
                    kwargs = builder(obj)
                except Exception as e:
                    failed += 1
                    self.stderr.write(f"  {label} {obj.id[:8]}: builder failed: {e}")
                    continue

                if only and kwargs.get('verb') not in only:
                    skipped += 1
                    continue

                if dry:
                    created += 1
                    continue

                try:
                    # Backdate to the source object's action time so the feed is
                    # ordered and dated by when the action actually happened. The
                    # field differs per model (ts_attr) — Verification re-affirms
                    # in place, so its action time is verified_at, not created_at.
                    record_activity(**kwargs, publish=False,
                                    created_ts=getattr(obj, ts_attr, None))
                    created += 1
                except Exception as e:
                    failed += 1
                    self.stderr.write(f"  {label} {obj.id[:8]}: record failed: {e}")

            self.stdout.write(
                f"{label}: created={created} skipped={skipped} failed={failed}"
            )
            grand_created += created
            grand_skipped += skipped
            grand_failed += failed

        verb = "would create" if dry else "created"
        self.stdout.write(self.style.SUCCESS(
            f"Done — {verb}={grand_created} skipped={grand_skipped} failed={grand_failed}"
        ))
