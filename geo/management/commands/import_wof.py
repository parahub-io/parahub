"""
Import Who's On First (WoF) localities from SQLite into Place model.

Usage:
    python3 manage.py import_wof                    # Import all (~1M localities)
    python3 manage.py import_wof --country PT       # Single country
    python3 manage.py import_wof --skip-geometry     # Metadata only (fast)
    python3 manage.py import_wof --dry-run           # Count only
    python3 manage.py import_wof --fix-slugs         # Fix slug priorities by population
    python3 manage.py import_wof --fix-slugs --dry-run  # Preview fixes

SQLite source: /opt/pelias/data/portugal/whosonfirst/sqlite/whosonfirst-data-admin-latest.db
"""

import json
import sqlite3
import time

from django.contrib.gis.geos import GEOSGeometry, MultiPolygon, Point
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from geo.models import Place

WOF_DB = "/opt/pelias/data/portugal/whosonfirst/sqlite/whosonfirst-data-admin-latest.db"
BATCH_SIZE = 5000


class Command(BaseCommand):
    help = "Import WoF localities/regions/countries from SQLite into Place model"

    def add_arguments(self, parser):
        parser.add_argument("--country", help="ISO alpha-2 country code filter (e.g. PT)")
        parser.add_argument("--skip-geometry", action="store_true", help="Skip geometry import (fast)")
        parser.add_argument("--dry-run", action="store_true", help="Count only, don't import")
        parser.add_argument("--db", default=WOF_DB, help="Path to WoF SQLite DB")
        parser.add_argument(
            "--fix-slugs", action="store_true",
            help="Fix slug priorities: promote populous cities, fix wrong-CC artifacts",
        )

    def handle(self, *args, **options):
        t0 = time.time()
        db_path = options["db"]
        country_filter = options.get("country", "").upper() if options.get("country") else None
        skip_geom = options["skip_geometry"]
        dry_run = options["dry_run"]

        if options["fix_slugs"]:
            self._fix_slugs(dry_run=dry_run)
            return

        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row

        try:
            if dry_run:
                self._dry_run(conn, country_filter)
                return

            # Pre-load existing slugs into memory for dedup
            self.used_slugs = set(Place.objects.values_list("slug", flat=True))
            self.stdout.write(f"Pre-loaded {len(self.used_slugs)} existing slugs")

            # Import order: countries → regions → localities (parent FK deps)
            # Build wof_id→Place.id maps for parent resolution
            self.wof_to_place_id = {}

            # Load existing wof_id mappings
            for wof_id, pk in Place.objects.filter(wof_id__isnull=False).values_list("wof_id", "id"):
                self.wof_to_place_id[wof_id] = pk

            self._import_countries(conn, country_filter, skip_geom)
            self._import_regions(conn, country_filter, skip_geom)
            self._import_localities(conn, country_filter, skip_geom)
        finally:
            conn.close()

        elapsed = time.time() - t0
        self.stdout.write(self.style.SUCCESS(f"\nImport complete in {elapsed:.0f}s"))

    def _dry_run(self, conn, country_filter):
        """Count records by placetype."""
        where = "AND s.country = ?" if country_filter else ""
        params = (country_filter,) if country_filter else ()

        for pt in ("country", "region", "locality"):
            cur = conn.execute(
                f"SELECT COUNT(*) FROM spr s WHERE s.is_current=1 AND s.placetype=? {where}",
                (pt, *params),
            )
            count = cur.fetchone()[0]
            self.stdout.write(f"  {pt}: {count}")

    def _import_countries(self, conn, country_filter, skip_geom):
        """Import countries (place_type='country')."""
        self.stdout.write("\n[1/3] Importing countries...")
        where = "AND s.country = ?" if country_filter else ""
        params = (country_filter,) if country_filter else ()

        rows = conn.execute(
            f"""SELECT s.id, s.name, s.country, s.latitude, s.longitude
                FROM spr s
                WHERE s.is_current=1 AND s.placetype='country' {where}
                ORDER BY s.name""",
            params,
        ).fetchall()

        created = updated = 0
        for row in rows:
            wof_id = row["id"]
            cc = (row["country"] or "").upper()[:2]
            name = row["name"] or ""
            slug = self._make_slug(slugify(name) or f"country-{cc}")

            geom, center = None, None
            if not skip_geom:
                geom, center = self._load_geometry(conn, wof_id)
            if not center and row["latitude"] and row["longitude"]:
                center = Point(float(row["longitude"]), float(row["latitude"]), srid=4326)

            place, is_new = Place.objects.update_or_create(
                wof_id=wof_id,
                defaults={
                    "name": name,
                    "slug": slug,
                    "country_code": cc,
                    "place_type": "country",
                    "geometry": geom,
                    "center_point": center,
                },
            )
            self.wof_to_place_id[wof_id] = place.id
            self.used_slugs.add(slug)
            if is_new:
                created += 1
            else:
                updated += 1

        self.stdout.write(f"  Countries: {created} created, {updated} updated")

    def _import_regions(self, conn, country_filter, skip_geom):
        """Import regions (place_type='region')."""
        self.stdout.write("\n[2/3] Importing regions...")
        where = "AND s.country = ?" if country_filter else ""
        params = (country_filter,) if country_filter else ()

        rows = conn.execute(
            f"""SELECT s.id, s.name, s.country, s.parent_id, s.latitude, s.longitude
                FROM spr s
                WHERE s.is_current=1 AND s.placetype='region' {where}
                ORDER BY s.name""",
            params,
        ).fetchall()

        batch_create = []
        batch_update = []

        for row in rows:
            wof_id = row["id"]
            cc = (row["country"] or "").upper()[:2]
            name = row["name"] or ""
            base = slugify(name) or f"region-{wof_id}"
            slug = self._make_slug(f"{base}-{cc.lower()}" if cc else base)

            parent_id = self.wof_to_place_id.get(row["parent_id"])

            geom, center = None, None
            if not skip_geom:
                geom, center = self._load_geometry(conn, wof_id)
            if not center and row["latitude"] and row["longitude"]:
                center = Point(float(row["longitude"]), float(row["latitude"]), srid=4326)

            existing = Place.objects.filter(wof_id=wof_id).first()
            if existing:
                existing.name = name
                existing.slug = slug
                existing.country_code = cc
                existing.place_type = "region"
                existing.geometry = geom
                existing.center_point = center
                existing.parent_place_id = parent_id
                batch_update.append(existing)
            else:
                batch_create.append(Place(
                    wof_id=wof_id,
                    name=name,
                    slug=slug,
                    country_code=cc,
                    place_type="region",
                    geometry=geom,
                    center_point=center,
                    parent_place_id=parent_id,
                ))
            self.used_slugs.add(slug)

        if batch_create:
            Place.objects.bulk_create(batch_create, batch_size=BATCH_SIZE)
        if batch_update:
            Place.objects.bulk_update(
                batch_update,
                ["name", "slug", "country_code", "place_type", "geometry", "center_point", "parent_place_id"],
                batch_size=BATCH_SIZE,
            )

        # Refresh wof→pk map
        for wof_id, pk in Place.objects.filter(
            wof_id__isnull=False, place_type="region"
        ).values_list("wof_id", "id"):
            self.wof_to_place_id[wof_id] = pk

        self.stdout.write(f"  Regions: {len(batch_create)} created, {len(batch_update)} updated")

    def _import_localities(self, conn, country_filter, skip_geom):
        """Import localities (place_type='city') in streaming batches."""
        self.stdout.write("\n[3/3] Importing localities...")
        where = "AND s.country = ?" if country_filter else ""
        params = (country_filter,) if country_filter else ()

        # Count for progress
        total = conn.execute(
            f"SELECT COUNT(*) FROM spr s WHERE s.is_current=1 AND s.placetype='locality' {where}",
            params,
        ).fetchone()[0]
        self.stdout.write(f"  Total localities to process: {total}")

        # Build region lookup: locality wof_id → region wof_id (from ancestors table)
        self.stdout.write("  Building region lookup from ancestors table...")
        region_lookup = {}
        region_cur = conn.execute(
            f"""SELECT a.id, a.ancestor_id
                FROM ancestors a
                JOIN spr s ON s.id = a.id
                WHERE a.ancestor_placetype = 'region'
                  AND s.is_current = 1
                  AND s.placetype = 'locality'
                  {where.replace('s.country', 's.country')}""",
            params,
        )
        for r in region_cur:
            region_lookup[r["id"]] = r["ancestor_id"]
        self.stdout.write(f"  Region lookup: {len(region_lookup)} entries")

        # Build country lookup: locality wof_id → country wof_id
        country_lookup = {}
        country_cur = conn.execute(
            f"""SELECT a.id, a.ancestor_id
                FROM ancestors a
                JOIN spr s ON s.id = a.id
                WHERE a.ancestor_placetype = 'country'
                  AND s.is_current = 1
                  AND s.placetype = 'locality'
                  {where.replace('s.country', 's.country')}""",
            params,
        )
        for r in country_cur:
            country_lookup[r["id"]] = r["ancestor_id"]

        # Pre-build slug→region_slug map for slug generation
        region_slugs = {}
        for wof_id, slug in Place.objects.filter(
            place_type="region", wof_id__isnull=False
        ).values_list("wof_id", "slug"):
            region_slugs[wof_id] = slug

        # Load existing WoF places for update detection
        existing_wof_ids = set(
            Place.objects.filter(wof_id__isnull=False, place_type="city")
            .values_list("wof_id", flat=True)
        )

        cursor = conn.execute(
            f"""SELECT s.id, s.name, s.country, s.parent_id, s.latitude, s.longitude
                FROM spr s
                WHERE s.is_current=1 AND s.placetype='locality' {where}
                ORDER BY s.id""",
            params,
        )

        batch_create = []
        batch_update_ids = []  # (wof_id, defaults_dict) for bulk update
        created = updated = 0
        processed = 0

        while True:
            rows = cursor.fetchmany(BATCH_SIZE)
            if not rows:
                break

            # Batch-load geometries for this chunk
            wof_ids_in_batch = [r["id"] for r in rows]
            geom_map = {}
            if not skip_geom:
                geom_map = self._load_geometries_batch(conn, wof_ids_in_batch)

            for row in rows:
                wof_id = row["id"]
                cc = (row["country"] or "").upper()[:2]
                name = row["name"] or ""

                # Resolve parent: prefer region from ancestors, fallback to parent_id
                region_wof = region_lookup.get(wof_id)
                parent_id = self.wof_to_place_id.get(region_wof) if region_wof else None
                if not parent_id:
                    parent_id = self.wof_to_place_id.get(row["parent_id"])

                # Slug generation with region context
                region_slug = region_slugs.get(region_wof, "") if region_wof else ""
                slug = self._make_locality_slug(name, cc, region_slug)

                geom, center = geom_map.get(wof_id, (None, None))
                if not center and row["latitude"] and row["longitude"]:
                    center = Point(float(row["longitude"]), float(row["latitude"]), srid=4326)

                # Population from geojson properties
                pop = geom_map.get(f"{wof_id}_pop")

                if wof_id in existing_wof_ids:
                    batch_update_ids.append((wof_id, {
                        "name": name,
                        "slug": slug,
                        "country_code": cc,
                        "place_type": "city",
                        "geometry": geom,
                        "center_point": center,
                        "parent_place_id": parent_id,
                        "population": pop,
                    }))
                    updated += 1
                else:
                    batch_create.append(Place(
                        wof_id=wof_id,
                        name=name,
                        slug=slug,
                        country_code=cc,
                        place_type="city",
                        geometry=geom,
                        center_point=center,
                        parent_place_id=parent_id,
                        population=pop,
                    ))
                    created += 1
                self.used_slugs.add(slug)

            # Flush creates
            if len(batch_create) >= BATCH_SIZE:
                Place.objects.bulk_create(batch_create, batch_size=BATCH_SIZE)
                batch_create.clear()

            # Flush updates (individual update_or_create is too slow for 1M)
            if len(batch_update_ids) >= BATCH_SIZE:
                self._flush_updates(batch_update_ids)
                batch_update_ids.clear()

            processed += len(rows)
            if processed % 50000 == 0:
                self.stdout.write(f"  Processed {processed}/{total} ({processed*100//total}%)")

        # Final flush
        if batch_create:
            Place.objects.bulk_create(batch_create, batch_size=BATCH_SIZE)
        if batch_update_ids:
            self._flush_updates(batch_update_ids)

        self.stdout.write(f"  Localities: {created} created, {updated} updated")

    def _flush_updates(self, batch_update_ids):
        """Update existing places by wof_id."""
        wof_ids = [item[0] for item in batch_update_ids]
        existing = {p.wof_id: p for p in Place.objects.filter(wof_id__in=wof_ids)}
        to_save = []
        for wof_id, defaults in batch_update_ids:
            place = existing.get(wof_id)
            if not place:
                continue
            for k, v in defaults.items():
                setattr(place, k, v)
            to_save.append(place)
        if to_save:
            Place.objects.bulk_update(
                to_save,
                ["name", "slug", "country_code", "place_type", "geometry",
                 "center_point", "parent_place_id", "population"],
                batch_size=BATCH_SIZE,
            )

    def _make_slug(self, base):
        """Generate a unique slug from base, appending -N if needed."""
        base = base[:190]
        slug = base
        counter = 2
        while slug in self.used_slugs:
            slug = f"{base}-{counter}"
            counter += 1
        return slug

    def _make_locality_slug(self, name, cc, region_slug):
        """Slug generation for localities with progressive disambiguation."""
        base = slugify(name) or f"loc-{hash(name) % 100000}"
        base = base[:150]

        # Try: name
        if base not in self.used_slugs:
            return base
        # Try: name-cc
        candidate = f"{base}-{cc.lower()}" if cc else base
        if candidate not in self.used_slugs:
            return candidate
        # Try: name-region-cc
        if region_slug:
            # Strip -cc suffix from region slug if present (e.g. "lisboa-pt" → "lisboa")
            reg_short = region_slug.rsplit(f"-{cc.lower()}", 1)[0] if cc else region_slug
            candidate = f"{base}-{reg_short}-{cc.lower()}"[:190]
            if candidate not in self.used_slugs:
                return candidate
        # Fallback: name-region-cc-N
        fallback_base = candidate if region_slug else f"{base}-{cc.lower()}"
        fallback_base = fallback_base[:185]
        counter = 2
        slug = f"{fallback_base}-{counter}"
        while slug in self.used_slugs:
            counter += 1
            slug = f"{fallback_base}-{counter}"
        return slug

    def _fix_slugs(self, dry_run=False):
        """Promote populous cities to prime slugs, fix wrong-CC artifacts.

        Phase 1: For each city name shared by multiple cities, promote the most
        populous one to the shortest slug (e.g. 'moscow' → Moscow RU, not Moscow KS).
        Phase 2: Fix swap losers and any city whose slug embeds a foreign CC
        (e.g. US city with '-ru' suffix).
        """
        from collections import defaultdict

        from django.db import connection

        self.stdout.write("[fix-slugs] Loading cities...")
        cities = {}
        for pk, name, slug, cc, pop, parent_name in Place.objects.filter(
            place_type="city"
        ).exclude(slug="").values_list(
            "id", "name", "slug", "country_code", "population", "parent_place__name"
        ):
            base = slugify(name)
            if not base:
                continue
            cities[pk] = {
                "base": base,
                "slug": slug,
                "cc": (cc or "").lower(),
                "pop": pop or 0,
                "parent_name": parent_name or "",
            }

        # Group by base name
        groups = defaultdict(list)
        for pk, info in cities.items():
            groups[info["base"]].append(pk)

        used_slugs = set(Place.objects.exclude(slug="").values_list("slug", flat=True))
        needs_fix = {}  # pk → 'promote' | 'demote' | 'wrong_cc'

        # ---- Phase 1: Population promotions ----
        for base, pks in groups.items():
            if len(pks) < 2:
                continue
            pks_sorted = sorted(pks, key=lambda pk: -cities[pk]["pop"])
            winner = cities[pks_sorted[0]]
            if winner["pop"] == 0 or winner["slug"] == base:
                continue
            # Who currently holds the prime slug?
            holder_pk = next((pk for pk in pks if cities[pk]["slug"] == base), None)
            if not holder_pk:
                continue
            if winner["pop"] <= cities[holder_pk]["pop"] * 5:
                continue
            needs_fix[pks_sorted[0]] = "promote"
            needs_fix[holder_pk] = "demote"

        # ---- Phase 2: Wrong-CC detection ----
        for pk, info in cities.items():
            if pk in needs_fix or not info["cc"]:
                continue
            suffix = info["slug"][len(info["base"]):]
            parts = suffix.strip("-").split("-") if suffix.strip("-") else []
            for i, part in enumerate(parts):
                if len(part) == 2 and part.isalpha() and part != info["cc"]:
                    is_last = i == len(parts) - 1 or (
                        i == len(parts) - 2 and parts[-1].isdigit()
                    )
                    if is_last:
                        needs_fix[pk] = "wrong_cc"
                        break

        n_promote = sum(1 for v in needs_fix.values() if v == "promote")
        n_demote = sum(1 for v in needs_fix.values() if v == "demote")
        n_wrong = sum(1 for v in needs_fix.values() if v == "wrong_cc")
        self.stdout.write(
            f"  Promotions: {n_promote}, Demotions: {n_demote}, Wrong-CC: {n_wrong}"
        )

        if not needs_fix:
            self.stdout.write(self.style.SUCCESS("No fixes needed"))
            return

        # ---- Phase 3: Regenerate slugs ----
        # Free all affected slugs first
        for pk in needs_fix:
            used_slugs.discard(cities[pk]["slug"])

        new_slugs = {}
        # Process promotions first (they claim prime slugs), then rest by pop DESC
        order = sorted(
            needs_fix.keys(),
            key=lambda pk: (0 if needs_fix[pk] == "promote" else 1, -cities[pk]["pop"]),
        )

        for pk in order:
            info = cities[pk]
            base, cc = info["base"], info["cc"]
            parent_name = info["parent_name"]

            if needs_fix[pk] == "promote" and base not in used_slugs:
                new_slugs[pk] = base
                used_slugs.add(base)
                continue

            # Standard disambiguation: base → base-cc → base-region-cc → base-region-cc-N
            candidates = []
            if base not in used_slugs:
                candidates.append(base)
            if cc:
                candidates.append(f"{base}-{cc}")
            if parent_name:
                reg = slugify(parent_name)
                if reg:
                    candidates.append(f"{base}-{reg}-{cc}")
                    for n in range(2, 500):
                        candidates.append(f"{base}-{reg}-{cc}-{n}")
            else:
                for n in range(2, 500):
                    candidates.append(f"{base}-{cc}-{n}" if cc else f"{base}-{n}")

            new_slug = next((c for c in candidates if c not in used_slugs), None)
            if new_slug:
                new_slugs[pk] = new_slug
                used_slugs.add(new_slug)
            else:
                self.stderr.write(f"  FAILED: {info['slug']} ({base}, {cc})")

        # Show preview
        for pk, new_slug in sorted(new_slugs.items(), key=lambda x: x[1])[:20]:
            old = cities[pk]["slug"]
            self.stdout.write(f"  {old:45s} -> {new_slug}")
        if len(new_slugs) > 20:
            self.stdout.write(f"  ... and {len(new_slugs) - 20} more")

        if dry_run:
            self.stdout.write(self.style.WARNING(f"Dry run: {len(new_slugs)} fixes"))
            return

        # ---- Phase 4: Apply via temp slugs (avoid unique constraint) ----
        with connection.cursor() as cur:
            for pk, new_slug in new_slugs.items():
                cur.execute(
                    "UPDATE geo_place SET slug = %s WHERE id = %s",
                    [f"__fix__{new_slug}", pk],
                )
            for pk, new_slug in new_slugs.items():
                cur.execute(
                    "UPDATE geo_place SET slug = %s WHERE id = %s", [new_slug, pk]
                )
        self.stdout.write(self.style.SUCCESS(f"Fixed {len(new_slugs)} slugs"))

    def _load_geometry(self, conn, wof_id):
        """Load geometry for a single WoF record. Returns (MultiPolygon|None, Point|None)."""
        row = conn.execute(
            "SELECT body FROM geojson WHERE id=? AND is_alt=0", (wof_id,)
        ).fetchone()
        if not row or not row["body"]:
            return None, None
        return self._parse_geojson(row["body"])

    def _load_geometries_batch(self, conn, wof_ids):
        """Load geometries for a batch of WoF IDs. Returns {wof_id: (geom, center), wof_id_pop: population}."""
        if not wof_ids:
            return {}
        result = {}
        placeholders = ",".join("?" * len(wof_ids))
        cur = conn.execute(
            f"SELECT id, body FROM geojson WHERE id IN ({placeholders}) AND is_alt=0",
            wof_ids,
        )
        for row in cur:
            wof_id = row["id"]
            body = row["body"]
            if not body:
                continue
            geom, center = self._parse_geojson(body)
            result[wof_id] = (geom, center)
            # Extract population
            try:
                data = json.loads(body)
                props = data.get("properties", {})
                pop = props.get("wof:population")
                if pop and int(pop) > 0:
                    result[f"{wof_id}_pop"] = int(pop)
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
        return result

    def _parse_geojson(self, body_str):
        """Parse GeoJSON Feature body → (MultiPolygon|None, Point|None)."""
        try:
            data = json.loads(body_str)
            geom_data = data.get("geometry")
            if not geom_data:
                return None, None

            gtype = geom_data.get("type")
            geos_geom = GEOSGeometry(json.dumps(geom_data), srid=4326)

            center = None
            props = data.get("properties", {})
            lbl_lat = props.get("lbl:latitude") or props.get("geom:latitude")
            lbl_lon = props.get("lbl:longitude") or props.get("geom:longitude")
            if lbl_lat and lbl_lon:
                center = Point(float(lbl_lon), float(lbl_lat), srid=4326)

            if gtype == "Point":
                # Point-only: no polygon geometry, just center
                if not center:
                    center = geos_geom
                return None, center
            elif gtype == "Polygon":
                # Wrap Polygon → MultiPolygon
                multi = MultiPolygon(geos_geom, srid=4326)
                if not center:
                    center = multi.centroid
                    center.srid = 4326
                return multi, center
            elif gtype == "MultiPolygon":
                if not center:
                    center = geos_geom.centroid
                    center.srid = 4326
                return geos_geom, center
            else:
                return None, center
        except Exception:
            return None, None
