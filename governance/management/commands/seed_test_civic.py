"""
seed_test_civic — test data for civic opinion polls.

Creates a real-code PT territory skeleton (codes verified against geoapi.pt:
Moncao DICO=1604, Barbeita DICOFRE=160404, Bela DICOFRE=160406, Norte NUTS II=PT11),
sets residency + civic consent for seed test users, and creates one opinion poll
per scope level with a handful of votes.

Usage:
    python3 manage.py seed_test_civic [--reset]
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from identity.models import Profile
from geo.models import Territory
from governance.models import Poll, PollContext, PollOption
from governance import civic

SEED_FLAG = '__test_civic_seed'


class Command(BaseCommand):
    help = "Seed civic territories + opinion polls for testing"

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Delete previously seeded polls first')

    def handle(self, *args, **opts):
        if opts['reset']:
            qs = Poll.objects.filter(poll_class=Poll.PollClass.OPINION,
                                     attributes__contains={SEED_FLAG: True})
            n = qs.count()
            ctx_ids = list(qs.values_list('context_id', flat=True))
            qs.delete()
            PollContext.objects.filter(id__in=ctx_ids).delete()
            self.stdout.write(f"Reset: deleted {n} seeded polls")

        # --- territory skeleton (idempotent; real codes) ---
        pt, _ = Territory.objects.update_or_create(
            country='PT', level='country', code='PT',
            defaults={'name': 'Portugal', 'is_active': True})
        norte, _ = Territory.objects.update_or_create(
            country='PT', level='region', code='PT11',
            defaults={'name': 'Norte', 'parent': pt, 'is_active': True})
        moncao, _ = Territory.objects.update_or_create(
            country='PT', level='municipality', code='1604',
            defaults={'name': 'Monção', 'parent': norte, 'is_active': True})
        barbeita, _ = Territory.objects.update_or_create(
            country='PT', level='parish', code='160404',
            defaults={'name': 'Barbeita', 'parent': moncao, 'is_active': True})
        bela, _ = Territory.objects.update_or_create(
            country='PT', level='parish', code='160406',
            defaults={'name': 'Bela', 'parent': moncao, 'is_active': True})

        # --- seed users: residency + consent ---
        users = list(Profile.objects.filter(account__email__endswith='test.parahub.io')
                     .select_related('account').order_by('account__email'))
        if not users:
            self.stderr.write("No seed users found — run seed_test_users first")
            return
        now = timezone.now()
        for p in users:
            p.residency_territory = barbeita
            p.civic_opinion_consent = True
            p.civic_opinion_consent_at = now
            p.save(update_fields=['residency_territory', 'civic_opinion_consent', 'civic_opinion_consent_at'])
        self.stdout.write(f"Residency (Barbeita) + consent set for {len(users)} seed users")

        creator = users[0]

        polls_spec = [
            (barbeita, "Saturday use of the junta hall?",
             "The junta de freguesia hall is free on Saturdays — what should it host?",
             ["Kids activities", "Local music rehearsals", "Crafts workshop", "Undecided"],
             "Junta de Freguesia de Barbeita — informal signal"),
            (moncao, "Budget remainder: solar panels or road repair?",
             "About 20k EUR remain in the budget. Where should it go?",
             ["20 solar panels for the school", "Road repair M-X", "Split evenly", "Undecided"],
             "Camara Municipal de Moncao, target 2026-09-01"),
            (norte, "Norte region investment priority",
             "What should the region strengthen first?",
             ["Rail connections", "Regional hospitals", "Agriculture support", "Tourism", "Undecided"],
             ""),
            (pt, "Test country-level question (seed)",
             "Synthetic question for country-scope testing.",
             ["For", "Against", "Abstain"],
             ""),
        ]

        created = []
        for territory, title, desc, options, destination in polls_spec:
            ctx = PollContext.objects.create(
                context_type=PollContext.ContextType.TERRITORY,
                context_id=territory.id, created_by=creator)
            poll = Poll.objects.create(
                context=ctx, title=title, description=desc,
                start_time=now, end_time=None,
                poll_class=Poll.PollClass.OPINION,
                ballot_mode=Poll.BallotMode.ANONYMOUS,
                allow_delegation=False, use_weights=False,
                civic_destination=destination,
                status=Poll.Status.ACTIVE, created_by=creator,
                attributes={SEED_FLAG: True},
            )
            for i, text in enumerate(options):
                PollOption.objects.create(poll=poll, text=text, order=i)
            created.append(poll)
            self.stdout.write(f"  + [{territory.level}] {title}")

        # --- slider poll (region level): status-quo-relative axes ---
        slider_ctx = PollContext.objects.create(
            context_type=PollContext.ContextType.TERRITORY,
            context_id=norte.id, created_by=creator)
        slider_poll = Poll.objects.create(
            context=slider_ctx,
            title="Norte funding priorities (sliders)",
            description="Relative to today: should the region fund these more or less?",
            start_time=now, end_time=None,
            poll_class=Poll.PollClass.OPINION,
            ballot_mode=Poll.BallotMode.ANONYMOUS,
            poll_type=Poll.PollType.SLIDERS,
            allow_delegation=False, use_weights=False,
            status=Poll.Status.ACTIVE, created_by=creator,
            attributes={SEED_FLAG: True},
        )
        for i, axis in enumerate(["Healthcare", "Public transport", "Environment programs"]):
            PollOption.objects.create(poll=slider_poll, text=axis, order=i)
        created.append(slider_poll)
        self.stdout.write(f"  + [region/sliders] {slider_poll.title}")

        # --- a few votes on the municipal poll (varied options) ---
        muni_poll = created[1]
        opts_list = list(muni_poll.options.all())
        r = civic._redis()
        for i, p in enumerate(users):
            option = opts_list[i % (len(opts_list) - 1)]  # skip 'Не определился' mostly
            r.delete(f"civic:cd:{muni_poll.id}:{p.id}")
            try:
                civic.cast_opinion_vote(muni_poll, p, option)
            except civic.CivicVoteError as e:
                self.stderr.write(f"  vote failed for {p.id[:8]}: {e.message}")

        self.stdout.write(self.style.SUCCESS(
            f"seed_test_civic done: {len(created)} polls, votes on '{muni_poll.title[:30]}...'"
        ))
