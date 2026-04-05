"""
Management command to create Mailcow mailboxes for existing users who don't have one yet,
and to backfill encrypted passwords for users whose mailbox exists but password is not stored.
"""
from django.core.management.base import BaseCommand
from identity.models import Account
from parahub.services.mailcow import MailcowService, encrypt_mail_password
import logging

logger = logging.getLogger('parahub.mailcow')


class Command(BaseCommand):
    help = 'Create @parahub.io mailboxes for existing users; use --backfill-passwords to reset passwords for existing mailboxes without stored password'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Show what would be done without doing it')
        parser.add_argument('--backfill-passwords', action='store_true',
                            help='Reset Mailcow password for accounts that have a mailbox but no stored password')
        parser.add_argument('--force-reset-all', action='store_true',
                            help='Force reset Mailcow password for ALL accounts (use after API fix)')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        backfill = options['backfill_passwords']
        force_reset = options['force_reset_all']
        accounts = Account.objects.filter(is_active=True).exclude(username='admin')

        created = skipped = updated = errors = 0

        for account in accounts:
            username = account.username
            try:
                exists = MailcowService.mailbox_exists(username)

                if not exists:
                    if dry_run:
                        self.stdout.write(self.style.WARNING(f'  [dry]  would create {username}@parahub.io'))
                    else:
                        display_name = account.get_full_name() or username
                        result = MailcowService.create_mailbox(username, display_name)
                        Account.objects.filter(pk=account.pk).update(
                            mail_password=encrypt_mail_password(result['password'])
                        )
                        self.stdout.write(self.style.SUCCESS(f'  create {username}@parahub.io'))
                        created += 1

                elif (backfill and not account.mail_password) or force_reset:
                    # Mailbox exists — reset password (backfill if no stored, or force-reset all)
                    if dry_run:
                        self.stdout.write(self.style.WARNING(f'  [dry]  would reset password for {username}@parahub.io'))
                    else:
                        new_password = MailcowService._generate_password()
                        ok = MailcowService.set_mailbox_password(username, new_password)
                        if ok:
                            Account.objects.filter(pk=account.pk).update(
                                mail_password=encrypt_mail_password(new_password)
                            )
                            self.stdout.write(self.style.SUCCESS(f'  reset  {username}@parahub.io'))
                            updated += 1
                        else:
                            self.stdout.write(self.style.ERROR(f'  error  {username}: API returned non-200'))
                            errors += 1
                else:
                    self.stdout.write(f'  skip  {username}@parahub.io')
                    skipped += 1

            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  error  {username}: {e}'))
                errors += 1

        self.stdout.write('')
        self.stdout.write(f'Done. created={created}, updated={updated}, skipped={skipped}, errors={errors}')
        if dry_run:
            self.stdout.write('(dry-run, nothing was changed)')
