"""Device sharing: universal ObjectAccess grants, claim-by-MAC, transfer.

Invariants:
- role ladder: OWNER (FK) > MANAGER > VIEWER; a missing grant is a 404 (no
  existence leak), an insufficient one is a 403
- the device list returns own + granted devices, with the viewer's effective
  role and the owner reference on shared rows
- only devices still owned by the fleet pool profile are claimable; claiming
  reassigns ownership and writes an OwnershipLog row, and leaves no grant behind
  (support is notified, never granted — remote help is the owner's to hand out)
- a claim matches any burned-in address the node reports (`hw_macs`), not only
  the device_id it registered under: the label carries the vendor's address,
  device_id is whatever br-private held at first boot
- transfer moves the owner FK, optionally leaving the previous owner a MANAGER
  grant, and supersedes any pre-existing grant of the new owner
- one physical tracker is one device row: Traccar permissions are many-to-many,
  so a device already owned here reaches other permitted users as a grant, and
  a Traccar device someone else owns is never adopted by a new registration
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
from iot.api.mesh import MeshHeartbeatIn, mesh_heartbeat
from iot.api.sharing import (
    ClaimIn, GrantIn, TransferIn, claim_device, claim_preview,
    grant_device_access, list_device_access, revoke_device_access,
    transfer_device,
)
from iot.models import IoTDevice
from iot.services import TraccarService

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
        # device_id is br-private's address; hw_macs are what the label may
        # actually carry (here: a second NIC, one octet off)
        self.pooled = IoTDevice.objects.create(
            device_id='aa:bb:cc:dd:ee:02', device_type='MESH_ROUTER',
            name='Parahub-EE02', owner=self.pool, last_seen=timezone.now(),
            connection_info={'hardware_profile': 'cudy_ap3000outdoor-v1',
                             'firmware_role': 'bumblebee',
                             'hw_macs': ['aa:bb:cc:dd:ee:02', 'aa:bb:cc:dd:ee:03']})

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

    def test_claim_transfers_ownership_leaves_no_grant_and_logs(self):
        with self._claim_settings():
            out = claim_device(self._req(self.friend, 'post'),
                               ClaimIn(mac='aabbccddee02'))
        self.assertEqual(out.status, 'claimed')
        self.pooled.refresh_from_db()
        self.assertEqual(self.pooled.owner_id, self.friend.id)
        # Nobody else keeps a key to a claimed router — not even support
        self.assertEqual(
            ObjectAccess.objects.filter(object_id=self.pooled.id).count(), 0)
        log = OwnershipLog.objects.get(object_id=self.pooled.id)
        self.assertEqual(log.action, 'claim')
        self.assertEqual(log.new_owner_id, self.friend.id)
        self.assertEqual(log.previous_owner_id, self.pool.id)

    def test_owned_device_is_not_claimable(self):
        # self.device belongs to self.owner — never claimable, even with the
        # right MAC. Answers "already owned", not "unknown MAC".
        with self._claim_settings():
            with self.assertRaises(HttpError) as ctx:
                claim_device(self._req(self.stranger, 'post'),
                             ClaimIn(mac='aa:bb:cc:dd:ee:01'))
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.code, 'claim_already_owned')
        self.device.refresh_from_db()
        self.assertEqual(self.device.owner_id, self.owner.id)

    def test_own_device_reports_already_yours(self):
        # Retyping the sticker of a router you already claimed must not send
        # you back to "check the label"
        with self._claim_settings():
            with self.assertRaises(HttpError) as ctx:
                claim_preview(self._req(self.owner, 'post'),
                              ClaimIn(mac='aa:bb:cc:dd:ee:01'))
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.code, 'claim_already_yours')

    def test_claim_by_hardware_mac_off_the_label(self):
        # The address on the sticker need not be the one the bridge took as
        # device_id — any of the box's own MACs proves possession
        with self._claim_settings():
            out = claim_device(self._req(self.friend, 'post'),
                               ClaimIn(mac='AA:BB:CC:DD:EE:03'))
        self.assertEqual(out.device_id, self.pooled.id)
        self.pooled.refresh_from_db()
        self.assertEqual(self.pooled.owner_id, self.friend.id)

    def test_unknown_mac_is_not_found(self):
        with self._claim_settings():
            with self.assertRaises(HttpError) as ctx:
                claim_preview(self._req(self.friend, 'post'),
                              ClaimIn(mac='aa:bb:cc:dd:ee:99'))
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.code, 'claim_not_found')

    def test_invalid_mac_rejected(self):
        with self._claim_settings():
            with self.assertRaises(HttpError) as ctx:
                claim_preview(self._req(self.friend, 'post'), ClaimIn(mac='zz:zz'))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_mac_separators_and_case_are_irrelevant(self):
        # People copy the label as they see it — run together, upper case,
        # dashes, dotted triplets, with stray spaces
        for typed in ('AABBCCDDEE02', 'aabbccddee02', 'AA-BB-CC-DD-EE-02',
                      'aabb.ccdd.ee02', '  aa:bb:cc:dd:ee:02  '):
            with self._claim_settings():
                out = claim_preview(self._req(self.friend, 'post'),
                                    ClaimIn(mac=typed))
            self.assertEqual(out.name, 'Parahub-EE02', typed)

    def test_unconfigured_pool_disables_claim(self):
        with override_settings(MESH_DEFAULT_OWNER_PROFILE_ID=''):
            with self.assertRaises(HttpError) as ctx:
                claim_preview(self._req(self.friend, 'post'),
                              ClaimIn(mac='aa:bb:cc:dd:ee:02'))
        self.assertEqual(ctx.exception.status_code, 503)


@override_settings(CACHES=LOCMEM_CACHE, MESH_HEARTBEAT_KEY='hb-key')
class ClaimAfterHeartbeatTests(SharingTestBase):
    """The firmware's hw_macs survive the heartbeat and reach the claim lookup.

    Registration keys on br-private's address, which on some boards is one the
    bridge invented (locally-administered, on no label). Without hw_macs such a
    router can never be claimed, because nobody can read its device_id anywhere.
    """

    def setUp(self):
        super().setUp()
        self.pool = _profile(self.instance, 'parahub-fleet-hb')
        self.support = _profile(self.instance, 'support-hb')

    def _heartbeat(self, **kwargs):
        payload = MeshHeartbeatIn(
            mac='02:cf:12:9d:5f:6d', hostname='Parahub-5F6D',
            firmware_role='bumblebee', **kwargs)
        request = self.rf.post('/api/v1/iot/mesh/heartbeat',
                               HTTP_AUTHORIZATION='Bearer hb-key')
        with override_settings(MESH_DEFAULT_OWNER_PROFILE_ID=self.pool.id):
            return mesh_heartbeat(request, payload)

    def test_claimable_by_label_mac_not_device_id(self):
        self._heartbeat(hw_macs=['94:83:C4:67:02:98', '94:83:c4:67:02:99'])
        device = IoTDevice.objects.get(device_id='02:cf:12:9d:5f:6d')
        self.assertEqual(device.connection_info['hw_macs'],
                         ['94:83:c4:67:02:98', '94:83:c4:67:02:99'])

        with override_settings(MESH_DEFAULT_OWNER_PROFILE_ID=self.pool.id,
                               MESH_SUPPORT_PROFILE_ID=self.support.id):
            out = claim_device(self._req(self.friend, 'post'),
                               ClaimIn(mac='9483c4670298'))
        self.assertEqual(out.device_id, device.id)
        device.refresh_from_db()
        self.assertEqual(device.owner_id, self.friend.id)

    def test_old_firmware_without_hw_macs_still_claims_by_device_id(self):
        self._heartbeat()
        device = IoTDevice.objects.get(device_id='02:cf:12:9d:5f:6d')
        self.assertNotIn('hw_macs', device.connection_info)
        with override_settings(MESH_DEFAULT_OWNER_PROFILE_ID=self.pool.id,
                               MESH_SUPPORT_PROFILE_ID=self.support.id):
            out = claim_device(self._req(self.friend, 'post'),
                               ClaimIn(mac='02:cf:12:9d:5f:6d'))
        self.assertEqual(out.device_id, device.id)


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


class _FakeTraccarCursor:
    """Canned psycopg2 cursor over an in-memory Traccar, keyed on SQL shape."""

    def __init__(self, db):
        self.db = db
        self._one = None
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        # INSERTs first: the permission INSERT carries a tc_users subquery
        text = ' '.join(sql.split())
        if text.startswith('SELECT id, email, name FROM tc_users'):
            self._one = self.db['users'].get(params[0])
        elif text.startswith('SELECT id FROM tc_devices WHERE uniqueid'):
            self._one = self.db['by_unique'].get(params[0])
        elif 'JOIN tc_user_device' in text:
            self._rows = [d for d in self.db['devices'] if params[0] in d['users']]
        elif text.startswith('INSERT INTO tc_devices'):
            new_id = max([d['id'] for d in self.db['devices']] + [0]) + 1
            self.db['devices'].append({
                'id': new_id, 'name': params[0], 'uniqueid': params[1],
                'status': 'offline', 'category': '', 'lastupdate': None,
                'users': set(),
            })
            self.db['by_unique'][params[1]] = {'id': new_id}
            self._one = {'id': new_id}
        elif text.startswith('INSERT INTO tc_user_device'):
            self.db['permissions'].append(params)
            user = self.db['users'].get(params[1])
            for device in self.db['devices']:
                if user and device['id'] == params[0]:
                    device['users'].add(user['id'])
        else:
            raise AssertionError(f'unexpected Traccar SQL: {text}')

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._rows

    def close(self):
        pass


class _FakeTraccarConn:
    def __init__(self, db):
        self.db = db

    def cursor(self, **kwargs):
        return _FakeTraccarCursor(self.db)

    def commit(self):
        pass

    def close(self):
        pass


class TraccarSyncTests(SharingTestBase):
    """A tracker permitted to several Traccar users stays one device here.

    The device list auto-syncs on every request, so an owner-scoped dedup let
    each permitted user's first page load mint a private copy of the same
    tracker — with its own ULID, invisible to the real owner.
    """

    def setUp(self):
        super().setUp()
        self.tracker = IoTDevice.objects.create(
            owner=self.owner, name='Pixel', device_type='TRACKER',
            device_id='10048355', traccar_device_id=12)
        self.db = {
            'users': {
                'deviceowner@test.parahub.io': {'id': 4, 'email': 'deviceowner@test.parahub.io', 'name': 'Owner'},
                'friend@test.parahub.io': {'id': 1, 'email': 'friend@test.parahub.io', 'name': 'Friend'},
                'stranger@test.parahub.io': {'id': 5, 'email': 'stranger@test.parahub.io', 'name': 'Stranger'},
            },
            'devices': [{
                'id': 12, 'name': 'Pixel 10', 'uniqueid': '10048355',
                'status': 'online', 'category': '', 'lastupdate': timezone.now(),
                'users': {1, 4},
            }],
            'by_unique': {},
            'permissions': [],
        }

    def _traccar(self):
        return patch.object(TraccarService, '_get_db',
                            return_value=_FakeTraccarConn(self.db))

    def _sync(self, profile):
        with self._traccar():
            return TraccarService.sync_devices_from_traccar(profile)

    def test_shared_device_becomes_a_grant_not_a_second_row(self):
        self.assertEqual(self._sync(self.friend), 0)
        self.assertEqual(IoTDevice.objects.filter(traccar_device_id=12).count(), 1)
        grant = ObjectAccess.objects.get(object_id=self.tracker.id, profile=self.friend)
        self.assertEqual(grant.role, ROLE_VIEWER)
        self.assertIsNone(grant.granted_by)

        with self._traccar():
            rows = list_devices(self._req(self.friend))
        shared = {r.name: r for r in rows}['Pixel']
        self.assertEqual(shared.id, self.tracker.id)
        self.assertEqual(shared.access_role, 'VIEWER')
        self.assertEqual(shared.owner_hna, self.owner.hna)

    def test_repeated_sync_is_idempotent(self):
        for _ in range(3):
            self._sync(self.friend)
        self.assertEqual(IoTDevice.objects.filter(traccar_device_id=12).count(), 1)
        self.assertEqual(ObjectAccess.objects.filter(object_id=self.tracker.id).count(), 1)

    def test_owner_sync_refreshes_own_device(self):
        self.assertEqual(self._sync(self.owner), 0)
        self.assertEqual(IoTDevice.objects.filter(traccar_device_id=12).count(), 1)
        self.tracker.refresh_from_db()
        self.assertEqual(self.tracker.name, 'Pixel 10')
        # The owner holds it by FK — no grant row for themselves
        self.assertFalse(ObjectAccess.objects.filter(object_id=self.tracker.id).exists())

    def test_unknown_device_is_imported_for_the_syncing_profile(self):
        self.db['devices'].append({
            'id': 13, 'name': 'Scooter', 'uniqueid': '7018520410',
            'status': 'offline', 'category': '', 'lastupdate': timezone.now(),
            'users': {1},
        })
        self.assertEqual(self._sync(self.friend), 1)
        imported = IoTDevice.objects.get(traccar_device_id=13)
        self.assertEqual(imported.owner_id, self.friend.id)
        self.assertEqual(imported.device_type, 'TRACKER')

    def test_registration_does_not_adopt_someone_elses_traccar_device(self):
        # The uniqueId is the IMEI printed on the box: registering it must not
        # hand the stranger the live positions of a tracker already owned here
        self.db['by_unique']['10048355'] = {'id': 12}
        with patch('iot.signals.spawn', lambda fn: fn()), \
             patch('iot.signals.psycopg2.connect',
                   return_value=_FakeTraccarConn(self.db)):
            with self.captureOnCommitCallbacks(execute=True):
                claimed = IoTDevice.objects.create(
                    owner=self.stranger, name='Not mine', device_type='TRACKER',
                    device_id='10048355')
        claimed.refresh_from_db()
        self.assertIsNone(claimed.traccar_device_id)

    def test_new_device_is_permitted_to_its_owner_only(self):
        with patch('iot.signals.spawn', lambda fn: fn()), \
             patch('iot.signals.psycopg2.connect',
                   return_value=_FakeTraccarConn(self.db)):
            with self.captureOnCommitCallbacks(execute=True):
                IoTDevice.objects.create(
                    owner=self.friend, name='New tracker',
                    device_type='TRACKER', device_id='7018520611')
        self.assertEqual([p[1] for p in self.db['permissions']],
                         ['friend@test.parahub.io'])


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
