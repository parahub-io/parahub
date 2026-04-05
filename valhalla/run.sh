#!/bin/bash
set -eo pipefail

CONFIG=/data/valhalla.json
TILE_DIR=/data/valhalla_tiles
PBF=/data/planet-latest.osm.pbf
ADMIN_DB=/data/admin_data/admins.sqlite
TZ_DB=/data/timezone_data/timezones.sqlite
ELEVATION_DIR=/data/elevation_data
THREADS=${VALHALLA_THREADS:-8}

echo "=== Valhalla $(valhalla_build_tiles --version 2>&1 || echo 'unknown') ==="
echo "Threads: $THREADS"

# Generate config if missing
if [ ! -f "$CONFIG" ]; then
  echo "Generating config..."
  valhalla_build_config \
    --mjolnir-tile-dir "$TILE_DIR" \
    --mjolnir-admin "$ADMIN_DB" \
    --mjolnir-timezone "$TZ_DB" \
    --mjolnir-concurrency "$THREADS" \
    --additional-data-elevation "$ELEVATION_DIR" \
    > "$CONFIG"
  echo "Config generated"
fi

# Remove stale transit references from config (transit now handled by MOTIS)
if [ -f "$CONFIG" ]; then
  sed -i 's|"transit_dir":.*||; s|"transit_feeds_dir":.*||' "$CONFIG" 2>/dev/null || true
fi

# Build admin DB if missing
if [ ! -f "$ADMIN_DB" ]; then
  echo "=== Building admin DB ==="
  mkdir -p "$(dirname $ADMIN_DB)"
  valhalla_build_admins -c "$CONFIG" "$PBF"
fi

# Build timezone DB if missing
if [ ! -f "$TZ_DB" ]; then
  echo "=== Building timezone DB ==="
  mkdir -p "$(dirname $TZ_DB)"
  valhalla_build_timezones > "$TZ_DB"
fi

# Build routing tiles if missing
if [ ! -d "$TILE_DIR" ] || [ -z "$(find $TILE_DIR -name '*.gph' 2>/dev/null | head -1)" ]; then
  echo "=== Building routing tiles ==="
  mkdir -p "$TILE_DIR"
  valhalla_build_tiles -c "$CONFIG" -j "$THREADS" "$PBF"
  echo "Routing tiles built"
else
  echo "Routing tiles already exist, skipping"
fi

echo "=== Starting Valhalla server ==="
exec valhalla_service "$CONFIG" "$THREADS"
