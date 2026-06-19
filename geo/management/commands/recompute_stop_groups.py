"""
Recompute virtual stop groups (StopGroup) — idempotent display-level dedup.

Runs automatically at the end of update_gtfs_feeds; manual import_gtfs runs
need a manual recompute. See PK/transit-system.md § Virtual stops.
"""
from django.core.management.base import BaseCommand
from django.db import connection

from geo.models import Stop, StopGroup
from geo.services.stop_grouping import compute_desired_groups, recompute_stop_groups


class Command(BaseCommand):
    help = "Recompute virtual stop groups (StopGroup). Idempotent: same data twice → zero diff."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help="Compute and report the diff, write nothing")
        parser.add_argument('--stats', action='store_true',
                            help="Print per-feed breakdown after the run")
        parser.add_argument('--clear', action='store_true',
                            help="Kill-switch: null all Stop.group FKs and delete all groups")
        parser.add_argument('--grep', metavar='SUBSTR',
                            help="Read-only audit: print clusters whose elected name contains SUBSTR")

    def handle(self, *args, **options):
        warn = lambda msg: self.stderr.write(self.style.WARNING(msg))

        if options['clear']:
            cleared = Stop.objects.exclude(group=None).update(group=None)
            deleted, _ = StopGroup.objects.all().delete()
            self.stdout.write(f"Kill-switch: cleared group FK on {cleared} stops, deleted {deleted} groups")
            return

        if options['grep']:
            self._grep(options['grep'], warn)
            return

        stats = recompute_stop_groups(dry_run=options['dry_run'], warn=warn)
        prefix = "[dry-run] " if options['dry_run'] else ""
        self.stdout.write(
            f"{prefix}groups: {stats['groups_total']} total "
            f"(+{stats['groups_created']} / ~{stats['groups_updated']} / -{stats['groups_deleted']}), "
            f"members: {stats['members_total']} "
            f"(assigned {stats['members_assigned']}, cleared {stats['members_cleared']})"
        )

        if options['stats']:
            self._feed_breakdown()

    def _grep(self, needle, warn):
        needle_cf = needle.casefold()
        desired = compute_desired_groups(warn=warn)
        matches = [c for c in desired if needle_cf in c['name'].casefold()]
        self.stdout.write(f"[read-only] {len(matches)} cluster(s) matching «{needle}»")
        for c in matches[:50]:
            self.stdout.write(f"• {c['name']}  ({c['member_count']} phys)  "
                              f"centroid {c['lat']:.6f},{c['lon']:.6f}")
            members = (Stop.objects.filter(id__in=c['member_ids'])
                       .select_related('agency__data_source')
                       .order_by('agency__data_source__slug', 'name'))
            for s in members:
                feed = s.agency.data_source.slug if s.agency.data_source else '?'
                self.stdout.write(f"    - [{feed}] {s.name}  lt={s.location_type}  "
                                  f"{s.location.y:.6f},{s.location.x:.6f}")
        if len(matches) > 50:
            self.stdout.write(f"  … and {len(matches) - 50} more")

    def _feed_breakdown(self):
        with connection.cursor() as cur:
            cur.execute("""
                SELECT ds.slug, COUNT(*) AS grouped_stops, COUNT(DISTINCT s.group_id) AS groups
                FROM geo_stop s
                JOIN geo_agency a ON a.id = s.agency_id
                JOIN geo_transitdatasource ds ON ds.id = a.data_source_id
                WHERE s.group_id IS NOT NULL
                GROUP BY ds.slug ORDER BY grouped_stops DESC
            """)
            rows = cur.fetchall()
        self.stdout.write("Per-feed: " + ", ".join(f"{slug}: {st} stops in {gr} groups"
                                                   for slug, st, gr in rows))
