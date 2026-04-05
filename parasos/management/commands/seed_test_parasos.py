from django.core.management.base import BaseCommand
from django.contrib.gis.geos import Point
from django.utils import timezone
from parasos.models import SafetyGroup, SafetyGroupMember, SOSAlert, SOSResponse
from identity.models import Profile


class Command(BaseCommand):
    help = 'Create test ParaSOS safety groups, members, and alerts'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete existing test ParaSOS data before creating new ones',
        )

    def handle(self, *args, **options):
        reset = options['reset']

        # Get test profiles
        try:
            alice = Profile.objects.get(local_name='alice', instance__domain='parahub.io')
        except Profile.DoesNotExist:
            self.stdout.write(self.style.ERROR('Alice profile not found. Run: python3 manage.py seed_test_users'))
            return

        bob = Profile.objects.filter(local_name='bob', instance__domain='parahub.io').first()
        charlie = Profile.objects.filter(local_name='charlie', instance__domain='parahub.io').first()

        # Try to get norn as REMOTE member
        norn = Profile.objects.filter(local_name='norn', instance__domain='parahub.io').first()

        if reset:
            count = SOSResponse.objects.all().delete()[0]
            count += SOSAlert.objects.all().delete()[0]
            count += SafetyGroupMember.objects.all().delete()[0]
            count += SafetyGroup.objects.all().delete()[0]
            self.stdout.write(self.style.WARNING(f'Deleted {count} ParaSOS objects'))

        # === Group 1: Podame village (active, with SOS) ===
        podame, created = SafetyGroup.objects.get_or_create(
            name='Vizinhos de Podame',
            defaults={
                'description': 'Grupo de segurança para a aldeia de Podame, Viana do Castelo',
                'created_by': alice,
                'center': Point(-8.386, 41.842, srid=4326),
                'radius_m': 1500,
                'quiet_hours_start': 23,
                'quiet_hours_end': 7,
            },
        )
        if created:
            self.stdout.write(f'  Created group: {podame.name}')
        else:
            self.stdout.write(f'  Exists: {podame.name}')

        # Add members
        members_added = 0
        for profile, role, presence in [
            (alice, 'ADMIN', 'LOCAL'),
            (bob, 'MEMBER', 'LOCAL'),
            (charlie, 'MEMBER', 'LOCAL'),
            (norn, 'MEMBER', 'REMOTE'),
        ]:
            if not profile:
                continue
            _, created = SafetyGroupMember.objects.get_or_create(
                group=podame, profile=profile,
                defaults={
                    'role': role,
                    'presence': presence,
                    'emergency_context': 'No known allergies' if presence == 'LOCAL' else 'Emergency contact: +351 912 345 678',
                },
            )
            if created:
                members_added += 1

        podame.members_count = podame.members.count()
        podame.save(update_fields=['members_count'])
        self.stdout.write(f'  Members: {podame.members_count} ({members_added} new)')

        # Create an active EMERGENCY alert from alice
        alert, created = SOSAlert.objects.get_or_create(
            group=podame,
            sender=alice,
            status=SOSAlert.Status.ACTIVE,
            defaults={
                'level': 'EMERGENCY',
                'category': 'INTRUSION',
                'message': 'Alguém está a tentar entrar na minha casa!',
                'location': Point(-8.3855, 41.8425, srid=4326),
                'source': 'MANUAL',
            },
        )
        if created:
            self.stdout.write(f'  Created active alert: EMERGENCY from alice')

            # Bob responded ON_WAY
            if bob:
                SOSResponse.objects.get_or_create(
                    alert=alert, responder=bob,
                    defaults={'status': 'ON_WAY', 'note': 'Estou a caminho, 3 minutos'},
                )
            # Charlie responded SEEN
            if charlie:
                SOSResponse.objects.get_or_create(
                    alert=alert, responder=charlie,
                    defaults={'status': 'SEEN'},
                )

            alert.seen_count = alert.responses.count()
            alert.responding_count = alert.responses.filter(
                status__in=['ON_WAY', 'ON_SITE'],
            ).count()
            alert.save(update_fields=['seen_count', 'responding_count'])
        else:
            self.stdout.write(f'  Exists: active alert')

        # Create a resolved INFO alert (history)
        resolved, created = SOSAlert.objects.get_or_create(
            group=podame,
            sender=alice,
            status=SOSAlert.Status.RESOLVED,
            level='INFO',
            defaults={
                'category': 'SUSPICIOUS_ACTIVITY',
                'message': 'Carro desconhecido parado em frente à casa há 30 minutos',
                'location': Point(-8.386, 41.842, srid=4326),
                'source': 'MANUAL',
                'resolved_at': timezone.now(),
                'resolved_by': alice,
            },
        )
        if created:
            self.stdout.write(f'  Created resolved alert: INFO (suspicious car)')

        # === Group 2: Lisbon neighborhood (empty, for testing join) ===
        lisbon, created = SafetyGroup.objects.get_or_create(
            name='Vizinhos de Alfama',
            defaults={
                'description': 'Grupo de segurança para o bairro de Alfama, Lisboa',
                'created_by': alice,
                'center': Point(-9.1305, 38.7119, srid=4326),
                'radius_m': 500,
            },
        )
        if created:
            SafetyGroupMember.objects.get_or_create(
                group=lisbon, profile=alice,
                defaults={'role': 'ADMIN', 'presence': 'LOCAL'},
            )
            lisbon.members_count = 1
            lisbon.save(update_fields=['members_count'])
            self.stdout.write(f'  Created group: {lisbon.name} (1 member, no alerts)')
        else:
            self.stdout.write(f'  Exists: {lisbon.name}')

        self.stdout.write(self.style.SUCCESS('\nDone! Groups: 2, active alert in Podame'))
