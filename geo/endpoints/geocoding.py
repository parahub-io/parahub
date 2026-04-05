"""
Geocoding and OSM feature endpoints.
"""

from ninja import Router
from ninja.errors import HttpError
from typing import Optional
from pydantic import BaseModel
from datetime import datetime
import os
import requests
import logging
from constance import config
from parahub.ratelimit import ratelimit

logger = logging.getLogger(__name__)

router = Router(tags=["Geo / Geocoding"])


class MissingImageRequest(BaseModel):
    """Request schema for reporting missing map images"""
    image_id: str
    user_agent: str = ""


@router.post("/log-missing-image", auth=None)
@ratelimit(group='geo:log_missing_image', key='ip', rate='30/m', method='POST')
def log_missing_image(request, payload: MissingImageRequest):
    """
    Log missing map sprite images to /tmp/missing_map_images.txt

    This endpoint is called by the frontend when MapLibre reports missing images.
    No authentication required as this is just logging for debugging.
    """
    try:
        timestamp = datetime.now().isoformat()
        log_entry = f"{timestamp} | {payload.image_id} | {payload.user_agent}\n"

        with open('/tmp/missing_map_images.txt', 'a') as f:
            f.write(log_entry)

        return {"status": "logged"}
    except Exception as e:
        logger.error(f"Error logging missing image: {e}")
        return {"status": "error", "message": str(e)}


# Pelias geocoding server URL
PELIAS_URL = "http://localhost:4000"

# Elasticsearch URL for direct multilingual search
ELASTICSEARCH_URL = "http://localhost:9200"

# OpenMapTiles database connection
OPENMAPTILES_DB = {
    'host': os.getenv('OPENMAPTILES_DB_HOST', 'localhost'),
    'port': int(os.getenv('OPENMAPTILES_DB_PORT', '5439')),
    'database': 'openmaptiles',
    'user': 'openmaptiles',
    'password': os.getenv('OPENMAPTILES_DB_PASSWORD', 'openmaptiles'),
}


@router.get("/geocode/search", auth=None)
@ratelimit(group='geo:geocode_search', key='ip', rate='60/m')
def geocode_search(request, q: str = "", limit: int = 10, lang: str = "",
                   focus_lat: float = None, focus_lon: float = None):
    """
    Geocode search - find location by name/address using Pelias with multilingual support.
    Returns GeoJSON FeatureCollection with planet-wide coverage.

    Language detection priority:
    1. User's profile.preferred_language (if authenticated)
    2. 'lang' query parameter
    3. Default to 'en'

    Parameters:
    - q: Search query (place name, address, coordinates)
    - limit: Maximum number of results (default 10)
    - lang: Language code override (optional)
    - focus_lat, focus_lon: Bias results toward this point (map center)
    """
    if not q:
        return {
            'type': 'FeatureCollection',
            'features': []
        }

    try:
        # Determine user language from profile or parameter
        user_lang = lang  # Start with parameter

        if not user_lang and request.user.is_authenticated:
            # Get language from user profile
            from identity.models import Profile
            try:
                profile = Profile.objects.get(account=request.user, is_primary=True)
                user_lang = profile.preferred_language or 'en'
            except Profile.DoesNotExist:
                user_lang = 'en'

        if not user_lang:
            user_lang = 'en'  # Final fallback

        # Use Pelias API (not direct ES) to get enriched data with admin hierarchy
        params = {
            'text': q,
            'size': limit,
            'lang': user_lang
        }

        # Bias results toward map viewport center
        if focus_lat is not None and focus_lon is not None:
            params['focus.point.lat'] = focus_lat
            params['focus.point.lon'] = focus_lon
            # autocomplete respects focus.point much better for nearby results
            endpoint = '/v1/autocomplete'
        else:
            endpoint = '/v1/search'

        response = requests.get(
            f"{PELIAS_URL}{endpoint}",
            params=params,
            timeout=5
        )
        response.raise_for_status()
        pelias_data = response.json()

        # Transform Pelias response to simplified format
        features = []
        for feature in pelias_data.get('features', []):
            props = feature.get('properties', {})

            # Filter out low-quality results (missing country or basic location data)
            # These are usually incorrect WOF data (e.g., "Podame" in Arabian Sea)
            country = props.get('country', '')
            layer = props.get('layer', '')

            # Skip results without country UNLESS they are large geographic features (ocean, marinearea)
            if not country and layer not in ['ocean', 'marinearea']:
                continue

            # Simplified format for frontend
            simplified_feature = {
                'type': 'Feature',
                'geometry': feature.get('geometry'),
                'properties': {
                    'osm_id': props.get('id', ''),
                    'osm_type': props.get('source', ''),
                    'osm_value': props.get('layer', ''),
                    'name': props.get('name', ''),
                    'label': props.get('label', ''),
                    'country': country,
                    'country_code': props.get('country_a', ''),
                    'region': props.get('region', ''),
                    'county': props.get('county', ''),
                    'locality': props.get('locality', ''),
                    'localadmin': props.get('localadmin', ''),
                    'city': props.get('locality') or props.get('localadmin', ''),
                    'street': props.get('street', ''),
                    'housenumber': props.get('housenumber', ''),
                    'postalcode': props.get('postalcode', '')
                }
            }
            features.append(simplified_feature)

        return {
            'type': 'FeatureCollection',
            'features': features
        }

    except requests.RequestException as e:
        logger.error(f"Geocoding error: {e}")
        raise HttpError(503, "Geocoding service temporarily unavailable")
    except Exception as e:
        logger.error(f"Unexpected error in geocoding: {e}", exc_info=True)
        raise HttpError(500, "Internal server error")


@router.get("/geocode/reverse", auth=None)
@ratelimit(group='geo:geocode_reverse', key='ip', rate='60/m')
def geocode_reverse(request, lat: float, lon: float):
    """
    Reverse geocoding - get address from coordinates using Pelias.

    Parameters:
    - lat: Latitude
    - lon: Longitude
    """
    try:
        params = {
            'point.lat': lat,
            'point.lon': lon,
            'size': 1
        }

        response = requests.get(
            f"{PELIAS_URL}/v1/reverse",
            params=params,
            timeout=5
        )
        response.raise_for_status()
        pelias_response = response.json()

        # Extract first feature
        features = pelias_response.get('features', [])
        if not features:
            raise HttpError(404, "No results found")

        feature = features[0]
        props = feature.get('properties', {})
        coords = feature.get('geometry', {}).get('coordinates', [0, 0])

        # Convert to simplified format
        return {
            'display_name': props.get('label', ''),
            'address': {
                'name': props.get('name'),
                'street': props.get('street'),
                'housenumber': props.get('housenumber'),
                'city': props.get('locality') or props.get('localadmin'),
                'county': props.get('county'),
                'state': props.get('region'),
                'country': props.get('country'),
                'country_code': props.get('country_code', ''),
                'country_a': props.get('country_a', ''),
                'postcode': props.get('postalcode')
            },
            'lat': coords[1],
            'lon': coords[0],
            'osm_id': props.get('id'),
            'osm_type': props.get('source')
        }

    except requests.RequestException as e:
        logger.error(f"Reverse geocoding error: {e}")
        raise HttpError(503, "Geocoding service temporarily unavailable")
    except Exception as e:
        logger.error(f"Unexpected error in reverse geocoding: {e}")
        raise HttpError(500, "Internal server error")


@router.get("/osm/at-point", auth=None)
@ratelimit(group='geo:osm_at_point', key='ip', rate='60/m')
def get_osm_features_at_point(
    request,
    lat: float,
    lon: float,
    layer: Optional[str] = None,
    radius: Optional[int] = None
):
    """
    Get OSM features at specific coordinates.
    Returns all features within radius (meters) of the point.

    Parameters:
    - lat: Latitude (WGS84)
    - lon: Longitude (WGS84)
    - layer: Optional layer hint (building, poi, transportation, etc.)
    - radius: Search radius in meters (default from settings: FEATURES_AT_POINT_RADIUS_M)
    """
    if radius is None:
        radius = config.FEATURES_AT_POINT_RADIUS_M
    import psycopg2
    from psycopg2.extras import RealDictCursor, register_hstore

    try:
        conn = psycopg2.connect(**OPENMAPTILES_DB)
        register_hstore(conn)  # Register hstore adapter to auto-parse hstore fields to dict
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Convert WGS84 to Web Mercator (EPSG:3857)
        point_query = f"ST_Transform(ST_SetSRID(ST_MakePoint({lon}, {lat}), 4326), 3857)"

        # Tables to search (table_name, geometry_type, table_type)
        # table_type: 'tags', 'building', 'landcover', 'landuse', 'park', 'water'
        search_tables = [
            ('osm_building_polygon', 'Polygon', 'building'),
            ('osm_poi_point', 'Point', 'tags'),
            ('osm_poi_polygon', 'Polygon', 'tags'),
            ('osm_park_polygon', 'Polygon', 'park'),
            ('osm_landcover_polygon', 'Polygon', 'landcover'),
            ('osm_landuse_polygon', 'Polygon', 'landuse'),
            ('osm_water_polygon', 'Polygon', 'water'),
            ('osm_waterway_linestring', 'LineString', 'tags'),  # Rivers, streams
            ('osm_boundary_polygon', 'Polygon', 'tags'),  # Administrative boundaries
            ('osm_railway_linestring', 'LineString', 'tags'),  # Railways (has name + tags)
            ('osm_highway_linestring', 'LineString', 'tags'),  # Roads
            # Note: osm_aeroway_* tables excluded - they lack name/tags fields
        ]

        # Filter by layer hint if provided, otherwise search all tables
        if layer:
            filtered_tables = [t for t in search_tables if layer.lower() in t[0].lower()]
            # If no tables match the layer, search all tables as fallback
            if not filtered_tables:
                logger.warning(f"No tables found for layer '{layer}', searching all tables")
                filtered_tables = search_tables
            search_tables = filtered_tables

        all_results = []

        for table_name, geom_type, table_type in search_tables:
            try:
                if table_type == 'tags':
                    # Generic tables with name and tags hstore
                    query = f"""
                        SELECT
                            t.osm_id,
                            '{table_name}' as source_table,
                            '{geom_type}' as geometry_type,
                            t.name,
                            t.tags,
                            ST_AsGeoJSON(ST_Transform(t.geometry, 4326))::json as geometry,
                            ST_Distance(t.geometry, {point_query}) as distance
                        FROM {table_name} t
                        WHERE ST_DWithin(t.geometry, {point_query}, {radius})
                        ORDER BY distance
                        LIMIT 5
                    """
                elif table_type == 'building':
                    # Buildings
                    query = f"""
                        SELECT
                            t.osm_id,
                            '{table_name}' as source_table,
                            '{geom_type}' as geometry_type,
                            t.building,
                            t.buildingpart,
                            t.buildingheight,
                            t.buildinglevels,
                            t.height,
                            t.levels,
                            t.material,
                            t.colour,
                            ST_AsGeoJSON(ST_Transform(t.geometry, 4326))::json as geometry,
                            ST_Distance(t.geometry, {point_query}) as distance
                        FROM {table_name} t
                        WHERE ST_DWithin(t.geometry, {point_query}, {radius})
                        ORDER BY distance
                        LIMIT 5
                    """
                elif table_type == 'landcover':
                    # Landcover (forests, grass, etc.)
                    query = f"""
                        SELECT
                            t.osm_id,
                            '{table_name}' as source_table,
                            '{geom_type}' as geometry_type,
                            t.subclass,
                            t.mapping_key,
                            t.area,
                            ST_AsGeoJSON(ST_Transform(t.geometry, 4326))::json as geometry,
                            ST_Distance(t.geometry, {point_query}) as distance
                        FROM {table_name} t
                        WHERE ST_DWithin(t.geometry, {point_query}, {radius})
                        ORDER BY distance
                        LIMIT 5
                    """
                elif table_type == 'landuse':
                    # Landuse (residential, commercial, etc.)
                    query = f"""
                        SELECT
                            t.osm_id,
                            '{table_name}' as source_table,
                            '{geom_type}' as geometry_type,
                            t.landuse,
                            t.amenity,
                            t.leisure,
                            t.tourism,
                            t.place,
                            t.waterway,
                            t.area,
                            ST_AsGeoJSON(ST_Transform(t.geometry, 4326))::json as geometry,
                            ST_Distance(t.geometry, {point_query}) as distance
                        FROM {table_name} t
                        WHERE ST_DWithin(t.geometry, {point_query}, {radius})
                        ORDER BY distance
                        LIMIT 5
                    """
                elif table_type == 'park':
                    # Parks and protected areas
                    query = f"""
                        SELECT
                            t.osm_id,
                            '{table_name}' as source_table,
                            '{geom_type}' as geometry_type,
                            t.name,
                            t.name_en,
                            t.name_de,
                            t.tags,
                            t.landuse,
                            t.leisure,
                            t.boundary,
                            t.protection_title,
                            t.area,
                            ST_AsGeoJSON(ST_Transform(t.geometry, 4326))::json as geometry,
                            ST_Distance(t.geometry, {point_query}) as distance
                        FROM {table_name} t
                        WHERE ST_DWithin(t.geometry, {point_query}, {radius})
                        ORDER BY distance
                        LIMIT 5
                    """
                elif table_type == 'water':
                    # Water features (lakes, rivers, etc.)
                    query = f"""
                        SELECT
                            t.osm_id,
                            '{table_name}' as source_table,
                            '{geom_type}' as geometry_type,
                            t.name,
                            t.name_en,
                            t.name_de,
                            t.tags,
                            t.place,
                            t.natural,
                            t.landuse,
                            t.waterway,
                            t.leisure,
                            t.water,
                            t.is_intermittent,
                            t.is_tunnel,
                            t.is_bridge,
                            t.area,
                            ST_AsGeoJSON(ST_Transform(t.geometry, 4326))::json as geometry,
                            ST_Distance(t.geometry, {point_query}) as distance
                        FROM {table_name} t
                        WHERE ST_DWithin(t.geometry, {point_query}, {radius})
                        ORDER BY distance
                        LIMIT 5
                    """

                cur.execute(query)
                rows = cur.fetchall()
            except psycopg2.Error as e:
                logger.error(f"Error querying table {table_name}: {e}")
                continue  # Skip this table and try next one

            for row in rows:
                # RealDictCursor returns dict-like row, convert to regular dict
                result = {k: v for k, v in row.items()}

                # Convert hstore to dict
                if 'tags' in result and result['tags']:
                    try:
                        result['tags'] = dict(result['tags'])
                    except (TypeError, ValueError) as e:
                        logger.warning(f"Could not convert tags to dict for {table_name}: {e}")
                        result['tags'] = str(result['tags'])  # Fallback to string

                # Get address for buildings
                if table_name == 'osm_building_polygon':
                    cur.execute("""
                        SELECT housenumber, street, block_number
                        FROM osm_housenumber_point
                        WHERE ST_Intersects(
                            geometry,
                            (SELECT geometry FROM osm_building_polygon WHERE osm_id = %s LIMIT 1)
                        )
                        LIMIT 1
                    """, (result['osm_id'],))
                    address_row = cur.fetchone()
                    if address_row:
                        result['address'] = dict(address_row)

                all_results.append(result)

        cur.close()
        conn.close()

        return {
            'lat': lat,
            'lon': lon,
            'radius': radius,
            'found': len(all_results),
            'features': all_results
        }

    except psycopg2.Error as e:
        logger.error(f"Database error fetching features at ({lat}, {lon}): {e}")
        raise HttpError(503, "Database temporarily unavailable")
    except Exception as e:
        logger.error(f"Unexpected error fetching features at ({lat}, {lon}): {e}")
        raise HttpError(500, "Internal server error")


@router.get("/osm/nearest-stops", auth=None)
@ratelimit(group='geo:osm_nearest_stops', key='ip', rate='60/m')
def get_nearest_transit_stops(
    request,
    lat: float,
    lon: float,
    radius: Optional[int] = None
):
    """
    Find nearest public transport stops (bus, tram, train) within radius.
    Uses local OpenMapTiles database for fast queries.

    Parameters:
    - lat: Latitude (WGS84)
    - lon: Longitude (WGS84)
    - radius: Search radius in meters (default from settings: GEOCODING_RADIUS_M = 5km)
    """
    if radius is None:
        radius = config.GEOCODING_RADIUS_M
    import psycopg2
    from psycopg2.extras import RealDictCursor

    try:
        conn = psycopg2.connect(**OPENMAPTILES_DB)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Transport stop types
        stop_types = ('bus_stop', 'bus_station', 'tram_stop', 'station', 'train_station_entrance')

        query = """
            WITH search_point AS (
                SELECT ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 3857) AS geom
            )
            SELECT
                osm_id,
                name,
                subclass,
                tags,
                station,
                network,
                operator,
                ST_X(ST_Transform(geometry, 4326)) as lon,
                ST_Y(ST_Transform(geometry, 4326)) as lat,
                ST_Distance(geometry, search_point.geom) AS distance_meters
            FROM osm_poi_point, search_point
            WHERE
                subclass = ANY(%s)
                AND ST_DWithin(geometry, search_point.geom, %s)
            ORDER BY distance_meters ASC
            LIMIT 10
        """

        cur.execute(query, (lon, lat, list(stop_types), radius))
        rows = cur.fetchall()

        results = []
        for row in rows:
            result = dict(row)
            # Convert hstore tags to dict
            if result.get('tags'):
                try:
                    result['tags'] = dict(result['tags'])
                except (TypeError, ValueError):
                    result['tags'] = {}
            results.append(result)

        cur.close()
        conn.close()

        return {
            'lat': lat,
            'lon': lon,
            'radius': radius,
            'found': len(results),
            'stops': results
        }

    except psycopg2.Error as e:
        logger.error(f"Database error finding stops at ({lat}, {lon}): {e}")
        raise HttpError(503, "Database temporarily unavailable")
    except Exception as e:
        logger.error(f"Unexpected error finding stops: {e}")
        raise HttpError(500, "Internal server error")


@router.get("/osm/{osm_id}", auth=None)
@ratelimit(group='geo:osm_feature', key='ip', rate='60/m')
def get_osm_feature_details(request, osm_id: int, layer: Optional[str] = None):
    """
    Get full OSM feature details by osm_id.
    Returns all available attributes from OpenMapTiles database.

    Parameters:
    - osm_id: OpenStreetMap object ID
    - layer: Optional layer hint (building, poi, transportation, etc.)
    """
    import psycopg2
    from psycopg2.extras import RealDictCursor

    try:
        # Connect to OpenMapTiles database
        conn = psycopg2.connect(**OPENMAPTILES_DB)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Tables to search with their priority and column mappings
        search_tables = [
            # POI tables have tags (hstore)
            ('osm_poi_point', 'Point', True),
            ('osm_poi_polygon', 'Polygon', True),
            # Building table (no tags, but has specific fields)
            ('osm_building_polygon', 'Polygon', False),
            # Transportation
            ('osm_transportation_name_linestring', 'LineString', True),
            ('osm_highway_linestring', 'LineString', True),
            # Water features
            ('osm_water_polygon', 'Polygon', True),
            ('osm_waterway_linestring', 'LineString', True),
            # Place names
            ('osm_city_point', 'Point', True),
            ('osm_peak_point', 'Point', True),
        ]

        # Filter by layer hint if provided
        if layer:
            search_tables = [t for t in search_tables if layer.lower() in t[0].lower()]

        result = None
        found_in_table = None

        for table_name, geom_type, has_tags in search_tables:
            if has_tags:
                # Tables with hstore tags
                query = f"""
                    SELECT
                        osm_id,
                        '{table_name}' as source_table,
                        '{geom_type}' as geometry_type,
                        tags,
                        ST_AsGeoJSON(ST_Transform(geometry, 4326))::json as geometry
                    FROM {table_name}
                    WHERE osm_id = %s
                    LIMIT 1
                """
            else:
                # Building table without tags
                query = f"""
                    SELECT
                        osm_id,
                        '{table_name}' as source_table,
                        '{geom_type}' as geometry_type,
                        building,
                        buildingpart,
                        buildingheight,
                        buildingmin_height,
                        buildinglevels,
                        buildingmin_level,
                        height,
                        min_height,
                        levels,
                        min_level,
                        material,
                        colour,
                        ST_AsGeoJSON(ST_Transform(geometry, 4326))::json as geometry
                    FROM {table_name}
                    WHERE osm_id = %s
                    LIMIT 1
                """

            cur.execute(query, (osm_id,))
            row = cur.fetchone()

            if row:
                result = dict(row)
                found_in_table = table_name
                break

        if not result:
            cur.close()
            conn.close()
            raise HttpError(404, f"OSM feature {osm_id} not found")

        # Convert hstore tags to dict if present
        if 'tags' in result and result['tags']:
            result['tags'] = dict(result['tags'])

        # Try to get address information from housenumber table
        if found_in_table == 'osm_building_polygon':
            cur.execute("""
                SELECT housenumber, street, block_number
                FROM osm_housenumber_point
                WHERE ST_Intersects(
                    geometry,
                    (SELECT geometry FROM osm_building_polygon WHERE osm_id = %s LIMIT 1)
                )
                LIMIT 1
            """, (osm_id,))
            address_row = cur.fetchone()
            if address_row:
                result['address'] = dict(address_row)

        cur.close()
        conn.close()

        return {
            'osm_id': osm_id,
            'found': True,
            'source_table': found_in_table,
            'data': result
        }

    except psycopg2.Error as e:
        logger.error(f"Database error fetching OSM feature {osm_id}: {e}")
        raise HttpError(503, "Database temporarily unavailable")
    except Exception as e:
        logger.error(f"Unexpected error fetching OSM feature {osm_id}: {e}")
        raise HttpError(500, "Internal server error")
