"""
Generate URL-friendly slugs for transit stops and routes.

Usage:
    python3 manage.py generate_transit_slugs
    python3 manage.py generate_transit_slugs --assign-orphans
"""

from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import connection
from django.utils.text import slugify

from geo.models import Place, Route, Stop


class Command(BaseCommand):
    help = "Generate URL slugs for transit stops and routes (per-place unique)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--assign-orphans", action="store_true",
            help="Assign stops/routes without a place to the nearest Place first",
        )
        parser.add_argument(
            "--force", action="store_true",
            help="Regenerate all slugs (not just empty ones)",
        )

    def handle(self, *args, **options):
        if options["assign_orphans"]:
            self._assign_orphans()

        self._generate_stop_slugs(force=options["force"])
        self._generate_route_slugs(force=options["force"])

    def _assign_orphans(self):
        """Assign stops/routes without a place to the nearest Place."""
        self.stdout.write("\nAssigning orphan stops to nearest Place...")
        with connection.cursor() as c:
            c.execute("""
                UPDATE geo_stop s SET place_id = (
                    SELECT p.id FROM geo_place p
                    WHERE p.slug != '' AND p.center_point IS NOT NULL
                    ORDER BY s.location::geometry <-> p.center_point::geometry LIMIT 1
                ) WHERE s.place_id IS NULL
            """)
            self.stdout.write(f"  Assigned {c.rowcount} orphan stops")

        self.stdout.write("Assigning orphan routes to nearest Place...")
        with connection.cursor() as c:
            c.execute("""
                UPDATE geo_route r SET place_id = sub.place_id
                FROM (
                    SELECT rs.route_id, s.place_id,
                           ROW_NUMBER() OVER (PARTITION BY rs.route_id ORDER BY COUNT(*) DESC) as rn
                    FROM geo_routestop rs
                    JOIN geo_stop s ON s.id = rs.stop_id
                    WHERE s.place_id IS NOT NULL
                    GROUP BY rs.route_id, s.place_id
                ) sub
                WHERE r.id = sub.route_id AND sub.rn = 1 AND r.place_id IS NULL
            """)
            self.stdout.write(f"  Assigned {c.rowcount} orphan routes")

        # Update cached counts
        with connection.cursor() as c:
            c.execute("""
                UPDATE geo_place p
                SET transit_stops_count = COALESCE(sc.cnt, 0),
                    transit_routes_count = COALESCE(rc.cnt, 0)
                FROM (SELECT place_id, COUNT(*) cnt FROM geo_stop WHERE place_id IS NOT NULL GROUP BY place_id) sc
                FULL OUTER JOIN (SELECT place_id, COUNT(*) cnt FROM geo_route WHERE place_id IS NOT NULL GROUP BY place_id) rc
                    ON sc.place_id = rc.place_id
                WHERE p.id = COALESCE(sc.place_id, rc.place_id)
                  AND p.slug != ''
            """)
            self.stdout.write(f"  Updated cached counts on {c.rowcount} places")

    def _generate_stop_slugs(self, force=False):
        """Generate slugs for stops, grouped by place."""
        self.stdout.write("\nGenerating stop slugs...")

        qs = Stop.objects.filter(place__isnull=False).select_related("place")
        if not force:
            qs = qs.filter(slug="")

        stops_by_place = defaultdict(list)
        for s in qs.order_by("place_id", "source_id"):
            stops_by_place[s.place_id].append(s)

        total = 0
        for place_id, stops in stops_by_place.items():
            # Load existing slugs for this place to avoid collisions
            existing_slugs = set(
                Stop.objects.filter(place_id=place_id)
                .exclude(slug="")
                .values_list("slug", flat=True)
            ) if not force else set()

            used = set(existing_slugs)
            to_update = []

            for s in stops:
                base = slugify(s.name) or f"stop-{s.source_id}"
                base = base[:140]  # Leave room for suffix
                slug = base
                counter = 2
                while slug in used:
                    slug = f"{base}-{counter}"
                    counter += 1
                used.add(slug)
                s.slug = slug
                to_update.append(s)

            if to_update:
                Stop.objects.bulk_update(to_update, ["slug"], batch_size=5000)
                total += len(to_update)

        self.stdout.write(self.style.SUCCESS(f"  Generated slugs for {total} stops"))

    def _generate_route_slugs(self, force=False):
        """Generate slugs for routes, grouped by place."""
        self.stdout.write("\nGenerating route slugs...")

        qs = Route.objects.filter(place__isnull=False).select_related("place")
        if not force:
            qs = qs.filter(slug="")

        routes_by_place = defaultdict(list)
        for r in qs.order_by("place_id", "source_id"):
            routes_by_place[r.place_id].append(r)

        total = 0
        for place_id, routes in routes_by_place.items():
            existing_slugs = set(
                Route.objects.filter(place_id=place_id)
                .exclude(slug="")
                .values_list("slug", flat=True)
            ) if not force else set()

            used = set(existing_slugs)
            to_update = []

            for r in routes:
                base = slugify(r.short_name) or f"route-{r.source_id}"
                base = base[:90]  # Leave room for suffix
                slug = base
                counter = 2
                while slug in used:
                    slug = f"{base}-{counter}"
                    counter += 1
                used.add(slug)
                r.slug = slug
                to_update.append(r)

            if to_update:
                Route.objects.bulk_update(to_update, ["slug"], batch_size=5000)
                total += len(to_update)

        self.stdout.write(self.style.SUCCESS(f"  Generated slugs for {total} routes"))
