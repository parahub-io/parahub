#!/bin/sh

./imposm import \
  -connection postgis://osm:OsmSecure2024@localhost:5436/gis \
  -mapping mapping-official.yaml \
  -read /opt/planet/planet-latest.osm.pbf \
  -cachedir ./cache \
  -diffdir ./diff \
  -write \
  -optimize \
  -deployproduction \
  -overwritecache \
  > imposm-final.log 2>&1 &

echo "Planet import finished successfully!"
echo "Import complete. Running VACUUM ANALYZE..."
#PGPASSWORD='OsmSecure2024' psql -h localhost -U osm -d gis -p 5436 -c 'VACUUM ANALYZE;'

exit
./imposm import -optimize -deployproduction \
    -connection postgis://osm:OsmSecure2024@localhost:5436/gis \
    -mapping mapping-official.yaml



