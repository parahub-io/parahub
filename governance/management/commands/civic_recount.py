"""
civic_recount — rebuild (or verify) Redis opinion-poll aggregates from PostgreSQL.

Usage:
    python3 manage.py civic_recount                 # rebuild all opinion polls
    python3 manage.py civic_recount --poll <ULID>   # one poll
    python3 manage.py civic_recount --verify        # report drift, change nothing
"""
from django.core.management.base import BaseCommand, CommandError

from governance.models import Poll
from governance import civic


class Command(BaseCommand):
    help = "Rebuild or verify Redis civic aggregates from PostgreSQL (CQRS repair)"

    def add_arguments(self, parser):
        parser.add_argument('--poll', type=str, default=None)
        parser.add_argument('--verify', action='store_true', help='Compare only, do not write')

    def handle(self, *args, **opts):
        if opts['poll']:
            polls = Poll.objects.filter(id=opts['poll'], poll_class=Poll.PollClass.OPINION)
            if not polls.exists():
                raise CommandError(f"Opinion poll {opts['poll']} not found")
        else:
            polls = Poll.objects.filter(poll_class=Poll.PollClass.OPINION, frozen_results__isnull=True)

        drifted = 0
        for poll in polls.iterator():
            truth = civic.recount_poll(poll, verify_only=True)
            r = civic._redis()
            redis_counts = {k: int(v) for k, v in r.hgetall(f"civic:{poll.id}:counts").items()}
            clean_truth = {k: v for k, v in truth['counts'].items() if v}
            clean_redis = {k: v for k, v in redis_counts.items() if v}
            if clean_truth != clean_redis:
                drifted += 1
                self.stdout.write(f"DRIFT {poll.id[:10]} '{poll.title[:40]}': pg={clean_truth} redis={clean_redis}")
                if not opts['verify']:
                    civic.recount_poll(poll)
                    self.stdout.write(f"  → rebuilt")
            elif opts['verify']:
                self.stdout.write(f"OK    {poll.id[:10]} n={sum(clean_truth.values())}")

        verb = 'verified' if opts['verify'] else 'processed'
        style = self.style.SUCCESS if drifted == 0 else self.style.WARNING
        self.stdout.write(style(f"civic_recount: {polls.count()} polls {verb}, {drifted} drifted"))
