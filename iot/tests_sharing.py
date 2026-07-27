"""Device sharing: universal ObjectAccess grants, claim-by-MAC, transfer.

Invariants:
- role ladder: OWNER (FK) > MANAGER > VIEWER; a missing grant is a 404 (no
  existence leak), an insufficient one is a 403
- the device list returns own + granted devices, with the viewer's effective
  role and the owner reference on shared rows
- only devices still owned by the fleet pool profile are claimable; claiming
  reassigns ownership, auto-grants the support profile MANAGER (revocable) and
  writes an OwnershipLog row
- transfer moves the owner FK, optionally leaving the previous owner a MANAGER
  grant, and supersedes any pre-existing grant of the new owner
"""

import json
from unittest.mock import patch

from django.http import Http404
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone
from ninja.errors import HttpError

from core.access import ROLE_MANAGER, ROLE_OWNER, ROLE_VIEWER, get_role
from core.models import Instance, ObjectAccess, OwnershipLog
from identity.models import Account, Profile
from iot.api.access import get_device_for
from iot.api.devices import (
    DeviceRenameIn, delete_device, get_device, list_devices, rename_device,
)
from iot.api.sharing import (
    ClaimIn, GrantIn, TransferIn, claim_device, claim_preview,
    grant_device_access, list_device_access, revoke_device_access,
    transfer_device,
)
from iot.models import IoTDevice

LOCMEM_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}


def _profile(instance, username):
    account = Account.objects.create_user(
        username=username, email=f'{username}@test.parahub.io',
        password='x', instance=instance)
    return Profile.objects.create(
        account=account, instance=instance, local_name=username,
        display_name=username.title(), is_primary=True)


class SharingTestBase(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.instance = Instance.objects.create(
            domain='test.parahub.io', name='Test', public_key='k',
            trust_level='local')
        self.owner = _profile(self.instance, 'deviceowner')
        self.friend = _profile(self.instance, 'friend')
        self.stranger = _profile(self.instance, 'stranger')
        self.device = IoTDevice.objects.create(
            device_id='aa:bb:cc:dd:ee:01', device_type='MESH_ROUTER',
            name='Parahub-EE01', owner=self.owner, last_seen=timezone.now())

    def _req(self, profile, method='get', body=None):
        factory = getattr(self.rf, method)
        request = factory('/', data=json.dumps(body) if body else None,
                          content_type='application/json')
        request.auth_profile = profile
        return request

    def _grant(self, profile, role=ROLE_VIEWER):
        return ObjectAccess.objects.create(
            object_id=self.device.id, profile=profile, role=role,
            granted_by=self.owner)


class AccessRoleTests(SharingTestBase):
    def test_owner_role_from_fk(self):
        self.assertEqual(get_role(self.device, self.owner), ROLE_OWNER)

    def test_stranger_gets_404_not_403(self):
        with self.assertRaises(Http404):
            get_device_for(self.stranger, self.device.id)

    def test_viewer_can_read_but_not_manage(self):
        self._grant(self.friend, ROLE_VIEWER)
        out = get_device(self._req(self.friend), self.device.id)
        self.assertEqual(out.access_role, 'VIEWER')
        self.assertEqual(out.owner_hna, self.owner.hna)
        with self.assertRaises(HttpError) as ctx:
            rename_device(self._req(self.friend, 'patch'), self.device.id,
                          DeviceRenameIn(name='hacked'))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_manager_can_rename_but_not_delete(self):
        self._grant(self.friend, ROLE_MANAGER)
        out = rename_device(self._req(self.friend, 'patch'), self.device.id,
                            DeviceRenameIn(name='Village AP'))
        self.assertEqual(out.name, 'Village AP')
        with self.assertRaises(HttpError) as ctx:
            delete_device(self._req(self.friend, 'delete'), self.device.id)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_list_includes_shared_with_role_and_owner(self):
        self._grant(self.friend, ROLE_VIEWER)
        IoTDevice.objects.create(
            device_id='imei-1', device_type='TRACKER', name='Own tracker',
            owner=self.friend)
        with patch('iot.api.devices.TraccarService.sync_devices_from_traccar',
                   return_value=0):
            rows = list_devices(self._req(self.friend))
        by_name = {r.name: r for r in rows}
        self.assertEqual(by_name['Own tracker'].access_role, 'OWNER')
        self.assertIsNone(by_name['Own tracker'].owner_hna)
        shared = by_name['Parahub-EE01']
        self.assertEqual(shared.access_role, 'VIEWER')
        self.assertEqual(shared.owner_hna, self.owner.hna)

    def test_owner_grants_and_grantee_self_revokes(self):
        out = grant_device_access(
            self._req(self.owner, 'post'), self.device.id,
            GrantIn(handle='friend', role='viewer'))
        self.assertEqual(out.role, 'VIEWER')
        grant = ObjectAccess.objects.get(object_id=self.device.id, profile=self.friend)

        # Stranger cannot revoke (no device access at all -> 404)
        with self.assertRaises(Http404):
            revoke_device_access(self._req(self.stranger, 'delete'),
                                 self.device.id, grant.id)
        # Grantee removes their own grant
        revoke_device_access(self._req(self.friend, 'delete'),
                             self.device.id, grant.id)
        self.assertFalse(ObjectAccess.objects.filter(id=grant.id).exists())

    def test_non_owner_cannot_grant(self):
        self._grant(self.friend, ROLE_MANAGER)
        with self.assertRaises(HttpError) as ctx:
            grant_device_access(self._req(self.friend, 'post'), self.device.id,
                                GrantIn(handle='stranger', role='VIEWER'))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_regrant_updates_role(self):
        self._grant(self.friend, ROLE_VIEWER)
        grant_device_access(self._req(self.owner, 'post'), self.device.id,
                            GrantIn(handle='friend', role='MANAGER'))
        self.assertEqual(
            ObjectAccess.objects.get(object_id=self.device.id, profile=self.friend).role,
            'MANAGER')

    def test_device_delete_cascades_grants(self):
        self._grant(self.friend, ROLE_VIEWER)
        self.device.delete()
        self.assertFalse(ObjectAccess.objects.filter(profile=self.friend).exists())


class ClaimTests(SharingTestBase):
    def setUp(self):
        super().setUp()
        self.pool = _profile(self.instance, 'parahub-fleet-test')
        self.support = _profile(self.instance, 'support')
        self.pooled = IoTDevice.objects.create(
            device_id='aa:bb:cc:dd:ee:02', device_type='MESH_ROUTER',
            name='Parahub-EE02', owner=self.pool, last_seen=timezone.now(),
            connection_info={'hardware_profile': 'cudy_ap3000outdoor-v1',
                             'firmware_role': 'bumblebee'})

    def _claim_settings(self):
        return override_settings(
            MESH_DEFAULT_OWNER_PROFILE_ID=self.pool.id,
            MESH_SUPPORT_PROFILE_ID=self.support.id,
        )

    def test_preview_returns_device_without_mutation(self):
        with self._claim_settings():
            out = claim_preview(self._req(self.friend, 'post'),
                                ClaimIn(mac='AA-BB-CC-DD-EE-02'))
        self.assertEqual(out.name, 'Parahub-EE02')
        self.assertEqual(out.hardware_profile, 'cudy_ap3000outdoor-v1')
        self.assertTrue(out.online)
        self.pooled.refresh_from_db()
        self.assertEqual(self.pooled.owner_id, self.pool.id)

    def test_claim_transfers_ownership_grants_support_and_logs(self):
        with self._claim_settings():
            out = claim_device(self._req(self.friend, 'post'),
                               ClaimIn(mac='aabbccddee02'))
        self.assertEqual(out.status, 'claimed')
        self.pooled.refresh_from_db()
        self.assertEqual(self.pooled.owner_id, self.friend.id)
        support_grant = ObjectAccess.objects.get(
            object_id=self.pooled.id, profile=self.support)
        self.assertEqual(support_grant.role, 'MANAGER')
        log = OwnershipLog.objects.get(object_id=self.pooled.id)
        self.assertEqual(log.action, 'claim')
        self.assertEqual(log.new_owner_id, self.friend.id)
        self.assertEqual(log.previous_owner_id, self.pool.id)

    def test_owned_device_is_not_claimable(self):
        # self.device belongs to self.owner — never claimable, even with the
        # right MAC
        with self._claim_settings():
            with self.assertRaises(HttpError) as ctx:
                claim_device(self._req(self.stranger, 'post'),
                             ClaimIn(mac='aa:bb:cc:dd:ee:01'))
        self.assertEqual(ctx.exception.status_code, 404)
        self.device.refresh_from_db()
        self.assertEqual(self.device.owner_id, self.owner.id)

    def test_invalid_mac_rejected(self):
        with self._claim_settings():
            with self.assertRaises(HttpError) as ctx:
                claim_preview(self._req(self.friend, 'post'), ClaimIn(mac='zz:zz'))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_unconfigured_pool_disables_claim(self):
        with override_settings(MESH_DEFAULT_OWNER_PROFILE_ID=''):
            with self.assertRaises(HttpError) as ctx:
                claim_preview(self._req(self.friend, 'post'),
                              ClaimIn(mac='aa:bb:cc:dd:ee:02'))
        self.assertEqual(ctx.exception.status_code, 503)


class RoutingTests(TestCase):
    def test_claim_path_not_shadowed_by_device_id_operations(self):
        # Ninja resolves paths in registration order and {param} segments match
        # literals: if /devices/{device_id} (GET/DELETE) registered before the
        # literal POST /devices/claim, the claim POST dies with 405. The
        # sharing module must import before devices in iot/api/__init__.py.
        for path in ('/api/v1/iot/devices/claim', '/api/v1/iot/devices/claim/preview'):
            resp = self.client.post(path, data='{"mac": "x"}',
                                    content_type='application/json')
            # 401 = reached the endpoint's auth gate; 405 = shadowed routing
            self.assertEqual(resp.status_code, 401, path)


class TransferTests(SharingTestBase):
    def test_transfer_keeps_previous_owner_as_manager(self):
        out = transfer_device(self._req(self.owner, 'post'), self.device.id,
                              TransferIn(handle='friend', keep_access=True))
        self.device.refresh_from_db()
        self.assertEqual(self.device.owner_id, self.friend.id)
        self.assertEqual(get_role(self.device, self.owner), ROLE_MANAGER)
        self.assertFalse(out.is_owner)
        log = OwnershipLog.objects.get(object_id=self.device.id)
        self.assertEqual(log.action, 'transfer')

    def test_transfer_without_keep_access_drops_previous_owner(self):
        transfer_device(self._req(self.owner, 'post'), self.device.id,
                        TransferIn(handle='friend', keep_access=False))
        self.device.refresh_from_db()
        self.assertIsNone(get_role(self.device, self.owner))

    def test_transfer_supersedes_new_owners_grant(self):
        self._grant(self.friend, ROLE_VIEWER)
        transfer_device(self._req(self.owner, 'post'), self.device.id,
                        TransferIn(handle='friend'))
        # Friend owns it now — the old VIEWER grant row must be gone
        self.assertFalse(ObjectAccess.objects.filter(
            object_id=self.device.id, profile=self.friend).exists())
        self.device.refresh_from_db()
        self.assertEqual(get_role(self.device, self.friend), ROLE_OWNER)

    def test_manager_cannot_transfer(self):
        self._grant(self.friend, ROLE_MANAGER)
        with self.assertRaises(HttpError) as ctx:
            transfer_device(self._req(self.friend, 'post'), self.device.id,
                            TransferIn(handle='stranger'))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_access_list_visible_to_manager(self):
        self._grant(self.friend, ROLE_MANAGER)
        out = list_device_access(self._req(self.friend), self.device.id)
        self.assertFalse(out.is_owner)
        self.assertEqual(len(out.grants), 1)
        self.assertEqual(out.grants[0].profile_name, 'Friend')

    def test_viewer_can_list_access_but_stranger_cannot(self):
        self._grant(self.friend, ROLE_VIEWER)
        out = list_device_access(self._req(self.friend), self.device.id)
        self.assertFalse(out.is_owner)
        with self.assertRaises(Http404):
            list_device_access(self._req(self.stranger), self.device.id)
