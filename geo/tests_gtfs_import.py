"""Tests for GTFS import helpers.

Covers the empty-headsign terminus backfill — operators may ship a blank
trip_headsign feed-wide (Carris Lisboa), which erases every (route, direction)
label derived from it. See PK/gtfs-feed-quirks.md (Carris empty trip_headsign).
"""
import os
import tempfile
import zipfile
from datetime import time
from io import StringIO
from unittest.mock import patch

from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.core.management import call_command
from django.test import TestCase

from geo.models import Agency, Place, Route, Stop, StopTime, TransitDataSource, Trip
from geo.management.commands.import_gtfs import backfill_empty_headsigns


class BackfillEmptyHeadsignsTests(TestCase):
    def setUp(self):
        self.ds = TransitDataSource.objects.create(name='Feed', format='gtfs', slug='feed')
        self.ag = Agency.objects.create(data_source=self.ds, name='A', timezone='Europe/Lisbon',
                                        lang='pt', source_id='a')
        self.route = Route.objects.create(agency=self.ag, source_id='764', short_name='764',
                                          long_name='Cidade Universitária - Damaia Cima', route_type=3)
        self._n = 0

    def _stop(self, name, agency=None):
        self._n += 1
        return Stop.objects.create(agency=agency or self.ag, name=name, source_id=f's{self._n}',
                                   location=Point(-9.2, 38.74, srid=4326), location_type=0)

    def _trip(self, headsign, direction_id, route=None):
        self._n += 1
        return Trip.objects.create(route=route or self.route, source_id=f't{self._n}',
                                   headsign=headsign, service_id='S1', direction_id=direction_id)

    def _chain(self, trip, *stops):
        for i, s in enumerate(stops, start=1):
            StopTime.objects.create(trip=trip, stop=s, stop_sequence=i,
                                    arrival_time=time(8, 0), departure_time=time(8, 0))

    def test_blank_headsign_filled_with_terminus(self):
        a, b, term = self._stop('R. Creche'), self._stop('Mid'), self._stop('Damaia Cima')
        t = self._trip('', 0)
        self._chain(t, a, b, term)
        self.assertEqual(backfill_empty_headsigns(), 1)
        t.refresh_from_db()
        self.assertEqual(t.headsign, 'Damaia Cima')

    def test_existing_headsign_untouched(self):
        a, term = self._stop('A'), self._stop('Z Terminus')
        t = self._trip('Original', 0)
        self._chain(t, a, term)
        self.assertEqual(backfill_empty_headsigns(), 0)
        t.refresh_from_db()
        self.assertEqual(t.headsign, 'Original')

    def test_per_trip_terminus_short_turn(self):
        # Two blank trips through the same pole ending at different termini → each
        # gets its OWN terminus (full run vs short-turn), not a shared route label.
        pole = self._stop('R. Creche')
        full = self._trip('', 1)
        self._chain(full, pole, self._stop('Cidade Universitária'))
        short = self._trip('', 1)
        self._chain(short, pole, self._stop('Colégio Militar'))
        self.assertEqual(backfill_empty_headsigns(), 2)
        full.refresh_from_db(); short.refresh_from_db()
        self.assertEqual(full.headsign, 'Cidade Universitária')
        self.assertEqual(short.headsign, 'Colégio Militar')

    def test_agency_scope_limits_writes(self):
        a, term = self._stop('A'), self._stop('TermA')
        t1 = self._trip('', 0)
        self._chain(t1, a, term)

        ds2 = TransitDataSource.objects.create(name='Other', format='gtfs', slug='other')
        ag2 = Agency.objects.create(data_source=ds2, name='B', timezone='UTC', lang='en', source_id='b')
        route2 = Route.objects.create(agency=ag2, source_id='R', short_name='R', long_name='R', route_type=3)
        t2 = self._trip('', 0, route=route2)
        self._chain(t2, self._stop('B1', agency=ag2), self._stop('TermB', agency=ag2))

        # Scope to the first agency only → t2 (other agency) stays blank.
        self.assertEqual(backfill_empty_headsigns([self.ag.id]), 1)
        t1.refresh_from_db(); t2.refresh_from_db()
        self.assertEqual(t1.headsign, 'TermA')
        self.assertEqual(t2.headsign, '')


class AgencyRenameReimportTests(TestCase):
    """An upstream agency_id rename must re-home rows (ULIDs preserved), never
    duplicate the feed graph.

    Both the upsert lookups and the stale-row prunes must see agencies that
    were dropped from agency.txt — when they only saw the current feed's
    agencies, a rename made every existing row unfindable and the import
    created a full second generation of agencies/routes/stops/trips
    (Carris Metropolitana, 2026-07-26).
    """

    FEED_URL = 'http://test.example/gtfs-rename'

    def setUp(self):
        self.ds = TransitDataSource.objects.create(
            name='RenameFeed', format='gtfs', slug='rename-feed', url=self.FEED_URL)

    def _write_zip(self, agency_ids, route_agency_ids=None, with_shapes=False):
        route_ag = route_agency_ids or agency_ids
        files = {
            'agency.txt': 'agency_id,agency_name,agency_url,agency_timezone\n' + ''.join(
                f'{a},Operator {i},http://example.org,Europe/Lisbon\n'
                for i, a in enumerate(agency_ids)),
            'stops.txt': ('stop_id,stop_name,stop_lat,stop_lon\n'
                          's1,Stop One,38.70,-9.10\n'
                          's2,Stop Two,38.71,-9.11\n'),
            'routes.txt': ('route_id,agency_id,route_short_name,route_long_name,route_type\n'
                           f'r1,{route_ag[0]},1,Route One,3\n'
                           f'r2,{route_ag[-1]},2,Route Two,3\n'),
            'trips.txt': ('trip_id,route_id,service_id,trip_headsign\n'
                          't1,r1,S1,Somewhere\n'),
            'stop_times.txt': ('trip_id,arrival_time,departure_time,stop_id,stop_sequence\n'
                               't1,08:00:00,08:00:00,s1,1\n'
                               't1,08:10:00,08:10:00,s2,2\n'),
            'calendar_dates.txt': 'service_id,date,exception_type\nS1,20260801,1\n',
        }
        if with_shapes:
            files['shapes.txt'] = ('shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\n'
                                   'sh1,38.70,-9.10,1\n'
                                   'sh1,38.71,-9.11,2\n')
            files['trips.txt'] = ('trip_id,route_id,service_id,trip_headsign,shape_id\n'
                                  't1,r1,S1,Somewhere,sh1\n')
        fd, path = tempfile.mkstemp(suffix='.zip')
        os.close(fd)
        with zipfile.ZipFile(path, 'w') as z:
            for name, content in files.items():
                z.writestr(name, content)
        self.addCleanup(os.unlink, path)
        return path

    def _import(self, path, **kwargs):
        out, err = StringIO(), StringIO()
        call_command('import_gtfs', file=path, feed_url=self.FEED_URL,
                     stdout=out, stderr=err, **kwargs)
        return out.getvalue() + err.getvalue()

    def _graph_ids(self):
        return {
            'agencies': dict(Agency.objects.filter(
                data_source=self.ds).values_list('source_id', 'id')),
            'routes': dict(Route.objects.filter(
                agency__data_source=self.ds).values_list('source_id', 'id')),
            'stops': dict(Stop.objects.filter(
                agency__data_source=self.ds).values_list('source_id', 'id')),
            'trips': dict(Trip.objects.filter(
                route__agency__data_source=self.ds).values_list('source_id', 'id')),
        }

    def test_consistent_rename_rehomes_rows(self):
        self._import(self._write_zip(['41', '42']))
        before = self._graph_ids()
        self.assertEqual(set(before['agencies']), {'41', '42'})

        out = self._import(self._write_zip(['A2L', 'BNA']))

        after = self._graph_ids()
        self.assertEqual(set(after['agencies']), {'A2L', 'BNA'})
        self.assertEqual(after['routes'], before['routes'])
        self.assertEqual(after['stops'], before['stops'])
        self.assertEqual(after['trips'], before['trips'])
        self.assertIn('Pruned dropped agency', out)

    def test_broken_rename_with_dangling_route_agency_ids(self):
        # CM-style: agency.txt renamed but routes.txt still references old ids
        self._import(self._write_zip(['41', '42']))
        before = self._graph_ids()

        self._import(self._write_zip(['A2L', 'BNA'], route_agency_ids=['41', '42']))

        after = self._graph_ids()
        self.assertEqual(set(after['agencies']), {'A2L', 'BNA'})
        self.assertEqual(after['routes'], before['routes'])
        self.assertEqual(after['stops'], before['stops'])
        self.assertEqual(after['trips'], before['trips'])

    def test_unmoved_rows_block_agency_prune(self):
        # --skip-shapes leaves shapes under the dropped primary agency: the
        # guard must keep that agency and say so, not silently cascade it away
        self._import(self._write_zip(['41', '42'], with_shapes=True))

        out = self._import(self._write_zip(['A2L', 'BNA'], with_shapes=True),
                           skip_shapes=True)

        remaining = set(Agency.objects.filter(
            data_source=self.ds).values_list('source_id', flat=True))
        self.assertIn('NOT pruning dropped agency', out)
        self.assertIn('41', remaining)      # blocked: still owns sh1
        self.assertNotIn('42', remaining)   # empty → pruned


class ResolveStaticUrlTests(TestCase):
    """resolve_static_url: GO Hub plan-registry URLs → the active plan's ZIP.

    TML rotates a pre-signed object-storage URL on every plan publication, so
    TransitDataSource.url stores the registry plus the operator's GO agency id
    as a fragment and resolves the download at fetch time.
    See PK/gtfs-feed-quirks.md "GO Hub (TML)".
    """

    PLANS_URL = 'https://go.tmlmobilidade.pt/hub/api/v1/plans'

    def _plans(self, *plans):
        class _Resp:
            @staticmethod
            def raise_for_status():
                return None

            @staticmethod
            def json():
                return {'data': list(plans), 'error': None, 'status_code': 200}

        return _Resp()

    def _plan(self, agency_id, plan_id, is_active, updated_at=0):
        return {
            '_id': plan_id,
            'agency_id': agency_id,
            'is_active': is_active,
            'updated_at': updated_at,
            'operation_file_url': f'https://objectstorage.example/o/plans/{plan_id}.zip',
        }

    def test_plain_url_passes_through_without_a_request(self):
        from geo.management.commands import import_gtfs

        def _boom(*a, **kw):  # pragma: no cover - must never be called
            raise AssertionError('plain URLs must not hit the network')

        with patch.object(import_gtfs.requests, 'get', _boom):
            url = 'https://api.carrismetropolitana.pt/gtfs'
            self.assertEqual(import_gtfs.resolve_static_url(url), url)

    def test_fragment_selects_the_agencys_active_plan(self):
        from geo.management.commands import import_gtfs

        resp = self._plans(
            self._plan('7NTB1', 'OLD11', is_active=False, updated_at=9),
            self._plan('HF16N', 'SBF83', is_active=True, updated_at=5),
            self._plan('7NTB1', '2XUL7', is_active=True, updated_at=3),
        )
        with patch.object(import_gtfs.requests, 'get', return_value=resp):
            self.assertEqual(
                import_gtfs.resolve_static_url(f'{self.PLANS_URL}#7NTB1'),
                'https://objectstorage.example/o/plans/2XUL7.zip',
            )

    def test_newest_wins_when_several_plans_are_active(self):
        from geo.management.commands import import_gtfs

        resp = self._plans(
            self._plan('7NTB1', 'OLDER', is_active=True, updated_at=1),
            self._plan('7NTB1', 'NEWER', is_active=True, updated_at=2),
        )
        with patch.object(import_gtfs.requests, 'get', return_value=resp):
            self.assertEqual(
                import_gtfs.resolve_static_url(f'{self.PLANS_URL}#7NTB1'),
                'https://objectstorage.example/o/plans/NEWER.zip',
            )

    def test_no_active_plan_raises_instead_of_importing_the_wrong_feed(self):
        from geo.management.commands import import_gtfs

        resp = self._plans(self._plan('7NTB1', 'OLD11', is_active=False))
        with patch.object(import_gtfs.requests, 'get', return_value=resp):
            with self.assertRaises(RuntimeError):
                import_gtfs.resolve_static_url(f'{self.PLANS_URL}#7NTB1')


class RouteChurnPlaceAndSlugTests(TestCase):
    """Replacing a feed's route set must still assign Route.place and slugs.

    Both were gated on STOP churn alone, which held until a feed swapped its
    upstream source: cp-rail's 2026-08-06 move to the GO Hub plan re-homed all
    454 stops (an *update*, not a create) while replacing 184 routes with 123.
    The gate saw no stop change, so place assignment was skipped — and
    _generate_slugs only slugs placed routes (the uniqueness constraint is
    per-place), leaving every new route place-less AND slug-less, i.e. with an
    unreachable page.
    """

    FEED_URL = 'http://test.example/gtfs-churn'

    def setUp(self):
        self.ds = TransitDataSource.objects.create(
            name='ChurnFeed', format='gtfs', slug='churn-feed', url=self.FEED_URL)
        self.place = Place.objects.create(
            name='Testville', slug='testville', place_type='city',
            geometry=MultiPolygon(Polygon(((-9.2, 38.6), (-9.0, 38.6),
                                           (-9.0, 38.8), (-9.2, 38.8), (-9.2, 38.6)))),
            center_point=Point(-9.1, 38.7),
        )

    def _write_zip(self, route_ids):
        files = {
            'agency.txt': ('agency_id,agency_name,agency_url,agency_timezone\n'
                           'a1,Operator,http://example.org,Europe/Lisbon\n'),
            # Stops never change — only routes churn.
            'stops.txt': ('stop_id,stop_name,stop_lat,stop_lon\n'
                          's1,Stop One,38.70,-9.10\n'
                          's2,Stop Two,38.71,-9.11\n'),
            'routes.txt': 'route_id,agency_id,route_short_name,route_long_name,route_type\n' + ''.join(
                f'{r},a1,{r},Route {r},3\n' for r in route_ids),
            'trips.txt': 'trip_id,route_id,service_id,trip_headsign\n' + ''.join(
                f't_{r},{r},S1,Somewhere\n' for r in route_ids),
            'stop_times.txt': 'trip_id,arrival_time,departure_time,stop_id,stop_sequence\n' + ''.join(
                f't_{r},08:00:00,08:00:00,s1,1\nt_{r},08:10:00,08:10:00,s2,2\n' for r in route_ids),
            'calendar_dates.txt': 'service_id,date,exception_type\nS1,20260801,1\n',
        }
        fd, path = tempfile.mkstemp(suffix='.zip')
        os.close(fd)
        with zipfile.ZipFile(path, 'w') as z:
            for name, content in files.items():
                z.writestr(name, content)
        self.addCleanup(os.unlink, path)
        return path

    def _import(self, route_ids):
        out, err = StringIO(), StringIO()
        call_command('import_gtfs', file=self._write_zip(route_ids),
                     feed_url=self.FEED_URL, stdout=out, stderr=err)
        return out.getvalue() + err.getvalue()

    def _routes(self):
        return Route.objects.filter(agency__data_source=self.ds)

    def test_replaced_routes_get_place_and_slug_though_stops_unchanged(self):
        self._import(['old1', 'old2'])
        self.assertEqual(Stop.objects.filter(agency__data_source=self.ds).count(), 2)

        self._import(['new1', 'new2', 'new3'])

        routes = self._routes()
        self.assertEqual(set(routes.values_list('source_id', flat=True)),
                         {'new1', 'new2', 'new3'})
        self.assertEqual(routes.filter(place__isnull=True).count(), 0,
                         'replaced routes must be assigned a place')
        self.assertEqual(routes.filter(slug='').count(), 0,
                         'placed routes must be slugged — an empty slug is an unreachable page')

    def test_unchanged_reimport_still_skips_the_work(self):
        self._import(['r1', 'r2'])
        log = self._import(['r1', 'r2'])
        self.assertIn('Skipping place assignment', log)


class IgnoreLineIdsTests(TestCase):
    """A feed may put a SERVICE CLASS in line_id rather than a line.

    CP's GO Hub plan tags every long-distance train AP/IC/IR/R, so grouping on
    it fused 49 unrelated regional services (Guarda-Lisboa beside Lagos-Portimao)
    into one nationwide "R" line with a 49-entry percursos selector.
    """

    FEED_URL = 'http://test.example/gtfs-lineid'

    def setUp(self):
        self.ds = TransitDataSource.objects.create(
            name='LineFeed', format='gtfs', slug='cp-rail', url=self.FEED_URL)

    def _write_zip(self):
        files = {
            'agency.txt': ('agency_id,agency_name,agency_url,agency_timezone\n'
                           'a1,Operator,http://example.org,Europe/Lisbon\n'),
            'stops.txt': ('stop_id,stop_name,stop_lat,stop_lon\n'
                          's1,Stop One,38.70,-9.10\n'
                          's2,Stop Two,38.71,-9.11\n'),
            'routes.txt': (
                'route_id,agency_id,route_short_name,route_long_name,route_type,line_id,line_long_name\n'
                'R_1,a1,R,Guarda - Lisboa,2,R,Regional\n'
                'R_2,a1,R,Lagos - Portimao,2,R,Regional\n'
                'CASCAIS_4,a1,Cascais,Cascais - Cais do Sodre,2,CASCAIS,Linha de Cascais\n'
            ),
            'trips.txt': ('trip_id,route_id,service_id,trip_headsign\n'
                          't1,R_1,S1,A\nt2,R_2,S1,B\nt3,CASCAIS_4,S1,C\n'),
            'stop_times.txt': 'trip_id,arrival_time,departure_time,stop_id,stop_sequence\n' + ''.join(
                f'{t},08:00:00,08:00:00,s1,1\n{t},08:10:00,08:10:00,s2,2\n'
                for t in ('t1', 't2', 't3')),
            'calendar_dates.txt': 'service_id,date,exception_type\nS1,20260801,1\n',
        }
        fd, path = tempfile.mkstemp(suffix='.zip')
        os.close(fd)
        with zipfile.ZipFile(path, 'w') as z:
            for name, content in files.items():
                z.writestr(name, content)
        self.addCleanup(os.unlink, path)
        return path

    def test_service_class_line_ids_blanked_real_lines_kept(self):
        out, err = StringIO(), StringIO()
        call_command('import_gtfs', file=self._write_zip(), feed_url=self.FEED_URL,
                     stdout=out, stderr=err)
        by_src = {r.source_id: r for r in Route.objects.filter(agency__data_source=self.ds)}
        self.assertEqual(by_src['R_1'].line_id, '', 'service class must not group')
        self.assertEqual(by_src['R_2'].line_id, '')
        self.assertEqual(by_src['R_1'].line_long_name, '')
        self.assertEqual(by_src['CASCAIS_4'].line_id, 'CASCAIS', 'real line must still group')
