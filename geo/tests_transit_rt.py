"""
Tests for RouteCache._load_all() — verifies all raw SQL queries are valid.

Catches SQL syntax errors (missing aliases, bad JOINs) that crash
per-source RT fetchers at startup.
"""

from django.test import TestCase

from geo.models import TransitDataSource, Route
from parahub.services.transit_rt import RouteCache


class RouteCacheLoadAllTest(TestCase):
    """Ensure _load_all executes without SQL errors."""

    def test_load_all_no_filter(self):
        """_load_all(None) — loads all routes, no WHERE clause."""
        cache = RouteCache()
        # Should not raise ProgrammingError
        route_info, headsign_info, shapes, stop_seqs = cache._load_all(data_source_ids=None)
        self.assertIsInstance(route_info, dict)
        self.assertIsInstance(headsign_info, dict)
        self.assertIsInstance(shapes, dict)
        self.assertIsInstance(stop_seqs, dict)

    def test_load_all_with_filter(self):
        """_load_all([ids]) — filtered mode, activates WHERE t.route_id = ANY(...)."""
        # Find a data source that has routes (exercises the SQL filter path)
        ds_with_routes = None
        for ds in TransitDataSource.objects.filter(is_active=True):
            if Route.objects.filter(agency__data_source=ds).exists():
                ds_with_routes = ds
                break

        if ds_with_routes is None:
            # No data sources with routes in test DB — use a dummy ID
            # This still exercises the SQL with an empty ANY() array
            from geo.models import Agency
            dummy_ds = TransitDataSource.objects.create(
                name='Test DS', slug='test-ds', is_active=True,
            )
            dummy_agency = Agency.objects.create(
                name='Test Agency', data_source=dummy_ds, source_id='test-agency',
            )
            Route.objects.create(
                agency=dummy_agency, source_id='test-route',
                short_name='T1', route_type=3,
            )
            ds_id = dummy_ds.id
        else:
            ds_id = ds_with_routes.id

        cache = RouteCache()
        # Should not raise ProgrammingError
        route_info, headsign_info, shapes, stop_seqs = cache._load_all(
            data_source_ids=[ds_id]
        )
        self.assertIsInstance(route_info, dict)
        self.assertIsInstance(shapes, dict)

    def test_load_all_with_nonexistent_ids(self):
        """_load_all with IDs that match no routes — should return empty, not crash."""
        cache = RouteCache()
        route_info, headsign_info, shapes, stop_seqs = cache._load_all(
            data_source_ids=['01ZZZZZZZZZZZZZZZZZZZZZZZZ']
        )
        self.assertEqual(route_info, {})
        self.assertEqual(headsign_info, {})
        self.assertEqual(shapes, {})
        self.assertEqual(stop_seqs, {})
