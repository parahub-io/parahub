-- PostgreSQL function to create composite OpenMapTiles MVT
-- This function combines all OpenMapTiles layers into a single tile
-- Martin will automatically discover and serve this as /openmaptiles/{z}/{x}/{y}

CREATE OR REPLACE FUNCTION public.openmaptiles(z integer, x integer, y integer)
RETURNS bytea AS $$
DECLARE
    result bytea;
    bbox geometry;
BEGIN
    -- Calculate tile bbox
    bbox := ST_TileEnvelope(z, x, y);

    -- Combine all layers into single MVT
    SELECT ST_AsMVT(layers, 'combined') INTO result
    FROM (
        -- Water
        SELECT ST_AsMVTGeom(geometry, bbox) AS geom,
               'water' as class, name, osm_id
        FROM osm_water_polygon
        WHERE geometry && bbox AND z >= 0

        UNION ALL

        -- Waterways
        SELECT ST_AsMVTGeom(geometry, bbox) AS geom,
               'waterway' as class, name, waterway as subclass, osm_id
        FROM osm_waterway_linestring
        WHERE geometry && bbox AND z >= 7

        UNION ALL

        -- Landcover
        SELECT ST_AsMVTGeom(geometry, bbox) AS geom,
               'landcover' as class, landcover as subclass, osm_id
        FROM osm_landcover_polygon
        WHERE geometry && bbox AND z >= 4

        UNION ALL

        -- Landuse
        SELECT ST_AsMVTGeom(geometry, bbox) AS geom,
               'landuse' as class, landuse as subclass, osm_id
        FROM osm_landuse_polygon
        WHERE geometry && bbox AND z >= 7

        UNION ALL

        -- Highways (transportation)
        SELECT ST_AsMVTGeom(geometry, bbox) AS geom,
               'transportation' as class, highway as subclass, name, osm_id
        FROM osm_highway_linestring
        WHERE geometry && bbox AND z >= 4

        UNION ALL

        -- Buildings
        SELECT ST_AsMVTGeom(geometry, bbox) AS geom,
               'building' as class, osm_id
        FROM osm_building_polygon
        WHERE geometry && bbox AND z >= 13

        UNION ALL

        -- POIs
        SELECT ST_AsMVTGeom(geometry, bbox) AS geom,
               'poi' as class, name, subclass, osm_id
        FROM osm_poi_point
        WHERE geometry && bbox AND z >= 12

        UNION ALL

        -- Places (cities, towns)
        SELECT ST_AsMVTGeom(geometry, bbox) AS geom,
               'place' as class, name, place, osm_id
        FROM osm_city_point
        WHERE geometry && bbox AND z >= 4

        UNION ALL

        -- Boundaries
        SELECT ST_AsMVTGeom(geometry, bbox) AS geom,
               'boundary' as class, admin_level, osm_id
        FROM osm_boundary_polygon
        WHERE geometry && bbox AND z >= 0

    ) AS layers;

    RETURN result;
END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE;

-- Create index on geometry columns if not exists (should already exist from imposm3)
-- These are just to ensure optimal performance

COMMENT ON FUNCTION public.openmaptiles(integer, integer, integer)
IS 'Composite OpenMapTiles MVT function combining all layers. Serves as /openmaptiles/{z}/{x}/{y}';
