"""Mesh pass: account-level speed entitlement + device binding.

Invariants:
- heartbeat translates bound MACs to paid IPs strictly through the node's own
  guest leases (no leases → no paid clients), and only for active passes
- grant extends a live pass from its future expiry, a lapsed one from now
- bind resolves request source port → conntrack ULA → neighbor MAC and
  refuses off-mesh, private-network and foreign-bound devices
- the ygg gate token is the only thing that makes X-Ygg-* headers trusted
"""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone
from ninja.errors import HttpError

from core.models import Instance
from identity.models import Account, Profile
from iot.api.mesh import (
    GuestLease, MeshHeartbeatIn, _parse_conntrack_client, _parse_neigh_mac,
    mesh_bind, mesh_heartbeat, mesh_network,
)
from iot.mesh_pass import grant_mesh_pass
from iot.models import IoTDevice, MeshDevice, MeshPass

LOCMEM_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}

NODE_YGG = '201:2123:d13:105a:5e5b:b319:2eed:b080'
CLIENT_ULA = 'fd00:bee5::1234'
CLIENT_MAC = 'aa:bb:cc:dd:ee:ff'
CLIENT_IP4 = '10.131.196.101'
GATE = 'test-gate-token'

CONNTRACK_FIXTURE = (
    "ipv6     10 tcp      6 431999 ESTABLISHED "
    "src=fd00:bee5:0000:0000:0000:0000:0000:1234 dst=0<YGG_ADDR_MAIN> "
    "sport=52344 dport=443 packets=10 bytes=1000 "
    "src=0<YGG_ADDR_MAIN> dst=0201:2123:0d13:105a:5e5b:b319:2eed:b080 "
    "sport=443 dport=61234 packets=8 bytes=900 [ASSURED] mark=0 zone=0 use=2\n"
    # The node's own HTTPS flow (heartbeat curl): original src is not a ULA
    "ipv6     10 tcp      6 100 ESTABLISHED "
    "src=0201:2123:0d13:105a:5e5b:b319:2eed:b080 dst=0<YGG_ADDR_MAIN> "
    "sport=40000 dport=443 packets=3 bytes=300 "
    "src=0<YGG_ADDR_MAIN> dst=0201:2123:0d13:105a:5e5b:b319:2eed:b080 "
    "sport=443 dport=40000 packets=2 bytes=200 [ASSURED] mark=0 zone=0 use=2\n"
)

NEIGH_FIXTURE = (
    "fd00:bee5::1234 dev br-guest lladdr aa:bb:cc:dd:ee:ff STALE\n"
    "300:2123:d13:105a:4cb3:b78c:5ddb:c4a8 dev br-private lladdr 2e:23:9f:72:b4:bd STALE\n"
    "fe80::5097:f5ff:fe49:fcf4 dev br-private FAILED\n"
)


def _profile(instance, username):
    account = Account.objects.create_user(
        username=username, email=f'{username}@test.parahub.io',
        password='x', instance=instance)
    return Profile.objects.create(
        account=account, instance=instance, local_name=username,
        display_name=username.title(), is_primary=True)


class ConntrackParserTests(TestCase):
    def test_resolves_reply_port_to_client_ula(self):
        self.assertEqual(
            _parse_conntrack_client(CONNTRACK_FIXTURE, 61234), 'fd00:bee5::1234')

    def test_ignores_non_ula_flows(self):
        # Port 40000 belongs to the node's own flow — never a guest
        self.assertIsNone(_parse_conntrack_client(CONNTRACK_FIXTURE, 40000))

    def test_unknown_port_returns_none(self):
        self.assertIsNone(_parse_conntrack_client(CONNTRACK_FIXTURE, 12345))

    def test_neigh_resolves_expanded_and_compressed(self):
        # conntrack gives expanded form; neigh table stores compressed
        expanded = 'fd00:bee5:0000:0000:0000:0000:0000:1234'
        self.assertEqual(_parse_neigh_mac(NEIGH_FIXTURE, expanded), CLIENT_MAC)

    def test_neigh_skips_failed_entries(self):
        self.assertIsNone(_parse_neigh_mac(NEIGH_FIXTURE, 'fe80::5097:f5ff:fe49:fcf4'))


class GrantTests(TestCase):
    def setUp(self):
        self.instance = Instance.objects.create(
            domain='test.parahub.io', name='Test', public_key='k')
        self.alice = _profile(self.instance, 'alice')

    def test_grant_starts_and_extends(self):
        mp = grant_mesh_pass(self.alice, 30, source='GRANT')
        first_expiry = mp.expires_at
        self.assertAlmostEqual(
            (first_expiry - timezone.now()).total_seconds(),
            timedelta(days=30).total_seconds(), delta=5)
        # A live pass extends from its future expiry, not from now
        mp = grant_mesh_pass(self.alice, 30, source='ACHIEVEMENT')
        self.assertAlmostEqual(
            (mp.expires_at - first_expiry).total_seconds(),
            timedelta(days=30).total_seconds(), delta=5)
        self.assertEqual(mp.credits.count(), 2)

    def test_lapsed_pass_restarts_from_now(self):
        mp = grant_mesh_pass(self.alice, 30)
        MeshPass.objects.filter(id=mp.id).update(
            expires_at=timezone.now() - timedelta(days=100))
        mp = grant_mesh_pass(self.alice, 30)
        self.assertAlmostEqual(
            (mp.expires_at - timezone.now()).total_seconds(),
            timedelta(days=30).total_seconds(), delta=5)


@override_settings(CACHES=LOCMEM_CACHE, MESH_HEARTBEAT_KEY='hb-key')
class HeartbeatPaidClientsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.rf = RequestFactory()
        self.instance = Instance.objects.create(
            domain='test.parahub.io', name='Test', public_key='k')
        self.owner = _profile(self.instance, 'owner')
        self.alice = _profile(self.instance, 'alice')

    def _heartbeat(self, leases):
        payload = MeshHeartbeatIn(
            mac='94:83:c4:76:ab:47', hostname='Parahub-AB47',
            yggdrasil_address=NODE_YGG, firmware_version='25.12.5-ph40',
            firmware_role='bumblebee', vpn_mode='vps',
            guest_leases=leases,
        )
        request = self.rf.post(
            '/api/v1/iot/mesh/heartbeat',
            HTTP_AUTHORIZATION='Bearer hb-key')
        with override_settings(MESH_DEFAULT_OWNER_PROFILE_ID=self.owner.id):
            return mesh_heartbeat(request, payload)

    def test_only_active_pass_macs_become_paid_ips(self):
        mp = grant_mesh_pass(self.alice, 30)
        MeshDevice.objects.create(mesh_pass=mp, mac=CLIENT_MAC)
        lapsed = _profile(self.instance, 'bob')
        mp2 = grant_mesh_pass(lapsed, 30)
        MeshPass.objects.filter(id=mp2.id).update(
            expires_at=timezone.now() - timedelta(days=1))
        MeshDevice.objects.create(mesh_pass=mp2, mac='11:22:33:44:55:66')

        out = self._heartbeat([
            GuestLease(mac=CLIENT_MAC, ip=CLIENT_IP4, host='Pixel-7'),
            GuestLease(mac='11:22:33:44:55:66', ip='10.131.196.102', host='Tab'),
            GuestLease(mac='77:88:99:aa:bb:cc', ip='10.131.196.103', host='Rando'),
        ])
        self.assertEqual(out.paid_clients, [CLIENT_IP4])
        d = MeshDevice.objects.get(mac=CLIENT_MAC)
        self.assertEqual(d.last_ipv4, CLIENT_IP4)
        self.assertIsNotNone(d.last_seen_at)
        self.assertEqual(d.last_gateway.device_id, '94:83:c4:76:ab:47')

    def test_no_leases_means_no_paid_clients(self):
        mp = grant_mesh_pass(self.alice, 30)
        MeshDevice.objects.create(mesh_pass=mp, mac=CLIENT_MAC)
        out = self._heartbeat(None)
        self.assertEqual(out.paid_clients, [])


@override_settings(
    CACHES=LOCMEM_CACHE, MESH_YGG_GATE_TOKEN=GATE, MESH_SSH_TIMEOUT=5)
class BindTests(TestCase):
    def setUp(self):
        cache.clear()
        self.rf = RequestFactory()
        self.instance = Instance.objects.create(
            domain='test.parahub.io', name='Test', public_key='k')
        self.alice = _profile(self.instance, 'alice')
        self.node = IoTDevice.objects.create(
            device_id='94:83:c4:76:ab:47', device_type='MESH_ROUTER',
            name='Parahub-AB47', owner=self.alice, last_seen=timezone.now(),
            connection_info={
                'yggdrasil_address': NODE_YGG,
                'hostname': 'Parahub-AB47',
                'firmware_role': 'bumblebee',
                'firmware_version': '25.12.5-ph40',
                'vpn_mode': 'vps',
                'mesh_macs': ['96:83:c4:76:ab:48'],
                'mesh_originators': [],
                'guest_leases': [
                    {'mac': CLIENT_MAC, 'ip': CLIENT_IP4, 'host': 'Pixel-7'},
                ],
            })

    def _bind_request(self, ip=NODE_YGG, port='61234', gate=GATE):
        request = self.rf.post(
            '/api/v1/iot/mesh/bind',
            HTTP_X_YGG_GATE=gate,
            HTTP_X_YGG_CLIENT_IP=ip,
            HTTP_X_YGG_CLIENT_PORT=port)
        request.auth_profile = self.alice
        return request

    def _ssh_ok(self, *args, **kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout=CONNTRACK_FIXTURE + '==NEIGH==\n' + NEIGH_FIXTURE,
            stderr='')

    def test_bind_happy_path(self):
        grant_mesh_pass(self.alice, 30)
        with patch('iot.api.mesh._mesh_ssh', side_effect=self._ssh_ok):
            out = mesh_bind(self._bind_request())
        self.assertTrue(out.activated)
        d = MeshDevice.objects.get(mac=CLIENT_MAC)
        self.assertEqual(d.last_ipv4, CLIENT_IP4)
        self.assertEqual(d.label, 'Pixel-7')
        self.assertEqual(d.mesh_pass.profile_id, self.alice.id)

    def test_bind_requires_gate_token(self):
        grant_mesh_pass(self.alice, 30)
        with self.assertRaises(HttpError) as ctx:
            mesh_bind(self._bind_request(gate='wrong'))
        self.assertEqual(ctx.exception.message, 'not_on_mesh')

    def test_bind_requires_active_pass(self):
        with self.assertRaises(HttpError) as ctx:
            mesh_bind(self._bind_request())
        self.assertEqual(ctx.exception.message, 'no_active_pass')

    def test_bind_private_network_rejected(self):
        grant_mesh_pass(self.alice, 30)
        with self.assertRaises(HttpError) as ctx:
            mesh_bind(self._bind_request(ip='300:2123:d13:105a:4cb3:b78c:5ddb:c4a8'))
        self.assertEqual(ctx.exception.message, 'on_private_network')

    def test_bind_foreign_device_rejected(self):
        grant_mesh_pass(self.alice, 30)
        other = _profile(self.instance, 'mallory')
        other_pass = grant_mesh_pass(other, 30)
        MeshDevice.objects.create(mesh_pass=other_pass, mac=CLIENT_MAC)
        with patch('iot.api.mesh._mesh_ssh', side_effect=self._ssh_ok):
            with self.assertRaises(HttpError) as ctx:
                mesh_bind(self._bind_request())
        self.assertEqual(ctx.exception.message, 'device_bound_elsewhere')

    def test_bind_device_limit(self):
        mp = grant_mesh_pass(self.alice, 30)
        for i in range(mp.max_devices):
            MeshDevice.objects.create(mesh_pass=mp, mac=f'00:00:00:00:00:{i:02x}')
        with patch('iot.api.mesh._mesh_ssh', side_effect=self._ssh_ok):
            with self.assertRaises(HttpError) as ctx:
                mesh_bind(self._bind_request())
        self.assertEqual(ctx.exception.message, 'device_limit_reached')

    def test_network_classification(self):
        req = self.rf.get('/api/v1/iot/mesh/network',
                          HTTP_X_YGG_GATE=GATE,
                          HTTP_X_YGG_CLIENT_IP=NODE_YGG,
                          HTTP_X_YGG_CLIENT_PORT='5555')
        out = mesh_network(req)
        self.assertTrue(out.on_mesh)
        self.assertEqual(out.network, 'guest')
        self.assertEqual(out.node_hostname, 'Parahub-AB47')

        req = self.rf.get('/api/v1/iot/mesh/network',
                          HTTP_X_YGG_GATE=GATE,
                          HTTP_X_YGG_CLIENT_IP='300:2123:d13:105a::1',
                          HTTP_X_YGG_CLIENT_PORT='5555')
        out = mesh_network(req)
        self.assertTrue(out.on_mesh)
        self.assertEqual(out.network, 'private')

        req = self.rf.get('/api/v1/iot/mesh/network')
        out = mesh_network(req)
        self.assertFalse(out.on_mesh)
