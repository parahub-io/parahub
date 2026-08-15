"""Mesh topology graph (ph50): heartbeat link storage + staff graph endpoint.

Invariants:
- mesh_links rows are validated on ingest (MACs checked, throughput clamped)
- a direct edge exists iff some reporter's originator-table row points at a
  nexthop interface OWNED BY THE SAME NODE as the originator; per-direction
  throughput is the max over that node pair's rows
- a row routing via a third node (nexthop owned by someone else) never
  creates an edge
- pairs where NEITHER endpoint reports links fall back to an inferred
  "sees in island" edge; if either endpoint reports links, no fallback
- a device referenced by a live reporter's links stays on the graph even
  when its own heartbeat is long dead
- endpoint is staff-only
"""

from datetime import timedelta

from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone
from ninja.errors import HttpError

from core.models import Instance
from identity.models import Account, Profile
from iot.api.mesh import MeshHeartbeatIn, MeshLinkIn, mesh_graph, mesh_heartbeat
from iot.models import IoTDevice

LOCMEM_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}

MAC_A = 'aa:00:00:00:00:0a'
MAC_B = 'aa:00:00:00:00:0b'
MAC_BEE = 'aa:00:00:00:00:0c'
MAC_DEAD = 'aa:00:00:00:00:0e'
A_IF1, A_IF2 = '02:00:00:00:0a:01', '02:00:00:00:0a:02'
B_IF1, B_IF2 = '02:00:00:00:0b:01', '02:00:00:00:0b:02'
BEE_IF = '02:00:00:00:0c:01'
DEAD_IF = '02:00:00:00:0e:01'


def _profile(instance, username, is_staff=False):
    account = Account.objects.create_user(
        username=username, email=f'{username}@test.parahub.io',
        password='x', instance=instance, is_staff=is_staff)
    return Profile.objects.create(
        account=account, instance=instance, local_name=username,
        display_name=username.title(), is_primary=True)


@override_settings(CACHES=LOCMEM_CACHE, MESH_HEARTBEAT_KEY='hb-key')
class MeshGraphTests(TestCase):
    def setUp(self):
        cache.clear()
        self.rf = RequestFactory()
        self.instance = Instance.objects.create(
            domain='test.parahub.io', name='Test', public_key='k')
        self.owner = _profile(self.instance, 'owner')
        self.staff = _profile(self.instance, 'staff', is_staff=True)

    def _heartbeat(self, mac, role='bumblebee', mesh_macs=None,
                   originators=None, links=None):
        payload = MeshHeartbeatIn(
            mac=mac, hostname=f'Parahub-{mac[-5:-3].upper()}{mac[-2:].upper()}',
            firmware_version='25.12.5-ph50', firmware_role=role,
            vpn_mode='vps' if role == 'bumblebee' else 'none',
            mesh_macs=mesh_macs, mesh_originators=originators,
            mesh_links=links,
        )
        request = self.rf.post(
            '/api/v1/iot/mesh/heartbeat', HTTP_AUTHORIZATION='Bearer hb-key')
        with override_settings(MESH_DEFAULT_OWNER_PROFILE_ID=self.owner.id):
            return mesh_heartbeat(request, payload)

    def _graph(self, profile=None):
        request = self.rf.get('/api/v1/iot/mesh/graph')
        request.auth_profile = profile or self.staff
        return mesh_graph(request)

    def _fleet(self):
        """A=B direct both ways, A=BEE direct one way, B routes to BEE only
        via A (multi-hop row that must NOT become an edge)."""
        self._heartbeat(
            MAC_A, mesh_macs=[A_IF1, A_IF2],
            originators=[B_IF1, BEE_IF],
            links=[
                MeshLinkIn(o=B_IF1, n=B_IF2, t=850.8),   # direct via B's 2nd radio
                MeshLinkIn(o=B_IF1, n=B_IF1, t=250.6),   # direct, weaker band
                MeshLinkIn(o=BEE_IF, n=BEE_IF, t=0.8),   # direct to the bee
            ])
        self._heartbeat(
            MAC_B, mesh_macs=[B_IF1, B_IF2],
            originators=[A_IF1, BEE_IF],
            links=[
                MeshLinkIn(o=A_IF1, n=A_IF2, t=400.0),   # direct back to A
                MeshLinkIn(o=BEE_IF, n=A_IF1, t=120.0),  # BEE via A — multi-hop
            ])
        self._heartbeat(
            MAC_BEE, role='bee', mesh_macs=[BEE_IF], originators=[A_IF1])

    def _edge(self, out, mac_x, mac_y):
        ids = {n.mac: n.id for n in out.nodes}
        pair = {ids[mac_x], ids[mac_y]}
        for e in out.edges:
            if {e.source, e.target} == pair:
                return e
        return None

    def test_staff_only(self):
        with self.assertRaises(HttpError) as ctx:
            self._graph(profile=self.owner)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_heartbeat_validates_and_stores_links(self):
        self._heartbeat(
            MAC_A, mesh_macs=[A_IF1],
            originators=[],
            links=[
                MeshLinkIn(o=B_IF1, n=B_IF1, t=99999999.0),  # clamped
                MeshLinkIn(o='not-a-mac', n=B_IF1, t=1.0),   # dropped
            ])
        stored = IoTDevice.objects.get(device_id=MAC_A).connection_info['mesh_links']
        self.assertEqual(stored, [{'o': B_IF1, 'n': B_IF1, 't': 100000.0}])

    def test_direct_edges_max_tp_per_direction(self):
        self._fleet()
        out = self._graph()
        ab = self._edge(out, MAC_A, MAC_B)
        self.assertIsNotNone(ab)
        self.assertFalse(ab.inferred)
        self.assertEqual(sorted([ab.tp_ab, ab.tp_ba]), [400.0, 850.8])

    def test_one_sided_reporter_gives_one_sided_tp(self):
        self._fleet()
        out = self._graph()
        abee = self._edge(out, MAC_A, MAC_BEE)
        self.assertIsNotNone(abee)
        self.assertFalse(abee.inferred)
        self.assertEqual(sorted([abee.tp_ab, abee.tp_ba],
                                key=lambda v: (v is None, v)), [0.8, None])

    def test_multihop_row_creates_no_edge(self):
        self._fleet()
        out = self._graph()
        # B sees BEE only through A; B reports links, so no fallback either
        self.assertIsNone(self._edge(out, MAC_B, MAC_BEE))

    def test_inferred_edge_when_neither_reports_links(self):
        c, d = 'aa:00:00:00:00:1c', 'aa:00:00:00:00:1d'
        c_if, d_if = '02:00:00:00:1c:01', '02:00:00:00:1d:01'
        self._heartbeat(c, mesh_macs=[c_if], originators=[d_if])
        self._heartbeat(d, mesh_macs=[d_if], originators=[c_if])
        out = self._graph()
        edge = self._edge(out, c, d)
        self.assertIsNotNone(edge)
        self.assertTrue(edge.inferred)
        self.assertIsNone(edge.tp_ab)

    def test_dead_heartbeat_node_kept_when_routed_to(self):
        self._heartbeat(MAC_DEAD, mesh_macs=[DEAD_IF], originators=[])
        IoTDevice.objects.filter(device_id=MAC_DEAD).update(
            last_seen=timezone.now() - timedelta(days=30))
        self._heartbeat(
            MAC_A, mesh_macs=[A_IF1], originators=[DEAD_IF],
            links=[MeshLinkIn(o=DEAD_IF, n=DEAD_IF, t=42.0)])
        out = self._graph()
        macs = {n.mac for n in out.nodes}
        self.assertIn(MAC_DEAD, macs)
        dead = next(n for n in out.nodes if n.mac == MAC_DEAD)
        self.assertFalse(dead.fresh)
        edge = self._edge(out, MAC_A, MAC_DEAD)
        self.assertIsNotNone(edge)
        self.assertEqual(edge.tp_ab or edge.tp_ba, 42.0)

    def test_terminator_flag_follows_election(self):
        self._fleet()
        out = self._graph()
        terminators = {n.mac for n in out.nodes if n.is_terminator}
        # one elected guest-VLAN terminator on the single island
        self.assertEqual(len(terminators), 1)
        self.assertIn(next(iter(terminators)), {MAC_A, MAC_B})
        self.assertEqual(out.islands, 1)
        self.assertEqual(out.fresh_nodes, 3)
