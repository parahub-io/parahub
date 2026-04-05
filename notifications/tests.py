"""
Tests for notification preference system.

Tests invariants that must never break:
- Profile.notification_prefs defaults to empty dict (all enabled)
- _should_notify respects per-category prefs
- Unknown notification types always send
- Missing profile = always send
- Allowed-keys filtering for pref updates
"""

from django.test import TestCase

from identity.models import Account, Profile
from core.models import Instance
from notifications.services import _should_notify


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_instance():
    return Instance.objects.create(
        domain='test.parahub.io',
        name='Test Instance',
        public_key='test-key',
    )


def _create_account(instance, username='alice', **kwargs):
    return Account.objects.create_user(
        username=username,
        email=f'{username}@test.parahub.io',
        password='testpass123',
        instance=instance,
        **kwargs,
    )


def _create_profile(account, instance, local_name=None, is_primary=True, **kwargs):
    local_name = local_name or account.username
    return Profile.objects.create(
        account=account,
        instance=instance,
        local_name=local_name,
        display_name=local_name.title(),
        is_primary=is_primary,
        profile_type=kwargs.pop('profile_type', Profile.ProfileType.PERSONAL),
        **kwargs,
    )


# ===========================================================================
# notification_prefs field defaults
# ===========================================================================

class NotificationPrefsDefaultTest(TestCase):
    """Test that Profile.notification_prefs defaults correctly."""

    def setUp(self):
        self.instance = _create_instance()
        self.account = _create_account(self.instance)
        self.profile = _create_profile(self.account, self.instance)

    def test_default_is_empty_dict(self):
        """Empty dict = all notifications enabled."""
        self.assertEqual(self.profile.notification_prefs, {})

    def test_default_persists_after_save(self):
        self.profile.save()
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.notification_prefs, {})

    def test_can_set_and_retrieve_prefs(self):
        self.profile.notification_prefs = {'social': False, 'contracts': True}
        self.profile.save(update_fields=['notification_prefs'])
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.notification_prefs, {'social': False, 'contracts': True})


# ===========================================================================
# _should_notify logic
# ===========================================================================

class ShouldNotifyTest(TestCase):
    """Test _should_notify respects per-category prefs."""

    def setUp(self):
        self.instance = _create_instance()
        self.account = _create_account(self.instance)
        self.profile = _create_profile(self.account, self.instance)

    def _set_prefs(self, prefs):
        self.profile.notification_prefs = prefs
        self.profile.save(update_fields=['notification_prefs'])

    def test_empty_prefs_all_enabled(self):
        """Empty prefs dict = all categories enabled."""
        self.assertTrue(_should_notify(self.account, 'partner_added'))
        self.assertTrue(_should_notify(self.account, 'new_contract'))
        self.assertTrue(_should_notify(self.account, 'new_poll'))
        self.assertTrue(_should_notify(self.account, 'incoming_call'))

    def test_disabled_social_blocks_partner_added(self):
        self._set_prefs({'social': False})
        self.assertFalse(_should_notify(self.account, 'partner_added'))

    def test_disabled_social_blocks_verification_received(self):
        self._set_prefs({'social': False})
        self.assertFalse(_should_notify(self.account, 'verification_received'))

    def test_disabled_contracts_blocks_new_contract(self):
        self._set_prefs({'contracts': False})
        self.assertFalse(_should_notify(self.account, 'new_contract'))

    def test_disabled_contracts_blocks_contract_signed(self):
        self._set_prefs({'contracts': False})
        self.assertFalse(_should_notify(self.account, 'contract_signed'))

    def test_disabled_contracts_blocks_new_debt(self):
        self._set_prefs({'contracts': False})
        self.assertFalse(_should_notify(self.account, 'new_debt'))

    def test_disabled_governance_blocks_new_poll(self):
        self._set_prefs({'governance': False})
        self.assertFalse(_should_notify(self.account, 'new_poll'))

    def test_disabled_calls_blocks_incoming_call(self):
        self._set_prefs({'calls': False})
        self.assertFalse(_should_notify(self.account, 'incoming_call'))

    def test_unknown_type_always_sends(self):
        """Unknown notification types bypass prefs check."""
        self._set_prefs({
            'social': False, 'contracts': False,
            'governance': False, 'calls': False,
        })
        self.assertTrue(_should_notify(self.account, 'unknown_type'))

    def test_no_profile_always_sends(self):
        """Account without a primary profile = always send."""
        orphan = Account.objects.create_user(
            username='orphan', email='orphan@test.parahub.io',
            password='testpass123', instance=self.instance,
        )
        self.assertTrue(_should_notify(orphan, 'partner_added'))

    def test_selective_disable(self):
        """Disabling one category doesn't affect others."""
        self._set_prefs({'social': False})
        self.assertFalse(_should_notify(self.account, 'partner_added'))
        self.assertTrue(_should_notify(self.account, 'new_contract'))
        self.assertTrue(_should_notify(self.account, 'new_poll'))

    def test_explicit_true_still_sends(self):
        self._set_prefs({'social': True})
        self.assertTrue(_should_notify(self.account, 'partner_added'))


# ===========================================================================
# Allowed-keys filtering (endpoint logic)
# ===========================================================================

class NotificationPrefsFilteringTest(TestCase):
    """Test that the endpoint filtering logic keeps only allowed keys."""

    def setUp(self):
        self.instance = _create_instance()
        self.account = _create_account(self.instance)
        self.profile = _create_profile(self.account, self.instance)

    def _apply_endpoint_filter(self, raw_prefs):
        """Simulate the endpoint's allowed-keys filtering."""
        allowed_keys = {'social', 'contracts', 'governance', 'calls'}
        return {k: bool(v) for k, v in raw_prefs.items() if k in allowed_keys}

    def test_allowed_keys_pass_through(self):
        result = self._apply_endpoint_filter({
            'social': False, 'contracts': True,
            'governance': False, 'calls': True,
        })
        self.assertEqual(result, {
            'social': False, 'contracts': True,
            'governance': False, 'calls': True,
        })

    def test_disallowed_keys_filtered_out(self):
        result = self._apply_endpoint_filter({
            'social': False, 'evil_key': True, 'admin': True,
        })
        self.assertNotIn('evil_key', result)
        self.assertNotIn('admin', result)
        self.assertIn('social', result)

    def test_values_coerced_to_bool(self):
        result = self._apply_endpoint_filter({'social': 0, 'calls': 1})
        self.assertIs(result['social'], False)
        self.assertIs(result['calls'], True)

    def test_empty_input(self):
        result = self._apply_endpoint_filter({})
        self.assertEqual(result, {})
