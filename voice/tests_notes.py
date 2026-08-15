"""Voice notes: who may read a conversation, who may hear the audio, what it costs.

The security-critical claim is the audio endpoint — a note's mp3 is private
speech, and the only thing standing between it and a guessed URL is this
handler's ownership check, so that one is exercised over real HTTP rather than
by calling the function.
"""

import json
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone
from ninja.errors import HttpError

from core.models import Instance
from identity.models import Account, Profile, ProfileBlock
from parahub.tmpdirs import make_scratch_dir
from voice.endpoints import (
    ConsentInput, delete_clone, get_note_audio, get_thread, grant_clone_consent,
    list_threads, mark_played,
)
from voice.models import VoiceClone, VoiceConsent, VoiceNote
from voice.services import notes as notes_service

MEDIA_ROOT = make_scratch_dir('test-voice')


def _profile(instance, username, *, language='en', staff=False):
    account = Account.objects.create_user(
        username=username, email=f'{username}@test.parahub.io',
        password='x', instance=instance, is_staff=staff)
    return Profile.objects.create(
        account=account, instance=instance, local_name=username,
        display_name=username.title(), is_primary=True,
        preferred_language=language)


class VoiceTestBase(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.instance = Instance.objects.create(
            domain='test.parahub.io', name='Test', public_key='k',
            trust_level='local')
        self.norn = _profile(self.instance, 'norn', language='ru')
        self.monica = _profile(self.instance, 'monica', language='pt')
        self.stranger = _profile(self.instance, 'stranger')

    def _req(self, profile, method='get', body=None):
        factory = getattr(self.rf, method)
        request = factory('/', data=json.dumps(body) if body else None,
                          content_type='application/json')
        request.auth_profile = profile
        return request

    def _note(self, sender, recipient, *, text='olá', translated='привет',
              seconds=4.0, audio=True, played=False):
        note = VoiceNote(
            sender=sender, recipient=recipient,
            source_lang=sender.preferred_language, target_lang=recipient.preferred_language,
            source_text=text, target_text=translated, audio_seconds=seconds,
            delivered_at=timezone.now(),
            played_at=timezone.now() if played else None,
        )
        if audio:
            note.audio_path = notes_service.audio_relative_path(note.id, timezone.now())
            note.audio_expires_at = timezone.now() + timedelta(days=30)
        note.save()
        return note


class ThreadTests(VoiceTestBase):
    def test_threads_group_by_counterpart_and_count_unplayed(self):
        self._note(self.monica, self.norn)
        self._note(self.norn, self.monica)
        self._note(self.monica, self.norn)

        out = list_threads(self._req(self.norn))

        self.assertEqual(out['count'], 1)
        thread = out['items'][0]
        self.assertEqual(thread['profile']['local_name'], 'monica')
        # Two arrived and neither was played; the one norn sent never counts.
        self.assertEqual(thread['unplayed'], 2)

    def test_thread_returns_both_directions_oldest_last(self):
        first = self._note(self.monica, self.norn, text='bom dia')
        second = self._note(self.norn, self.monica, text='доброе утро')

        out = get_thread(self._req(self.norn), 'monica')

        self.assertEqual([n['id'] for n in out['items']], [first.id, second.id])
        self.assertEqual(out['items'][0]['direction'], 'in')
        self.assertEqual(out['items'][1]['direction'], 'out')

    def test_thread_of_a_blocked_profile_is_refused(self):
        ProfileBlock.objects.create(blocker=self.monica, blocked=self.norn)
        with self.assertRaises(HttpError) as ctx:
            get_thread(self._req(self.norn), 'monica')
        self.assertEqual(ctx.exception.status_code, 403)

    def test_mark_played_is_idempotent_and_recipient_only(self):
        note = self._note(self.monica, self.norn)

        first = mark_played(self._req(self.norn, 'post'), note.id)
        second = mark_played(self._req(self.norn, 'post'), note.id)
        self.assertEqual(first['played_at'], second['played_at'])

        # The sender is not the one who hears it.
        from django.http import Http404
        with self.assertRaises(Http404):
            mark_played(self._req(self.monica, 'post'), note.id)


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class AudioAccessTests(VoiceTestBase):
    """The mp3 is private speech: two people, nobody else, over real HTTP."""

    def _bearer(self, profile):
        from ninja_jwt.tokens import RefreshToken
        return f'Bearer {RefreshToken.for_user(profile.account).access_token}'

    def setUp(self):
        super().setUp()
        self.note = self._note(self.monica, self.norn)
        path = Path(MEDIA_ROOT) / self.note.audio_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'\xff\xfb\x90\x64fake mp3')

    def test_recipient_and_sender_get_an_internal_redirect(self):
        for profile in (self.norn, self.monica):
            response = self.client.get(
                f'/api/v1/voice/notes/{self.note.id}/audio',
                HTTP_AUTHORIZATION=self._bearer(profile),
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['X-Accel-Redirect'],
                             f'/media/{self.note.audio_path}')
            # The body must stay empty — nginx serves the bytes, not Django.
            self.assertEqual(response.content, b'')

    def test_third_party_cannot_fetch_the_audio(self):
        response = self.client.get(
            f'/api/v1/voice/notes/{self.note.id}/audio',
            HTTP_AUTHORIZATION=self._bearer(self.stranger),
        )
        self.assertEqual(response.status_code, 404)

    def test_anonymous_cannot_fetch_the_audio(self):
        response = self.client.get(f'/api/v1/voice/notes/{self.note.id}/audio')
        self.assertEqual(response.status_code, 401)

    def test_expired_audio_answers_410_and_keeps_the_text(self):
        self.note.audio_path = ''
        self.note.save(update_fields=['audio_path'])
        with self.assertRaises(HttpError) as ctx:
            get_note_audio(self._req(self.norn), self.note.id)
        self.assertEqual(ctx.exception.status_code, 410)
        self.assertEqual(VoiceNote.objects.get(id=self.note.id).target_text, 'привет')


class QuotaTests(VoiceTestBase):
    def test_only_sent_audio_this_month_counts(self):
        self._note(self.norn, self.monica, seconds=120)
        self._note(self.monica, self.norn, seconds=600)  # received: not ours
        old = self._note(self.norn, self.monica, seconds=900)
        VoiceNote.objects.filter(id=old.id).update(
            created_at=timezone.now() - timedelta(days=40))

        quota = notes_service.quota_for(self.norn)

        self.assertAlmostEqual(quota.used_seconds, 120)
        self.assertFalse(quota.exhausted)

    def test_quota_exhausts_at_the_free_threshold(self):
        self._note(self.norn, self.monica, seconds=notes_service.FREE_MONTHLY_SECONDS)
        self.assertTrue(notes_service.quota_for(self.norn).exhausted)

    def test_an_exhausted_quota_refuses_before_a_provider_is_touched(self):
        """The check has to come first — the refusal must cost nothing."""
        from asgiref.sync import async_to_sync

        self._note(self.norn, self.monica, seconds=notes_service.FREE_MONTHLY_SECONDS)

        with patch('voice.services.pipeline.transcribe') as transcribe:
            with self.assertRaises(notes_service.QuotaExceeded) as ctx:
                async_to_sync(notes_service.create_note)(
                    self.norn, self.monica, b'\x1a\x45\xdf\xa3' + b'\x00' * 4000)

        transcribe.assert_not_called()
        self.assertEqual(ctx.exception.limit_seconds, notes_service.FREE_MONTHLY_SECONDS)

    def test_staff_are_unmetered(self):
        admin = _profile(self.instance, 'admin', staff=True)
        self._note(admin, self.monica, seconds=notes_service.FREE_MONTHLY_SECONDS * 3)
        quota = notes_service.quota_for(admin)
        self.assertTrue(quota.unlimited)
        self.assertFalse(quota.exhausted)


class LanguageResolutionTests(VoiceTestBase):
    def test_what_was_spoken_beats_the_ui_preference(self):
        # norn's interface is Russian, but this note was recorded in Portuguese.
        source, target = notes_service.resolve_languages(self.norn, self.monica, 'pt')
        self.assertEqual((source, target), ('pt', 'pt'))

    def test_unrecognised_detection_falls_back_to_the_preference(self):
        source, target = notes_service.resolve_languages(self.norn, self.monica, 'zh')
        self.assertEqual((source, target), ('ru', 'pt'))

    def test_recipient_without_a_preference_gets_english(self):
        source, target = notes_service.resolve_languages(self.norn, self.stranger, '')
        self.assertEqual(target, 'en')


class NotificationTests(VoiceTestBase):
    def test_arrival_writes_a_notification_pointing_at_the_thread(self):
        from notifications.models import Notification
        from notifications.services import notify_voice_note

        note = self._note(self.monica, self.norn, translated='привет, обед готов')
        with patch('notifications.services.send_push_notification', return_value=(1, 0)):
            notify_voice_note(self.norn.account, note)

        row = Notification.objects.get(recipient=self.norn.account)
        self.assertEqual(row.type, 'voice_note')
        self.assertEqual(row.category, 'messages')
        self.assertEqual(row.url, '/talk/monica')
        self.assertIn('обед готов', row.body)
        self.assertEqual(row.data['note_id'], note.id)

    def test_muting_messages_silences_it(self):
        from notifications.models import Notification
        from notifications.services import notify_voice_note

        self.norn.notification_prefs = {'messages': False}
        self.norn.save(update_fields=['notification_prefs'])
        note = self._note(self.monica, self.norn)

        with patch('notifications.services.send_push_notification', return_value=(1, 0)):
            notify_voice_note(self.norn.account, note)

        self.assertFalse(Notification.objects.filter(recipient=self.norn.account).exists())

    def test_muting_social_does_not_silence_a_message(self):
        """The whole reason messages are their own category."""
        from notifications.models import Notification
        from notifications.services import notify_voice_note

        self.norn.notification_prefs = {'social': False}
        self.norn.save(update_fields=['notification_prefs'])
        note = self._note(self.monica, self.norn)

        with patch('notifications.services.send_push_notification', return_value=(1, 0)):
            notify_voice_note(self.norn.account, note)

        self.assertTrue(Notification.objects.filter(recipient=self.norn.account).exists())


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class ConsentTests(VoiceTestBase):
    def test_consent_must_be_explicit(self):
        with self.assertRaises(HttpError) as ctx:
            grant_clone_consent(self._req(self.norn, 'post'),
                                ConsentInput(accepted=False))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertFalse(VoiceConsent.objects.filter(profile=self.norn).exists())

    def test_grant_records_evidence_and_is_idempotent(self):
        grant_clone_consent(self._req(self.norn, 'post'), ConsentInput(accepted=True))
        grant_clone_consent(self._req(self.norn, 'post'), ConsentInput(accepted=True))

        rows = VoiceConsent.objects.filter(profile=self.norn)
        self.assertEqual(rows.count(), 1)
        self.assertIn('user_agent', rows.first().evidence)

    def test_revoking_keeps_the_consent_row_as_evidence(self):
        grant_clone_consent(self._req(self.norn, 'post'), ConsentInput(accepted=True))
        VoiceClone.objects.create(profile=self.norn, voice_id='v-1', stage=1)

        with patch('voice.services.cloning._elevenlabs_client') as client:
            delete_clone(self._req(self.norn, 'delete'), revoke_consent=True)

        client.return_value.voices.delete.assert_called_once_with('v-1')
        consent = VoiceConsent.objects.get(profile=self.norn)
        self.assertIsNotNone(consent.revoked_at)
        self.assertEqual(VoiceClone.objects.get(profile=self.norn).status,
                         VoiceClone.Status.REVOKED)

    def test_a_revoked_clone_is_never_spoken_in(self):
        from voice.services import cloning

        VoiceClone.objects.create(profile=self.norn, voice_id='v-1', stage=2)
        # No consent row at all: the clone must not be usable even so.
        self.assertIsNone(cloning.usable_clone(self.norn))
