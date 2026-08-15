"""
Validate Wikidata-imported freguesias and deactivate records that are not parishes.

The freguesia import pulls every Wikidata item located in a municipality
(wdt:P131) — hotels, stadiums, pubs and archaeological sites slip through the
name-pattern filter and get a "Freguesia de" name prefix. This command asks
Wikidata what each imported item actually is (P31) and deactivates everything
that is neither a current freguesia (Q1131296) nor a former one (Q56046844).

Every checked record gets attributes['parish_status'] = 'current' | 'former'
| 'none', so later decisions (e.g. hiding former freguesias) need no refetch.

Usage:
    python3 manage.py clean_freguesia_import --dry-run
    python3 manage.py clean_freguesia_import
"""

import time
from django.core.cache import cache
from django.core.management.base import BaseCommand

from geo.management.commands.import_poi_portugal import WIKIDATA_URL, _fetch_json

CURRENT_PARISH = 'Q1131296'   # freguesia de Portugal
FORMER_PARISH = 'Q56046844'   # antiga freguesia de Portugal (pre-2013 reform)
CHUNK = 400


class Command(BaseCommand):
    help = "Deactivate imported 'freguesias' whose Wikidata P31 is not a parish class"

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, **options):
        from geo.models import Establishment

        dry_run = options['dry_run']
        records = list(Establishment.objects.filter(
            attributes__import_source='wikidata_freguesia_import',
        ))
        by_qid = {}
        for e in records:
            qid = e.attributes.get('wikidata_qid')
            if qid:
                by_qid.setdefault(qid, []).append(e)
        self.stdout.write(f"{len(records)} imported records, {len(by_qid)} unique QIDs")

        p31 = self._fetch_p31(sorted(by_qid))

        counts = {'current': 0, 'former': 0, 'none': 0}
        deactivated = []
        for qid, establishments in by_qid.items():
            classes = p31.get(qid, [])
            if CURRENT_PARISH in classes:
                status = 'current'
            elif FORMER_PARISH in classes:
                status = 'former'
            else:
                status = 'none'
            counts[status] += len(establishments)

            for e in establishments:
                e.attributes['parish_status'] = status
                if status == 'none':
                    e.attributes['p31'] = classes
                    e.is_active = False
                    deactivated.append(e.name)
                if not dry_run:
                    e.save(update_fields=['attributes', 'is_active', 'updated_at'])

        prefix = '[DRY] ' if dry_run else ''
        self.stdout.write(
            f"{prefix}current: {counts['current']}, former: {counts['former']}, "
            f"deactivated non-parish: {counts['none']}"
        )
        for name in sorted(deactivated):
            self.stdout.write(f"  {prefix}- {name}")

        if not dry_run and deactivated:
            cache.delete('geo:gov_map')
            self.stdout.write("Invalidated geo:gov_map cache")

    def _fetch_p31(self, qids):
        """Return {qid: [P31 class QIDs]} for all given items, queried in chunks."""
        result = {}
        for i in range(0, len(qids), CHUNK):
            chunk = qids[i:i + CHUNK]
            values = ' '.join(f'wd:{q}' for q in chunk)
            query = f"""
SELECT ?item ?class WHERE {{
  VALUES ?item {{ {values} }}
  ?item wdt:P31 ?class .
}}"""
            data = _fetch_json(WIKIDATA_URL, {'format': 'json', 'query': query})
            for r in data['results']['bindings']:
                qid = r['item']['value'].split('/')[-1]
                cls = r['class']['value'].split('/')[-1]
                result.setdefault(qid, []).append(cls)
            self.stdout.write(f"  P31 fetched for {min(i + CHUNK, len(qids))}/{len(qids)}")
            time.sleep(2)
        return result
