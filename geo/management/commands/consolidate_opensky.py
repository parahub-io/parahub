"""
Split-merge consolidation of an OpenSky mission cluster into one seamless
super-tile (Phase 2 — see PK/opensky-system.md § Consolidation).

Joint ODM reconstruction of all members' photos removes the affine seam that
per-mission 2D consensus cannot. The consolidation is itself an OpenSkyMission
row (is_consolidation=True) that overrides its members in latest/; members keep
their tiles/orthos and point back via superseded_by, so it can be rolled back by
deleting the consolidation.

Usage:
  # explicit member set (recommended for the first runs — bounded size)
  python manage.py consolidate_opensky --missions=ULID1,ULID2,ULID3

  # expand the connected ORB-overlap component from an anchor mission
  python manage.py consolidate_opensky --cluster=ULID --dry-run

  # re-run an existing (failed/interrupted) consolidation, resuming its scratch:
  # pooling is skipped if all photos are in place, ODM skips completed stages
  python manage.py consolidate_opensky --retry=CONSOLIDATION_ULID --no-split

Run as a transient systemd unit (multi-hour GPU job) — see
gotcha-session-freeze-background-jobs.
"""
import logging
import re
import sys

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

logger = logging.getLogger('opensky')


class Command(BaseCommand):
    help = 'Split-merge consolidate an OpenSky mission cluster into one seamless super-tile'

    def add_arguments(self, parser):
        parser.add_argument('--missions', type=str,
                            help='Comma-separated member mission ULIDs (explicit cluster)')
        parser.add_argument('--cluster', type=str,
                            help='Anchor mission ULID — expand to its connected ORB-overlap component')
        parser.add_argument('--retry', type=str,
                            help='Existing consolidation ULID to re-run — reuses its member set and '
                                 'resumes the scratch dir (skips re-pooling and completed ODM stages)')
        parser.add_argument('--max-photos', type=int, default=None,
                            help='Override the photo-count cap (default MAX_CONSOLIDATION_PHOTOS)')
        parser.add_argument('--no-split', action='store_true',
                            help='Single global reconstruction (no ODM submodels) — avoids submodel-merge misalignment; needs RAM+swap >= ~65MB x photos at pc-quality high')
        parser.add_argument('--gps-accuracy', type=float, default=None,
                            help='Override ODM --gps-accuracy (default 3m). For cross-season clusters '
                                 'raise to ~30m so feature matches weld per-flight GPS-bias blocks '
                                 'instead of BA pinning each flight to its biased coords (run-5b fix)')
        parser.add_argument('--dry-run', action='store_true',
                            help='Show the member set, union bounds and photo count; change nothing')

    def _expand_cluster(self, anchor_id):
        """Connected component of anchor over ORB_PAIR pose edges, restricted to
        PUBLISHED non-consolidation missions."""
        from geo.models import OpenSkyMission, OpenSkyPoseEdge
        seen = {anchor_id}
        frontier = [anchor_id]
        while frontier:
            cur = frontier.pop()
            edges = OpenSkyPoseEdge.objects.filter(
                edge_type=OpenSkyPoseEdge.EdgeType.ORB_PAIR
            ).filter(Q(mission_a_id=cur) | Q(mission_b_id=cur))
            for e in edges:
                for nid in (e.mission_a_id, e.mission_b_id):
                    if not nid or nid in seen:
                        continue
                    m = OpenSkyMission.objects.filter(
                        id=nid, is_consolidation=False,
                        status=OpenSkyMission.Status.PUBLISHED,
                    ).first()
                    if m:
                        seen.add(nid)
                        frontier.append(nid)
        return seen

    def handle(self, *args, **options):
        from geo.models import OpenSkyMission, OpenSkyConsolidationMember
        from geo.opensky_processor import (
            process_consolidation, opensky_tile_lock,
            MAX_CONSOLIDATION_PHOTOS,
        )

        dry_run = options['dry_run']
        max_photos = options['max_photos'] or MAX_CONSOLIDATION_PHOTOS

        # --- Resolve member set ---
        if options['retry'] and (options['missions'] or options['cluster']):
            self.stderr.write(self.style.ERROR(
                "--retry takes its member set from the existing consolidation; drop --missions/--cluster"))
            return

        consolidation = None
        if options['retry']:
            consolidation = OpenSkyMission.objects.filter(
                id=options['retry'].strip(), is_consolidation=True).first()
            if not consolidation:
                self.stderr.write(self.style.ERROR(f"Consolidation {options['retry']} not found"))
                return
            ids = [l.member_id for l in consolidation.members.order_by('order')]
            if not ids:
                self.stderr.write(self.style.ERROR(f"Consolidation {consolidation.id} has no members"))
                return
        elif options['missions']:
            ids = [s.strip() for s in options['missions'].split(',') if s.strip()]
        elif options['cluster']:
            anchor = options['cluster'].strip()
            if not OpenSkyMission.objects.filter(id=anchor).exists():
                self.stderr.write(self.style.ERROR(f"Anchor mission {anchor} not found"))
                return
            ids = sorted(self._expand_cluster(anchor))
            self.stdout.write(f"Cluster from {anchor[:8]}: {len(ids)} missions")
        else:
            self.stderr.write(self.style.ERROR("Provide --missions=... or --cluster=..."))
            return

        members = list(OpenSkyMission.objects.filter(id__in=ids).order_by('uploaded_at'))
        found_ids = {m.id for m in members}
        missing = [i for i in ids if i not in found_ids]
        if missing:
            self.stderr.write(self.style.ERROR(f"Missions not found: {missing}"))
            return
        if len(members) < 2:
            self.stderr.write(self.style.ERROR("Need >= 2 members to consolidate"))
            return

        # --- Validate ---
        problems = []
        for m in members:
            if m.is_consolidation:
                problems.append(f"{m.id[:8]} is itself a consolidation")
            if m.status != OpenSkyMission.Status.PUBLISHED:
                problems.append(f"{m.id[:8]} is {m.status}, not PUBLISHED")
            if m.superseded_by_id and not (consolidation and m.superseded_by_id == consolidation.id):
                problems.append(f"{m.id[:8]} already in consolidation {m.superseded_by_id[:8]} — delete it first")
        if problems:
            for p in problems:
                self.stderr.write(self.style.ERROR(p))
            return

        total_photos = sum(m.source_photos_count for m in members)
        self.stdout.write(
            f"Members: {len(members)} | photos: {total_photos} (cap {max_photos})"
        )
        for i, m in enumerate(members):
            self.stdout.write(f"  m{i:02d}_  {m.id}  {m.name or ''}  {m.source_photos_count}ph  {m.place_label}")

        if total_photos > max_photos:
            self.stderr.write(self.style.ERROR(
                f"Cluster has {total_photos} photos > cap {max_photos}. "
                f"Scope it down with --missions or raise --max-photos (watch disk/RAM)."))
            return

        if dry_run:
            self.stdout.write(self.style.SUCCESS("[DRY RUN] would consolidate the above; nothing changed"))
            return

        # --- Create the consolidation record + membership, then run under lock ---
        if consolidation is None:
            consolidation = OpenSkyMission.objects.create(
                is_consolidation=True,
                status=OpenSkyMission.Status.QUEUED,
                name=f"Consolidation of {len(members)} missions",
                source_photos_count=total_photos,
            )
            for i, m in enumerate(members):
                OpenSkyConsolidationMember.objects.create(
                    consolidation=consolidation, member=m, prefix=f"m{i:02d}_", order=i,
                )
            self.stdout.write(f"Created consolidation {consolidation.id}")
        else:
            self.stdout.write(
                f"Retrying consolidation {consolidation.id} (was {consolidation.status}; resuming scratch)")

        # Block on the shared tile lock so we never race the per-mission processor
        # (it try-locks and skips its tick while we hold this).
        self.stdout.write("Acquiring OpenSky tile lock (waits for any in-flight mission)...")
        with opensky_tile_lock(blocking=True):
            ok = process_consolidation(consolidation.id, no_split=options['no_split'],
                                       resume=bool(options['retry']),
                                       gps_accuracy=options['gps_accuracy'])

        if ok:
            self.stdout.write(self.style.SUCCESS(
                f"Consolidation {consolidation.id} PUBLISHED — {len(members)} missions merged"))
        else:
            consolidation.refresh_from_db()
            err = consolidation.error_message or ''
            if re.search(r'exit status 255|timed out after', err):
                # Transport-level death (tunnel flap / skystore reboot): exit 75
                # (EX_TEMPFAIL) so a unit with Restart=on-failure relaunches us
                # (--retry resumes scratch + re-adopts a running ODM container),
                # while RestartPreventExitStatus=1 keeps real failures parked.
                self.stderr.write(self.style.ERROR(
                    f"Consolidation {consolidation.id} transient transport failure "
                    f"(exit 75, retryable): {err[:200]}"))
                sys.exit(75)
            # CommandError → exit code 1: permanent failure (e.g. verification
            # gate) — needs diagnosis, not a blind retry
            raise CommandError(
                f"Consolidation {consolidation.id} FAILED — see logs; members untouched")
