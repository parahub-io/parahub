"""
Import UAS geographical zones (drone no-fly / restricted airspace) into DroneZone.

Source: ANAC (Autoridade Nacional da Aviacao Civil, Portugal) publishes the national
geozones in EUROCAE ED-269 format as a single static JS file used by their public map.
The file assigns `data = {...}`; we strip the prefix and parse the JSON.

Each ED-269 feature may carry several geometry segments, each with its own vertical
band; we store one DroneZone row per segment to keep altitude limits precise.
Circles are buffered to geodesic polygons. The whole source is reloaded on each run
(small, version-stamped dataset), so there is no per-row upsert.

Usage:
    python3 manage.py import_drone_zones                 # fetch + load if version changed
    python3 manage.py import_drone_zones --force         # reload even if version unchanged
    python3 manage.py import_drone_zones --dry-run        # parse + report, write nothing
    python3 manage.py import_drone_zones --file PATH      # load from a local file instead of URL
"""

import json
import math
import re
import urllib.request

from django.contrib.gis.geos import GEOSGeometry, MultiPolygon, Polygon
from django.core.management.base import BaseCommand
from django.db import transaction

from geo.models import DroneZone

ANAC_URL = "https://dnt.anac.pt/mapa_UASZoneVersion.js"
SOURCE_KEY = "anac_pt"
USER_AGENT = "Parahub/1.0 (import_drone_zones)"
CIRCLE_SEGMENTS = 64
EARTH_R = 6371000.0
FT_TO_M = 0.3048


def _fetch(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def _parse_payload(text):
    """Strip the leading `data =` assignment and parse the JSON object."""
    text = text.strip()
    eq = text.index("=")
    body = text[eq + 1:].strip()
    if body.endswith(";"):
        body = body[:-1]
    return json.loads(body)


def _circle_polygon(center, radius_m, segments=CIRCLE_SEGMENTS):
    """Geodesic circle as a closed [lng,lat] ring buffered from center+radius."""
    lng0, lat0 = center[0], center[1]
    phi1 = math.radians(lat0)
    lam1 = math.radians(lng0)
    delta = radius_m / EARTH_R
    ring = []
    for i in range(segments):
        theta = math.radians(360.0 * i / segments)
        phi2 = math.asin(
            math.sin(phi1) * math.cos(delta)
            + math.cos(phi1) * math.sin(delta) * math.cos(theta)
        )
        lam2 = lam1 + math.atan2(
            math.sin(theta) * math.sin(delta) * math.cos(phi1),
            math.cos(delta) - math.sin(phi1) * math.sin(phi2),
        )
        ring.append([math.degrees(lam2), math.degrees(phi2)])
    ring.append(ring[0])  # close
    return Polygon(ring)


def _close_ring(ring):
    if ring and ring[0] != ring[-1]:
        ring = ring + [ring[0]]
    return ring


def _segment_geometry(hp):
    """Build a GEOS Polygon (lng/lat, SRID 4326) from an ED-269 horizontalProjection."""
    gtype = hp.get("type")
    if gtype == "Circle":
        center = hp["center"]
        radius = float(hp["radius"])
        return _circle_polygon(center, radius)
    if gtype == "Polygon":
        rings = [_close_ring(r) for r in hp["coordinates"]]
        geom = GEOSGeometry(json.dumps({"type": "Polygon", "coordinates": rings}), srid=4326)
        return geom
    raise ValueError(f"Unsupported horizontalProjection type: {gtype}")


def _to_metres(value, uom):
    if value is None:
        return None
    v = float(value)
    return v * FT_TO_M if (uom or "").upper() == "FT" else v


class Command(BaseCommand):
    help = "Import ANAC drone geographical zones (ED-269) into DroneZone"

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Reload even if version unchanged")
        parser.add_argument("--dry-run", action="store_true", help="Parse and report; write nothing")
        parser.add_argument("--file", help="Load from a local ED-269 JS file instead of the URL")

    def handle(self, *args, **opts):
        if opts.get("file"):
            with open(opts["file"], "r", encoding="utf-8") as fh:
                text = fh.read()
            self.stdout.write(f"Loaded {len(text)} bytes from {opts['file']}")
        else:
            text = _fetch(ANAC_URL)
            self.stdout.write(f"Fetched {len(text)} bytes from {ANAC_URL}")

        payload = _parse_payload(text)
        features = payload.get("features", [])
        desc = payload.get("description", "") or ""
        m = re.search(r"(\d{6,})", desc)
        version = m.group(1) if m else desc[:64]
        self.stdout.write(f"Title: {payload.get('title', '')}")
        self.stdout.write(f"Version: {version}  Features: {len(features)}")

        current = (
            DroneZone.objects.filter(source=SOURCE_KEY)
            .values_list("source_version", flat=True)
            .first()
        )
        if current == version and not opts["force"] and not opts["dry_run"]:
            self.stdout.write(self.style.SUCCESS(f"Already at version {version}; nothing to do (use --force)."))
            return

        rows = []
        skipped = []
        for feat in features:
            ident = feat.get("identifier", "")
            name = feat.get("name", "")
            restriction = feat.get("restriction", DroneZone.Restriction.REQ_AUTHORISATION)
            reason = feat.get("reason") or []
            message = feat.get("message", "") or ""
            ext = feat.get("extendedProperties") or {}
            attrs = {
                "color": ext.get("color"),
                "arc": ext.get("arc"),
                "otherReasonInfo": feat.get("otherReasonInfo"),
                "applicability": feat.get("applicability"),
                "zoneAuthority": feat.get("zoneAuthority"),
            }
            for seg in feat.get("geometry") or []:
                hp = seg.get("horizontalProjection") or {}
                try:
                    poly = _segment_geometry(hp)
                except (ValueError, KeyError, TypeError) as e:
                    skipped.append((ident, str(e)))
                    continue
                if not poly.valid:
                    poly = poly.buffer(0)
                if isinstance(poly, Polygon):
                    mp = MultiPolygon(poly, srid=4326)
                elif isinstance(poly, MultiPolygon):
                    mp = poly
                else:
                    skipped.append((ident, f"buffer(0) produced {poly.geom_type}"))
                    continue
                uom = seg.get("uomDimensions")
                rows.append(DroneZone(
                    source=SOURCE_KEY,
                    source_version=version,
                    zone_identifier=ident,
                    name=name,
                    country_code=feat.get("country", "PRT"),
                    restriction=restriction,
                    reason=reason,
                    message=message,
                    lower_limit_m=_to_metres(seg.get("lowerLimit"), uom) or 0.0,
                    upper_limit_m=_to_metres(seg.get("upperLimit"), uom) or 0.0,
                    lower_ref=seg.get("lowerVerticalReference", "AGL"),
                    upper_ref=seg.get("upperVerticalReference", "AGL"),
                    geometry=mp,
                    attributes=attrs,
                ))

        self.stdout.write(f"Prepared {len(rows)} zone segments; skipped {len(skipped)}")
        for ident, err in skipped[:20]:
            self.stdout.write(self.style.WARNING(f"  skip {ident}: {err}"))

        if opts["dry_run"]:
            self.stdout.write(self.style.SUCCESS("Dry run: no changes written."))
            return

        with transaction.atomic():
            deleted, _ = DroneZone.objects.filter(source=SOURCE_KEY).delete()
            DroneZone.objects.bulk_create(rows, batch_size=500)
        self.stdout.write(self.style.SUCCESS(
            f"Replaced source '{SOURCE_KEY}': deleted {deleted}, inserted {len(rows)} (version {version})."
        ))
