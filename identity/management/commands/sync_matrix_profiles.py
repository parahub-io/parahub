"""Mirror primary-profile display names and avatars onto their Matrix users.

Runtime mirroring happens on the avatar write paths and on Matrix session mint;
this command is the backfill for profiles whose avatar predates that wiring, and
the repair tool after a Synapse media loss.

Accounts MAS does not know are skipped, never provisioned — see
`sync_matrix_profile`.
"""

from django.core.management.base import BaseCommand

from identity.models import Profile
from parahub.endpoints.matrix_auth import get_matrix_user_id, sync_matrix_profile


class Command(BaseCommand):
    help = "Mirror primary-profile display names and avatars onto their Matrix users"

    def add_arguments(self, parser):
        parser.add_argument('--username', help="Sync a single account by username")
        parser.add_argument(
            '--all', action='store_true',
            help="Include profiles with no avatar (clears a stale Matrix avatar)",
        )
        parser.add_argument(
            '--force', action='store_true',
            help="Re-upload even when the avatar is unchanged",
        )
        parser.add_argument('--dry-run', action='store_true', help="List targets, change nothing")

    def handle(self, *args, **options):
        profiles = (
            Profile.objects.filter(is_primary=True)
            .select_related('account', 'instance')
            .order_by('local_name')
        )
        if options['username']:
            profiles = profiles.filter(account__username=options['username'])
        elif not options['all']:
            profiles = profiles.exclude(avatar='').exclude(avatar__isnull=True)

        synced = skipped = 0
        for profile in profiles:
            matrix_user_id = get_matrix_user_id(str(profile.account_id))
            avatar = profile.avatar.name if profile.avatar else '(no avatar)'

            if options['dry_run']:
                self.stdout.write(f"  would sync {matrix_user_id} — {avatar}")
                continue

            if sync_matrix_profile(str(profile.account_id), force=options['force']):
                synced += 1
                self.stdout.write(self.style.SUCCESS(f"  synced {matrix_user_id} — {avatar}"))
            else:
                skipped += 1
                self.stdout.write(f"  skipped {matrix_user_id} (no Matrix user, or sync failed — see log)")

        if not options['dry_run']:
            self.stdout.write(self.style.SUCCESS(f"Done: {synced} synced, {skipped} skipped"))
