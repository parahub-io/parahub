"""
Management command to recalculate reputation scores for all profiles.

Usage:
    python3 manage.py recalculate_reputation [--reset] [--verbose]
"""

from decimal import Decimal

from django.core.management.base import BaseCommand

from identity.models import Profile
from identity.reputation import calculate_reputation


class Command(BaseCommand):
    help = 'Recalculate 6-dimension reputation scores for all profiles'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset', action='store_true',
            help='Also recalculate seed/test profiles',
        )
        parser.add_argument(
            '--verbose', action='store_true',
            help='Print per-profile breakdown',
        )

    def handle(self, *args, **options):
        verbose = options['verbose']
        reset = options['reset']

        qs = Profile.objects.select_related('account').all()
        if not reset:
            qs = qs.filter(account__is_test=False)

        updated = 0
        significant = 0

        for profile in qs.iterator():
            old_score = profile.reputation_score
            result = calculate_reputation(profile)
            new_score = result['total']

            if verbose:
                self.stdout.write(
                    f"{profile.hna:30s}  "
                    f"I={result['identity']:6.2f}  "
                    f"C={result['commerce']:6.2f}  "
                    f"Cm={result['community']:6.2f}  "
                    f"Ct={result['contribution']:6.2f}  "
                    f"G={result['governance']:6.2f}  "
                    f"R={result['reliability']:6.2f}  "
                    f"T={new_score:6.2f}  "
                    f"A={result['active_dimensions']}  "
                    f"(was {old_score:.2f})"
                )

            if new_score != old_score:
                profile.reputation_score = new_score
                profile.save(update_fields=['reputation_score'])
                updated += 1

                delta = abs(new_score - old_score)
                if delta > 10:
                    significant += 1
                    if not verbose:
                        self.stdout.write(
                            f"  Significant change: {profile.hna} "
                            f"{old_score:.2f} → {new_score:.2f} (Δ{delta:.2f})"
                        )

        self.stdout.write(self.style.SUCCESS(
            f"Done. {updated} profiles updated, {significant} significant changes (>10 pts)."
        ))
