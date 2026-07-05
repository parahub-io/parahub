"""
Response schemas for the transit API.
"""


from typing import Dict, Optional, List
from pydantic import BaseModel
import logging
from datetime import datetime



logger = logging.getLogger(__name__)

class TransitPlaceResponse(BaseModel):
    name: str
    slug: str
    country_code: str
    place_type: str
    stops_count: int = 0
    routes_count: int = 0

class AgencyResponse(BaseModel):
    id: str
    object_type: str = "transit_agency"
    name: str
    source_id: str
    url: str
    data_source_url: str = ""
    timezone: str
    lang: str
    routes_count: int = 0
    stops_count: int = 0
    last_imported_at: Optional[datetime] = None

class TransitRouteListItem(BaseModel):
    id: str
    object_type: str = "transit_route"
    slug: str = ""
    place_slug: str = ""
    short_name: str
    long_name: str
    route_type: int
    route_color: str
    route_text_color: str
    agency_id: str

class TransitRouteDirection(BaseModel):
    direction_id: int
    headsign: str = ""

class TransitRoutePlaceItem(BaseModel):
    name: str
    slug: str
    country_code: str

class TransitRouteVariant(BaseModel):
    """A sibling path-variant of the same line (CM percurso)."""
    slug: str = ""
    place_slug: str = ""
    source_id: str = ""
    long_name: str = ""
    path_type: int = 0
    directions: list[TransitRouteDirection] = []
    is_current: bool = False
    runs_today: bool = True  # False only when other variants run today and this one doesn't

class TransitRouteDetail(BaseModel):
    id: str
    object_type: str = "transit_route"
    source_id: str = ""
    data_source_id: str = ""
    slug: str = ""
    place_slug: str = ""
    short_name: str
    long_name: str
    description: str
    route_type: int
    route_color: str
    route_text_color: str
    agency_id: str
    agency_name: str = ""
    agency_timezone: str = ""  # GTFS agency tz (Europe/Lisbon …) — frontend renders live ETA/now in stop's zone, not browser's
    # Line grouping (CM ext): multiple variants share line_id; canonical = lowest path_type.
    line_id: str = ""
    line_long_name: str = ""
    canonical_slug: str = ""  # slug of the canonical (lowest path_type) variant; empty if single-variant
    variants: list[TransitRouteVariant] = []  # all path-variants of this line (incl. current)
    stops: list = []          # direction_id=0 stops (or undirected)
    stops_dir1: list = []     # direction_id=1 stops (empty if route has no inbound direction)
    directions: list[TransitRouteDirection] = []
    places: list[TransitRoutePlaceItem] = []  # All places this route passes through
    geometry: Optional[Dict] = None

class TransitStopResponse(BaseModel):
    id: str
    object_type: str = "transit_stop"
    slug: str = ""
    place_slug: str = ""
    name: str
    # Unabbreviated GTFS tts_stop_name (driver-mode TTS, screen-reader aria-label);
    # "" when the feed omits it. Not shown as visible text — name stays the display label.
    tts_name: str = ""
    source_id: str
    lat: float
    lon: float
    location_type: int
    agency_id: str
    data_source_id: str = ""
    routes: list = []
    # Top destinations served from THIS pole (busiest trip headsigns) — the
    # direction label that disambiguates same-name opposite-direction poles.
    directions: list = []
    # Transport modes reachable at this location (self + group siblings) when it
    # spans >1 mode — an intermodal interchange (e.g. ['bus', 'metro']). Empty
    # otherwise. See _interchange_modes_for_stops.
    interchange_modes: list = []
    # Virtual stop this physical stop belongs to: {id, name, member_count, lat,
    # lon, stops: [member dicts incl. self]} — null when ungrouped
    group: Optional[Dict] = None

class ScheduleEntry(BaseModel):
    departure_time: str
    route_short_name: str
    route_color: str
    headsign: str
    trip_id: str

class TransitFeedResponse(BaseModel):
    id: str
    object_type: str = "transit_feed"
    name: str
    url: str
    format: str
    is_active: bool
    last_imported_at: Optional[datetime] = None
    last_error: str = ""
    rt_vehicles_url: str = ""
    agencies: List[str] = []
    routes_count: int = 0
    stops_count: int = 0
    trips_count: int = 0
