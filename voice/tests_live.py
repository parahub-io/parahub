"""Live mode: the direction rule, the privacy rule, and the wire protocol.

Two of these are load-bearing beyond the feature and would fail silently:

- **Nothing but the meter survives a turn.** The guest across the table has no
  account and agreed to nothing, so no transcript, no translation and no
  recording may be written down — and a stray `retain_sample()` call would feed
  a stranger's voice into the account holder's clone without anyone noticing.
- **Both surfaces draw on one allowance.** Live turns that did not count would
  be a hole in the quota, and the hole would only show up on a provider bill.
"""

from unittest.mock import AsyncMock, patch

from django.contrib.auth.models import AnonymousUser
from django.test import TransactionTestCase

from core.models import Instance
from identity.models import Account, Profile
from parahub.testing import WebsocketCommunicator
from voice.consumers import VoiceNoteConsumer
from voice.models import CONSENT_TEXT_VERSION, VoiceClone, VoiceConsent, VoiceLiveTurn, VoiceNote
from voice.services import live as live_service
from voice.services import notes as notes_service
from voice.services import pipeline

PATH = '/ws/v1/voice/notes/'
AUDIO = b'\x1a\x45\xdf\xa3' + b'\x00' * 4000  # webm magic + enough bytes to pass the floor
MP3 = b'\xff\xfb' + b'\x00' * 200


def _profile(instance, username, language='en'):
    account = Account.objects.create_user(
        username=username, email=f'{username}@test.parahub.io',
        password='x', instance=instance)
    return Profile.objects.create(
        account=account, instance=instance, local_name=username,
        display_name=username.title(), is_primary=True,
        preferred_language=language)


class ResolveDirectionTests(TransactionTestCase):
    """Whoever actually spoke owns the turn — the buttons are only a guess.

    On a shared phone the guest reaches over and talks into the host's half
    constantly. Left uncorrected the turn is wasted: the translator is told the
    message is already in the target language and repeats it verbatim.
    """

    def test_the_expected_language_leaves_the_turn_alone(self):
        self.assertEqual(
            live_service.resolve_direction('HOST', 'ru', 'pt', 'ru'),
            ('HOST', 'ru', 'pt'))

    def test_the_other_half_language_flips_the_pair_and_the_side(self):
        self.assertEqual(
            live_service.resolve_direction('HOST', 'ru', 'pt', 'pt'),
            ('GUEST', 'pt', 'ru'))
        self.assertEqual(
            live_service.resolve_direction('GUEST', 'pt', 'ru', 'ru'),
            ('HOST', 'ru', 'pt'))

    def test_a_third_language_never_overrides_the_pickers(self):
        """The pair is the user's choice; detection only reorders it.

        Detection is allowed to say the two known languages are the other way
        round, never to introduce one nobody picked — a noisy clip heard as
        English must not silently retarget a Russian/Portuguese conversation.
        """
        self.assertEqual(
            live_service.resolve_direction('HOST', 'ru', 'pt', 'en'),
            ('HOST', 'ru', 'pt'))

    def test_an_unplaceable_clip_leaves_the_turn_alone(self):
        self.assertEqual(
            live_service.resolve_direction('HOST', 'ru', 'pt', ''),
            ('HOST', 'ru', 'pt'))


class LiveTurnServiceTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # These tests commit for real (TransactionTestCase), which fires the
        # Neo4j profile sync — and Neo4j is deliberately unreachable under test.
        from django.db.models.signals import post_save

        from barter.signals import sync_profile_to_neo4j
        post_save.disconnect(sync_profile_to_neo4j, sender=Profile)
        cls.addClassCleanup(post_save.connect, sync_profile_to_neo4j, sender=Profile)

    def setUp(self):
        self.instance = Instance.objects.create(
            domain='test.parahub.io', name='Test', public_key='k',
            trust_level='local')
        self.norn = _profile(self.instance, 'livenorn', 'ru')

    def _grant_clone(self, voice_id='clone-voice'):
        VoiceConsent.objects.create(
            profile=self.norn, consent_text_version=CONSENT_TEXT_VERSION)
        return VoiceClone.objects.create(
            profile=self.norn, voice_id=voice_id, stage=1, sample_seconds=90.0)

    def _stub_pipeline(self, text='привет', language='ru', seconds=3.0,
                       translated='olá'):
        """Patch the three provider calls; return the `speak` mock to inspect."""
        transcribe = AsyncMock(return_value=pipeline.Transcription(
            text=text, language=language, seconds=seconds))
        translate = AsyncMock(return_value=pipeline.Translation(
            texts={'pt': translated, 'ru': translated}, model='gemini-test'))
        speak = AsyncMock(return_value=MP3)
        return (
            patch('voice.services.pipeline.transcribe', transcribe),
            patch('voice.services.pipeline.translate', translate),
            patch('voice.services.pipeline.speak', speak),
            speak,
        )

    async def test_a_host_turn_leaves_one_meter_row_and_nothing_else(self):
        from channels.db import database_sync_to_async

        p_tr, p_tx, p_sp, _ = self._stub_pipeline()
        with p_tr, p_tx, p_sp:
            turn = await live_service.translate_turn(
                self.norn, AUDIO, spoken_by='HOST',
                source_lang='ru', target_lang='pt')

        self.assertEqual(turn.spoken_by, 'HOST')
        self.assertEqual(turn.source_text, 'привет')
        self.assertEqual(turn.target_text, 'olá')
        self.assertEqual(turn.audio, MP3)

        rows = await database_sync_to_async(list)(VoiceLiveTurn.objects.all())
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0].source_lang, rows[0].target_lang), ('ru', 'pt'))
        self.assertEqual(rows[0].audio_seconds, 3.0)
        # The meter carries seconds and a language pair. Not the words.
        self.assertFalse(hasattr(rows[0], 'source_text'))
        # And no note: a live turn has no recipient to be a message to.
        self.assertEqual(await database_sync_to_async(VoiceNote.objects.count)(), 0)

    async def test_no_recording_from_live_mode_is_ever_kept_as_clone_material(self):
        """The microphone is shared, so we cannot prove who spoke into it.

        A voice note may keep the sender's own audio, because the sender is the
        only person who could have made it. Here either person could have, so
        neither half is retainable — not the guest's, who consented to nothing,
        and not the host's, which cannot be told apart from it.
        """
        p_tr, p_tx, p_sp, _ = self._stub_pipeline()
        with p_tr, p_tx, p_sp, \
                patch('voice.services.cloning.retain_sample') as retain, \
                patch('voice.services.cloning.maybe_start_clone') as start:
            await live_service.translate_turn(
                self.norn, AUDIO, spoken_by='HOST',
                source_lang='ru', target_lang='pt')
        retain.assert_not_called()
        start.assert_not_called()

    async def test_the_host_is_read_back_in_their_own_clone(self):
        from channels.db import database_sync_to_async

        await database_sync_to_async(self._grant_clone)()
        p_tr, p_tx, p_sp, speak = self._stub_pipeline()
        with p_tr, p_tx, p_sp:
            turn = await live_service.translate_turn(
                self.norn, AUDIO, spoken_by='HOST',
                source_lang='ru', target_lang='pt')

        self.assertEqual(speak.await_args.args[1], 'clone-voice')
        self.assertTrue(turn.cloned_voice)

    async def test_the_guest_is_read_back_in_the_stock_voice(self):
        """A stranger has no clone here, and the host's would misattribute them."""
        from channels.db import database_sync_to_async

        await database_sync_to_async(self._grant_clone)()
        p_tr, p_tx, p_sp, speak = self._stub_pipeline(language='pt', text='olá',
                                                      translated='привет')
        with p_tr, p_tx, p_sp:
            turn = await live_service.translate_turn(
                self.norn, AUDIO, spoken_by='GUEST',
                source_lang='pt', target_lang='ru')

        self.assertEqual(speak.await_args.args[1], pipeline.DEFAULT_VOICE_ID)
        self.assertFalse(turn.cloned_voice)

    async def test_a_mistapped_button_is_corrected_end_to_end(self):
        """The guest talked into the host's half: the whole turn turns around."""
        from channels.db import database_sync_to_async

        await database_sync_to_async(self._grant_clone)()
        p_tr, p_tx, p_sp, speak = self._stub_pipeline(text='olá', language='pt',
                                                      translated='привет')
        with p_tr, p_tx, p_sp:
            turn = await live_service.translate_turn(
                self.norn, AUDIO, spoken_by='HOST',
                source_lang='ru', target_lang='pt')

        self.assertEqual(turn.spoken_by, 'GUEST')
        self.assertEqual((turn.source_lang, turn.target_lang), ('pt', 'ru'))
        # The voice follows the speaker, not the button that was pressed.
        self.assertEqual(speak.await_args.args[1], pipeline.DEFAULT_VOICE_ID)

    async def test_one_language_on_both_sides_is_refused(self):
        with self.assertRaises(live_service.SameLanguage):
            await live_service.translate_turn(
                self.norn, AUDIO, spoken_by='HOST',
                source_lang='pt', target_lang='pt')

    async def test_live_turns_spend_the_same_monthly_allowance_as_notes(self):
        from channels.db import database_sync_to_async

        await database_sync_to_async(VoiceLiveTurn.objects.create)(
            profile=self.norn, spoken_by='GUEST',
            source_lang='pt', target_lang='ru', audio_seconds=40.0)
        await database_sync_to_async(VoiceNote.objects.create)(
            sender=self.norn, recipient=self.norn, audio_seconds=20.0)

        quota = await database_sync_to_async(notes_service.quota_for)(self.norn)
        # The guest's 40 seconds are the account holder's provider bill too.
        self.assertEqual(quota.used_seconds, 60.0)


class LiveConsumerTests(TransactionTestCase):
    """The frame order the page is written against."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from django.db.models.signals import post_save

        from barter.signals import sync_profile_to_neo4j
        post_save.disconnect(sync_profile_to_neo4j, sender=Profile)
        cls.addClassCleanup(post_save.connect, sync_profile_to_neo4j, sender=Profile)

    def setUp(self):
        self.instance = Instance.objects.create(
            domain='test.parahub.io', name='Test', public_key='k',
            trust_level='local')
        self.norn = _profile(self.instance, 'liveconsumer', 'ru')

    async def _connected(self):
        communicator = WebsocketCommunicator(VoiceNoteConsumer.as_asgi(), PATH, scope={
            'user': self.norn.account,
            'profile': self.norn,
        })
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.receive_json_from()  # connection.established
        await communicator.receive_json_from()  # ready
        return communicator

    async def test_a_turn_answers_with_its_metadata_and_then_its_audio(self):
        communicator = await self._connected()
        await communicator.send_json_to({
            'type': 'live.begin', 'spoken_by': 'HOST',
            'source_lang': 'ru', 'target_lang': 'pt',
        })
        ready = await communicator.receive_json_from()
        self.assertEqual(ready['type'], 'live.ready')

        async def _fake_turn(profile, audio, *, spoken_by, source_lang, target_lang,
                             on_status=None):
            await on_status('transcribing')
            return live_service.LiveTurn(
                spoken_by=spoken_by, source_lang=source_lang, target_lang=target_lang,
                source_text='привет', target_text='olá', seconds=3.0,
                cloned_voice=False, audio=MP3)

        with patch('voice.services.live.translate_turn', new=_fake_turn):
            await communicator.send_to(bytes_data=AUDIO)
            status = await communicator.receive_json_from()
            meta = await communicator.receive_json_from()
            audio = await communicator.receive_bytes_from()

        self.assertEqual(status['status'], 'transcribing')
        self.assertEqual(meta['type'], 'live.turn')
        self.assertEqual(meta['turn']['target_text'], 'olá')
        # AI Act: the clip that follows is machine-generated and says so.
        self.assertTrue(meta['turn']['synthetic_voice'])
        self.assertIn('used_seconds', meta['quota'])
        # Nothing is stored, so this frame is bound to that metadata by order
        # alone — it must arrive on its heels, not on a fetch.
        self.assertEqual(audio, MP3)
        await communicator.disconnect()

    async def test_one_language_on_both_sides_is_refused_before_any_audio(self):
        communicator = await self._connected()
        with patch('voice.services.live.translate_turn', new=AsyncMock()) as run:
            await communicator.send_json_to({
                'type': 'live.begin', 'spoken_by': 'HOST',
                'source_lang': 'pt', 'target_lang': 'pt',
            })
            answer = await communicator.receive_json_from()
        self.assertEqual(answer['code'], 'same_language')
        run.assert_not_called()
        await communicator.disconnect()

    async def test_an_unsupported_language_is_refused(self):
        communicator = await self._connected()
        await communicator.send_json_to({
            'type': 'live.begin', 'spoken_by': 'HOST',
            'source_lang': 'ru', 'target_lang': 'zh',
        })
        answer = await communicator.receive_json_from()
        self.assertEqual(answer['code'], 'unsupported_language')
        await communicator.disconnect()

    async def test_audio_before_any_begin_is_refused_as_a_note(self):
        """The default mode is the asynchronous one; live must be asked for."""
        communicator = await self._connected()
        await communicator.send_to(bytes_data=AUDIO)
        answer = await communicator.receive_json_from()
        self.assertEqual(answer['code'], 'no_recipient')
        await communicator.disconnect()
