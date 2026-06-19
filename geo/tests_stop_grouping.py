"""Tests for virtual stop grouping (StopGroup). See PK/transit-system.md § Virtual stops."""
import io

from django.contrib.gis.geos import Point
from django.core.management import call_command
from django.test import TestCase

from geo.models import Agency, Stop, StopGroup, TransitDataSource
from geo.services.stop_grouping import (
    edge_passes,
    normalize_tokens,
    recompute_stop_groups,
)

# ~degrees of latitude per meter at any longitude
M = 1 / 111_320
BASE_LAT, BASE_LON = 38.737, -9.146  # Lisbon


class NormalizeTokensTests(TestCase):
    def test_abbreviation_canonicalization(self):
        self.assertEqual(normalize_tokens('пл. Ленина'), normalize_tokens('площадь Ленина'))
        self.assertEqual(normalize_tokens('Площадь ЛЕНИНА'), normalize_tokens('площадь ленина'))
        self.assertEqual(normalize_tokens('Pç. Luís de Camões'), normalize_tokens('Praca Luis Camoes'))

    def test_diacritics_and_stopwords(self):
        self.assertEqual(normalize_tokens('Cais do Sodré'), normalize_tokens('Cais Sodre'))
        self.assertEqual(normalize_tokens('Estação'), normalize_tokens('estacao'))

    def test_containment_edge(self):
        self.assertTrue(edge_passes(normalize_tokens('Ленина'), normalize_tokens('площадь Ленина')))
        self.assertTrue(edge_passes(normalize_tokens('Alameda'),
                                    normalize_tokens('Alameda D. Afonso Henriques')))

    def test_negative_pairs(self):
        self.assertFalse(edge_passes(normalize_tokens('Saldanha'),
                                     normalize_tokens("Av. Duque D'Ávila")))
        # broken-coordinate 0.0m pair from calibration — names must gate it out
        self.assertFalse(edge_passes(normalize_tokens('Pç. Águas Livres'),
                                     normalize_tokens('Damaia (Estação)')))

    def test_numeric_containment_guarded(self):
        # a bare number must never glue two stops
        self.assertFalse(edge_passes(normalize_tokens('25'), normalize_tokens('Rua Alegria 25')))

    def test_empty_names(self):
        self.assertFalse(edge_passes(normalize_tokens(''), normalize_tokens('X')))


class StopGroupingTests(TestCase):
    def setUp(self):
        self.ds1 = TransitDataSource.objects.create(name='Feed One', format='gtfs', slug='feed-one')
        self.ds2 = TransitDataSource.objects.create(name='Feed Two', format='gtfs', slug='feed-two')
        self.ag1 = Agency.objects.create(data_source=self.ds1, name='A1',
                                         timezone='Europe/Lisbon', lang='pt', source_id='a1')
        self.ag2 = Agency.objects.create(data_source=self.ds2, name='A2',
                                         timezone='Europe/Lisbon', lang='pt', source_id='a2')
        self._seq = 0

    def stop(self, agency, name, north_m=0.0, lt=0, parent=None, lon_east_m=0.0):
        self._seq += 1
        return Stop.objects.create(
            agency=agency, name=name, source_id=f's{self._seq}',
            location=Point(BASE_LON + lon_east_m * M, BASE_LAT + north_m * M, srid=4326),
            location_type=lt, parent_station=parent,
        )

    def test_same_feed_pole_pair(self):
        a = self.stop(self.ag1, 'Rua Alegria', 0)
        b = self.stop(self.ag1, 'Rua Alegria', 20)
        stats = recompute_stop_groups()
        self.assertEqual(stats['groups_created'], 1)
        a.refresh_from_db(); b.refresh_from_db()
        self.assertIsNotNone(a.group_id)
        self.assertEqual(a.group_id, b.group_id)
        g = a.group
        self.assertEqual(g.member_count, 2)
        # centroid = midpoint of the two poles
        self.assertAlmostEqual(g.location.y, BASE_LAT + 10 * M, places=9)
        self.assertAlmostEqual(g.location.x, BASE_LON, places=9)

    def test_cross_feed_abbreviation_merge(self):
        a = self.stop(self.ag1, 'Praça Luís de Camões', 0)
        b = self.stop(self.ag2, 'Pç. Luis Camoes', 15)
        recompute_stop_groups()
        a.refresh_from_db(); b.refresh_from_db()
        self.assertEqual(a.group_id, b.group_id)
        self.assertIsNotNone(a.group_id)

    def test_containment_majority_name_and_type_conflict(self):
        bare = self.stop(self.ag2, 'Ленина', 0)
        p1 = self.stop(self.ag1, 'площадь Ленина', 20)
        p2 = self.stop(self.ag1, 'пл. Ленина', 30)
        street = self.stop(self.ag1, 'улица Ленина', -40)  # 60/70m from squares: no direct edge
        recompute_stop_groups()
        for s in (bare, p1, p2, street):
            s.refresh_from_db()
        self.assertIsNotNone(bare.group_id)
        self.assertEqual(bare.group_id, p1.group_id)
        self.assertEqual(p1.group_id, p2.group_id)
        # type-conflict guard: «улица Ленина» must stay out despite the bare-name bridge
        self.assertIsNone(street.group_id)
        # majority canonical set {площадь, ленина}, displayed as its longest raw spelling
        self.assertEqual(p1.group.name, 'площадь Ленина')
        self.assertEqual(p1.group.member_count, 3)

    def test_same_feed_station_guard(self):
        s1 = self.stop(self.ag1, 'Terminal', 0, lt=1)
        s2 = self.stop(self.ag1, 'Terminal', 30, lt=1)
        recompute_stop_groups()
        s1.refresh_from_db(); s2.refresh_from_db()
        self.assertIsNone(s1.group_id)
        self.assertIsNone(s2.group_id)

    def test_cross_feed_stations_merge_with_count_fallback(self):
        s1 = self.stop(self.ag1, 'Terminal', 0, lt=1)
        s2 = self.stop(self.ag2, 'Terminal', 30, lt=1)
        recompute_stop_groups()
        s1.refresh_from_db(); s2.refresh_from_db()
        self.assertEqual(s1.group_id, s2.group_id)
        self.assertIsNotNone(s1.group_id)
        # no lt=0 members → member_count falls back to total members
        self.assertEqual(s1.group.member_count, 2)

    def test_parent_station_tree_and_station_name(self):
        station = self.stop(self.ag1, 'Alameda', 0, lt=1)
        c1 = self.stop(self.ag1, 'Alameda — Cais 1', 5, parent=station)
        c2 = self.stop(self.ag1, 'Alameda — Cais 2', -5, parent=station)
        pole = self.stop(self.ag2, 'Alameda D. Afonso Henriques', 16)
        recompute_stop_groups()
        for s in (station, c1, c2, pole):
            s.refresh_from_db()
        self.assertIsNotNone(station.group_id)
        self.assertEqual({station.group_id}, {c1.group_id, c2.group_id, pole.group_id})
        g = station.group
        self.assertEqual(g.name, 'Alameda')      # station-grade name wins
        self.assertEqual(g.member_count, 3)      # 2 platforms + 1 pole (lt=0)
        # centroid over unit roots: station counts once, not once per platform
        self.assertAlmostEqual(g.location.y, BASE_LAT + 8 * M, places=9)

    def test_location_type_234_excluded(self):
        a = self.stop(self.ag1, 'Hlavní nádraží', 0)
        b = self.stop(self.ag1, 'Hlavní nádraží', 20)
        entrance = self.stop(self.ag1, 'Hlavní nádraží', 10, lt=2)
        recompute_stop_groups()
        a.refresh_from_db(); entrance.refresh_from_db()
        self.assertIsNotNone(a.group_id)
        self.assertIsNone(entrance.group_id)
        self.assertEqual(a.group.member_count, 2)

    def test_zero_distance_different_names_not_merged(self):
        a = self.stop(self.ag1, 'Pç. Águas Livres', 0)
        b = self.stop(self.ag2, 'Damaia (Estação)', 0)
        recompute_stop_groups()
        a.refresh_from_db(); b.refresh_from_db()
        self.assertIsNone(a.group_id)
        self.assertIsNone(b.group_id)

    def test_inactive_feed_excluded(self):
        ds3 = TransitDataSource.objects.create(name='Dead', format='gtfs', slug='dead', is_active=False)
        ag3 = Agency.objects.create(data_source=ds3, name='A3', timezone='UTC', lang='en', source_id='a3')
        a = self.stop(self.ag1, 'Rua Alegria', 0)
        b = self.stop(ag3, 'Rua Alegria', 20)
        recompute_stop_groups()
        a.refresh_from_db(); b.refresh_from_db()
        self.assertIsNone(a.group_id)  # singleton after exclusion
        self.assertIsNone(b.group_id)

    def test_idempotent_second_run_zero_diff(self):
        self.stop(self.ag1, 'Rua Alegria', 0)
        self.stop(self.ag1, 'Rua Alegria', 20)
        self.stop(self.ag2, 'Alameda', 100, lt=1)
        self.stop(self.ag1, 'Alameda D. Afonso Henriques', 116)
        stats1 = recompute_stop_groups()
        self.assertEqual(stats1['groups_created'], 2)
        ids = set(StopGroup.objects.values_list('id', flat=True))
        stats2 = recompute_stop_groups()
        for key in ('groups_created', 'groups_updated', 'groups_deleted',
                    'members_assigned', 'members_cleared'):
            self.assertEqual(stats2[key], 0, f'{key} not zero on second run')
        self.assertEqual(ids, set(StopGroup.objects.values_list('id', flat=True)))

    def test_membership_change_keeps_group_ulid(self):
        self.stop(self.ag1, 'Rua Alegria', 0)
        self.stop(self.ag1, 'Rua Alegria', 20)
        recompute_stop_groups()
        gid = StopGroup.objects.get().id
        c = self.stop(self.ag2, 'Rua Alegria', 30)  # new feed adds a third pole
        stats = recompute_stop_groups()
        self.assertEqual(stats['groups_created'], 0)
        self.assertEqual(stats['groups_updated'], 1)   # centroid + member_count changed
        self.assertEqual(stats['members_assigned'], 1)
        c.refresh_from_db()
        self.assertEqual(c.group_id, gid)
        self.assertEqual(StopGroup.objects.get().id, gid)
        self.assertEqual(StopGroup.objects.get().member_count, 3)

    def test_member_loss_deletes_group(self):
        a = self.stop(self.ag1, 'Rua Alegria', 0)
        b = self.stop(self.ag1, 'Rua Alegria', 20)
        recompute_stop_groups()
        b.delete()
        stats = recompute_stop_groups()
        self.assertEqual(stats['groups_deleted'], 1)
        a.refresh_from_db()
        self.assertIsNone(a.group_id)
        self.assertEqual(StopGroup.objects.count(), 0)

    def test_dry_run_writes_nothing(self):
        self.stop(self.ag1, 'Rua Alegria', 0)
        self.stop(self.ag1, 'Rua Alegria', 20)
        stats = recompute_stop_groups(dry_run=True)
        self.assertEqual(stats['groups_created'], 1)
        self.assertEqual(stats['members_assigned'], 2)
        self.assertEqual(StopGroup.objects.count(), 0)
        self.assertFalse(Stop.objects.exclude(group=None).exists())

    def test_clear_kill_switch(self):
        self.stop(self.ag1, 'Rua Alegria', 0)
        self.stop(self.ag1, 'Rua Alegria', 20)
        recompute_stop_groups()
        self.assertEqual(StopGroup.objects.count(), 1)
        out = io.StringIO()
        call_command('recompute_stop_groups', '--clear', stdout=out)
        self.assertEqual(StopGroup.objects.count(), 0)
        self.assertFalse(Stop.objects.exclude(group=None).exists())
