# Parahub Sprite Source SVG Files

This directory contains all 279 source SVG files used to generate the Parahub sprite.

## Composition

**244 icons from OSM Liberty** (BSD-3-Clause):
- Original colored icons from maputnik/osm-liberty
- Sources: `svgs_iconset/` and `svgs_not_in_iconset/`

**53 icons from Maki v8** (CC0 Public Domain):
- Colorized to match OSM Liberty palette
- Added `fill="color"` attribute to all `<path>` tags
- Sports, eating, shopping, transport, health, public service categories

**5 icons from Lucide** (MIT):
- railway (train-track), recycling (recycle), theme_park (roller-coaster)
- ice_rink (snowflake), bollard (construction)
- Converted from stroke to fill

**18 custom hand-drawn icons** (CC0):
- billiards, boxing, canoe, rowing, running, sailing, climbing, gymnastics
- judo, yoga, chess, escape_game, hackerspace, boules, shooting
- brownfield, multi, motorcycle_parking
- Simple geometric shapes, colored by category

## Rebuild Sprite

To regenerate sprite after modifying SVGs:

```bash
cd /opt/parahub/frontend/public/sprites/sources

# Download spreet if needed
wget https://github.com/flother/spreet/releases/download/v0.11.0/spreet-x86_64-unknown-linux-musl.tar.gz
tar -xzf spreet-x86_64-unknown-linux-musl.tar.gz

# Generate sprites
./spreet --unique --minify-index-file --recursive . ../parahub
./spreet --unique --minify-index-file --recursive --retina . ../parahub@2x

# Clean up
rm spreet spreet-x86_64-unknown-linux-musl.tar.gz

# Rebuild frontend
/opt/parahub/0restart
```

## Color Palette

Use these colors when adding new icons:

- `#5d60be` - Shopping/Leisure (shop, office, art_gallery, music, chess, hackerspace)
- `#d97200` - Eating (bakery, cafe, restaurant, grocery, beer)
- `#76a723` - Sport/Nature (all sports, park, recycling)
- `#4898ff` - Transport (bus, car, parking, ferry, atm, railway)
- `#ba3827` - Health (hospital, dentist, pharmacy)
- `#725a50` - Infrastructure (gate, bollard, police, post, brownfield)

## Licenses

All icons are open source and commercially usable:
- OSM Liberty: BSD-3-Clause
- Maki: CC0-1.0 (Public Domain)
- Lucide: MIT
- Custom icons: CC0-1.0 (Public Domain)
