"""The WebSocket contract the recorder on `/talk` is written against.

Every message shape here is one the frontend branches on, so a rename that looks
harmless in Python breaks a page that no Python test would notice. The pipeline
itself is stubbed — what is under test is the protocol: who may connect, what
order the frames come in, and which refusals carry which code.
"""

from unittest.mock import AsyncMock, patch

from django.contrib.auth.models import AnonymousUser
from django.test import TransactionTestCase
from django.utils import timezone

from core.models import Instance
from identity.models import Account, Profile, ProfileBlock
from parahub.testing import WebsocketCommunicator
from voice.consumers import VoiceNoteConsumer
from voice.models import VoiceNote
from voice.services import notes as notes_service

PATH = '/ws/v1/voice/notes/'
AUDIO = b'\x1a\x45\xdf\xa3' + b'\x00' * 4000  # webm magic + enough bytes to pass the floor


def _profile(instance, username, language='en'):
    account = Account.objects.create_user(
        username=username, email=f'{username}@test.parahub.io',
        password='x', instance=instance)
    return Profile.objects.create(
        account=account, instance=instance, local_name=username,
        display_name=username.title(), is_primary=True,
        preferred_language=language)


class VoiceNoteConsumerTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # These tests commit for real (TransactionTestCase), which fires the
        # Neo4j profile sync — and Neo4j is deliberately unreachable under test
        # (settings.py points it at a dead port). Its background retries hold DB
        # connections open past teardown, so the runner then cannot drop the
        # test database. Nothing here touches the graph; disconnect it.
        from django.db.models.signals import post_save

        from barter.signals import sync_profile_to_neo4j
        post_save.disconnect(sync_profile_to_neo4j, sender=Profile)
        cls.addClassCleanup(post_save.connect, sync_profile_to_neo4j, sender=Profile)

    def setUp(self):
        self.instance = Instance.objects.create(
            domain='test.parahub.io', name='Test', public_key='k',
            trust_level='local')
        self.norn = _profile(self.instance, 'wsnorn', 'ru')
        self.monica = _profile(self.instance, 'wsmonica', 'pt')

    def _communicator(self, profile):
        # The JWT middleware fills these in production; here they are the input.
        return WebsocketCommunicator(VoiceNoteConsumer.as_asgi(), PATH, scope={
            'user': profile.account if profile else AnonymousUser(),
            'profile': profile,
        })

    async def _connected(self, profile):
        """Connect and swallow the two frames every session opens with."""
        communicator = self._communicator(profile)
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.receive_json_from()  # connection.established
        ready = await communicator.receive_json_from()
        self.assertEqual(ready['type'], 'ready')
        return communicator, ready

    async def test_anonymous_is_accepted_then_closed_with_a_reason(self):
        """Refusing *after* accepting is deliberate, not sloppy.

        A close before the accept answers the upgrade with HTTP 403, which the
        Android WebView paints as a full-page system error over the app. The
        client gets a reason it can render instead.
        """
        communicator = self._communicator(None)
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.receive_json_from()  # connection.established
        refusal = await communicator.receive_json_from()
        self.assertEqual(refusal['code'], 'unauthenticated')
        closed = await communicator.receive_output()
        self.assertEqual(closed['type'], 'websocket.close')
        self.assertEqual(closed['code'], 4001)

    async def test_ready_carries_the_quota_and_the_limits(self):
        communicator, ready = await self._connected(self.norn)
        self.assertEqual(ready['profile_id'], self.norn.id)
        self.assertEqual(ready['quota']['limit_seconds'], notes_service.FREE_MONTHLY_SECONDS)
        self.assertEqual(ready['limits']['max_bytes'], notes_service.MAX_AUDIO_BYTES)
        await communicator.disconnect()

    async def test_begin_resolves_the_recipient_by_handle(self):
        communicator, _ = await self._connected(self.norn)
        await communicator.send_json_to({'type': 'note.begin', 'recipient_id': 'wsmonica'})
        answer = await communicator.receive_json_from()
        self.assertEqual(answer['type'], 'note.ready')
        self.assertEqual(answer['recipient']['id'], self.monica.id)
        self.assertEqual(answer['recipient']['language'], 'pt')
        await communicator.disconnect()

    async def test_audio_without_a_recipient_is_refused(self):
        communicator, _ = await self._connected(self.norn)
        await communicator.send_to(bytes_data=AUDIO)
        answer = await communicator.receive_json_from()
        self.assertEqual(answer['code'], 'no_recipient')
        await communicator.disconnect()

    async def test_a_note_to_yourself_is_refused(self):
        communicator, _ = await self._connected(self.norn)
        await communicator.send_json_to({'type': 'note.begin', 'recipient_id': 'wsnorn'})
        answer = await communicator.receive_json_from()
        self.assertEqual(answer['code'], 'self_note')
        await communicator.disconnect()

    async def test_unknown_recipient_is_refused(self):
        communicator, _ = await self._connected(self.norn)
        await communicator.send_json_to({'type': 'note.begin', 'recipient_id': 'nobody'})
        answer = await communicator.receive_json_from()
        self.assertEqual(answer['code'], 'recipient_not_found')
        await communicator.disconnect()

    async def test_a_block_closes_the_channel_in_both_directions(self):
        from channels.db import database_sync_to_async
        await database_sync_to_async(ProfileBlock.objects.create)(
            blocker=self.monica, blocked=self.norn)

        communicator, _ = await self._connected(self.norn)
        await communicator.send_json_to({'type': 'note.begin', 'recipient_id': 'wsmonica'})
        answer = await communicator.receive_json_from()
        # Deliberately not "they blocked you" — the message names no direction.
        self.assertEqual(answer['code'], 'blocked')
        await communicator.disconnect()

    async def test_oversized_audio_is_refused_before_any_provider_call(self):
        communicator, _ = await self._connected(self.norn)
        await communicator.send_json_to({'type': 'note.begin', 'recipient_id': 'wsmonica'})
        await communicator.receive_json_from()

        with patch('voice.services.notes.create_note', new=AsyncMock()) as create:
            await communicator.send_to(bytes_data=b'\x00' * (notes_service.MAX_AUDIO_BYTES + 1))
            answer = await communicator.receive_json_from()
        self.assertEqual(answer['code'], 'audio_too_large')
        create.assert_not_called()
        await communicator.disconnect()

    async def test_a_finished_note_comes_back_with_the_texts_and_the_quota(self):
        from channels.db import database_sync_to_async

        note = await database_sync_to_async(VoiceNote.objects.create)(
            sender=self.norn, recipient=self.monica,
            source_lang='ru', target_lang='pt',
            source_text='привет', target_text='olá',
            audio_seconds=3.0, delivered_at=timezone.now(),
        )
        communicator, _ = await self._connected(self.norn)
        await communicator.send_json_to({'type': 'note.begin', 'recipient_id': 'wsmonica'})
        await communicator.receive_json_from()

        async def _fake_create(sender, recipient, audio, on_status=None):
            await on_status('transcribing')
            await on_status('speaking')
            return note

        with patch('voice.services.notes.create_note', new=_fake_create):
            await communicator.send_to(bytes_data=AUDIO)
            first = await communicator.receive_json_from()
            second = await communicator.receive_json_from()
            final = await communicator.receive_json_from()

        self.assertEqual((first['type'], first['status']), ('status', 'transcribing'))
        self.assertEqual(second['status'], 'speaking')
        self.assertEqual(final['type'], 'note')
        self.assertEqual(final['note']['source_text'], 'привет')
        self.assertEqual(final['note']['target_text'], 'olá')
        self.assertEqual(final['note']['direction'], 'out')
        self.assertTrue(final['note']['synthetic_voice'])
        self.assertIn('used_seconds', final['quota'])
        await communicator.disconnect()

    async def test_quota_refusal_names_the_numbers_the_ui_shows(self):
        communicator, _ = await self._connected(self.norn)
        await communicator.send_json_to({'type': 'note.begin', 'recipient_id': 'wsmonica'})
        await communicator.receive_json_from()

        async def _over_quota(*args, **kwargs):
            raise notes_service.QuotaExceeded(1800.0, 1800.0)

        with patch('voice.services.notes.create_note', new=_over_quota):
            await communicator.send_to(bytes_data=AUDIO)
            answer = await communicator.receive_json_from()

        self.assertEqual(answer['code'], 'quota_exceeded')
        self.assertEqual(answer['minutes_used'], 30.0)
        self.assertEqual(answer['minutes_limit'], 30.0)
        await communicator.disconnect()
