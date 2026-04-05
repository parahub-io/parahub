"""
Management command to seed test poll data
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from identity.models import Profile
from governance.models import (
    Poll, PollContext, PollOption, PollEligibleVoter,
    PollVote, PollVoteDelegation
)
from governance.services import AuditService


class Command(BaseCommand):
    help = 'Seed test poll data for testing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete all existing polls before seeding',
        )

    def handle(self, *args, **options):
        if options['reset']:
            self.stdout.write('Deleting existing polls...')
            Poll.objects.all().delete()
            PollContext.objects.all().delete()
            self.stdout.write(self.style.SUCCESS('✓ Deleted all polls'))

        # Get test profiles (any 3 personal profiles)
        profiles = list(Profile.objects.filter(profile_type='PERSONAL')[:3])

        if len(profiles) < 3:
            self.stdout.write(self.style.ERROR(
                'Need at least 3 profiles. Run: python3 manage.py seed_test_users --count 3'
            ))
            return

        alice, bob, carol = profiles[0], profiles[1], profiles[2]

        self.stdout.write(f'Using profiles:')
        self.stdout.write(f'  Alice: {alice.hna}')
        self.stdout.write(f'  Bob: {bob.hna}')
        self.stdout.write(f'  Carol: {carol.hna}')

        # Create test poll
        self.stdout.write('Creating test poll...')

        context = PollContext.objects.create(
            context_type='adhoc',
            context_id='01K7M4MDWPFZ5WQ4A5GRPPVZR2',
            created_by=alice
        )

        poll = Poll.objects.create(
            context=context,
            title='Куда потратить бюджет на благоустройство?',
            description='''На счету ТСЖ накопилось 500 000 руб.
Предлагаю проголосовать за направление трат на благоустройство территории.

Варианты:
1. Ремонт детской площадки
2. Покраска фасада
3. Установка камер видеонаблюдения

Голосование открыто до 15 ноября 2025 года.''',
            poll_type=Poll.PollType.MULTIPLE_CHOICE,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(days=7),
            warning_hours=24,
            quorum_type=Poll.QuorumType.SIMPLE_MAJORITY,
            quorum_percent=Decimal('50.00'),
            allow_delegation=True,
            require_wot_verified=False,
            public_results=True,
            status=Poll.Status.ACTIVE,
            created_by=alice
        )

        # Audit: poll created
        AuditService.create_log_entry(
            poll=poll,
            action='poll_created',
            actor=alice,
            payload={
                'poll_id': poll.id,
                'title': poll.title,
                'poll_type': poll.poll_type,
            },
            pgp_signature='MOCK_SIGNATURE_SEED',
        )

        # Create options
        option1 = PollOption.objects.create(
            poll=poll,
            text='Ремонт детской площадки',
            description='Замена качелей, песочницы и установка нового оборудования',
            order=0
        )

        PollOption.objects.create(
            poll=poll,
            text='Покраска фасада',
            description='Покраска фасада здания в новый цвет',
            order=1
        )

        PollOption.objects.create(
            poll=poll,
            text='Установка камер видеонаблюдения',
            description='Установка 8 камер по периметру здания',
            order=2
        )

        # Add eligible voters
        PollEligibleVoter.objects.create(
            poll=poll,
            profile=alice,
            weight=Decimal('1.0000')
        )

        PollEligibleVoter.objects.create(
            poll=poll,
            profile=bob,
            weight=Decimal('1.0000')
        )

        PollEligibleVoter.objects.create(
            poll=poll,
            profile=carol,
            weight=Decimal('1.0000')
        )

        # Alice votes for option1
        vote = PollVote.objects.create(
            poll=poll,
            voter=alice,
            option=option1,
            pgp_signature='MOCK_SIGNATURE_ALICE',
            signed_payload={
                'poll_id': poll.id,
                'option_id': option1.id,
                'timestamp': timezone.now().isoformat()
            },
            effective_weight=Decimal('1.0000')
        )

        # Audit: vote cast
        AuditService.create_log_entry(
            poll=poll,
            action='vote_cast',
            actor=alice,
            payload={
                'vote_id': vote.id,
                'option_id': option1.id,
                'effective_weight': str(Decimal('1.0000')),
            },
            pgp_signature='MOCK_SIGNATURE_ALICE',
        )

        self.stdout.write(self.style.SUCCESS(
            f'✓ Created test poll: {poll.id}'
        ))
        self.stdout.write(f'  Title: {poll.title}')
        self.stdout.write(f'  Options: {poll.options.count()}')
        self.stdout.write(f'  Eligible voters: {poll.eligible_voters.count()}')
        self.stdout.write(f'  Status: {poll.status}')
        self.stdout.write(f'  URL: https://parahub.io/governance/polls/{poll.id}')
