from unittest import mock

from django.core.management import call_command
from django.test import RequestFactory, TestCase, override_settings
from django.core.cache import cache
from django.utils import timezone

from core.models import Instance
from identity.models import Account, Profile
from iot.models import IoTDevice
from iot.api.mesh import (
    MeshHeartbeatIn, _compute_islands, _elect_guest_gateway, mesh_heartbeat,
    ygg_probe_key,
)


def _profile(instance, username):
    account = Account.objects.create_user(
        username=username, email=f'{username}@test.parahub.io',
        password='x', instance=instance)
    return Profile.objects.create(
        account=account, instance=instance, local_name=username,
        display_name=username.title(), is_primary=True)


LOCMEM_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}


@override_settings(CACHES=LOCMEM_CACHE)
class GuestGatewayElectionTests(TestCase):
    """Per-island guest-VLAN gateway election over heartbeat-reported topology."""

    def setUp(self):
        cache.clear()
        self.instance = Instance.objects.create(
            domain='test.parahub.io', name='Test', public_key='k')
        self.owner = _profile(self.instance, 'meshowner')
        self.now = timezone.now()

    def _node(self, mac, mesh_macs=None, originators=None, vpn_mode='vps',
              version='25.12.5-ph37', role='bumblebee', force=False, topology=True):
        ci = {
            'firmware_role': role,
            'firmware_version': version,
            'vpn_mode': vpn_mode,
        }
        if topology:
            ci['mesh_macs'] = mesh_macs or []
            ci['mesh_originators'] = originators or []
        return IoTDevice.objects.create(
            device_id=mac, device_type='MESH_ROUTER', name=mac,
            owner=self.owner, last_seen=self.now, connection_info=ci,
            guest_gateway_force=force)

    # --- _compute_islands -----------------------------------------------------

    def test_one_directional_sighting_joins_island(self):
        a = self._node('aa:00:00:00:00:01', mesh_macs=['a2:00:00:00:00:01'],
                       originators=['b2:00:00:00:00:02'])
        b = self._node('bb:00:00:00:00:02', mesh_macs=['b2:00:00:00:00:02'],
                       originators=[])
        islands = _compute_islands([a, b])
        self.assertEqual(len(islands), 1)

    def test_solo_node_is_own_island(self):
        a = self._node('aa:00:00:00:00:01', mesh_macs=['a2:00:00:00:00:01'],
                       originators=['b2:00:00:00:00:02'])
        b = self._node('bb:00:00:00:00:02', mesh_macs=['b2:00:00:00:00:02'])
        solo = self._node('cc:00:00:00:00:03', mesh_macs=['c2:00:00:00:00:03'])
        islands = _compute_islands([a, b, solo])
        self.assertEqual(len(islands), 2)
        solo_island = next(i for i in islands if solo in i)
        self.assertEqual(len(solo_island), 1)

    def test_transitive_islands(self):
        a = self._node('aa:00:00:00:00:01', mesh_macs=['a2:00:00:00:00:01'],
                       originators=['b2:00:00:00:00:02'])
        b = self._node('bb:00:00:00:00:02', mesh_macs=['b2:00:00:00:00:02'],
                       originators=['c2:00:00:00:00:03'])
        c = self._node('cc:00:00:00:00:03', mesh_macs=['c2:00:00:00:00:03'])
        islands = _compute_islands([a, b, c])
        self.assertEqual(len(islands), 1)
        self.assertEqual(len(islands[0]), 3)

    # --- per-island election --------------------------------------------------

    def test_each_island_elects_own_gateway(self):
        a = self._node('aa:00:00:00:00:01', mesh_macs=['a2:00:00:00:00:01'],
                       originators=['b2:00:00:00:00:02'])
        self._node('bb:00:00:00:00:02', mesh_macs=['b2:00:00:00:00:02'],
                   originators=['a2:00:00:00:00:01'])
        solo = self._node('cc:00:00:00:00:03', mesh_macs=['c2:00:00:00:00:03'])
        # island {a,b}: deterministic first by MAC = a
        self.assertEqual(_elect_guest_gateway(a.device_id, self.now), a.device_id)
        # solo island elects itself
        self.assertEqual(_elect_guest_gateway(solo.device_id, self.now), solo.device_id)

    def test_solo_island_without_vpn_elects_local_only_terminator(self):
        # Blackout mode: an all-VPN-down island still elects a terminator so
        # guest DHCP/RA and the NAT66->ygg platform path stay alive.
        solo = self._node('cc:00:00:00:00:03', mesh_macs=['c2:00:00:00:00:03'],
                          vpn_mode='none')
        self.assertEqual(_elect_guest_gateway(solo.device_id, self.now),
                         solo.device_id)

    def test_vpn_candidate_preferred_over_local_only(self):
        # 'aa' sorts first but has no VPN; the VPN-backed 'bb' must win.
        a = self._node('aa:00:00:00:00:01', mesh_macs=['a2:00:00:00:00:01'],
                       originators=['b2:00:00:00:00:02'], vpn_mode='none')
        b = self._node('bb:00:00:00:00:02', mesh_macs=['b2:00:00:00:00:02'],
                       originators=['a2:00:00:00:00:01'])
        self.assertEqual(_elect_guest_gateway(a.device_id, self.now), b.device_id)

    def test_blackout_keeps_incumbent_seated(self):
        # Fleet-wide VPN loss must not churn the terminator (leases survive).
        a = self._node('aa:00:00:00:00:01', mesh_macs=['a2:00:00:00:00:01'],
                       originators=['b2:00:00:00:00:02'], vpn_mode='none')
        b = self._node('bb:00:00:00:00:02', mesh_macs=['b2:00:00:00:00:02'],
                       originators=['a2:00:00:00:00:01'], vpn_mode='none')
        key = f"mesh_guest_gateway:island:{a.device_id}"
        cache.set(key, b.device_id, 1800)
        self.assertEqual(_elect_guest_gateway(a.device_id, self.now), b.device_id)

    def test_vpn_recovery_displaces_local_only_incumbent(self):
        a = self._node('aa:00:00:00:00:01', mesh_macs=['a2:00:00:00:00:01'],
                       originators=['b2:00:00:00:00:02'], vpn_mode='none')
        b = self._node('bb:00:00:00:00:02', mesh_macs=['b2:00:00:00:00:02'],
                       originators=['a2:00:00:00:00:01'])
        key = f"mesh_guest_gateway:island:{a.device_id}"
        cache.set(key, a.device_id, 1800)
        self.assertEqual(_elect_guest_gateway(a.device_id, self.now), b.device_id)

    def test_local_tier_still_gated_on_min_build_and_force(self):
        # Pre-ph35 and force-flagged nodes never join the local tier: an island
        # of only such nodes gets no terminator even in blackout mode.
        self._node('aa:00:00:00:00:01', mesh_macs=['a2:00:00:00:00:01'],
                   originators=['b2:00:00:00:00:02'], vpn_mode='none',
                   version='25.12.5-ph34')
        b = self._node('bb:00:00:00:00:02', mesh_macs=['b2:00:00:00:00:02'],
                       originators=['a2:00:00:00:00:01'], vpn_mode='none',
                       force=True)
        self.assertIsNone(_elect_guest_gateway(b.device_id, self.now))

    def test_election_is_sticky_per_island(self):
        a = self._node('aa:00:00:00:00:01', mesh_macs=['a2:00:00:00:00:01'],
                       originators=['b2:00:00:00:00:02'])
        b = self._node('bb:00:00:00:00:02', mesh_macs=['b2:00:00:00:00:02'],
                       originators=['a2:00:00:00:00:01'])
        key = f"mesh_guest_gateway:island:{a.device_id}"
        cache.set(key, b.device_id, 1800)
        self.assertEqual(_elect_guest_gateway(a.device_id, self.now), b.device_id)

    def test_per_island_adopts_fleet_global_incumbent(self):
        a = self._node('aa:00:00:00:00:01', mesh_macs=['a2:00:00:00:00:01'],
                       originators=['b2:00:00:00:00:02'])
        b = self._node('bb:00:00:00:00:02', mesh_macs=['b2:00:00:00:00:02'],
                       originators=['a2:00:00:00:00:01'])
        cache.set('mesh_guest_gateway', b.device_id, 1800)
        self.assertEqual(_elect_guest_gateway(a.device_id, self.now), b.device_id)

    def test_forced_node_excluded_from_election(self):
        a = self._node('aa:00:00:00:00:01', mesh_macs=['a2:00:00:00:00:01'],
                       originators=['b2:00:00:00:00:02'], force=True)
        b = self._node('bb:00:00:00:00:02', mesh_macs=['b2:00:00:00:00:02'],
                       originators=['a2:00:00:00:00:01'])
        self.assertEqual(_elect_guest_gateway(b.device_id, self.now), b.device_id)

    def test_failover_when_incumbent_loses_vpn(self):
        a = self._node('aa:00:00:00:00:01', mesh_macs=['a2:00:00:00:00:01'],
                       originators=['b2:00:00:00:00:02'], vpn_mode='none')
        b = self._node('bb:00:00:00:00:02', mesh_macs=['b2:00:00:00:00:02'],
                       originators=['a2:00:00:00:00:01'])
        key = f"mesh_guest_gateway:island:{a.device_id}"
        cache.set(key, a.device_id, 1800)
        self.assertEqual(_elect_guest_gateway(b.device_id, self.now), b.device_id)

    # --- mixed-fleet fallback -------------------------------------------------

    def test_mixed_fleet_falls_back_to_global_election(self):
        # One pre-topology (ph36) bumblebee keeps the whole fleet on the global
        # election: partial data could split a physical island -> DHCP race.
        a = self._node('aa:00:00:00:00:01', mesh_macs=['a2:00:00:00:00:01'])
        old = self._node('bb:00:00:00:00:02', version='25.12.5-ph36', topology=False)
        # Global election picks the sorted-first eligible MAC for everyone.
        self.assertEqual(_elect_guest_gateway(a.device_id, self.now), a.device_id)
        self.assertEqual(_elect_guest_gateway(old.device_id, self.now), a.device_id)
        # No island keys were created in mixed mode.
        self.assertIsNone(cache.get(f"mesh_guest_gateway:island:{a.device_id}"))
        self.assertEqual(cache.get('mesh_guest_gateway'), a.device_id)


@override_settings(CACHES=LOCMEM_CACHE, MESH_HEARTBEAT_KEY='hb-key')
class YggInboundSelfHealTests(TestCase):
    """Backend ygg:22 probe streaks + the heartbeat ygg_inbound_dead flag."""

    MAC = '80:af:ca:ec:f9:5e'
    YGG = '201:db1c:bda9:8e59:7495:f13a:70aa:1d99'

    def setUp(self):
        cache.clear()
        self.rf = RequestFactory()
        self.instance = Instance.objects.create(
            domain='test.parahub.io', name='Test', public_key='k')
        self.owner = _profile(self.instance, 'owner')

    def _heartbeat(self):
        payload = MeshHeartbeatIn(
            mac=self.MAC, hostname='Parahub',
            yggdrasil_address=self.YGG, firmware_version='25.12.5-ph42',
            firmware_role='bumblebee', vpn_mode='mullvad')
        request = self.rf.post(
            '/api/v1/iot/mesh/heartbeat', HTTP_AUTHORIZATION='Bearer hb-key')
        with override_settings(MESH_DEFAULT_OWNER_PROFILE_ID=self.owner.id):
            return mesh_heartbeat(request, payload)

    def test_no_probe_state_means_no_flag(self):
        self.assertFalse(self._heartbeat().ygg_inbound_dead)

    def test_confirmed_dead_streak_sets_flag(self):
        cache.set(ygg_probe_key(self.MAC), {'ok': False, 'fails': 3, 'dead': True}, 900)
        self.assertTrue(self._heartbeat().ygg_inbound_dead)

    def test_single_failure_is_not_dead(self):
        cache.set(ygg_probe_key(self.MAC), {'ok': False, 'fails': 1, 'dead': False}, 900)
        self.assertFalse(self._heartbeat().ygg_inbound_dead)

    def test_probe_command_builds_streak_and_recovers(self):
        self._heartbeat()  # registers a fresh device with a ygg address
        with mock.patch(
            'iot.management.commands.mesh_probe_inbound._tcp_ok',
            return_value=False,
        ):
            for expected_fails in (1, 2, 3):
                call_command('mesh_probe_inbound')
                state = cache.get(ygg_probe_key(self.MAC))
                self.assertEqual(state['fails'], expected_fails)
        self.assertTrue(state['dead'])
        self.assertTrue(self._heartbeat().ygg_inbound_dead)

        with mock.patch(
            'iot.management.commands.mesh_probe_inbound._tcp_ok',
            return_value=True,
        ):
            call_command('mesh_probe_inbound')
        state = cache.get(ygg_probe_key(self.MAC))
        self.assertFalse(state['dead'])
        self.assertEqual(state['fails'], 0)
        self.assertFalse(self._heartbeat().ygg_inbound_dead)

    def test_stale_node_not_probed(self):
        self._heartbeat()
        IoTDevice.objects.filter(device_id=self.MAC).update(
            last_seen=timezone.now() - timezone.timedelta(minutes=30))
        with mock.patch(
            'iot.management.commands.mesh_probe_inbound._tcp_ok',
            return_value=False,
        ):
            call_command('mesh_probe_inbound')
        self.assertIsNone(cache.get(ygg_probe_key(self.MAC)))
