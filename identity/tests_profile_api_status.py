"""
Profile + psych endpoints exercised over HTTP, for their status codes.

These paths all used to answer 500: they returned `(body, status)` where
django-ninja expects `(status, body)`, or raised a control-flow exception
inside a `try` whose broad `except Exception` relabelled it as a server
fault. Both failure modes are invisible to a test that calls the view
function directly — the status code is only decided in the response layer.
"""

from django.test import TestCase

from identity.models import Account, Profile, PsychProfile
from identity.tests import _create_instance, _create_account, _create_profile


class ProfileApiStatusTest(TestCase):
    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance, is_verified_wot=True)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance, local_name='bob')

    def _bearer(self, account):
        from ninja_jwt.tokens import RefreshToken
        return f'Bearer {RefreshToken.for_user(account).access_token}'

    # --- delete profile -----------------------------------------------------

    def test_delete_primary_profile_is_400_with_code(self):
        """The main profile is undeletable — the UI must be able to say why."""
        response = self.client.delete(
            f'/api/v1/profiles/{self.alice.id}/',
            HTTP_AUTHORIZATION=self._bearer(self.alice_account),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'cannot_delete_primary')
        self.assertTrue(Profile.objects.filter(id=self.alice.id).exists())

    def test_delete_someone_elses_profile_is_403_with_code(self):
        extra = Profile.objects.create(
            account=self.bob_account,
            instance=self.instance,
            local_name='bob-alt',
            display_name='Bob Alt',
            is_primary=False,
            profile_type=Profile.ProfileType.PSEUDONYMOUS,
        )

        response = self.client.delete(
            f'/api/v1/profiles/{extra.id}/',
            HTTP_AUTHORIZATION=self._bearer(self.alice_account),
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['code'], 'permission_denied')
        self.assertTrue(Profile.objects.filter(id=extra.id).exists())

    def test_delete_own_secondary_profile_is_200(self):
        extra = Profile.objects.create(
            account=self.alice_account,
            instance=self.instance,
            local_name='alice-alt',
            display_name='Alice Alt',
            is_primary=False,
            profile_type=Profile.ProfileType.PSEUDONYMOUS,
        )

        response = self.client.delete(
            f'/api/v1/profiles/{extra.id}/',
            HTTP_AUTHORIZATION=self._bearer(self.alice_account),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Profile.objects.filter(id=extra.id).exists())

    def test_delete_unknown_profile_is_404(self):
        response = self.client.delete(
            '/api/v1/profiles/01NONEXISTENTNONEXISTENT00/',
            HTTP_AUTHORIZATION=self._bearer(self.alice_account),
        )
        self.assertEqual(response.status_code, 404)

    # --- mail credentials ---------------------------------------------------

    def test_mail_credentials_without_mailbox_is_404(self):
        response = self.client.get(
            '/api/v1/profiles/me/mail-credentials/',
            HTTP_AUTHORIZATION=self._bearer(self.alice_account),
        )
        self.assertEqual(response.status_code, 404)

    # --- reviews ------------------------------------------------------------

    def test_reviews_for_unknown_profile_is_404(self):
        """A missing profile is a 404, not an empty review list."""
        response = self.client.get('/api/v1/profiles/01NONEXISTENTNONEXISTENT00/reviews/')
        self.assertEqual(response.status_code, 404)

    # --- psych --------------------------------------------------------------

    def test_psych_hash_wrong_length_is_400(self):
        response = self.client.post(
            '/api/v1/profiles/me/psych/',
            data={'psych_hash_4': ['one', 'two']},
            content_type='application/json',
            HTTP_AUTHORIZATION=self._bearer(self.alice_account),
        )
        self.assertEqual(response.status_code, 400)

    def test_psych_form3_answer_out_of_range_is_400(self):
        response = self.client.post(
            '/api/v1/profiles/me/psych/',
            data={'form3_data': {'q1': 9}},
            content_type='application/json',
            HTTP_AUTHORIZATION=self._bearer(self.alice_account),
        )
        self.assertEqual(response.status_code, 400)

    def test_psych_valid_update_is_200(self):
        response = self.client.post(
            '/api/v1/profiles/me/psych/',
            data={'psych_hash_4': ['calm', 'sharp', 'warm', 'open']},
            content_type='application/json',
            HTTP_AUTHORIZATION=self._bearer(self.alice_account),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['psych_hash_4'], ['calm', 'sharp', 'warm', 'open'])

    def test_psych_of_unknown_profile_is_404(self):
        response = self.client.get(
            '/api/v1/profiles/01NONEXISTENTNONEXISTENT00/psych/',
            HTTP_AUTHORIZATION=self._bearer(self.alice_account),
        )
        self.assertEqual(response.status_code, 404)
