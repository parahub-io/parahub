"""Retention: what gets deleted, and — just as important — what does not.

These are the promises the consent screen makes in writing (audio expires, the
text stays, withdrawn consent takes the samples with it), so they are worth a
test that actually looks at the filesystem rather than trusting the code path.
"""

from datetime import timedelta
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import Instance
from identity.models import Account, Profile
from parahub.tmpdirs import make_scratch_dir
from voice.models import VoiceConsent, VoiceNote
from voice.services import cloning, notes as notes_service

MEDIA_ROOT = make_scratch_dir('test-voice-retention')


def _profile(instance, username):
    account = Account.objects.create_user(
        username=username, email=f'{username}@test.parahub.io',
        password='x', instance=instance)
    return Profile.objects.create(
        account=account, instance=instance, local_name=username,
        display_name=username.title(), is_primary=True)


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class PurgeCommandTests(TestCase):
    def setUp(self):
        self.instance = Instance.objects.create(
            domain='test.parahub.io', name='Test', public_key='k',
            trust_level='local')
        self.alice = _profile(self.instance, 'purgealice')
        self.bob = _profile(self.instance, 'purgebob')
        # The module-level roots were computed at import time from the real
        # MEDIA_ROOT; point them at the scratch tree for the duration.
        self._real_audio_root = notes_service.AUDIO_ROOT
        self._real_samples_root = cloning.SAMPLES_ROOT
        notes_service.AUDIO_ROOT = Path(MEDIA_ROOT) / 'private' / 'voice_notes'
        cloning.SAMPLES_ROOT = Path(MEDIA_ROOT) / 'private' / 'voice_samples'

    def tearDown(self):
        notes_service.AUDIO_ROOT = self._real_audio_root
        cloning.SAMPLES_ROOT = self._real_samples_root

    def _note(self, *, expires_in_days=30):
        note = VoiceNote(
            sender=self.alice, recipient=self.bob,
            source_text='olá', target_text='привет', audio_seconds=5.0,
            audio_expires_at=timezone.now() + timedelta(days=expires_in_days),
        )
        note.audio_path = notes_service.audio_relative_path(note.id, timezone.now())
        note.save()
        path = Path(MEDIA_ROOT) / note.audio_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'\xff\xfb' + b'\x00' * 500)
        return note, path

    def _sample(self, profile, *, age_days=0):
        directory = cloning.samples_dir(profile.id)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / '00006000-abcdef01.webm'
        path.write_bytes(b'\x1a\x45\xdf\xa3' + b'\x00' * 200)
        if age_days:
            old = (timezone.now() - timedelta(days=age_days)).timestamp()
            import os
            os.utime(path, (old, old))
        return path

    def _run(self, *args):
        out = StringIO()
        call_command('purge_voice_audio', *args, stdout=out, stderr=out)
        return out.getvalue()

    def test_expired_audio_goes_and_the_text_stays(self):
        note, path = self._note(expires_in_days=-1)

        self._run()

        self.assertFalse(path.exists())
        note.refresh_from_db()
        self.assertEqual(note.audio_path, '')
        self.assertEqual(note.target_text, 'привет')  # the record is untouched

    def test_unexpired_audio_is_left_alone(self):
        note, path = self._note(expires_in_days=10)
        self._run()
        self.assertTrue(path.exists())
        note.refresh_from_db()
        self.assertNotEqual(note.audio_path, '')

    def test_dry_run_deletes_nothing(self):
        note, path = self._note(expires_in_days=-1)
        output = self._run('--dry-run')
        self.assertIn('would delete', output)
        self.assertTrue(path.exists())
        note.refresh_from_db()
        self.assertNotEqual(note.audio_path, '')

    def test_audio_whose_note_row_is_gone_is_swept(self):
        note, path = self._note()
        VoiceNote.objects.filter(pk=note.pk).delete()

        self._run()

        self.assertFalse(path.exists())

    def test_samples_of_a_withdrawn_consent_are_deleted(self):
        VoiceConsent.objects.create(profile=self.alice, revoked_at=timezone.now())
        path = self._sample(self.alice)

        self._run()

        self.assertFalse(path.exists())

    def test_samples_of_an_active_consent_survive(self):
        VoiceConsent.objects.create(profile=self.alice)
        path = self._sample(self.alice)

        self._run()

        self.assertTrue(path.exists())

    def test_a_stalled_collection_does_not_hoard_voice_forever(self):
        VoiceConsent.objects.create(profile=self.alice)
        fresh = self._sample(self.alice)
        stale = cloning.samples_dir(self.alice.id) / '00006000-11111111.webm'
        stale.write_bytes(b'\x1a\x45\xdf\xa3')
        import os
        old = (timezone.now() - timedelta(days=40)).timestamp()
        os.utime(stale, (old, old))

        self._run()

        self.assertTrue(fresh.exists())
        self.assertFalse(stale.exists())
