"""
Invite endpoints exercised over HTTP, through django-ninja's response layer.

Kept separate from identity/tests.py, which calls view functions directly:
that path skips response serialization entirely, so it cannot see a status
code at all. A view returning `(body, status)` instead of `(status, body)`
serializes fine as a Python value and 500s only over the wire — the failure
that took /invite/{token} down for repeat visitors.

Covers: repeat accept, duplicate direct add, revoked token, SITE_URL-derived
invite link, and the quick-signup transaction.
"""

from unittest.mock import patch

from django.test import TestCase

from identity.models import Account, Profile, Partner
from identity.tests import _create_instance, _create_account, _create_profile


class PartnerInviteHttpTest(TestCase):
    """Exercise the invite endpoints over HTTP.

    Calling the view function directly (as PartnerInviteTest does) skips
    django-ninja's response layer, where a return value shaped
    `(body, status)` instead of `(status, body)` blows up with
    `TypeError: unhashable type: 'dict'` -> 500. These tests cover the
    already-a-partner branches, which are what a user hits by opening the
    same invite link twice.
    """

    def setUp(self):
        from django.core.cache import cache

        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance, local_name='bob')
        self.alice.generate_invite_token()
        # Rate-limit counters live in Redis and outlive the test DB, so a
        # 3/h endpoint like quick-signup would start 429ing on re-runs.
        cache.clear()

    def _bearer(self, account):
        from ninja_jwt.tokens import RefreshToken
        return f'Bearer {RefreshToken.for_user(account).access_token}'

    def test_accept_same_invite_twice_returns_200(self):
        """Opening the same invite link again is a no-op, not a 500."""
        Partner.objects.create(profile=self.bob, partner_profile=self.alice)

        response = self.client.post(
            '/api/v1/partners/accept/',
            data={'invite_token': self.alice.invite_token},
            content_type='application/json',
            HTTP_AUTHORIZATION=self._bearer(self.bob_account),
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['message'], 'Already in your partners')
        # The page renders the inviter's name from this payload
        self.assertEqual(body['partner']['hna'], self.alice.hna)

    def test_add_existing_partner_returns_200(self):
        """Direct add of someone already partnered is a no-op, not a 500."""
        Partner.objects.create(profile=self.bob, partner_profile=self.alice)

        response = self.client.post(
            f'/api/v1/partners/add/{self.alice.id}/',
            content_type='application/json',
            HTTP_AUTHORIZATION=self._bearer(self.bob_account),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['message'], 'Already in your partners')

    def test_accept_invalid_token_returns_400(self):
        """Revoked/unknown token stays a clean 400 over HTTP."""
        response = self.client.post(
            '/api/v1/partners/accept/',
            data={'invite_token': 'nonexistent-token-123'},
            content_type='application/json',
            HTTP_AUTHORIZATION=self._bearer(self.bob_account),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'Invalid or inactive invite token')

    def test_invite_url_uses_site_url(self):
        """Invite URL is built from SITE_URL, not a hardcoded domain."""
        with self.settings(SITE_URL='https://node2.example.org'):
            response = self.client.get(
                '/api/v1/partners/invite/',
                HTTP_AUTHORIZATION=self._bearer(self.alice_account),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()['invite_url'],
            f'https://node2.example.org/invite/{self.alice.invite_token}',
        )

    def test_quick_signup_creates_account_and_mutual_partnership(self):
        """Anonymous invite signup: account + profile + both partner rows + JWT."""
        with patch('parahub.endpoints.auth._check_username_available_in_matrix', return_value=True), \
                patch('parahub.endpoints.matrix_auth.create_dm_between_accounts', return_value=None), \
                self.settings(FEDERATION_DOMAIN='test.parahub.io'):
            response = self.client.post(
                '/api/v1/partners/quick-signup/',
                data={'invite_token': self.alice.invite_token, 'local_name': 'carol'},
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body['username'], 'carol')
        self.assertEqual(body['inviter_hna'], self.alice.hna)
        self.assertTrue(body['access_token'] and body['refresh_token'])

        carol = Profile.objects.get(local_name='carol')
        self.assertEqual(carol.invited_by_id, self.alice.id)
        self.assertTrue(Partner.objects.filter(profile=carol, partner_profile=self.alice).exists())
        self.assertTrue(Partner.objects.filter(profile=self.alice, partner_profile=carol).exists())

    def test_quick_signup_rolls_back_on_failure(self):
        """A failure mid-signup leaves no account that can log in without a profile."""
        with patch('parahub.endpoints.auth._check_username_available_in_matrix', return_value=True), \
                patch('parahub.endpoints.matrix_auth.create_dm_between_accounts', return_value=None), \
                patch('identity.models.Partner.objects.create', side_effect=RuntimeError('boom')), \
                self.settings(FEDERATION_DOMAIN='test.parahub.io'):
            response = self.client.post(
                '/api/v1/partners/quick-signup/',
                data={'invite_token': self.alice.invite_token, 'local_name': 'carol'},
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 500)
        self.assertFalse(Account.objects.filter(username='carol').exists())
        self.assertFalse(Profile.objects.filter(local_name='carol').exists())

    def test_quick_signup_rejects_reserved_username(self):
        """Reserved names are refused with a 400, not silently created."""
        with patch('parahub.endpoints.auth._check_username_available_in_matrix', return_value=True), \
                self.settings(FEDERATION_DOMAIN='test.parahub.io'):
            response = self.client.post(
                '/api/v1/partners/quick-signup/',
                data={'invite_token': self.alice.invite_token, 'local_name': 'admin'},
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Account.objects.filter(username='admin').exists())
