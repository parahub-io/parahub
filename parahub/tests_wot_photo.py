"""
WoT verification-photo access control tests.

The photo is GDPR Art.9 biometric data served to ANY profile with
`can_verify_others()` — there is no verifier↔subject pairing to gate on. What
bounds it instead: every fetch is logged, the subject is notified, and one
verifier can only pull up so many DISTINCT people per window. These tests pin
that behaviour down.

Endpoints are called directly with RequestFactory requests (market/tests.py
style); the rate-limit decorator skips localhost so it does not interfere.
"""

import tempfile
from datetime import timedelta
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import TestCase, RequestFactory, override_settings
from django.utils import timezone
from ninja.errors import HttpError

from core.models import Instance
from identity.models import (
    Account, Profile, ProfileVerificationPhoto, Verification,
    VerificationPhotoAccess,
)
from parahub.endpoints.wot import (
    get_verification_photo, PHOTO_TARGETS_PER_HOUR, PHOTO_TARGETS_PER_DAY,
)
from parahub.endpoints.profiles.photos import (
    my_verification_photo, verification_photo_access_log,
)

JPEG = b'\xff\xd8\xff\xdb' + b'0' * 64


# The test DB is throwaway, MEDIA_ROOT is not: without this every run leaves
# stub JPEGs in the live media/private/verification_photos/ tree.
@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix='parahub-test-media-'))
class VerificationPhotoAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.instance = Instance.objects.create(
            domain='test.parahub.io', name='Test Instance', public_key='k')
        cls.factory = RequestFactory()

    def _profile(self, username, with_pgp=True):
        account = Account.objects.create_user(
            username=username, email=f'{username}@test.parahub.io',
            password='x', instance=self.instance)
        return Profile.objects.create(
            account=account, instance=self.instance, local_name=username,
            display_name=username.title(), is_primary=True,
            profile_type=Profile.ProfileType.PERSONAL,
            pgp_public_key='KEY' if with_pgp else '',
            pgp_fingerprint='FPR' if with_pgp else '')

    def _make_verifier(self, username='verifier'):
        """A standard (non-foundation) verifier: PGP + WoT status + 3 verifications."""
        profile = self._profile(username)
        profile.is_verified_wot = True
        profile.save(update_fields=['is_verified_wot'])
        for i in range(3):
            voucher = self._profile(f'{username}voucher{i}')
            Verification.objects.create(
                verifier=voucher, verified_profile=profile, is_active=True)
        self.assertTrue(profile.can_verify_others())
        return profile

    def _with_photo(self, username='subject'):
        profile = self._profile(username)
        vp = ProfileVerificationPhoto.objects.create(
            profile=profile, face_embedding=b'e' * 512, photo_hash='h' * 64,
            biometric_consent=True, biometric_consent_at=timezone.now())
        vp.photo.save(f'{profile.id}_vp.jpg', ContentFile(JPEG), save=True)
        return profile

    def _req(self, profile):
        request = self.factory.get('/fake/')
        request.user = profile.account
        request.auth = profile
        request.auth_profile = profile
        return request

    def _fetch(self, viewer, target):
        with patch('notifications.services.notify_verification_photo_viewed') as notify:
            response = get_verification_photo(self._req(viewer), target.id)
        return response, notify

    # ── gate ─────────────────────────────────────────────────────────

    def test_non_verifier_is_refused(self):
        stranger = self._profile('stranger')
        subject = self._with_photo()
        with self.assertRaises(HttpError) as cm:
            get_verification_photo(self._req(stranger), subject.id)
        self.assertEqual(cm.exception.status_code, 403)
        self.assertEqual(VerificationPhotoAccess.objects.count(), 0)

    def test_verifier_gets_photo_via_x_accel(self):
        verifier = self._make_verifier()
        subject = self._with_photo()
        response, _ = self._fetch(verifier, subject)
        self.assertEqual(response['Content-Type'], 'image/jpeg')
        self.assertIn('_vp.jpg', response['X-Accel-Redirect'])
        self.assertEqual(response['Cache-Control'], 'no-store, no-cache')

    def test_missing_photo_is_404_and_leaves_no_trail(self):
        verifier = self._make_verifier()
        subject = self._profile('photoless')
        with self.assertRaises(HttpError) as cm:
            get_verification_photo(self._req(verifier), subject.id)
        self.assertEqual(cm.exception.status_code, 404)
        self.assertEqual(VerificationPhotoAccess.objects.count(), 0)

    # ── trail ────────────────────────────────────────────────────────

    def test_every_fetch_is_recorded(self):
        verifier = self._make_verifier()
        subject = self._with_photo()
        self._fetch(verifier, subject)
        self._fetch(verifier, subject)
        rows = VerificationPhotoAccess.objects.filter(
            viewer=verifier, target_profile=subject)
        self.assertEqual(rows.count(), 2)

    def test_subject_is_notified_once_per_viewer_per_day(self):
        verifier = self._make_verifier()
        subject = self._with_photo()

        _, first = self._fetch(verifier, subject)
        self.assertEqual(first.call_count, 1)
        self.assertEqual(first.call_args[0][0], subject.account)

        # Same session, photo reopened — no second ping.
        _, second = self._fetch(verifier, subject)
        self.assertEqual(second.call_count, 0)

        # A different verifier is a separate notice.
        other = self._make_verifier('verifier2')
        _, third = self._fetch(other, subject)
        self.assertEqual(third.call_count, 1)

        # Yesterday's look does not suppress today's.
        VerificationPhotoAccess.objects.filter(viewer=verifier).update(
            created_at=timezone.now() - timedelta(days=2))
        _, fourth = self._fetch(verifier, subject)
        self.assertEqual(fourth.call_count, 1)

    def test_owner_reading_own_photo_leaves_no_trail(self):
        subject = self._with_photo()
        subject.is_verified_wot = True
        subject.save(update_fields=['is_verified_wot'])
        for i in range(3):
            Verification.objects.create(
                verifier=self._profile(f'sv{i}'), verified_profile=subject, is_active=True)

        _, notify = self._fetch(subject, subject)
        self.assertEqual(VerificationPhotoAccess.objects.count(), 0)
        self.assertEqual(notify.call_count, 0)

    # ── quota ────────────────────────────────────────────────────────

    def _seed_views(self, viewer, count, age):
        """Backdate `count` distinct-target views so quota windows can be exercised."""
        for i in range(count):
            row = VerificationPhotoAccess.objects.create(
                viewer=viewer, target_profile=self._profile(f'seen{viewer.local_name}{i}'))
            VerificationPhotoAccess.objects.filter(id=row.id).update(
                created_at=timezone.now() - age)

    def test_hourly_distinct_target_quota_blocks_a_new_face(self):
        verifier = self._make_verifier()
        self._seed_views(verifier, PHOTO_TARGETS_PER_HOUR, timedelta(minutes=5))
        fresh = self._with_photo('freshface')
        with self.assertRaises(HttpError) as cm:
            get_verification_photo(self._req(verifier), fresh.id)
        self.assertEqual(cm.exception.status_code, 429)

    def test_quota_does_not_block_reopening_the_same_person(self):
        """A verification session reopens one photo repeatedly — that must stay free."""
        verifier = self._make_verifier()
        subject = self._with_photo()
        VerificationPhotoAccess.objects.create(viewer=verifier, target_profile=subject)
        self._seed_views(verifier, PHOTO_TARGETS_PER_HOUR - 1, timedelta(minutes=5))

        response, _ = self._fetch(verifier, subject)
        self.assertIn('_vp.jpg', response['X-Accel-Redirect'])

    def test_hour_old_views_stop_counting(self):
        """The mass-verification case: an event runs past the hour, the table resets."""
        verifier = self._make_verifier()
        self._seed_views(verifier, PHOTO_TARGETS_PER_HOUR, timedelta(hours=2))
        fresh = self._with_photo('nexthour')
        response, _ = self._fetch(verifier, fresh)
        self.assertIn('_vp.jpg', response['X-Accel-Redirect'])

    def test_daily_quota_still_applies_across_hours(self):
        verifier = self._make_verifier()
        self._seed_views(verifier, PHOTO_TARGETS_PER_DAY, timedelta(hours=5))
        fresh = self._with_photo('overday')
        with self.assertRaises(HttpError) as cm:
            get_verification_photo(self._req(verifier), fresh.id)
        self.assertEqual(cm.exception.status_code, 429)

    # ── owner-facing surfaces ────────────────────────────────────────

    def test_owner_preview_endpoint(self):
        subject = self._with_photo()
        response = my_verification_photo(self._req(subject))
        self.assertIn('_vp.jpg', response['X-Accel-Redirect'])
        self.assertEqual(response['Cache-Control'], 'no-store, no-cache')

    def test_owner_preview_404_without_photo(self):
        profile = self._profile('nophoto')
        with self.assertRaises(HttpError) as cm:
            my_verification_photo(self._req(profile))
        self.assertEqual(cm.exception.status_code, 404)

    def test_access_log_shows_only_own_viewers(self):
        verifier = self._make_verifier()
        subject = self._with_photo()
        other_subject = self._with_photo('other')
        self._fetch(verifier, subject)
        self._fetch(verifier, other_subject)

        log = verification_photo_access_log(self._req(subject))
        self.assertEqual(len(log['accesses']), 1)
        entry = log['accesses'][0]
        self.assertEqual(entry['viewer_id'], verifier.id)
        self.assertEqual(entry['viewer_hna'], verifier.hna)
        self.assertEqual(entry['object_type'], 'verification_photo_access')

    def test_access_log_groups_a_session_but_keeps_every_row(self):
        verifier = self._make_verifier()
        other = self._make_verifier('verifier2')
        subject = self._with_photo()
        self._fetch(verifier, subject)
        self._fetch(verifier, subject)
        self._fetch(verifier, subject)
        self._fetch(other, subject)

        log = verification_photo_access_log(self._req(subject))
        by_viewer = {a['viewer_id']: a for a in log['accesses']}
        self.assertEqual(len(log['accesses']), 2)
        self.assertEqual(by_viewer[verifier.id]['views'], 3)
        self.assertEqual(by_viewer[other.id]['views'], 1)
        # The grouping is presentation only — the trail itself keeps every fetch.
        self.assertEqual(
            VerificationPhotoAccess.objects.filter(target_profile=subject).count(), 4)
