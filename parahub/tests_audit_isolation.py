"""
Audit-log git isolation tests.

Guard the settings-level test redirect of AUDIT_LOG_GIT_PATH: test runs must
never write to the real audit-log repos (the public one is pushed to Gitea and
Bitcoin-anchored — test records there are permanent public noise), while the
redirected temp repos must stay fully functional so registry code paths are
still exercised end-to-end.
"""
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase

from audit_log.registry import RegistryService
from core.models import Instance
from geo.models import Establishment
from identity.models import Account, Profile
from parahub.tmpdirs import scratch_root


class AuditGitIsolationTests(TestCase):
    def test_audit_git_path_redirected_away_from_real_repo(self):
        real_root = settings.BASE_DIR / 'audit-log'
        self.assertNotEqual(Path(settings.AUDIT_LOG_GIT_PATH), real_root)
        self.assertTrue(
            str(settings.AUDIT_LOG_GIT_PATH).startswith(scratch_root('test-audit')),
            f'audit repos must live in the test-audit scratch root, got '
            f'{settings.AUDIT_LOG_GIT_PATH}')
        self.assertEqual(settings.AUDIT_LOG_PUBLIC_GIT_REMOTE, '')

    def test_registry_service_commits_into_redirected_repo(self):
        instance = Instance.objects.create(
            domain='test.parahub.io', name='Test Instance', public_key='k')
        account = Account.objects.create_user(
            username='isotest', email='isotest@test.parahub.io',
            password='x', instance=instance, is_test=True)
        profile = Profile.objects.create(
            account=account, instance=instance, local_name='isotest',
            display_name='Iso Test', is_primary=True,
            profile_type=Profile.ProfileType.PERSONAL)
        establishment = Establishment.objects.create(
            name='Isolation Test Cafe', owner=profile)

        with patch.object(RegistryService, '_sign_with_node_key', return_value=None):
            commit_sha = RegistryService().register_organization(establishment)

        self.assertIsNotNone(commit_sha)
        org_file = (Path(settings.AUDIT_LOG_GIT_PATH) / 'public-git'
                    / 'organizations' / f'{establishment.id}.json')
        self.assertTrue(org_file.exists())
