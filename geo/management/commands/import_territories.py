"""
Import civic Territory reference data.

Countries: /usr/share/iso-codes/json/iso_3166-1.json (Debian iso-codes, offline, 249 entries).
Portugal hierarchy: CAOP GeoPackages from DGT (authoritative; carries DICOFRE/DICO codes,
NUTS II codes AND names, and boundary geometry). NUTS II codes come from the data itself —
the 2024 NUTS revision reshaped PT regions (AML split etc.), so nothing is hardcoded.

CAOP 2025 downloads (see dados.gov.pt "Carta Administrativa Oficial de Portugal"):
    https://geo2.dgterritorio.gov.pt/caop/CAOP_Continente_2025-gpkg.zip
    https://geo2.dgterritorio.gov.pt/caop/CAOP_RAA_2025-gpkg.zip
    https://geo2.dgterritorio.gov.pt/caop/CAOP_RAM_2025-gpkg.zip

Usage:
    python3 manage.py import_territories --countries
    python3 manage.py import_territories --pt --caop-dir /path/with/gpkg [--skip-geometry]
    python3 manage.py import_territories --pt --caop-dir /tmp/caop --download
    python3 manage.py import_territories --pt --caop-dir ... --deactivate-missing
"""
import glob
import json
import os
import urllib.request
import zipfile

from django.contrib.gis.gdal import DataSource
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon, Polygon
from django.core.management.base import BaseCommand, CommandError

from geo.models import Territory

ISO_CODES_PATH = "/usr/share/iso-codes/json/iso_3166-1.json"
CAOP_URLS = [
    "https://geo2.dgterritorio.gov.pt/caop/CAOP_Continente_2025-gpkg.zip",
    "https://geo2.dgterritorio.gov.pt/caop/CAOP_RAA_2025-gpkg.zip",
    "https://geo2.dgterritorio.gov.pt/caop/CAOP_RAM_2025-gpkg.zip",
]
SIMPLIFY_TOLERANCE_DEG = 0.0005  # ~50 m; boundaries are for residency auto-suggest, not cartography


def _to_multipolygon_4326(ogr_geom, simplify=True):
    """OGR geometry (EPSG:3763 PT-TM06) → simplified WGS84 MultiPolygon, or None."""
    try:
        ogr_geom.transform(4326)
        geos = GEOSGeometry(ogr_geom.wkb, srid=4326)
        if simplify:
            geos = geos.simplify(SIMPLIFY_TOLERANCE_DEG, preserve_topology=True)
        if geos.empty:
            return None
        if isinstance(geos, Polygon):
            geos = MultiPolygon(geos, srid=4326)
        if not isinstance(geos, MultiPolygon):
            return None
        return geos
    except Exception:
        return None


class Command(BaseCommand):
    help = "Import civic Territory reference (ISO countries + PT hierarchy from CAOP)"

    def add_arguments(self, parser):
        parser.add_argument('--countries', action='store_true', help='Import ISO 3166-1 country rows')
        parser.add_argument('--pt', action='store_true', help='Import PT regions/municipalities/parishes from CAOP')
        parser.add_argument('--caop-dir', type=str, default=None, help='Directory containing CAOP *.gpkg files')
        parser.add_argument('--download', action='store_true', help='Download CAOP zips into --caop-dir first (~115 MB)')
        parser.add_argument('--skip-geometry', action='store_true', help='Import codes/names only, no boundaries')
        parser.add_argument('--deactivate-missing', action='store_true',
                            help='Set is_active=False on PT parishes/municipalities absent from the files (reforms)')

    def handle(self, *args, **opts):
        if not opts['countries'] and not opts['pt']:
            raise CommandError("Pass --countries and/or --pt")
        if opts['countries']:
            self.import_countries()
        if opts['pt']:
            if not opts['caop_dir']:
                raise CommandError("--pt requires --caop-dir (see command docstring for CAOP downloads)")
            if opts['download']:
                self.download_caop(opts['caop_dir'])
            self.import_pt(opts['caop_dir'], skip_geometry=opts['skip_geometry'],
                           deactivate_missing=opts['deactivate_missing'])

    # ------------------------------------------------------------------ countries

    def import_countries(self):
        with open(ISO_CODES_PATH) as f:
            entries = json.load(f)['3166-1']
        created = updated = 0
        for e in entries:
            code = e['alpha_2']
            name = e.get('common_name') or e['name']
            _, was_created = Territory.objects.update_or_create(
                country=code, level=Territory.Level.COUNTRY, code=code,
                defaults={'name': name, 'parent': None, 'is_active': True},
            )
            created += was_created
            updated += not was_created
        self.stdout.write(f"Countries: {created} created, {updated} updated ({len(entries)} total)")

    # ------------------------------------------------------------------ CAOP download

    def download_caop(self, caop_dir):
        os.makedirs(caop_dir, exist_ok=True)
        for url in CAOP_URLS:
            zip_path = os.path.join(caop_dir, url.rsplit('/', 1)[-1])
            if not os.path.exists(zip_path):
                self.stdout.write(f"Downloading {url} ...")
                urllib.request.urlretrieve(url, zip_path)
            with zipfile.ZipFile(zip_path) as z:
                z.extractall(caop_dir)
        self.stdout.write("CAOP archives ready")

    # ------------------------------------------------------------------ Portugal

    def import_pt(self, caop_dir, skip_geometry=False, deactivate_missing=False):
        gpkgs = sorted(glob.glob(os.path.join(caop_dir, '*.gpkg')))
        if not gpkgs:
            raise CommandError(f"No *.gpkg files in {caop_dir}")

        pt, _ = Territory.objects.update_or_create(
            country='PT', level=Territory.Level.COUNTRY, code='PT',
            defaults={'name': 'Portugal', 'parent': None, 'is_active': True},
        )

        regions_by_name = {}
        munis_by_code = {}
        seen_muni, seen_parish = set(), set()
        n_parish = 0

        for path in gpkgs:
            ds = DataSource(path)
            layers = {l.name: l for l in ds}
            nuts2_layers = [l for n, l in layers.items() if n.endswith('_nuts2')]
            muni_layers = [l for n, l in layers.items() if n.endswith('_municipios')]
            parish_layers = [l for n, l in layers.items() if n.endswith('_freguesias')]
            self.stdout.write(f"{os.path.basename(path)}: "
                              f"{sum(l.num_feat for l in parish_layers)} parishes")

            # Regions: official NUTS II codes from the data (prefixed PT → Eurostat style)
            for layer in nuts2_layers:
                for feat in layer:
                    name = feat.get('nuts2')
                    code = 'PT' + str(feat.get('codigo'))
                    geom = None if skip_geometry else _to_multipolygon_4326(feat.geom)
                    region, _ = Territory.objects.update_or_create(
                        country='PT', level=Territory.Level.REGION, code=code,
                        defaults={'name': name, 'parent': pt, 'is_active': True,
                                  **({'geometry': geom} if geom else {})},
                    )
                    regions_by_name[name] = region

            for layer in muni_layers:
                for feat in layer:
                    code = str(feat.get('dtmn'))
                    name = feat.get('municipio')
                    region = regions_by_name.get(feat.get('nuts2'))
                    if region is None:
                        self.stderr.write(f"  ! municipality {name}: unknown NUTS2 '{feat.get('nuts2')}'")
                        continue
                    geom = None if skip_geometry else _to_multipolygon_4326(feat.geom)
                    muni, _ = Territory.objects.update_or_create(
                        country='PT', level=Territory.Level.MUNICIPALITY, code=code,
                        defaults={'name': name, 'parent': region, 'is_active': True,
                                  **({'geometry': geom} if geom else {})},
                    )
                    munis_by_code[code] = muni
                    seen_muni.add(code)

            for layer in parish_layers:
                for feat in layer:
                    code = str(feat.get('dtmnfr'))
                    name = feat.get('freguesia')
                    muni = munis_by_code.get(code[:4])
                    if muni is None:
                        self.stderr.write(f"  ! parish {name} ({code}): municipality {code[:4]} not found")
                        continue
                    geom = None if skip_geometry else _to_multipolygon_4326(feat.geom)
                    Territory.objects.update_or_create(
                        country='PT', level=Territory.Level.PARISH, code=code,
                        defaults={'name': name, 'parent': muni, 'is_active': True,
                                  **({'geometry': geom} if geom else {})},
                    )
                    seen_parish.add(code)
                    n_parish += 1

        if deactivate_missing:
            gone_p = Territory.objects.filter(
                country='PT', level=Territory.Level.PARISH, is_active=True
            ).exclude(code__in=seen_parish).update(is_active=False)
            gone_m = Territory.objects.filter(
                country='PT', level=Territory.Level.MUNICIPALITY, is_active=True
            ).exclude(code__in=seen_muni).update(is_active=False)
            self.stdout.write(f"Deactivated: {gone_p} parishes, {gone_m} municipalities (administrative reforms)")

        self.stdout.write(self.style.SUCCESS(
            f"PT import done: {len(regions_by_name)} regions, {len(seen_muni)} municipalities, {n_parish} parishes"
        ))
