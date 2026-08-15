"""Machine-translate the category tree into additional locales, into the CSV.

The tree is reference data: its source of truth is ``data/categories_i18n.csv``
(git-tracked), not the database. This command fills missing languages *there*,
so the result lands in a reviewable diff, survives a database rebuild and can
be corrected one line at a time. Nothing is written to the database — run
``import_categories_csv --i18n-only`` afterwards, then ``export_categories_json``.

That routing also keeps the two-layer i18n contract intact: the runtime
machine layer lives in per-row ``mt_cache`` (see ``parahub/services/translation.py``)
and never touches ``*_i18n``. A generated-then-committed CSV is an accepted
artifact, not runtime output.

Ambiguity is resolved by ancestor context: "Painting" under Auto Services is a
paint job, not an art form, so every item carries its English path.

``--fix-case`` runs the second job on the same plumbing: recapitalize existing
labels without retranslating them. The model may only change letter case there —
every result is checked word-for-word against the original, case-insensitively,
and a reply that alters any wording is discarded rather than trusted.

Usage:
    python3 manage.py translate_categories_csv --langs fr,de [--dry-run] [--limit N]
    python3 manage.py translate_categories_csv --fix-case --langs pt,es,ru [--dry-run]
"""

import csv
import json
from django.core.management.base import BaseCommand, CommandError

from parahub.services.translation import GEMINI_TRANSLATION_MODEL, LANGUAGE_NAMES

# One request carries this many categories. Sized well inside the model's
# output window — a batch that overflows loses items, and we refuse to
# silently drop any (see _translate_batch).
BATCH_SIZE = 60

# Capitalization is the one convention a translator gets wrong by default:
# English title case leaks into languages that use sentence case.
CASE_RULES = {
    'fr': 'French sentence case — capitalize only the first word and proper nouns '
          '("Voyages et loisirs", not "Voyages et Loisirs")',
    'de': 'German rules — capitalize every noun, lowercase adjectives and verbs',
    'es': 'Spanish sentence case — capitalize only the first word and proper nouns',
    'pt': 'Portuguese sentence case — capitalize only the first word and proper nouns',
    'ru': 'Russian sentence case — capitalize only the first word and proper nouns',
}


class Command(BaseCommand):
    help = 'Machine-translate categories into extra languages, writing data/categories_i18n.csv'

    def add_arguments(self, parser):
        parser.add_argument('--langs', type=str, default='fr,de',
                            help='Comma-separated target languages (default: fr,de)')
        parser.add_argument('--structure-file', type=str, default='data/categories.csv')
        parser.add_argument('--i18n-file', type=str, default='data/categories_i18n.csv')
        parser.add_argument('--batch-size', type=int, default=BATCH_SIZE)
        parser.add_argument('--limit', type=int, default=0,
                            help='Translate at most N categories per language (smoke test)')
        parser.add_argument('--dry-run', action='store_true',
                            help='Translate and print, but leave the CSV untouched')
        parser.add_argument('--fix-case', action='store_true',
                            help='Recapitalize existing labels instead of translating missing ones')

    def handle(self, *args, **options):
        langs = [l.strip() for l in options['langs'].split(',') if l.strip()]
        unknown = [l for l in langs if l not in LANGUAGE_NAMES]
        if unknown:
            raise CommandError(f"Unknown language(s): {', '.join(unknown)}")

        structure = self._read_structure(options['structure_file'])
        rows = self._read_i18n(options['i18n_file'])

        # category_id -> {lang: row}; the file groups every category's languages
        # together, and we keep it that way so a later export is a no-op diff.
        by_cat = {}
        order = []
        for row in rows:
            cid = row['category_id']
            if cid not in by_cat:
                by_cat[cid] = {}
                order.append(cid)
            by_cat[cid][row['lang']] = row

        english = {cid: langs_.get('en') for cid, langs_ in by_cat.items()}
        missing_en = [cid for cid, en in english.items() if not en or not en['name'].strip()]
        if missing_en:
            raise CommandError(
                f"{len(missing_en)} categories have no English name — nothing to translate from")

        client = self._client()

        if options['fix_case']:
            self._fix_case(client, langs, order, by_cat, options)
            if options['dry_run']:
                self.stdout.write(self.style.WARNING("\nDRY RUN — CSV not written"))
                return
            self._write_i18n(options['i18n_file'], order, by_cat)
            self.stdout.write(self.style.SUCCESS(f"\n✅ Wrote {options['i18n_file']}"))
            return

        for lang in langs:
            todo = [cid for cid in order if not (by_cat[cid].get(lang) or {}).get('name', '').strip()]
            if options['limit']:
                todo = todo[:options['limit']]
            if not todo:
                self.stdout.write(f"{lang}: nothing missing")
                continue

            self.stdout.write(self.style.WARNING(
                f"\n{lang}: {len(todo)} categories to translate "
                f"in {-(-len(todo) // options['batch_size'])} request(s)"))

            done = 0
            for start in range(0, len(todo), options['batch_size']):
                chunk = todo[start:start + options['batch_size']]
                payload = [{
                    'i': idx,
                    'path': self._path(cid, structure, english),
                    'name': english[cid]['name'],
                    **({'desc': english[cid]['description']} if english[cid].get('description') else {}),
                } for idx, cid in enumerate(chunk)]

                result = self._translate_batch(client, payload, lang)

                for idx, cid in enumerate(chunk):
                    item = result[idx]
                    row = by_cat[cid].setdefault(lang, {
                        'category_id': cid, 'lang': lang, 'name': '', 'description': ''})
                    row['name'] = item['name']
                    row['description'] = item.get('desc', '') or ''
                done += len(chunk)
                self.stdout.write(f"  {done}/{len(todo)}")

            sample = todo[:3]
            for cid in sample:
                self.stdout.write(
                    f"    {english[cid]['name']} → {by_cat[cid][lang]['name']}")

        if options['dry_run']:
            self.stdout.write(self.style.WARNING("\nDRY RUN — CSV not written"))
            return

        self._write_i18n(options['i18n_file'], order, by_cat)
        self.stdout.write(self.style.SUCCESS(
            f"\n✅ Wrote {options['i18n_file']}\n"
            f"   Next: manage.py import_categories_csv --i18n-only && "
            f"manage.py export_categories_json"))

    # ── Case normalization ─────────────────────────────────────────────────

    @staticmethod
    def _looks_title_cased(name):
        """A non-initial word starting with a capital, ignoring all-caps acronyms.

        Over-selects on purpose: proper nouns land in the batch too and simply
        come back unchanged, which is cheaper than maintaining a name list.
        """
        words = name.split()
        return len(words) > 1 and any(w[:1].isupper() and not w.isupper() for w in words[1:])

    def _fix_case(self, client, langs, order, by_cat, options):
        for lang in langs:
            todo = [cid for cid in order
                    if self._looks_title_cased((by_cat[cid].get(lang) or {}).get('name', ''))]
            if options['limit']:
                todo = todo[:options['limit']]
            if not todo:
                self.stdout.write(f"{lang}: nothing to recapitalize")
                continue

            self.stdout.write(self.style.WARNING(
                f"\n{lang}: {len(todo)} label(s) to check "
                f"in {-(-len(todo) // options['batch_size'])} request(s)"))

            changed, rejected = [], []
            for start in range(0, len(todo), options['batch_size']):
                chunk = todo[start:start + options['batch_size']]
                payload = [{'i': idx, 'name': by_cat[cid][lang]['name']}
                           for idx, cid in enumerate(chunk)]
                result = self._case_batch(client, payload, lang)

                for idx, cid in enumerate(chunk):
                    old = by_cat[cid][lang]['name']
                    new = (result.get(idx) or {}).get('name', '')
                    # The model is allowed to touch case and nothing else.
                    if [w.lower() for w in new.split()] != [w.lower() for w in old.split()]:
                        rejected.append((old, new))
                        continue
                    if new != old:
                        by_cat[cid][lang]['name'] = new
                        changed.append((old, new))

            self.stdout.write(f"  changed {len(changed)}, left as-is "
                              f"{len(todo) - len(changed) - len(rejected)}, "
                              f"rejected {len(rejected)}")
            for old, new in changed[:8]:
                self.stdout.write(f"    {old} → {new}")
            for old, new in rejected[:5]:
                self.stdout.write(self.style.ERROR(f"    rejected: {old} ↛ {new}"))

    def _case_batch(self, client, payload, lang):
        from google.genai import types as genai_types

        target = LANGUAGE_NAMES.get(lang, lang)
        prompt = (
            f"You are fixing the capitalization of {target} UI category labels.\n"
            "Do not translate, do not reword, do not reorder, do not add or remove anything — "
            "return each label with exactly the same words, changing letter case only.\n"
            f"Rule: {CASE_RULES.get(lang, 'follow the conventions of ' + target)}.\n"
            "Leave proper nouns, brand names and acronyms exactly as they are "
            "(PlayStation, Android, Wi-Fi, DDoS, HoReCa, Data Science, TI, IT, PC, GPS, SUV).\n"
            "A label that is already correct comes back unchanged.\n"
            'Return strict JSON: [{"i": <int>, "name": "<label>"}], one entry per input item, '
            "nothing else.\n\n"
            + json.dumps(payload, ensure_ascii=False)
        )
        response = client.models.generate_content(
            model=GEMINI_TRANSLATION_MODEL,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=16384,
                response_mime_type='application/json',
            ),
        )
        try:
            items = json.loads(response.text)
        except (TypeError, ValueError) as e:
            raise CommandError(f"Model returned non-JSON for a {lang} case batch: {e}")
        return {int(it['i']): it for it in items if 'i' in it and it.get('name')}

    # ── I/O ────────────────────────────────────────────────────────────────

    def _read_structure(self, path):
        with open(path, encoding='utf-8') as f:
            return {r['id']: r for r in csv.DictReader(f)}

    def _read_i18n(self, path):
        with open(path, encoding='utf-8') as f:
            return list(csv.DictReader(f))

    def _write_i18n(self, path, order, by_cat):
        """Rewrite the file, languages of one category kept adjacent and in a
        stable order — the same shape ``export_categories_csv`` produces."""
        lang_order = ['en', 'ru', 'pt', 'es', 'fr', 'de']
        with open(path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['category_id', 'lang', 'name', 'description'])
            for cid in order:
                langs_ = by_cat[cid]
                for lang in lang_order + [l for l in langs_ if l not in lang_order]:
                    row = langs_.get(lang)
                    if row and row['name'].strip():
                        writer.writerow([cid, lang, row['name'], row.get('description', '')])

    def _path(self, cid, structure, english):
        """English ancestor chain, root first — the disambiguation context."""
        parts, cur, guard = [], cid, 0
        while cur and guard < 8:
            en = english.get(cur)
            parts.append(en['name'] if en else structure.get(cur, {}).get('slug', '?'))
            cur = structure.get(cur, {}).get('parent_id') or None
            guard += 1
        return ' > '.join(reversed(parts))

    # ── Provider ───────────────────────────────────────────────────────────

    def _client(self):
        from parahub.models import AISettings
        from google import genai
        settings_row = AISettings.objects.first()
        if not (settings_row and settings_row.enabled and settings_row.google_api_key):
            raise CommandError("AISettings has no enabled Google API key")
        return genai.Client(api_key=settings_row.google_api_key)

    def _translate_batch(self, client, payload, lang, _retry=True):
        """Returns {index: {'name': ..., 'desc': ...}} covering every input item.

        A short response is retried for the missing indices only; if the model
        still skips an item the command fails rather than writing a partial
        language — a silently missing label is worse than a visible crash.
        """
        from google.genai import types as genai_types

        target = LANGUAGE_NAMES.get(lang, lang)
        prompt = (
            f"You are localizing a marketplace and directory category tree into {target}.\n"
            "Each item has `path` (its ancestors in English, for disambiguation), `name` "
            "(the label to translate) and sometimes `desc` (a short description).\n"
            "Translate `name`, and `desc` when it is present. Use `path` only as context — "
            "never translate it, never merge it into the label.\n"
            "Register: a short category label — no leading article, no trailing period, "
            "plural where the English is plural.\n"
            f"Capitalization: {CASE_RULES.get(lang, 'follow the conventions of ' + target)}.\n"
            "Keep technical and brand tokens the language uses as-is (Wi-Fi, P2P, SUV, USB, GPS).\n"
            'Return strict JSON: a list of {"i": <int>, "name": "<translation>", '
            '"desc": "<translation or empty string>"}. Return one entry for every input item, '
            "nothing else.\n\n"
            + json.dumps(payload, ensure_ascii=False)
        )

        response = client.models.generate_content(
            model=GEMINI_TRANSLATION_MODEL,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=16384,
                response_mime_type='application/json',
            ),
        )
        try:
            items = json.loads(response.text)
        except (TypeError, ValueError) as e:
            raise CommandError(f"Model returned non-JSON for a {lang} batch: {e}")

        result = {int(it['i']): it for it in items if 'i' in it and it.get('name')}
        missing = [it for it in payload if it['i'] not in result]
        if missing and _retry:
            self.stdout.write(self.style.WARNING(
                f"  retrying {len(missing)} item(s) the model skipped"))
            retry_payload = [{**it, 'i': n} for n, it in enumerate(missing)]
            retried = self._translate_batch(client, retry_payload, lang, _retry=False)
            for n, it in enumerate(missing):
                result[it['i']] = retried[n]
        elif missing:
            raise CommandError(
                f"Model skipped {len(missing)} item(s) twice: "
                f"{[it['name'] for it in missing[:5]]}")
        return result
