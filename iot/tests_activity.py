"""Device console journal: what the middleware records, and who may read it.

Invariants:
- every completed mutation on a device lands in ObjectActionLog with the
  actor's effective role at that moment; plain reads do not
- a GET that hands out a credential (root/WiFi password) is recorded too — the
  point of the journal is disclosure, not just change
- request bodies contribute keys, never values: the journal must not become a
  second home for the WiFi password it just carried
- a 403 is recorded (someone with access reached past their role), an
  unauthenticated or unknown-device call is not (no actor to name)
- deleting the device leaves its journal standing — an audit trail that a
  delete erases is not one
- the journal is readable by anyone with access to the device, so an owner sees
  what a helper did and a helper sees the same record
"""

from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from ninja_jwt.tokens import RefreshToken

from core.access import ROLE_MANAGER, ROLE_VIEWER
from core.models import Instance, ObjectAccess, ObjectActionLog
from identity.models import Account, Profile
from iot.models import IoTDevice

LOCMEM_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}


def _profile(instance, username):
    account = Account.objects.create_user(
        username=username, email=f'{username}@test.parahub.io',
        password='x', instance=instance)
    profile = Profile.objects.create(
        account=account, instance=instance, local_name=username,
        display_name=username.title(), is_primary=True)
    return profile


class DeviceActivityTests(TestCase):
    def setUp(self):
        self.instance = Instance.objects.create(
            domain='test.parahub.io', name='Test', public_key='k',
            trust_level='local')
        self.owner = _profile(self.instance, 'journalowner')
        self.helper = _profile(self.instance, 'journalhelper')
        self.watcher = _profile(self.instance, 'journalwatcher')
        self.stranger = _profile(self.instance, 'journalstranger')
        self.device = IoTDevice.objects.create(
            device_id='aa:bb:cc:dd:ee:11', device_type='MESH_ROUTER',
            name='Parahub-EE11', owner=self.owner, last_seen=timezone.now(),
            connection_info={'firmware_role': 'bumblebee',
                             'yggdrasil_address': '200:1::1'})
        ObjectAccess.objects.create(object_id=self.device.id, profile=self.helper,
                                    role=ROLE_MANAGER, granted_by=self.owner)
        ObjectAccess.objects.create(object_id=self.device.id, profile=self.watcher,
                                    role=ROLE_VIEWER, granted_by=self.owner)

    def _bearer(self, profile):
        return f'Bearer {RefreshToken.for_user(profile.account).access_token}'

    def _rename(self, profile, name='Renamed'):
        return self.client.patch(
            f'/api/v1/iot/devices/{self.device.id}/rename',
            data={'name': name}, content_type='application/json',
            HTTP_AUTHORIZATION=self._bearer(profile))

    def _rows(self):
        return list(ObjectActionLog.objects.filter(object_id=self.device.id))

    # --- what gets written --------------------------------------------------

    def test_mutation_records_actor_role_and_fields_not_values(self):
        self.assertEqual(self._rename(self.helper, 'Kitchen AP').status_code, 200)
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.action, 'rename')
        self.assertEqual(row.actor_id, self.helper.id)
        self.assertEqual(row.role, ROLE_MANAGER)
        self.assertEqual(row.detail['method'], 'PATCH')
        self.assertEqual(row.detail['status'], 200)
        self.assertEqual(row.detail['fields'], ['name'])
        # The value travelled, the journal kept only the shape of the call
        self.assertNotIn('Kitchen AP', str(row.detail))

    def test_owner_action_records_owner_role(self):
        self._rename(self.owner)
        self.assertEqual(self._rows()[0].role, 'OWNER')

    def test_plain_read_is_not_recorded(self):
        response = self.client.get(f'/api/v1/iot/devices/{self.device.id}',
                                   HTTP_AUTHORIZATION=self._bearer(self.owner))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._rows(), [])

    def test_credential_read_is_recorded(self):
        # The endpoint reads the password off the node; the journal entry is
        # about the disclosure, so the SSH leg is stubbed
        with patch('iot.api.mesh._mesh_ssh') as ssh:
            ssh.return_value.returncode = 0
            ssh.return_value.stdout = 'hunter2\n'
            response = self.client.get(
                f'/api/v1/iot/devices/{self.device.id}/root-password',
                HTTP_AUTHORIZATION=self._bearer(self.helper))
        self.assertEqual(response.status_code, 200)
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].action, 'root-password:read')
        self.assertEqual(rows[0].detail['method'], 'GET')
        self.assertNotIn('hunter2', str(rows[0].detail))

    def test_denied_attempt_is_recorded_with_the_role_that_was_short(self):
        self.assertEqual(self._rename(self.watcher).status_code, 403)
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].role, ROLE_VIEWER)
        self.assertEqual(rows[0].detail['status'], 403)

    def test_stranger_and_anonymous_are_not_recorded(self):
        # 404 hides the device's existence; there is nothing to journal on an
        # object the caller may not know about
        self.assertEqual(self._rename(self.stranger).status_code, 404)
        anon = self.client.patch(
            f'/api/v1/iot/devices/{self.device.id}/rename',
            data={'name': 'x'}, content_type='application/json')
        self.assertEqual(anon.status_code, 401)
        self.assertEqual(self._rows(), [])

    def test_delete_leaves_the_journal_standing(self):
        response = self.client.delete(f'/api/v1/iot/devices/{self.device.id}',
                                      HTTP_AUTHORIZATION=self._bearer(self.owner))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(IoTDevice.objects.filter(id=self.device.id).exists())
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].action, 'device')
        self.assertEqual(rows[0].detail['method'], 'DELETE')
        # The role that allowed it is gone with the device — not invented
        self.assertEqual(rows[0].role, '')

    # --- who may read it ----------------------------------------------------

    def test_activity_is_readable_by_everyone_with_access(self):
        self._rename(self.helper, 'Hallway AP')
        for profile in (self.owner, self.helper, self.watcher):
            response = self.client.get(
                f'/api/v1/iot/devices/{self.device.id}/activity',
                HTTP_AUTHORIZATION=self._bearer(profile))
            self.assertEqual(response.status_code, 200, profile.local_name)
            body = response.json()
            self.assertEqual(len(body), 1, profile.local_name)
            self.assertEqual(body[0]['action'], 'rename')
            self.assertEqual(body[0]['actor_name'], 'Journalhelper')
            self.assertEqual(body[0]['role'], ROLE_MANAGER)
            self.assertEqual(body[0]['fields'], ['name'])

    def test_activity_hidden_from_strangers(self):
        response = self.client.get(
            f'/api/v1/iot/devices/{self.device.id}/activity',
            HTTP_AUTHORIZATION=self._bearer(self.stranger))
        self.assertEqual(response.status_code, 404)

    def test_activity_is_newest_first(self):
        self._rename(self.owner, 'First')
        self._rename(self.helper, 'Second')
        body = self.client.get(
            f'/api/v1/iot/devices/{self.device.id}/activity',
            HTTP_AUTHORIZATION=self._bearer(self.owner)).json()
        self.assertEqual([r['actor_name'] for r in body],
                         ['Journalhelper', 'Journalowner'])

    def test_reading_the_activity_list_does_not_log_itself(self):
        self.client.get(f'/api/v1/iot/devices/{self.device.id}/activity',
                        HTTP_AUTHORIZATION=self._bearer(self.owner))
        self.assertEqual(self._rows(), [])
