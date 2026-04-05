-- This patch adds waterway_label layer to openmaptiles() function
-- Execute this after running imposm import to enable waterway labels

-- The waterway_label layer uses osm_important_waterway_linestring table
-- which contains major rivers and streams that should have labels.

-- The layer is generated starting from zoom 10 using:
-- - z10: osm_important_waterway_linestring_gen_z10
-- - z11: osm_important_waterway_linestring_gen_z11  
-- - z12+: osm_important_waterway_linestring

-- This layer provides LineString features with 'name' and 'class' properties
-- that can be used with symbol layers with symbol-placement: "line"

-- To apply this patch, the full openmaptiles() function was recreated
-- See the function definition in martin-config.yaml or query:
-- SELECT pg_get_functiondef('openmaptiles'::regproc);
