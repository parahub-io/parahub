"""Mesh sharing budgets (ph44): heartbeat rate delivery + settings API.

Invariants:
- every mesh heartbeat reply carries `rates`; defaults are 512 kbps / 10 Mbps
- guest_kbps is the node's OWN knob (applies where it terminates the guest VLAN)
- host_mbps is the min over the island's donor bumblebees, excluding the node
  itself (its own budget bounds others, not itself)
- a solo island (no donors) falls back to the default host budget
- mesh-settings is MANAGER-gated, bumblebee-only, and validates ranges
"""

import json

from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone
from ninja.errors import HttpError

from core.models import Instance
from identity.models import Account, Profile
from iot.api.devices import MeshSettingsIn, get_mesh_settings, set_mesh_settings
from iot.api.mesh import MeshHeartbeatIn, mesh_heartbeat
from iot.models import IoTDevice

LOCMEM_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}

MAC_A = 'aa:00:00:00:00:0a'
MAC_B = 'aa:00:00:00:00:0b'
MAC_BEE = 'aa:00:00:00:00:0c'
MESH_A = '02:00:00:00:00:0a'
MESH_B = '02:00:00:00:00:0b'
MESH_BEE = '02:00:00:00:00:0c'


def _profile(instance, username):
    account = Account.objects.create_user(
        username=username, email=f'{username}@test.parahub.io',
        password='x', instance=instance)
    return Profile.objects.create(
        account=account, instance=instance, local_name=username,
        display_name=username.title(), is_primary=True)


@override_settings(CACHES=LOCMEM_CACHE, MESH_HEARTBEAT_KEY='hb-key')
class HeartbeatRatesTests(TestCase):
    def setUp(self):
        cache.clear()
        self.rf = RequestFactory()
        self.instance = Instance.objects.create(
            domain='test.parahub.io', name='Test', public_key='k')
        self.owner = _profile(self.instance, 'owner')

    def _heartbeat(self, mac, role='bumblebee', mesh_macs=None, originators=None):
        payload = MeshHeartbeatIn(
            mac=mac, hostname=f'Parahub-{mac[-5:-3].upper()}{mac[-2:].upper()}',
            firmware_version='25.12.5-ph44', firmware_role=role,
            vpn_mode='vps' if role == 'bumblebee' else 'none',
            mesh_macs=mesh_macs, mesh_originators=originators,
        )
        request = self.rf.post(
            '/api/v1/iot/mesh/heartbeat', HTTP_AUTHORIZATION='Bearer hb-key')
        with override_settings(MESH_DEFAULT_OWNER_PROFILE_ID=self.owner.id):
            return mesh_heartbeat(request, payload)

    def _island(self):
        """A(bumblebee) — B(bumblebee) — BEE, one island via originator sets."""
        self._heartbeat(MAC_A, mesh_macs=[MESH_A], originators=[MESH_B, MESH_BEE])
        self._heartbeat(MAC_B, mesh_macs=[MESH_B], originators=[MESH_A])
        return self._heartbeat(
            MAC_BEE, role='bee', mesh_macs=[MESH_BEE], originators=[MESH_A])

    def test_defaults(self):
        out = self._heartbeat(MAC_A, mesh_macs=[MESH_A], originators=[])
        self.assertEqual(out.rates.guest_kbps, 512)
        self.assertEqual(out.rates.host_mbps, 10)

    def test_guest_rate_is_own_knob(self):
        self._heartbeat(MAC_A, mesh_macs=[MESH_A], originators=[])
        IoTDevice.objects.filter(device_id=MAC_A).update(mesh_guest_rate_kbps=1024)
        out = self._heartbeat(MAC_A, mesh_macs=[MESH_A], originators=[])
        self.assertEqual(out.rates.guest_kbps, 1024)

    def test_bee_gets_island_min_host_budget(self):
        self._island()
        IoTDevice.objects.filter(device_id=MAC_A).update(mesh_host_rate_mbps=50)
        IoTDevice.objects.filter(device_id=MAC_B).update(mesh_host_rate_mbps=2)
        out = self._heartbeat(
            MAC_BEE, role='bee', mesh_macs=[MESH_BEE], originators=[MESH_A])
        self.assertEqual(out.rates.host_mbps, 2)

    def test_bumblebee_host_budget_excludes_itself(self):
        self._island()
        IoTDevice.objects.filter(device_id=MAC_A).update(mesh_host_rate_mbps=50)
        IoTDevice.objects.filter(device_id=MAC_B).update(mesh_host_rate_mbps=2)
        # B's own fallback budget comes from A (its only donor), not from B
        out = self._heartbeat(MAC_B, mesh_macs=[MESH_B], originators=[MESH_A])
        self.assertEqual(out.rates.host_mbps, 50)

    def test_solo_island_falls_back_to_default(self):
        self._island()
        IoTDevice.objects.filter(device_id=MAC_A).update(mesh_host_rate_mbps=2)
        solo = 'aa:00:00:00:00:0d'
        out = self._heartbeat(
            solo, role='bee', mesh_macs=['02:00:00:00:00:0d'], originators=[])
        self.assertEqual(out.rates.host_mbps, 10)


class MeshSettingsApiTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.instance = Instance.objects.create(
            domain='test.parahub.io', name='Test', public_key='k')
        self.owner = _profile(self.instance, 'owner')
        self.stranger = _profile(self.instance, 'stranger')
        self.device = IoTDevice.objects.create(
            device_id=MAC_A, device_type='MESH_ROUTER', name='Parahub-000A',
            owner=self.owner, last_seen=timezone.now(),
            connection_info={'firmware_role': 'bumblebee'})

    def _req(self, profile, method='get', body=None):
        factory = getattr(self.rf, method)
        request = factory('/', data=json.dumps(body) if body else None,
                          content_type='application/json')
        request.auth_profile = profile
        return request

    def test_get_returns_defaults(self):
        out = get_mesh_settings(self._req(self.owner), self.device.id)
        self.assertEqual(out.guest_rate_kbps, 512)
        self.assertEqual(out.host_rate_mbps, 10)
        self.assertIsNone(out.uplink_type)

    def test_put_updates_and_clears(self):
        out = set_mesh_settings(
            self._req(self.owner, 'put'), self.device.id,
            MeshSettingsIn(guest_rate_kbps=1024, host_rate_mbps=20,
                           uplink_type='FIBER', uplink_down_mbps=1000,
                           uplink_up_mbps=200))
        self.assertEqual(out.guest_rate_kbps, 1024)
        self.assertEqual(out.host_rate_mbps, 20)
        self.assertEqual(out.uplink_type, 'FIBER')
        # partial update leaves others untouched; ''/0 clear the passport
        out = set_mesh_settings(
            self._req(self.owner, 'put'), self.device.id,
            MeshSettingsIn(uplink_type='', uplink_down_mbps=0))
        self.assertEqual(out.guest_rate_kbps, 1024)
        self.assertIsNone(out.uplink_type)
        self.assertIsNone(out.uplink_down_mbps)
        self.assertEqual(out.uplink_up_mbps, 200)

    def test_put_validates_ranges(self):
        for payload in (
            MeshSettingsIn(guest_rate_kbps=10),
            MeshSettingsIn(guest_rate_kbps=200000),
            MeshSettingsIn(host_rate_mbps=0),
            MeshSettingsIn(uplink_type='CARRIER_PIGEON'),
        ):
            with self.assertRaises(HttpError):
                set_mesh_settings(self._req(self.owner, 'put'), self.device.id, payload)

    def test_bee_rejected(self):
        self.device.connection_info = {'firmware_role': 'bee'}
        self.device.save(update_fields=['connection_info'])
        with self.assertRaises(HttpError):
            get_mesh_settings(self._req(self.owner), self.device.id)

    def test_stranger_gets_404(self):
        from django.http import Http404
        with self.assertRaises(Http404):
            get_mesh_settings(self._req(self.stranger), self.device.id)
