"""
Barter exchange endpoints exercised over HTTP, for their status codes.

barter/tests.py calls the view functions directly, which never runs
django-ninja's response layer — the layer that decides the status code and
that a malformed return blows up in. These three paths used to answer 500
where they meant 404/403; only an over-the-wire assertion can hold that line.
"""

from django.test import TestCase

from barter.tests import (
    _create_instance,
    _create_account,
    _create_profile,
    _create_exchange,
)


class BarterExchangeHttpStatusTest(TestCase):
    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance, 'bob')
        self.exchange = _create_exchange(user_chain=[self.alice.id, self.bob.id, self.alice.id])

    def _bearer(self, account):
        from ninja_jwt.tokens import RefreshToken
        return f'Bearer {RefreshToken.for_user(account).access_token}'

    def test_unknown_exchange_is_404(self):
        response = self.client.get(
            '/api/v1/barter/exchanges/nonexistent-id',
            HTTP_AUTHORIZATION=self._bearer(self.alice_account),
        )
        self.assertEqual(response.status_code, 404)

    def test_known_exchange_is_200(self):
        response = self.client.get(
            f'/api/v1/barter/exchanges/{self.exchange.id}',
            HTTP_AUTHORIZATION=self._bearer(self.alice_account),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['cri'], self.exchange.id)

    def test_approve_by_non_participant_is_403(self):
        charlie_account = _create_account(self.instance, 'charlie')
        _create_profile(charlie_account, self.instance, 'charlie')

        response = self.client.post(
            f'/api/v1/barter/exchanges/{self.exchange.id}/approve',
            data={'approved': True},
            content_type='application/json',
            HTTP_AUTHORIZATION=self._bearer(charlie_account),
        )
        self.assertEqual(response.status_code, 403)

    def test_approve_unknown_exchange_is_404(self):
        response = self.client.post(
            '/api/v1/barter/exchanges/fake-id/approve',
            data={'approved': True},
            content_type='application/json',
            HTTP_AUTHORIZATION=self._bearer(self.alice_account),
        )
        self.assertEqual(response.status_code, 404)
