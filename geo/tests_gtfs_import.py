"""Tests for GTFS import helpers.

Covers the empty-headsign terminus backfill — operators may ship a blank
trip_headsign feed-wide (Carris Lisboa), which erases every (route, direction)
label derived from it. See PK/gtfs-feed-quirks.md (Carris empty trip_headsign).
"""
from datetime import time

from django.contrib.gis.geos import Point
from django.test import TestCase

from geo.models import Agency, Route, Stop, StopTime, TransitDataSource, Trip
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
