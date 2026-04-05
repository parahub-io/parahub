-- Minimal osm2pgsql flex config for standard planet import
-- Creates standard tables compatible with Martin tile server

-- Define output tables
local tables = {}

tables.point = osm2pgsql.define_table{
    name = 'planet_osm_point',
    ids = { type = 'node', id_column = 'osm_id' },
    columns = {
        { column = 'name', type = 'text' },
        { column = 'tags', type = 'hstore' },
        { column = 'geom', type = 'point', projection = 3857 },
    }
}

tables.line = osm2pgsql.define_table{
    name = 'planet_osm_line',
    ids = { type = 'way', id_column = 'osm_id' },
    columns = {
        { column = 'name', type = 'text' },
        { column = 'tags', type = 'hstore' },
        { column = 'geom', type = 'linestring', projection = 3857 },
    }
}

tables.polygon = osm2pgsql.define_table{
    name = 'planet_osm_polygon',
    ids = { type = 'area', id_column = 'osm_id' },
    columns = {
        { column = 'name', type = 'text' },
        { column = 'tags', type = 'hstore' },
        { column = 'geom', type = 'geometry', projection = 3857 },
    }
}

tables.roads = osm2pgsql.define_table{
    name = 'planet_osm_roads',
    ids = { type = 'way', id_column = 'osm_id' },
    columns = {
        { column = 'name', type = 'text' },
        { column = 'tags', type = 'hstore' },
        { column = 'geom', type = 'linestring', projection = 3857 },
    }
}

-- Process nodes
function osm2pgsql.process_node(object)
    if object.tags.name or object.tags.place or object.tags.amenity then
        tables.point:insert({
            name = object.tags.name,
            tags = object.tags,
            geom = object:as_point()
        })
    end
end

-- Process ways
function osm2pgsql.process_way(object)
    local name = object.tags.name
    local tags = object.tags

    if object.is_closed and (tags.building or tags.landuse or tags.natural == 'water') then
        tables.polygon:insert({
            name = name,
            tags = tags,
            geom = object:as_polygon()
        })
    else
        tables.line:insert({
            name = name,
            tags = tags,
            geom = object:as_linestring()
        })

        if tags.highway then
            tables.roads:insert({
                name = name,
                tags = tags,
                geom = object:as_linestring()
            })
        end
    end
end

-- Process relations
function osm2pgsql.process_relation(object)
    if object.tags.type == 'multipolygon' or object.tags.type == 'boundary' then
        tables.polygon:insert({
            name = object.tags.name,
            tags = object.tags,
            geom = object:as_multipolygon()
        })
    end
end
