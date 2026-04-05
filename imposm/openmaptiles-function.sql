-- OpenMapTiles MVT generation function
-- Simplified version using actual imposm3 column names

DROP FUNCTION IF EXISTS openmaptiles(integer, integer, integer);

CREATE OR REPLACE FUNCTION openmaptiles(z integer, x integer, y integer)
RETURNS bytea
LANGUAGE plpgsql
IMMUTABLE STRICT PARALLEL SAFE
AS $$
DECLARE
    result bytea;
    bbox geometry;
BEGIN
    bbox := ST_TileEnvelope(z, x, y);

    -- Generate MVT with multiple layers
    SELECT string_agg(layer_mvt, '') INTO result
    FROM (
        -- Water layer (z0+) - oceans + inland water with zoom-based generalization
        SELECT ST_AsMVT(q, 'water', 4096, 'geom') AS layer_mvt
        FROM (
            -- Ocean polygons (z0-z5: ocean only, no inland water to avoid overload)
            SELECT ST_AsMVTGeom(geom, bbox, 4096, 64) AS geom,
                   NULL::bigint as osm_id,
                   NULL::varchar as name,
                   NULL::boolean as intermittent
            FROM water_polygons
            WHERE z <= 5 AND geom && bbox

            UNION ALL

            -- Ocean + largest lakes (z6)
            SELECT ST_AsMVTGeom(geom, bbox, 4096, 64) AS geom,
                   NULL::bigint as osm_id,
                   NULL::varchar as name,
                   NULL::boolean as intermittent
            FROM water_polygons
            WHERE z = 6 AND geom && bbox

            UNION ALL

            SELECT ST_AsMVTGeom(geometry, bbox, 4096, 64) AS geom,
                   osm_id, name, is_intermittent as intermittent
            FROM osm_water_polygon_gen_z6
            WHERE z = 6 AND geometry && bbox

            UNION ALL

            -- Ocean + large lakes (z7)
            SELECT ST_AsMVTGeom(geom, bbox, 4096, 64) AS geom,
                   NULL::bigint as osm_id,
                   NULL::varchar as name,
                   NULL::boolean as intermittent
            FROM water_polygons
            WHERE z = 7 AND geom && bbox

            UNION ALL

            SELECT ST_AsMVTGeom(geometry, bbox, 4096, 64) AS geom,
                   osm_id, name, is_intermittent as intermittent
            FROM osm_water_polygon_gen_z7
            WHERE z = 7 AND geometry && bbox

            UNION ALL

            -- Ocean + generalized inland water (z8-z11) - use DETAILED polygons
            SELECT ST_AsMVTGeom(geom, bbox, 4096, 64) AS geom,
                   NULL::bigint as osm_id,
                   NULL::varchar as name,
                   NULL::boolean as intermittent
            FROM water_polygons_detailed
            WHERE z >= 8 AND z <= 11 AND geom && bbox

            UNION ALL

            SELECT ST_AsMVTGeom(geometry, bbox, 4096, 64) AS geom,
                   osm_id, name, is_intermittent as intermittent
            FROM osm_water_polygon_gen_z8
            WHERE z = 8 AND geometry && bbox

            UNION ALL

            SELECT ST_AsMVTGeom(geometry, bbox, 4096, 64) AS geom,
                   osm_id, name, is_intermittent as intermittent
            FROM osm_water_polygon_gen_z9
            WHERE z = 9 AND geometry && bbox

            UNION ALL

            SELECT ST_AsMVTGeom(geometry, bbox, 4096, 64) AS geom,
                   osm_id, name, is_intermittent as intermittent
            FROM osm_water_polygon_gen_z10
            WHERE z = 10 AND geometry && bbox

            UNION ALL

            SELECT ST_AsMVTGeom(geometry, bbox, 4096, 64) AS geom,
                   osm_id, name, is_intermittent as intermittent
            FROM osm_water_polygon_gen_z11
            WHERE z = 11 AND geometry && bbox

            UNION ALL

            -- Ocean + full detail inland water (z12+) - use DETAILED polygons
            SELECT ST_AsMVTGeom(geom, bbox, 4096, 64) AS geom,
                   NULL::bigint as osm_id,
                   NULL::varchar as name,
                   NULL::boolean as intermittent
            FROM water_polygons_detailed
            WHERE z >= 12 AND geom && bbox

            UNION ALL

            SELECT ST_AsMVTGeom(geometry, bbox, 4096, 64) AS geom,
                   osm_id, name, is_intermittent as intermittent
            FROM osm_water_polygon
            WHERE z >= 12 AND geometry && bbox
        ) q
        WHERE q.geom IS NOT NULL

        UNION ALL

        -- Waterway layer (z8+)
        SELECT ST_AsMVT(q, 'waterway', 4096, 'geom') AS layer_mvt
        FROM (
            SELECT ST_AsMVTGeom(geometry, bbox, 4096, 64) AS geom,
                   osm_id, name, waterway as class, is_intermittent as intermittent
            FROM osm_waterway_linestring
            WHERE z >= 8 AND geometry && bbox
        ) q
        WHERE q.geom IS NOT NULL

        UNION ALL

        -- Landcover layer (z7+)
        SELECT ST_AsMVT(q, 'landcover', 4096, 'geom') AS layer_mvt
        FROM (
            SELECT ST_AsMVTGeom(geometry, bbox, 4096, 64) AS geom,
                   osm_id, subclass as class
            FROM osm_landcover_polygon
            WHERE z >= 7 AND geometry && bbox
        ) q
        WHERE q.geom IS NOT NULL

        UNION ALL

        -- Landuse layer (z4+) with zoom-based generalization
        SELECT ST_AsMVT(q, 'landuse', 4096, 'geom') AS layer_mvt
        FROM (
            SELECT ST_AsMVTGeom(geometry, bbox, 4096, 64) AS geom,
                   osm_id, landuse as class
            FROM osm_landuse_polygon_gen_z6
            WHERE z >= 4 AND z <= 6 AND geometry && bbox

            UNION ALL

            SELECT ST_AsMVTGeom(geometry, bbox, 4096, 64) AS geom,
                   osm_id, landuse as class
            FROM osm_landuse_polygon_gen_z7
            WHERE z = 7 AND geometry && bbox

            UNION ALL

            SELECT ST_AsMVTGeom(geometry, bbox, 4096, 64) AS geom,
                   osm_id, landuse as class
            FROM osm_landuse_polygon_gen_z8
            WHERE z = 8 AND geometry && bbox

            UNION ALL

            SELECT ST_AsMVTGeom(geometry, bbox, 4096, 64) AS geom,
                   osm_id, landuse as class
            FROM osm_landuse_polygon_gen_z9
            WHERE z = 9 AND geometry && bbox

            UNION ALL

            SELECT ST_AsMVTGeom(geometry, bbox, 4096, 64) AS geom,
                   osm_id, landuse as class
            FROM osm_landuse_polygon_gen_z10
            WHERE z = 10 AND geometry && bbox

            UNION ALL

            SELECT ST_AsMVTGeom(geometry, bbox, 4096, 64) AS geom,
                   osm_id, landuse as class
            FROM osm_landuse_polygon_gen_z11
            WHERE z = 11 AND geometry && bbox

            UNION ALL

            SELECT ST_AsMVTGeom(geometry, bbox, 4096, 64) AS geom,
                   osm_id, landuse as class
            FROM osm_landuse_polygon_gen_z12
            WHERE z = 12 AND geometry && bbox

            UNION ALL

            SELECT ST_AsMVTGeom(geometry, bbox, 4096, 64) AS geom,
                   osm_id, landuse as class
            FROM osm_landuse_polygon_gen_z13
            WHERE z = 13 AND geometry && bbox

            UNION ALL

            SELECT ST_AsMVTGeom(geometry, bbox, 4096, 64) AS geom,
                   osm_id, landuse as class
            FROM osm_landuse_polygon
            WHERE z >= 14 AND geometry && bbox
        ) q
        WHERE q.geom IS NOT NULL

        UNION ALL

        -- Park layer (z8+) - too detailed for z4-z7
        SELECT ST_AsMVT(q, 'park', 4096, 'geom') AS layer_mvt
        FROM (
            SELECT ST_AsMVTGeom(geometry, bbox, 4096, 64) AS geom,
                   osm_id, name
            FROM osm_park_polygon
            WHERE z >= 8 AND geometry && bbox
        ) q
        WHERE q.geom IS NOT NULL

        UNION ALL

        -- Building layer (z13+)
        SELECT ST_AsMVT(q, 'building', 4096, 'geom') AS layer_mvt
        FROM (
            SELECT ST_AsMVTGeom(geometry, bbox, 4096, 64) AS geom,
                   osm_id
            FROM osm_building_polygon
            WHERE z >= 13 AND geometry && bbox
        ) q
        WHERE q.geom IS NOT NULL

        UNION ALL

        -- Transportation layer (highways with zoom-based pre-merged tables)
        SELECT ST_AsMVT(q, 'transportation', 4096, 'geom') AS layer_mvt
        FROM (
            -- z4: use pre-merged z4 table
            SELECT ST_AsMVTGeom(geometry, bbox, 4096, 64) AS geom,
                   osm_id,
                   highway as class,
                   network,
                   is_bridge as brunnel,
                   expressway
            FROM osm_transportation_merge_linestring_gen_z4
            WHERE z = 4 AND geometry && bbox

            UNION ALL

            -- z5: use pre-merged z5 table
            SELECT ST_AsMVTGeom(geometry, bbox, 4096, 64) AS geom,
                   osm_id,
                   highway as class,
                   network,
                   is_bridge as brunnel,
                   expressway
            FROM osm_transportation_merge_linestring_gen_z5
            WHERE z = 5 AND geometry && bbox

            UNION ALL

            -- z6: use pre-merged z6 table
            SELECT ST_AsMVTGeom(geometry, bbox, 4096, 64) AS geom,
                   osm_id,
                   highway as class,
                   network,
                   is_bridge as brunnel,
                   expressway
            FROM osm_transportation_merge_linestring_gen_z6
            WHERE z = 6 AND geometry && bbox

            UNION ALL

            -- z7: use pre-merged z7 table
            SELECT ST_AsMVTGeom(geometry, bbox, 4096, 64) AS geom,
                   osm_id,
                   highway as class,
                   network,
                   is_bridge as brunnel,
                   expressway
            FROM osm_transportation_merge_linestring_gen_z7
            WHERE z = 7 AND geometry && bbox

            UNION ALL

            -- z8: use pre-merged z8 table
            SELECT ST_AsMVTGeom(geometry, bbox, 4096, 64) AS geom,
                   osm_id,
                   highway as class,
                   network,
                   is_bridge as brunnel,
                   expressway
            FROM osm_transportation_merge_linestring_gen_z8
            WHERE z = 8 AND geometry && bbox

            UNION ALL

            -- z9: use pre-merged z9 table
            SELECT ST_AsMVTGeom(geometry, bbox, 4096, 64) AS geom,
                   osm_id,
                   highway as class,
                   network,
                   is_bridge as brunnel,
                   expressway
            FROM osm_transportation_merge_linestring_gen_z9
            WHERE z = 9 AND geometry && bbox

            UNION ALL

            -- z10: use pre-merged z10 table
            SELECT ST_AsMVTGeom(geometry, bbox, 4096, 64) AS geom,
                   osm_id,
                   highway as class,
                   network,
                   is_bridge as brunnel,
                   expressway
            FROM osm_transportation_merge_linestring_gen_z10
            WHERE z = 10 AND geometry && bbox

            UNION ALL

            -- z11: use pre-merged z11 table
            SELECT ST_AsMVTGeom(geometry, bbox, 4096, 64) AS geom,
                   osm_id,
                   highway as class,
                   network,
                   is_bridge as brunnel,
                   expressway
            FROM osm_transportation_merge_linestring_gen_z11
            WHERE z = 11 AND geometry && bbox

            UNION ALL

            -- z12+: all roads from base table
            SELECT ST_AsMVTGeom(geometry, bbox, 4096, 64) AS geom,
                   osm_id,
                   highway as class,
                   NULL::varchar as network,
                   is_bridge as brunnel,
                   NULL::boolean as expressway
            FROM osm_highway_linestring
            WHERE z >= 12 AND geometry && bbox
        ) q
        WHERE q.geom IS NOT NULL

        UNION ALL

        -- Boundary layer (z0+) - simplified, no admin_level in imposm3 schema
        SELECT ST_AsMVT(q, 'boundary', 4096, 'geom') AS layer_mvt
        FROM (
            SELECT ST_AsMVTGeom(geometry, bbox, 4096, 64) AS geom,
                   osm_id, name, boundary
            FROM osm_boundary_polygon
            WHERE geometry && bbox
        ) q
        WHERE q.geom IS NOT NULL

        UNION ALL

        -- Place layer (z4+) with zoom-based filtering
        SELECT ST_AsMVT(q, 'place', 4096, 'geom') AS layer_mvt
        FROM (
            SELECT ST_AsMVTGeom(geometry, bbox, 4096, 64) AS geom,
                   osm_id,
                   name,
                   COALESCE(name_en, name) as "name:latin",
                   CASE WHEN name != COALESCE(name_en, name) THEN name END as "name:nonlatin",
                   name_en as "name:en",
                   name_de as "name:de",
                   place as class,
                   population
            FROM osm_city_point
            WHERE geometry && bbox
              AND (
                -- z4-z7: only major cities (city, town)
                (z >= 4 AND z <= 7 AND place IN ('city', 'town'))
                -- z8+: all places
                OR z >= 8
              )
        ) q
        WHERE q.geom IS NOT NULL

        UNION ALL

        -- POI layer (z12+)
        SELECT ST_AsMVT(q, 'poi', 4096, 'geom') AS layer_mvt
        FROM (
            SELECT ST_AsMVTGeom(geometry, bbox, 4096, 64) AS geom,
                   osm_id,
                   name,
                   COALESCE(name_en, name) as "name:latin",
                   CASE WHEN name != COALESCE(name_en, name) THEN name END as "name:nonlatin",
                   name_en as "name:en",
                   name_de as "name:de",
                   subclass
            FROM osm_poi_point
            WHERE z >= 12 AND geometry && bbox
        ) q
        WHERE q.geom IS NOT NULL

        UNION ALL

        -- Aerodrome label layer (z10+)
        SELECT ST_AsMVT(q, 'aerodrome_label', 4096, 'geom') AS layer_mvt
        FROM (
            SELECT ST_AsMVTGeom(geometry, bbox, 4096, 64) AS geom,
                   osm_id, name, iata, icao
            FROM osm_aerodrome_label_point
            WHERE z >= 10 AND geometry && bbox
        ) q
        WHERE q.geom IS NOT NULL

        UNION ALL

        -- Aeroway layer (z10+)
        SELECT ST_AsMVT(q, 'aeroway', 4096, 'geom') AS layer_mvt
        FROM (
            SELECT ST_AsMVTGeom(geometry, bbox, 4096, 64) AS geom,
                   osm_id, aeroway as class
            FROM osm_aeroway_polygon
            WHERE z >= 10 AND geometry && bbox
        ) q
        WHERE q.geom IS NOT NULL

        UNION ALL

        -- Transportation name layer (z12+) - street names
        SELECT ST_AsMVT(q, 'transportation_name', 4096, 'geom') AS layer_mvt
        FROM (
            SELECT ST_AsMVTGeom(geometry, bbox, 4096, 64) AS geom,
                   osm_id,
                   name,
                   COALESCE(name_en, name) as "name:latin",
                   CASE WHEN name != COALESCE(name_en, name) THEN name END as "name:nonlatin",
                   name_en as "name:en",
                   name_de as "name:de",
                   ref,
                   highway as class
            FROM osm_highway_linestring
            WHERE z >= 12 AND geometry && bbox AND name IS NOT NULL
        ) q
        WHERE q.geom IS NOT NULL

        UNION ALL

        -- Housenumber layer (z14+) - house numbers
        SELECT ST_AsMVT(q, 'housenumber', 4096, 'geom') AS layer_mvt
        FROM (
            SELECT ST_AsMVTGeom(geometry, bbox, 4096, 256) AS geom,
                   osm_id,
                   housenumber
            FROM osm_housenumber_point
            WHERE z >= 14 AND geometry && bbox
        ) q
        WHERE q.geom IS NOT NULL
    ) layers;

    RETURN result;
END;
$$;

COMMENT ON FUNCTION openmaptiles(integer, integer, integer) IS
'OpenMapTiles-compatible MVT generation using imposm3 column names';
