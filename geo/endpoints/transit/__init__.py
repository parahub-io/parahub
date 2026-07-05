"""
Transit (GTFS) endpoints — split by resource from the former single
transit.py. Importing the endpoint modules registers their routes on the
shared router (import order preserves the original registration order).
"""

from .base import router
from . import discovery, geojson, stops, routes, timetable, live, relay, sitemap  # noqa: E402,F401
from .helpers import _grouped_pole_members  # noqa: F401  (parahub.consumers.transit)

__all__ = ['router', '_grouped_pole_members']
