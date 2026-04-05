# Parahub Sprite Build Scripts

## Current Sprite: 258 colored icons

**Location**: `/opt/parahub/frontend/public/sprites/parahub`

**Composition**:
- 244 icons from OSM Liberty (base, colored)
- 44 icons from Maki v8 (colorized to OSM Liberty palette)
- 5 icons from Lucide (railway, recycling, theme_park, ice_rink, bollard)

## OSM Liberty Color Palette

- **Blue #5d60be** (Shopping/Leisure): shop, furniture, art_gallery, music, theme_park
- **Orange #d97200** (Eating): bakery, cafe, restaurant, grocery, beer
- **Green #76a723** (Sport/Nature): sports_centre, athletics, pitch, soccer, park, recycling, cycling, bicycle_parking
- **Light Blue #4898ff** (Transport): bus, car, parking, fuel, ferry_terminal, swimming_pool, atm, railway, ice_rink
- **Red #ba3827** (Health): hospital, dentist, pharmacy
- **Brown #725a50** (Infrastructure): gate, lift_gate, bollard, office, police, post, town_hall, school, entrance, waste_basket

## Build Process

1. Clone sources:
```bash
cd /tmp/sprite_build
git clone https://github.com/maputnik/osm-liberty.git
git clone https://github.com/mapbox/maki.git
```

2. Copy base SVGs:
```bash
mkdir -p /tmp/parahub_sprite/icons
cp -r /tmp/sprite_build/osm-liberty/svgs/svgs_not_in_iconset/*.svg /tmp/parahub_sprite/icons/
cp -r /tmp/sprite_build/osm-liberty/svgs/svgs_iconset/*.svg /tmp/parahub_sprite/icons/
```

3. Add missing icons from Maki (colorized):
```bash
# Use add_fill_color.sh to add fill="#color" to Maki SVGs
./add_fill_color.sh /path/to/icon.svg "#725a50"
```

4. Add icons from Lucide:
```bash
# Use export_lucide.js to export from lucide-vue-next
node export_lucide.js
```

5. Generate sprites with spreet:
```bash
wget https://github.com/flother/spreet/releases/download/v0.11.0/spreet-x86_64-unknown-linux-musl.tar.gz
tar -xzf spreet-x86_64-unknown-linux-musl.tar.gz
./spreet --unique --minify-index-file --recursive ./icons/ ./sprites/parahub
./spreet --unique --minify-index-file --recursive --retina ./icons/ ./sprites/parahub@2x
```

6. Deploy:
```bash
cp sprites/* /opt/parahub/frontend/public/sprites/
```

## Licenses

- **OSM Liberty**: BSD-3-Clause
- **Maki**: CC0-1.0 (public domain)
- **Lucide**: MIT

All icons are open source and free to use commercially.
