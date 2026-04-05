"""
Import juntas de freguesia from OpenStreetMap via Overpass API.

Usage:
    python3 manage.py import_freguesias                          # All Portugal
    python3 manage.py import_freguesias --bbox 41.5,-8.9,42.2,-8.1  # Viana do Castelo
    python3 manage.py import_freguesias --bbox 41.95,-8.55,42.15,-8.2  # Monção area
    python3 manage.py import_freguesias --reset                  # Delete all imported + reimport
    python3 manage.py import_freguesias --dry-run                # Preview without creating
"""

import json
import urllib.request
import urllib.parse
from django.core.management.base import BaseCommand
from django.contrib.gis.geos import Point
from geo.models import Establishment
from identity.models import Profile
from taxonomy.models import Category


OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Portugal bounding box (generous) — reject Overpass results outside this
PT_BBOX = (36.8, -9.6, 42.3, -6.0)  # south, west, north, east

# Overpass query template — {area_filter} is either area or bbox
QUERY_BBOX = """
[out:json][timeout:120];
(
  nwr["office"="government"]["government"="parish_council"]{bbox};
  nwr["amenity"="townhall"]["name"~"Junta de Freguesia",i]{bbox};
  nwr["office"="government"]["name"~"Junta de Freguesia",i]{bbox};
  nwr["amenity"="townhall"]["name"~"União de Freguesias",i]{bbox};
);
out center;
"""

QUERY_COUNTRY = """
[out:json][timeout:120];
area["ISO3166-1"="PT"]->.pt;
(
  nwr["office"="government"]["government"="parish_council"](area.pt);
  nwr["amenity"="townhall"]["name"~"Junta de Freguesia",i](area.pt);
  nwr["office"="government"]["name"~"Junta de Freguesia",i](area.pt);
  nwr["amenity"="townhall"]["name"~"União de Freguesias",i](area.pt);
);
out center;
"""

# Tag used to identify imported establishments for --reset
IMPORT_TAG = "overpass_freguesia_import"


class Command(BaseCommand):
    help = "Import juntas de freguesia from OpenStreetMap Overpass API as Establishments"

    def add_arguments(self, parser):
        parser.add_argument(
            "--bbox",
            help="Bounding box: south,west,north,east (e.g. 41.95,-8.55,42.15,-8.2)",
        )
        parser.add_argument(
            "--reset", action="store_true",
            help="Delete previously imported freguesias before reimporting",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Preview results without creating anything",
        )
        parser.add_argument(
            "--owner",
            default="norn",
            help="Username of the owner profile (default: norn)",
        )

    def handle(self, **options):
        # Resolve owner
        try:
            owner = Profile.objects.get(account__username=options["owner"])
        except Profile.DoesNotExist:
            self.stderr.write(f"Profile not found for username: {options['owner']}")
            return

        # Resolve category
        try:
            category = Category.objects.get(slug="parish-council")
        except Category.DoesNotExist:
            self.stderr.write("Category 'parish-council' not found. Create it first.")
            return

        # Reset if requested
        if options["reset"]:
            qs = Establishment.objects.filter(
                category=category,
                attributes__import_source=IMPORT_TAG,
            )
            count = qs.count()
            if not options["dry_run"]:
                qs.delete()
            self.stdout.write(f"Deleted {count} previously imported freguesias")

        # Build Overpass query
        if options["bbox"]:
            parts = options["bbox"].split(",")
            if len(parts) != 4:
                self.stderr.write("bbox must be: south,west,north,east")
                return
            bbox_str = f"({parts[0]},{parts[1]},{parts[2]},{parts[3]})"
            query = QUERY_BBOX.replace("{bbox}", bbox_str)
        else:
            query = QUERY_COUNTRY

        # Fetch from Overpass
        self.stdout.write("Fetching from Overpass API...")
        data = urllib.request.urlopen(
            urllib.request.Request(
                OVERPASS_URL,
                data=urllib.parse.urlencode({"data": query}).encode(),
                headers={"User-Agent": "Parahub/1.0 (import_freguesias)"},
            ),
            timeout=180,
        )
        result = json.loads(data.read())
        elements = result.get("elements", [])
        self.stdout.write(f"Got {len(elements)} elements from Overpass")

        if not elements:
            self.stdout.write("Nothing found. Try a different bbox or check Overpass.")
            return

        created = 0
        skipped = 0

        for el in elements:
            # Get coordinates (center for ways/relations, direct for nodes)
            if el["type"] == "node":
                lat, lon = el["lat"], el["lon"]
            elif "center" in el:
                lat, lon = el["center"]["lat"], el["center"]["lon"]
            else:
                skipped += 1
                continue

            # Reject coordinates outside Portugal (Overpass area filter isn't perfect)
            s, w, n, e = PT_BBOX
            if not (s <= lat <= n and w <= lon <= e):
                skipped += 1
                continue

            tags = el.get("tags", {})
            name = tags.get("name", "")
            if not name:
                name = tags.get("official_name", "")
            if not name:
                skipped += 1
                continue

            osm_id = f"{el['type']}/{el['id']}"

            # Check for duplicate by OSM ID in attributes
            if Establishment.objects.filter(
                category=category,
                attributes__osm_id=osm_id,
            ).exists():
                skipped += 1
                continue

            if options["dry_run"]:
                self.stdout.write(f"  [DRY] {name} ({lat:.5f}, {lon:.5f}) — {osm_id}")
                created += 1
                continue

            # Extract useful OSM tags
            phone = tags.get("phone", tags.get("contact:phone", ""))
            email = tags.get("email", tags.get("contact:email", ""))
            website = tags.get("website", tags.get("contact:website", ""))
            addr_street = tags.get("addr:street", "")
            addr_number = tags.get("addr:housenumber", "")
            addr_city = tags.get("addr:city", "")
            addr_postcode = tags.get("addr:postcode", "")

            opening_hours_raw = tags.get("opening_hours", "")
            opening_hours = {"raw": opening_hours_raw} if opening_hours_raw else {}

            Establishment.objects.create(
                name=name,
                owner=owner,
                category=category,
                organization_type="GOVERNMENT",
                location=Point(lon, lat, srid=4326),
                phone=phone,
                email=email,
                website=website,
                opening_hours=opening_hours,
                is_verified=False,
                is_active=True,
                attributes={
                    "import_source": IMPORT_TAG,
                    "osm_id": osm_id,
                    "addr_street": addr_street,
                    "addr_number": addr_number,
                    "addr_city": addr_city,
                    "addr_postcode": addr_postcode,
                },
            )
            created += 1

        action = "Would create" if options["dry_run"] else "Created"
        self.stdout.write(f"{action} {created} freguesias, skipped {skipped}")
