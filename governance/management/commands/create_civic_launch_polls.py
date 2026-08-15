"""
create_civic_launch_polls — real (non-demo) civic opinion polls for the public
barometer: EU, country (PT) and local (Minho) scopes.

These are LIVE polls, not seed/test data:
- created by the owner account (staff, not is_test/is_bot) so they pass the
  demo-isolation filter and are visible to the public (see governance/access.py);
- marked ``attributes.civic_launch`` only for findability — NOT a demo flag;
- no votes are pre-seeded — counts start honestly at zero;
- anonymous ballots (territory opinion is pseudonymous by design, GDPR Art. 9).

Content (title/description/options/destination) is hand-authored in six languages
in data/civic_launch_polls.json — base language pt, plus en/ru/es/de/fr. These are
authoritative translations (voting legitimacy), never machine-translated. The whole
{lang: text} map ships to the client, which picks by locale (see PK/civic-polls-system.md).

Idempotent: re-running matches an existing poll by its base (pt) title + launch flag
and refreshes the i18n maps in place — safe to run again after a translation edit.

Usage:
    python3 manage.py create_civic_launch_polls [--owner-email norn@parahub.io]
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone

from identity.models import Profile
from geo.models import Territory
from governance.models import Poll, PollContext, PollOption

LAUNCH_FLAG = 'civic_launch'
BASE_LANG = 'pt'  # launch polls are authored in Portuguese; the map's other langs are translations
DATA_FILE = Path(__file__).resolve().parent / 'data' / 'civic_launch_polls.json'


def _load_content():
    with DATA_FILE.open(encoding='utf-8') as fh:
        return json.load(fh)['buckets']


class Command(BaseCommand):
    help = "Create/refresh real civic opinion polls (EU/country/local) with 6-language i18n"

    def add_arguments(self, parser):
        parser.add_argument('--owner-email', default='norn@parahub.io',
                            help='Email of the (non-test) account that owns the polls')

    def handle(self, *args, **opts):
        owner = (Profile.objects.filter(account__email=opts['owner_email'], is_primary=True)
                 .select_related('account').first())
        if owner is None:
            self.stderr.write(f"Owner profile not found for {opts['owner_email']}")
            return

        eu = Territory.objects.filter(level=Territory.Level.EU, code='EU').first()
        if eu is None:
            self.stderr.write("EU territory missing — run seed_eu_territory first")
            return
        pt = Territory.objects.filter(level=Territory.Level.COUNTRY, code='PT').first()
        if pt is None:
            self.stderr.write("PT country territory missing — run import_territories --countries")
            return

        content = _load_content()
        buckets = [(eu, content['eu']), (pt, content['country'])]
        for entry in content['local']:
            terr = Territory.objects.filter(
                level=Territory.Level.MUNICIPALITY, code=entry['municipality']).first()
            if terr is None:
                self.stderr.write(
                    f"Municipality {entry['municipality']} missing — skipping "
                    f"'{entry['poll']['title'][BASE_LANG][:40]}'")
                continue
            buckets.append((terr, [entry['poll']]))

        now = timezone.now()
        created = updated = unchanged = 0
        for territory, specs in buckets:
            for spec in specs:
                outcome = self._apply(territory, spec, owner, now)
                if outcome == 'created':
                    created += 1
                    self.stdout.write(f"  + [{territory.level}] {spec['title'][BASE_LANG]}")
                elif outcome == 'updated':
                    updated += 1
                    self.stdout.write(f"  ~ [{territory.level}] {spec['title'][BASE_LANG]} (i18n refreshed)")
                else:
                    unchanged += 1

        self.stdout.write(self.style.SUCCESS(
            f"create_civic_launch_polls done: {created} created, "
            f"{updated} updated, {unchanged} unchanged"))

    def _apply(self, territory, spec, owner, now) -> str:
        """Create the poll or refresh its i18n maps in place. Returns created|updated|unchanged."""
        title = spec['title']
        desc = spec['description']
        dest = spec.get('destination') or {}
        options = spec['options']

        existing = Poll.objects.filter(
            attributes__contains={LAUNCH_FLAG: True}, title=title[BASE_LANG]).first()

        if existing:
            changed = False
            if existing.title_i18n != title:
                existing.title_i18n = title
                changed = True
            if existing.description_i18n != desc:
                existing.description_i18n = desc
                changed = True
            if existing.civic_destination_i18n != dest:
                existing.civic_destination_i18n = dest
                changed = True
            if changed:
                existing.save(update_fields=[
                    'title_i18n', 'description_i18n', 'civic_destination_i18n'])
            by_order = {o.order: o for o in existing.options.all()}
            for i, opt in enumerate(options):
                po = by_order.get(i)
                if po and po.text_i18n != opt:
                    po.text_i18n = opt
                    po.save(update_fields=['text_i18n'])
                    changed = True
            return 'updated' if changed else 'unchanged'

        ctx = PollContext.objects.create(
            context_type=PollContext.ContextType.TERRITORY,
            context_id=territory.id, created_by=owner)
        poll = Poll.objects.create(
            context=ctx,
            title=title[BASE_LANG], title_i18n=title,
            description=desc[BASE_LANG], description_i18n=desc,
            start_time=now, end_time=None,
            poll_class=Poll.PollClass.OPINION,
            ballot_mode=Poll.BallotMode.ANONYMOUS,
            allow_delegation=True, use_weights=False,
            civic_destination=dest.get(BASE_LANG, ''), civic_destination_i18n=dest,
            status=Poll.Status.ACTIVE, created_by=owner,
            attributes={LAUNCH_FLAG: True},
        )
        for i, opt in enumerate(options):
            PollOption.objects.create(poll=poll, text=opt[BASE_LANG], text_i18n=opt, order=i)
        return 'created'
