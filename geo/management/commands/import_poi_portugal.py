"""
Import POI data for all Portugal: freguesias (Wikidata + Overpass) and churches (Overpass).

Usage:
    python3 manage.py import_poi_portugal                    # All: freguesias + churches
    python3 manage.py import_poi_portugal --type freguesias  # Only freguesias
    python3 manage.py import_poi_portugal --type churches    # Only churches
    python3 manage.py import_poi_portugal --dry-run          # Preview only
    python3 manage.py import_poi_portugal --reset churches   # Delete imported churches + reimport
"""

import json
import re
import time
import urllib.request
import urllib.parse
from django.core.management.base import BaseCommand
from django.contrib.gis.geos import Point
from django.utils.text import slugify

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
WIKIDATA_URL = "https://query.wikidata.org/sparql"
USER_AGENT = "Parahub/1.0 (import_poi_portugal)"

# Portugal mainland bbox strips (to avoid Overpass timeouts)
PT_BBOX_STRIPS = [
    (36.9, -9.6, 38.0, -6.1),   # Algarve + south Alentejo
    (38.0, -9.6, 39.5, -6.1),   # Lisboa + Alentejo
    (39.5, -9.6, 40.5, -7.0),   # Centro
    (40.5, -9.0, 41.5, -6.1),   # Centro-north
    (41.5, -8.9, 42.2, -6.1),   # Norte
]

# Portuguese districts with Wikidata QIDs (class Q3032141 = distrito de Portugal)
PT_DISTRICTS = {
    'Aveiro': 'Q210527', 'Beja': 'Q321455', 'Braga': 'Q326203',
    'Bragança': 'Q373528', 'Castelo Branco': 'Q273529',
    'Coimbra': 'Q244517', 'Évora': 'Q274118', 'Faro': 'Q244521',
    'Guarda': 'Q273533', 'Leiria': 'Q244512', 'Lisboa': 'Q207199',
    'Portalegre': 'Q225189', 'Porto': 'Q322792', 'Santarém': 'Q244510',
    'Setúbal': 'Q274109', 'Viana do Castelo': 'Q326214',
    'Vila Real': 'Q379372', 'Viseu': 'Q273525',
    # Islands (historical districts)
    'Angra do Heroísmo': 'Q10267294', 'Horta': 'Q4412409',
    'Ponta Delgada': 'Q4348932', 'Funchal': 'Q10267318',
}

# Filter patterns for non-parish Wikidata items
SKIP_PATTERNS = [
    'Biblioteca', 'Centro de Sa', 'Igreja', 'Church', 'Estação', 'Apeadeiro',
    'Museu', 'Ponte ', 'Cine-', 'Paragem', 'Termas', 'Confraria', 'Associação',
    'Aquamuseu', 'Castle', 'Castelo de', 'Capela', 'Convento', 'Mosteiro',
    'Santuário', 'Torre de', 'Forte ', 'Pelourinho', 'Solar de', 'Paço de',
    'Centro Ciência', 'Oficinas', 'Jogo do Pau', 'Cruzeiro', 'Posto de',
    'Hospital', 'Tribunal', 'Universidade', 'Escola', 'Quartel',
    'Rio ', 'Serra de', 'Praia ', 'Barragem', 'Albufeira',
]


def _fetch_json(url, data=None, headers=None, timeout=180):
    """Fetch JSON from URL with POST data."""
    hdrs = {"User-Agent": USER_AGENT}
    if headers:
        hdrs.update(headers)
    if data:
        body = urllib.parse.urlencode(data).encode()
    else:
        body = None
    req = urllib.request.Request(url, data=body, headers=hdrs)
    resp = urllib.request.urlopen(req, timeout=timeout)
    return json.loads(resp.read())


class Command(BaseCommand):
    help = "Import freguesias (Wikidata+Overpass) and churches (Overpass) for all Portugal"

    def add_arguments(self, parser):
        parser.add_argument(
            '--type', choices=['freguesias', 'churches', 'all'], default='all',
            help='What to import (default: all)',
        )
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument(
            '--reset', nargs='?', const='all', choices=['freguesias', 'churches', 'all'],
            help='Delete previously imported data before reimporting',
        )
        parser.add_argument('--owner', default='norn')

    def handle(self, **options):
        from identity.models import Profile
        try:
            self.owner = Profile.objects.get(account__username=options['owner'])
        except Profile.DoesNotExist:
            self.stderr.write(f"Profile not found: {options['owner']}")
            return

        self.dry_run = options['dry_run']
        import_type = options['type']
        reset = options.get('reset')

        if reset:
            self._reset(reset)

        if import_type in ('freguesias', 'all'):
            self._import_freguesias_wikidata()
            self._import_freguesias_overpass()

        if import_type in ('churches', 'all'):
            self._import_churches()

    def _reset(self, what):
        from geo.models import Establishment
        from taxonomy.models import Category

        if what in ('freguesias', 'all'):
            cat = Category.objects.filter(slug='parish-council').first()
            if cat:
                qs = Establishment.objects.filter(category=cat, attributes__import_source__in=[
                    'overpass_freguesia_import', 'wikidata_freguesia_import',
                ])
                count = qs.count()
                if not self.dry_run:
                    qs.delete()
                self.stdout.write(f"Deleted {count} imported freguesias")

        if what in ('churches', 'all'):
            cat = Category.objects.filter(slug='church').first()
            if cat:
                qs = Establishment.objects.filter(category=cat, attributes__import_source='overpass_church_import')
                count = qs.count()
                if not self.dry_run:
                    qs.delete()
                self.stdout.write(f"Deleted {count} imported churches")

    # ===== FREGUESIAS: WIKIDATA =====

    def _import_freguesias_wikidata(self):
        from taxonomy.models import Category
        category = Category.objects.get(slug='parish-council')

        self.stdout.write("\n=== Importing freguesias from Wikidata ===")
        total_created = 0

        for district_name, district_qid in sorted(PT_DISTRICTS.items()):
            self.stdout.write(f"\n--- {district_name} ---")

            # Step 1: Get municipalities in district
            municipalities = self._wikidata_municipalities(district_qid)
            if not municipalities:
                self.stdout.write(f"  No municipalities found for {district_name}")
                continue
            self.stdout.write(f"  {len(municipalities)} municipalities")

            # Step 2: Get parishes for all municipalities (batch)
            parishes = self._wikidata_parishes(municipalities)
            self.stdout.write(f"  {len(parishes)} raw items from Wikidata")

            # Step 3: Filter & import
            created = self._import_wikidata_parishes(parishes, category)
            total_created += created
            self.stdout.write(f"  Created {created} new parishes")

            time.sleep(1)  # courtesy delay

        self.stdout.write(f"\nWikidata total: {total_created} new freguesias")

    def _wikidata_municipalities(self, district_qid):
        """Get municipality QIDs for a district."""
        query = f"""
SELECT ?item ?itemLabel WHERE {{
  ?item wdt:P131 wd:{district_qid} .
  ?item wdt:P31 wd:Q13217644 .
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "pt,en" . }}
}} ORDER BY ?itemLabel"""
        try:
            data = _fetch_json(WIKIDATA_URL, {'format': 'json', 'query': query})
            return [
                (r['item']['value'].split('/')[-1], r['itemLabel']['value'])
                for r in data['results']['bindings']
            ]
        except Exception as e:
            self.stderr.write(f"  Wikidata error: {e}")
            return []

    def _wikidata_parishes(self, municipalities):
        """Get parishes with coords for a batch of municipalities."""
        qid_values = ' '.join(f'wd:{qid}' for qid, _ in municipalities)
        mun_map = {qid: name for qid, name in municipalities}

        query = f"""
SELECT DISTINCT ?item ?itemLabel ?coord ?municipality WHERE {{
  VALUES ?municipality {{ {qid_values} }}
  ?item wdt:P131 ?municipality .
  ?item wdt:P625 ?coord .
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "pt,en" . }}
}}"""
        try:
            data = _fetch_json(WIKIDATA_URL, {'format': 'json', 'query': query})
        except Exception as e:
            self.stderr.write(f"  Wikidata query error: {e}")
            return []

        results = []
        for r in data['results']['bindings']:
            name = r['itemLabel']['value']
            # Skip unlabeled
            if re.match(r'^Q\d+$', name):
                continue
            # Skip non-parish items
            if any(p in name for p in SKIP_PATTERNS):
                continue
            coord = r['coord']['value']
            m = re.match(r'Point\(([-\d.]+) ([-\d.]+)\)', coord)
            if not m:
                continue
            lng, lat = float(m.group(1)), float(m.group(2))
            qid = r['item']['value'].split('/')[-1]
            mun_qid = r['municipality']['value'].split('/')[-1]
            results.append({
                'name': name, 'lat': lat, 'lng': lng, 'qid': qid,
                'municipality': mun_map.get(mun_qid, ''),
            })

        # Deduplicate by name+municipality
        seen = set()
        unique = []
        for p in results:
            key = (p['name'], p['municipality'])
            if key not in seen:
                seen.add(key)
                unique.append(p)
        return unique

    def _import_wikidata_parishes(self, parishes, category):
        from geo.models import Establishment

        created = 0
        for p in parishes:
            # Already imported by QID?
            if Establishment.objects.filter(
                category=category, attributes__wikidata_qid=p['qid'],
            ).exists():
                continue

            # Already exists within 500m? (Overpass import)
            point = Point(p['lng'], p['lat'], srid=4326)
            if Establishment.objects.filter(
                category=category, location__distance_lte=(point, 500),
            ).exists():
                continue

            name = p['name']
            if not any(x in name for x in ['Freguesia', 'União']):
                name = f'Freguesia de {name}'

            if self.dry_run:
                self.stdout.write(f"    [DRY] {name} | {p['municipality']}")
                created += 1
                continue

            Establishment.objects.create(
                name=name,
                owner=self.owner,
                category=category,
                organization_type='GOVERNMENT',
                location=point,
                is_verified=False,
                is_active=True,
                attributes={
                    'import_source': 'wikidata_freguesia_import',
                    'wikidata_qid': p['qid'],
                    'municipality': p['municipality'],
                },
            )
            created += 1
        return created

    # ===== FREGUESIAS: OVERPASS =====

    def _import_freguesias_overpass(self):
        self.stdout.write("\n=== Importing freguesia offices from Overpass ===")
        from geo.management.commands.import_freguesias import Command as OverpassCmd

        total = 0
        for south, west, north, east in PT_BBOX_STRIPS:
            bbox = f"{south},{west},{north},{east}"
            self.stdout.write(f"  Strip: {bbox}")
            try:
                cmd = OverpassCmd()
                cmd.handle(bbox=bbox, reset=False, dry_run=self.dry_run, owner='norn')
            except Exception as e:
                self.stderr.write(f"  Overpass error for {bbox}: {e}")
            time.sleep(5)  # rate limit

    # ===== CHURCHES =====

    def _import_churches(self):
        from geo.models import Establishment
        from taxonomy.models import Category

        category = Category.objects.get(slug='church')
        self.stdout.write("\n=== Importing churches from Overpass ===")
        total_created = 0

        for south, west, north, east in PT_BBOX_STRIPS:
            bbox_str = f"({south},{west},{north},{east})"
            self.stdout.write(f"  Strip: {bbox_str}")

            query = f'[out:json][timeout:120];(nwr["amenity"="place_of_worship"]["religion"="christian"]{bbox_str};);out center;'
            try:
                data = _fetch_json(
                    OVERPASS_URL,
                    {'data': query},
                    timeout=180,
                )
            except Exception as e:
                self.stderr.write(f"  Overpass error: {e}")
                time.sleep(10)
                continue

            elements = data.get('elements', [])
            self.stdout.write(f"    {len(elements)} elements")

            created = 0
            for el in elements:
                tags = el.get('tags', {})
                name = tags.get('name', '')
                if not name:
                    continue

                if el['type'] == 'node':
                    lat, lon = el['lat'], el['lon']
                elif 'center' in el:
                    lat, lon = el['center']['lat'], el['center']['lon']
                else:
                    continue

                osm_id = f"{el['type']}/{el['id']}"
                if Establishment.objects.filter(category=category, attributes__osm_id=osm_id).exists():
                    continue

                if self.dry_run:
                    created += 1
                    continue

                phone = tags.get('phone', tags.get('contact:phone', ''))[:50]
                website = tags.get('website', tags.get('contact:website', ''))

                Establishment.objects.create(
                    name=name,
                    owner=self.owner,
                    category=category,
                    location=Point(lon, lat, srid=4326),
                    phone=phone,
                    website=website,
                    opening_hours={'raw': tags['opening_hours']} if tags.get('opening_hours') else {},
                    is_verified=False,
                    is_active=True,
                    attributes={
                        'import_source': 'overpass_church_import',
                        'osm_id': osm_id,
                        'denomination': tags.get('denomination', ''),
                    },
                )
                created += 1

            total_created += created
            self.stdout.write(f"    Created {created}")
            time.sleep(5)  # rate limit

        self.stdout.write(f"\nChurches total: {total_created}")
