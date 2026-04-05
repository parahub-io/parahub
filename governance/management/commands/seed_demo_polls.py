"""
Seed demo polls for Show HN readiness.
Creates 4 realistic community polls in different states with votes and delegations.
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

# Fixed ULIDs for demo poll contexts (deterministic for idempotent creation)
# Format: 00000000000000000000DEMO01..04
DEMO_CONTEXT_IDS = [
    '00000000000000000DEMO01',  # Poll 1 context
    '00000000000000000DEMO02',  # Poll 2 context
    '00000000000000000DEMO03',  # Poll 3 context
    '00000000000000000DEMO04',  # Poll 4 context
]


class Command(BaseCommand):
    help = 'Create demo polls for Show HN readiness'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete demo polls before recreating (only demo data)',
        )

    def _get_test_profiles(self):
        """Get alice, bob, charlie test profiles."""
        profiles = {}
        for name in ('alice', 'bob', 'charlie'):
            try:
                profiles[name] = Profile.objects.get(
                    local_name=name, instance__domain='parahub.io'
                )
            except Profile.DoesNotExist:
                pass
        return profiles

    def handle(self, *args, **options):
        if options['reset']:
            contexts = PollContext.objects.filter(context_id__in=DEMO_CONTEXT_IDS)
            poll_count = Poll.objects.filter(context__in=contexts).count()
            contexts.delete()
            self.stdout.write(self.style.WARNING(f'Deleted {poll_count} demo polls'))

        profiles = self._get_test_profiles()
        if len(profiles) < 3:
            self.stdout.write(self.style.ERROR(
                'Need alice, bob, charlie. Run: python3 manage.py seed_test_users --count 3'
            ))
            return

        alice, bob, charlie = profiles['alice'], profiles['bob'], profiles['charlie']
        now = timezone.now()
        created = 0

        # --- Poll 1: Active community decision (multiple choice, has votes) ---
        ctx1, _ = PollContext.objects.get_or_create(
            context_type='adhoc',
            context_id=DEMO_CONTEXT_IDS[0],
            defaults={'created_by': alice}
        )
        poll1, p1_new = Poll.objects.get_or_create(
            context=ctx1,
            title='Community garden: how to spend the maintenance budget?',
            defaults={
                'description': (
                    'Our community garden has €800 in the maintenance fund this quarter.\n\n'
                    'We need to decide how to allocate it. Options include new raised beds, '
                    'a drip irrigation system, compost bins, or a tool shed upgrade.\n\n'
                    'Please vote for your preferred option. Delegation is enabled — '
                    'if you trust someone\'s judgment, you can delegate your vote.'
                ),
                'poll_type': Poll.PollType.MULTIPLE_CHOICE,
                'start_time': now - timedelta(days=2),
                'end_time': now + timedelta(days=5),
                'warning_hours': 24,
                'quorum_type': Poll.QuorumType.SIMPLE_MAJORITY,
                'quorum_percent': Decimal('50.00'),
                'allow_delegation': True,
                'require_wot_verified': False,
                'public_results': True,
                'status': Poll.Status.ACTIVE,
                'created_by': alice,
            }
        )
        if p1_new:
            created += 1
            opts1 = []
            for i, (text, desc) in enumerate([
                ('New raised beds', 'Build 4 cedar raised beds (1.2m × 2.4m) for vegetables and herbs'),
                ('Drip irrigation system', 'Install automated drip irrigation with timer — saves water and time'),
                ('Compost station', '3-bin compost system with worm farm for organic waste recycling'),
                ('Tool shed upgrade', 'Repair roof, add shelving, and replace worn-out shared tools'),
            ]):
                opt = PollOption.objects.create(poll=poll1, text=text, description=desc, order=i)
                opts1.append(opt)

            for profile in (alice, bob, charlie):
                PollEligibleVoter.objects.create(poll=poll1, profile=profile, weight=Decimal('1.0000'))

            # Alice votes for irrigation
            PollVote.objects.create(
                poll=poll1, voter=alice, option=opts1[1],
                pgp_signature='DEMO_SIG_ALICE_P1',
                signed_payload={'poll_id': poll1.id, 'option_id': opts1[1].id,
                                'timestamp': now.isoformat()},
                effective_weight=Decimal('1.0000')
            )
            # Bob votes for raised beds
            PollVote.objects.create(
                poll=poll1, voter=bob, option=opts1[0],
                pgp_signature='DEMO_SIG_BOB_P1',
                signed_payload={'poll_id': poll1.id, 'option_id': opts1[0].id,
                                'timestamp': now.isoformat()},
                effective_weight=Decimal('1.0000')
            )
            AuditService.create_log_entry(
                poll=poll1, action='poll_created', actor=alice,
                payload={'poll_id': poll1.id, 'title': poll1.title},
                pgp_signature='DEMO_SIG',
            )
            self.stdout.write(self.style.SUCCESS(f'  ✓ Poll 1 (active, 2 votes): {poll1.title}'))

        # --- Poll 2: Active yes/no poll (simple, no votes yet) ---
        ctx2, _ = PollContext.objects.get_or_create(
            context_type='adhoc',
            context_id=DEMO_CONTEXT_IDS[1],
            defaults={'created_by': bob}
        )
        poll2, p2_new = Poll.objects.get_or_create(
            context=ctx2,
            title='Should we install solar panels on the community building?',
            defaults={
                'description': (
                    'A local installer quoted €4,200 for a 3kW rooftop solar system '
                    'on our community building. Expected payback: 5-6 years.\n\n'
                    'Government subsidy covers 30% of the cost. The remaining €2,940 '
                    'would come from the building reserve fund.\n\n'
                    'This is a binding vote — qualified majority (2/3) required.'
                ),
                'poll_type': Poll.PollType.SIMPLE,
                'start_time': now - timedelta(hours=6),
                'end_time': now + timedelta(days=14),
                'warning_hours': 48,
                'quorum_type': Poll.QuorumType.QUALIFIED_MAJORITY,
                'quorum_percent': Decimal('66.67'),
                'allow_delegation': True,
                'require_wot_verified': False,
                'public_results': True,
                'status': Poll.Status.ACTIVE,
                'created_by': bob,
            }
        )
        if p2_new:
            created += 1
            PollOption.objects.create(poll=poll2, text='Yes — install solar panels', order=0)
            PollOption.objects.create(poll=poll2, text='No — keep the reserve fund intact', order=1)

            for profile in (alice, bob, charlie):
                PollEligibleVoter.objects.create(poll=poll2, profile=profile, weight=Decimal('1.0000'))

            AuditService.create_log_entry(
                poll=poll2, action='poll_created', actor=bob,
                payload={'poll_id': poll2.id, 'title': poll2.title},
                pgp_signature='DEMO_SIG',
            )
            self.stdout.write(self.style.SUCCESS(f'  ✓ Poll 2 (active, 0 votes): {poll2.title}'))

        # --- Poll 3: Active with delegation ---
        ctx3, _ = PollContext.objects.get_or_create(
            context_type='adhoc',
            context_id=DEMO_CONTEXT_IDS[2],
            defaults={'created_by': charlie}
        )
        poll3, p3_new = Poll.objects.get_or_create(
            context=ctx3,
            title='What should be the theme of our next community event?',
            defaults={
                'description': (
                    'We plan a community get-together for next month and need to pick a theme.\n\n'
                    'The event will be held in the community garden (weather permitting) '
                    'or in the co-working space if it rains.\n\n'
                    'Budget: €200 from the social fund.'
                ),
                'poll_type': Poll.PollType.MULTIPLE_CHOICE,
                'start_time': now - timedelta(days=1),
                'end_time': now + timedelta(days=10),
                'warning_hours': 24,
                'quorum_type': Poll.QuorumType.SIMPLE_MAJORITY,
                'quorum_percent': Decimal('50.00'),
                'allow_delegation': True,
                'require_wot_verified': False,
                'public_results': True,
                'status': Poll.Status.ACTIVE,
                'created_by': charlie,
            }
        )
        if p3_new:
            created += 1
            opts3 = []
            for i, (text, desc) in enumerate([
                ('Open-air cinema night', 'Screen a film on a projector with blankets and popcorn'),
                ('Potluck dinner', 'Everyone brings a dish from their home cuisine — share food, share stories'),
                ('Repair café', 'Bring broken items, fix them together. Reduce waste, learn skills'),
                ('Skill swap workshop', 'Each person teaches a 20-minute mini-class on something they know'),
                ('Board game tournament', 'Bring your favorite games — prizes for the winners'),
            ]):
                opt = PollOption.objects.create(poll=poll3, text=text, description=desc, order=i)
                opts3.append(opt)

            for profile in (alice, bob, charlie):
                PollEligibleVoter.objects.create(poll=poll3, profile=profile, weight=Decimal('1.0000'))

            # Charlie votes for repair café
            PollVote.objects.create(
                poll=poll3, voter=charlie, option=opts3[2],
                pgp_signature='DEMO_SIG_CHARLIE_P3',
                signed_payload={'poll_id': poll3.id, 'option_id': opts3[2].id,
                                'timestamp': now.isoformat()},
                effective_weight=Decimal('1.0000')
            )
            # Alice delegates to Charlie (liquid democracy demo)
            PollVoteDelegation.objects.create(
                poll=poll3, delegator=alice, delegate=charlie,
                pgp_signature='DEMO_SIG_ALICE_DELEG_P3',
                signed_payload={
                    'poll_id': poll3.id,
                    'delegate_id': charlie.id,
                    'timestamp': now.isoformat(),
                },
            )

            AuditService.create_log_entry(
                poll=poll3, action='poll_created', actor=charlie,
                payload={'poll_id': poll3.id, 'title': poll3.title},
                pgp_signature='DEMO_SIG',
            )
            self.stdout.write(self.style.SUCCESS(f'  ✓ Poll 3 (active, 1 vote + 1 delegation): {poll3.title}'))

        # --- Poll 4: Completed poll (ended, shows results) ---
        ctx4, _ = PollContext.objects.get_or_create(
            context_type='adhoc',
            context_id=DEMO_CONTEXT_IDS[3],
            defaults={'created_by': alice}
        )
        poll4, p4_new = Poll.objects.get_or_create(
            context=ctx4,
            title='Which day works best for weekly community meetings?',
            defaults={
                'description': (
                    'We need to settle on a regular meeting day for our weekly stand-up.\n\n'
                    'The meeting will be 30 minutes, either in-person or via Jitsi.'
                ),
                'poll_type': Poll.PollType.MULTIPLE_CHOICE,
                'start_time': now - timedelta(days=14),
                'end_time': now - timedelta(days=7),
                'warning_hours': 24,
                'quorum_type': Poll.QuorumType.SIMPLE_MAJORITY,
                'quorum_percent': Decimal('50.00'),
                'allow_delegation': False,
                'require_wot_verified': False,
                'public_results': True,
                'status': Poll.Status.ENDED,
                'created_by': alice,
            }
        )
        if p4_new:
            created += 1
            opts4 = []
            for i, text in enumerate(['Tuesday evening', 'Wednesday lunch', 'Thursday evening', 'Saturday morning']):
                opt = PollOption.objects.create(poll=poll4, text=text, order=i)
                opts4.append(opt)

            for profile in (alice, bob, charlie):
                PollEligibleVoter.objects.create(poll=poll4, profile=profile, weight=Decimal('1.0000'))

            # All 3 voted — Thursday won
            PollVote.objects.create(
                poll=poll4, voter=alice, option=opts4[2],
                pgp_signature='DEMO_SIG_ALICE_P4',
                signed_payload={'poll_id': poll4.id, 'option_id': opts4[2].id,
                                'timestamp': (now - timedelta(days=10)).isoformat()},
                effective_weight=Decimal('1.0000')
            )
            PollVote.objects.create(
                poll=poll4, voter=bob, option=opts4[2],
                pgp_signature='DEMO_SIG_BOB_P4',
                signed_payload={'poll_id': poll4.id, 'option_id': opts4[2].id,
                                'timestamp': (now - timedelta(days=9)).isoformat()},
                effective_weight=Decimal('1.0000')
            )
            PollVote.objects.create(
                poll=poll4, voter=charlie, option=opts4[0],
                pgp_signature='DEMO_SIG_CHARLIE_P4',
                signed_payload={'poll_id': poll4.id, 'option_id': opts4[0].id,
                                'timestamp': (now - timedelta(days=8)).isoformat()},
                effective_weight=Decimal('1.0000')
            )

            AuditService.create_log_entry(
                poll=poll4, action='poll_created', actor=alice,
                payload={'poll_id': poll4.id, 'title': poll4.title},
                pgp_signature='DEMO_SIG',
            )
            self.stdout.write(self.style.SUCCESS(f'  ✓ Poll 4 (ended, 3 votes): {poll4.title}'))

        self.stdout.write(self.style.SUCCESS(f'\nTotal: {created} demo polls created'))
