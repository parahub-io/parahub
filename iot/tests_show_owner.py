"""Owner attribution on public map feeds (show_owner opt-in).

Invariants:
- attribution is off by default: publishing a station/router position is not
  consent to naming the owner at that point
- when opted in, the anonymous feeds carry (owner_name, owner_cri); the name
  follows the anonymous gate of Profile.name_visible — display_name only when
  name_public, the @handle otherwise; the CRI is always the local_name
- mesh attribution is static: an offline router keeps it
- the device toggle is ROLE_OWNER-only (a MANAGER may not disclose the
  owner's identity)
"""

import json
import secrets

from django.contrib.gis.geos import Point
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone
from ninja.errors import HttpError

from core.access import ROLE_MANAGER
from core.models import Instance, ObjectAccess
from identity.models import Account, Profile
from iot.api.devices import DeviceShowOwnerIn, set_device_show_owner
from iot.api.env import EnvStationPatch, env_stations_map, patch_env_station
from iot.api.mesh import get_mesh_router_public_positions
from iot.models import EnvStation, IoTDevice

LOCMEM_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}


def _profile(instance, username, **kwargs):
    account = Account.objects.create_user(
        username=username, email=f'{username}@test.parahub.io',
        password='x', instance=instance)
    return Profile.objects.create(
        account=account, instance=instance, local_name=username,
        display_name=username.title(), is_primary=True, **kwargs)


@override_settings(CACHES=LOCMEM_CACHE)
class ShowOwnerTestBase(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.instance = Instance.objects.create(
            domain='test.parahub.io', name='Test', public_key='k',
            trust_level='local')
        self.owner = _profile(self.instance, 'stationowner')

    def _req(self, profile=None, method='get', body=None):
        factory = getattr(self.rf, method)
        request = factory('/', data=json.dumps(body) if body else None,
                          content_type='application/json')
        request.auth_profile = profile
        return request


class EnvStationAttributionTests(ShowOwnerTestBase):
    def setUp(self):
        super().setUp()
        self.station = EnvStation.objects.create(
            owner=self.owner, name='Backyard', source=EnvStation.Source.GENERIC,
            ingest_token=secrets.token_hex(10),
            location=Point(-8.83, 41.83), is_public=True,
            last_reading_at=timezone.now(), latest={'temperature': 21.0})

    def _feed_row(self):
        rows = env_stations_map(self._req())
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_no_attribution_by_default(self):
        row = self._feed_row()
        self.assertEqual(row.owner_name, '')
        self.assertEqual(row.owner_cri, '')

    def test_opt_in_shows_handle_when_name_gated(self):
        self.station.show_owner = True
        self.station.save(update_fields=['show_owner'])
        row = self._feed_row()
        self.assertEqual(row.owner_name, 'stationowner')
        self.assertEqual(row.owner_cri, 'stationowner')

    def test_opt_in_shows_display_name_when_name_public(self):
        self.owner.name_public = True
        self.owner.save(update_fields=['name_public'])
        self.station.show_owner = True
        self.station.save(update_fields=['show_owner'])
        row = self._feed_row()
        self.assertEqual(row.owner_name, 'Stationowner')
        self.assertEqual(row.owner_cri, 'stationowner')

    def test_patch_toggles_show_owner(self):
        out = patch_env_station(
            self._req(self.owner, 'patch'), self.station.id,
            EnvStationPatch(show_owner=True))
        self.assertTrue(out.show_owner)
        self.station.refresh_from_db()
        self.assertTrue(self.station.show_owner)


class MeshRouterAttributionTests(ShowOwnerTestBase):
    def setUp(self):
        super().setUp()
        self.device = IoTDevice.objects.create(
            device_id='aa:bb:cc:dd:ee:02', device_type='MESH_ROUTER',
            name='Parahub-EE02', owner=self.owner,
            latitude=41.83, longitude=-8.83, last_seen=timezone.now())

    def _feed_row(self):
        rows = get_mesh_router_public_positions(self._req())
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_no_attribution_by_default(self):
        row = self._feed_row()
        self.assertIsNone(row.owner_name)
        self.assertIsNone(row.owner_cri)

    def test_opt_in_attributes_even_offline(self):
        self.device.show_owner = True
        self.device.last_seen = None  # offline
        self.device.save(update_fields=['show_owner', 'last_seen'])
        row = self._feed_row()
        self.assertEqual(row.status, 'offline')
        self.assertEqual(row.owner_name, 'stationowner')
        self.assertEqual(row.owner_cri, 'stationowner')

    def test_toggle_is_owner_only(self):
        manager = _profile(self.instance, 'manager')
        ObjectAccess.objects.create(
            object_id=self.device.id, profile=manager, role=ROLE_MANAGER,
            granted_by=self.owner)
        with self.assertRaises(HttpError) as ctx:
            set_device_show_owner(
                self._req(manager, 'patch'), self.device.id,
                DeviceShowOwnerIn(show_owner=True))
        self.assertEqual(ctx.exception.status_code, 403)

        out = set_device_show_owner(
            self._req(self.owner, 'patch'), self.device.id,
            DeviceShowOwnerIn(show_owner=True))
        self.assertTrue(out.show_owner)
        self.device.refresh_from_db()
        self.assertTrue(self.device.show_owner)
