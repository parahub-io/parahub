"""
Federation endpoint tests — the profile-migration lifecycle and the
inter-node confirmation endpoint (the multi-signature heart of federation,
previously untested).

External boundaries are mocked: the git registry (RegistryService), the
account export ZIP (ProofExportService) and the WS broadcast. Endpoints are
called directly with RequestFactory requests, market/tests.py style; the
rate limiter skips localhost so it does not interfere.
"""

import hashlib
import io
import json
from unittest.mock import patch

from django.test import TestCase, RequestFactory
from ninja.errors import HttpError

from identity.models import Account, Profile
from core.models import Instance, ProfileMigration
from parahub.endpoints.federation import (
    initiate_migration, sign_migration, export_migration_data,
    complete_migration, cancel_migration, get_migration, list_migrations,
    confirm_migration_from_peer,
)


class FederationMigrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.instance = Instance.objects.create(
            domain='test.parahub.io', name='Test Instance', public_key='k')

        def make_profile(username, is_staff=False):
            account = Account.objects.create_user(
                username=username, email=f'{username}@test.parahub.io',
                password='x', instance=cls.instance, is_staff=is_staff)
            return Profile.objects.create(
                account=account, instance=cls.instance, local_name=username,
                display_name=username.title(), is_primary=True,
                profile_type=Profile.ProfileType.PERSONAL)

        cls.alice = make_profile('fedalice')
        cls.bob = make_profile('fedbob')
        cls.staff = make_profile('fedstaff', is_staff=True)
        cls.factory = RequestFactory()

    def _req(self, profile=None, method='post', body=None):
        fn = getattr(self.factory, method)
        if body is not None:
            request = fn('/fake/', data=json.dumps(body), content_type='application/json')
        else:
            request = fn('/fake/')
        if profile is not None:
            request.user = profile.account
            request.auth = profile
        return request

    def _initiate(self, profile=None, **kwargs):
        kwargs.setdefault('to_node', 'other.example.org')
        with patch('audit_log.registry.RegistryService._sign_with_node_key',
                   return_value='NODE-SIG'):
            return initiate_migration(self._req(profile or self.alice), **kwargs)

    # ── initiate ─────────────────────────────────────────────────────

    def test_initiate_creates_signed_record(self):
        resp = self._initiate(reason='moving home')
        self.assertEqual(resp['status'], ProfileMigration.INITIATED)
        self.assertTrue(resp['from_hna'].startswith('fedalice@'))
        self.assertEqual(resp['to_node'], 'other.example.org')
        self.assertTrue(resp['has_from_node_signature'])
        self.assertFalse(resp['has_from_signature'])
        m = ProfileMigration.objects.get(id=resp['id'])
        self.assertEqual(m.from_node_signature, 'NODE-SIG')
        self.assertEqual(m.reason, 'moving home')

    def test_initiate_derives_to_node_from_hna(self):
        resp = self._initiate(to_node='', to_hna='fedalice@dest.example.org')
        self.assertEqual(resp['to_node'], 'dest.example.org')

    def test_initiate_rejects_second_active_migration(self):
        self._initiate()
        with self.assertRaises(HttpError) as cm:
            self._initiate()
        self.assertEqual(cm.exception.status_code, 409)

    def test_initiate_allowed_after_cancel(self):
        first = self._initiate()
        cancel_migration(self._req(self.alice), first['id'])
        second = self._initiate()
        self.assertNotEqual(first['id'], second['id'])

    # ── sign ─────────────────────────────────────────────────────────

    def test_sign_stores_signature_and_proof(self):
        m = self._initiate()
        resp = sign_migration(self._req(self.alice), m['id'],
                              signature='USER-SIG', continuity_proof='PROOF')
        self.assertTrue(resp['has_from_signature'])
        self.assertEqual(resp['continuity_proof'], 'PROOF')

    def test_sign_foreign_migration_forbidden(self):
        m = self._initiate()
        with self.assertRaises(HttpError) as cm:
            sign_migration(self._req(self.bob), m['id'], signature='X')
        self.assertEqual(cm.exception.status_code, 403)

    def test_sign_rejected_after_cancel(self):
        m = self._initiate()
        cancel_migration(self._req(self.alice), m['id'])
        with self.assertRaises(HttpError) as cm:
            sign_migration(self._req(self.alice), m['id'], signature='X')
        self.assertEqual(cm.exception.status_code, 400)

    def test_sign_unknown_migration_404(self):
        with self.assertRaises(HttpError) as cm:
            sign_migration(self._req(self.alice), '01AAAAAAAAAAAAAAAAAAAAAAAA', signature='X')
        self.assertEqual(cm.exception.status_code, 404)

    # ── export ───────────────────────────────────────────────────────

    def test_export_sets_hash_and_status(self):
        m = self._initiate()
        with patch('audit_log.services.ProofExportService.export_full_account',
                   return_value=io.BytesIO(b'zipdata')):
            resp = export_migration_data(self._req(self.alice), m['id'])
        self.assertEqual(b''.join(resp.streaming_content), b'zipdata')
        mig = ProfileMigration.objects.get(id=m['id'])
        self.assertEqual(mig.status, ProfileMigration.EXPORTED)
        self.assertEqual(mig.export_hash, hashlib.sha256(b'zipdata').hexdigest())

    def test_export_foreign_migration_forbidden(self):
        m = self._initiate()
        with self.assertRaises(HttpError) as cm:
            export_migration_data(self._req(self.bob), m['id'])
        self.assertEqual(cm.exception.status_code, 403)

    # ── complete ─────────────────────────────────────────────────────

    def _complete(self, migration_id, profile, **kwargs):
        with patch('audit_log.registry.RegistryService.register_migration',
                   return_value='cafe1234') as reg, \
             patch('parahub.services.ws_publish.ws_publish') as ws:
            resp = complete_migration(self._req(profile), migration_id, **kwargs)
        return resp, reg, ws

    def test_complete_requires_source_signature(self):
        m = self._initiate()
        with self.assertRaises(HttpError) as cm:
            self._complete(m['id'], self.alice)
        self.assertEqual(cm.exception.status_code, 400)

    def test_complete_by_stranger_forbidden(self):
        m = self._initiate()
        sign_migration(self._req(self.alice), m['id'], signature='USER-SIG')
        with self.assertRaises(HttpError) as cm:
            self._complete(m['id'], self.bob)
        self.assertEqual(cm.exception.status_code, 403)

    def test_complete_happy_path_commits_registry_and_broadcasts(self):
        m = self._initiate(to_hna='fedalice@dest.example.org', to_node='')
        sign_migration(self._req(self.alice), m['id'], signature='USER-SIG')
        resp, reg, ws = self._complete(m['id'], self.alice, to_user_signature='DEST-SIG')
        self.assertEqual(resp['status'], ProfileMigration.COMPLETED)
        self.assertEqual(resp['git_commit_hash'], 'cafe1234')
        self.assertTrue(resp['has_to_signature'])
        reg.assert_called_once()
        self.assertEqual(reg.call_args.kwargs['from_signature'], 'USER-SIG')
        self.assertEqual(reg.call_args.kwargs['to_signature'], 'DEST-SIG')
        ws.assert_called_once()
        # completed migrations are terminal
        with self.assertRaises(HttpError) as cm:
            self._complete(m['id'], self.alice)
        self.assertEqual(cm.exception.status_code, 400)

    def test_complete_by_staff_allowed(self):
        m = self._initiate()
        sign_migration(self._req(self.alice), m['id'], signature='USER-SIG')
        resp, _, _ = self._complete(m['id'], self.staff)
        self.assertEqual(resp['status'], ProfileMigration.COMPLETED)

    # ── cancel / read ────────────────────────────────────────────────

    def test_cancel_completed_migration_rejected(self):
        m = self._initiate()
        sign_migration(self._req(self.alice), m['id'], signature='USER-SIG')
        self._complete(m['id'], self.alice)
        with self.assertRaises(HttpError) as cm:
            cancel_migration(self._req(self.alice), m['id'])
        self.assertEqual(cm.exception.status_code, 400)

    def test_get_foreign_migration_forbidden_but_staff_allowed(self):
        m = self._initiate()
        with self.assertRaises(HttpError) as cm:
            get_migration(self._req(self.bob, method='get'), m['id'])
        self.assertEqual(cm.exception.status_code, 403)
        resp = get_migration(self._req(self.staff, method='get'), m['id'])
        self.assertEqual(resp['id'], m['id'])

    def test_list_scoped_to_owner_except_staff(self):
        mine = self._initiate()
        own = list_migrations(self._req(self.alice, method='get'))
        self.assertEqual([m['id'] for m in own], [mine['id']])
        self.assertEqual(list_migrations(self._req(self.bob, method='get')), [])
        staff_view = list_migrations(self._req(self.staff, method='get'))
        self.assertIn(mine['id'], [m['id'] for m in staff_view])

    # ── inter-node confirm (auth=None) ───────────────────────────────

    def test_confirm_requires_id_and_domain(self):
        with self.assertRaises(HttpError) as cm:
            confirm_migration_from_peer(self._req(body={'migration_id': 'x'}))
        self.assertEqual(cm.exception.status_code, 400)

    def test_confirm_invalid_json_400(self):
        request = self.factory.post('/fake/', data='not-json', content_type='application/json')
        with self.assertRaises(HttpError) as cm:
            confirm_migration_from_peer(request)
        self.assertEqual(cm.exception.status_code, 400)

    def test_confirm_domain_mismatch_forbidden(self):
        m = self._initiate(to_node='dest.example.org')
        with self.assertRaises(HttpError) as cm:
            confirm_migration_from_peer(self._req(body={
                'migration_id': m['id'], 'domain': 'evil.example.org',
                'to_node_signature': 'X'}))
        self.assertEqual(cm.exception.status_code, 403)

    def test_confirm_stores_signatures_on_domain_match(self):
        # Documents the CURRENT contract: the endpoint checks only that the
        # claimed domain equals migration.to_node — it does NOT verify the
        # signatures against the peer node's PGP key (tracked in PK/issues.md).
        m = self._initiate(to_node='dest.example.org')
        resp = confirm_migration_from_peer(self._req(body={
            'migration_id': m['id'], 'domain': 'dest.example.org',
            'to_node_signature': 'PEER-NODE-SIG', 'to_user_signature': 'PEER-USER-SIG'}))
        self.assertEqual(resp['status'], 'ok')
        mig = ProfileMigration.objects.get(id=m['id'])
        self.assertEqual(mig.to_node_signature, 'PEER-NODE-SIG')
        self.assertEqual(mig.to_user_signature, 'PEER-USER-SIG')
