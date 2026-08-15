"""
Para-ID photo (id_photo) access control tests.

The photo is private media served to the owner or to ANY WoT-verified member —
there is no viewer↔subject pairing to gate on, and unlike the biometric
verification photo no notification goes out. So the subject's only visibility is
the trail: every fetch by someone else is logged and readable back. These tests
pin that down.

Endpoints are called directly with RequestFactory requests (tests_wot_photo.py
style); the rate-limit decorator skips localhost so it does not interfere.
"""

from datetime import timedelta

from django.core.files.base import ContentFile
from django.test import TestCase, RequestFactory, override_settings
from django.utils import timezone
from ninja.errors import HttpError

from core.models import Instance
from identity.models import Account, IdPhotoAccess, Profile
from parahub.endpoints.profiles.photos import get_id_photo, id_photo_access_log
from parahub.tmpdirs import make_scratch_dir, register_cleanup

JPEG = b'\xff\xd8\xff\xdb' + b'0' * 64

# Evaluated at import, i.e. on every test run that merely discovers this module,
# so it must clean up after itself rather than pile up one directory per run.
_MEDIA_ROOT = make_scratch_dir('test-media')
register_cleanup(_MEDIA_ROOT)


# The test DB is throwaway, MEDIA_ROOT is not: without this every run leaves
# stub JPEGs in the live media/private/id_photos/ tree.
@override_settings(MEDIA_ROOT=_MEDIA_ROOT)
class IdPhotoAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.instance = Instance.objects.create(
            domain='test.parahub.io', name='Test Instance', public_key='k')
        cls.factory = RequestFactory()

    def _profile(self, username, verified=False):
        account = Account.objects.create_user(
            username=username, email=f'{username}@test.parahub.io',
            password='x', instance=self.instance)
        return Profile.objects.create(
            account=account, instance=self.instance, local_name=username,
            display_name=username.title(), is_primary=True,
            profile_type=Profile.ProfileType.PERSONAL,
            is_verified_wot=verified)

    def _with_photo(self, username='subject'):
        profile = self._profile(username)
        profile.id_photo.save(f'{profile.id}_id.jpg', ContentFile(JPEG), save=True)
        return profile

    def _req(self, profile):
        request = self.factory.get('/fake/')
        request.user = profile.account
        request.auth = profile
        request.auth_profile = profile
        return request

    # ── gate ─────────────────────────────────────────────────────────

    def test_unverified_member_is_refused(self):
        stranger = self._profile('stranger')
        subject = self._with_photo()
        with self.assertRaises(HttpError) as cm:
            get_id_photo(self._req(stranger), subject.id)
        self.assertEqual(cm.exception.status_code, 403)
        self.assertEqual(IdPhotoAccess.objects.count(), 0)

    def test_verified_member_gets_photo_via_x_accel(self):
        viewer = self._profile('viewer', verified=True)
        subject = self._with_photo()
        response = get_id_photo(self._req(viewer), subject.id)
        self.assertEqual(response['Content-Type'], 'image/jpeg')
        self.assertIn('_id.jpg', response['X-Accel-Redirect'])
        self.assertEqual(response['Cache-Control'], 'no-store, no-cache')

    def test_missing_photo_is_404_and_leaves_no_trail(self):
        viewer = self._profile('viewer', verified=True)
        subject = self._profile('photoless')
        with self.assertRaises(HttpError) as cm:
            get_id_photo(self._req(viewer), subject.id)
        self.assertEqual(cm.exception.status_code, 404)
        self.assertEqual(IdPhotoAccess.objects.count(), 0)

    # ── trail ────────────────────────────────────────────────────────

    def test_every_fetch_is_recorded(self):
        viewer = self._profile('viewer', verified=True)
        subject = self._with_photo()
        get_id_photo(self._req(viewer), subject.id)
        get_id_photo(self._req(viewer), subject.id)
        self.assertEqual(
            IdPhotoAccess.objects.filter(viewer=viewer, target_profile=subject).count(), 2)

    def test_owner_leaves_no_trail(self):
        subject = self._with_photo()
        get_id_photo(self._req(subject), subject.id)
        self.assertEqual(IdPhotoAccess.objects.count(), 0)

    def test_row_survives_photo_deletion(self):
        viewer = self._profile('viewer', verified=True)
        subject = self._with_photo()
        get_id_photo(self._req(viewer), subject.id)

        subject.id_photo.delete(save=True)
        self.assertEqual(
            IdPhotoAccess.objects.filter(target_profile=subject).count(), 1)

    # ── log ──────────────────────────────────────────────────────────

    def test_access_log_groups_a_session_but_keeps_every_row(self):
        viewer = self._profile('viewer', verified=True)
        subject = self._with_photo()
        for _ in range(3):
            get_id_photo(self._req(viewer), subject.id)

        log = id_photo_access_log(self._req(subject))
        self.assertEqual(len(log['accesses']), 1)
        entry = log['accesses'][0]
        self.assertEqual(entry['views'], 3)
        self.assertEqual(entry['viewer_id'], viewer.id)
        self.assertEqual(entry['viewer_display_name'], viewer.display_name)
        self.assertEqual(entry['object_type'], 'id_photo_access')
        self.assertEqual(IdPhotoAccess.objects.count(), 3)

    def test_access_log_separates_days(self):
        viewer = self._profile('viewer', verified=True)
        subject = self._with_photo()
        get_id_photo(self._req(viewer), subject.id)
        IdPhotoAccess.objects.filter(viewer=viewer).update(
            created_at=timezone.now() - timedelta(days=2))
        get_id_photo(self._req(viewer), subject.id)

        log = id_photo_access_log(self._req(subject))
        self.assertEqual(len(log['accesses']), 2)

    def test_access_log_shows_only_own_viewers(self):
        viewer = self._profile('viewer', verified=True)
        subject = self._with_photo()
        other = self._with_photo('other')
        get_id_photo(self._req(viewer), other.id)

        self.assertEqual(id_photo_access_log(self._req(subject))['accesses'], [])
        self.assertEqual(len(id_photo_access_log(self._req(other))['accesses']), 1)
