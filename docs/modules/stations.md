# Environmental Stations

Your own weather station or air-quality sensor, on the community map. Readings are yours; publishing them is a choice you make per station.

## What a Station Measures

Whatever the hardware reports -- every metric is optional, and one station may cover weather, air quality, or both:

- **Weather**: temperature, humidity, pressure, wind speed, gusts and direction, rain rate and daily rain, solar radiation, UV index.
- **Air**: particulates (PM1, PM2.5, PM10), CO2, and volatile-compound and nitrogen-oxide indices.

Air quality is summarised as a standard AQI value with its colour band, computed from PM2.5.

## Getting Readings In

Two paths, depending on the device:

- **The device pushes** -- supported weather stations and air-quality monitors can post their measurements to a dedicated ingest address that Parahub gives you when you add the station. This works from anywhere on the internet.
- **Parahub polls over the mesh** -- if the sensor sits on the local network of a Parahub mesh node, readings are collected from it every few minutes with **no device configuration at all**: no account on a vendor cloud, no ingest address to paste, nothing to set up on the sensor.

Ecowitt and AirGradient devices are supported directly; a generic option exists for anything else.

## On the Map

Public stations appear on the map's Environment layer as a hexagon coloured by air quality, with a live instrument readout floating beside it -- AQI and category, temperature, PM2.5, CO2, wind, UV, humidity, depending on what the station measures. A station that reports wind direction also wears a compass ring with a pointer at the wind's origin, which keeps pointing the right way when you rotate the map.

Values update **live**, without reloading. A station that has gone quiet for a while dims and is marked stale rather than silently showing old numbers.

Devices standing within a few metres of each other are drawn as one tidy cluster instead of overlapping pins.

## Your Stations

Each station gets a card under Devices, showing its location on a map, its freshness, its latest values, and history charts over 24 hours or 7 days, with a raw CSV download for offline analysis. History is kept for a year.

You can rename a station inline, move it, and paste a link to the station's own public page on its vendor's site so anyone can cross-check your data against the source.

## Privacy

Two separate switches, deliberately:

- **Public** -- whether the station's readings appear on the community map at all.
- **Show owner** -- whether your profile is named next to it. Publishing readings at a point is not the same as announcing who lives there, so making a station public never reveals you by itself.

Private stations are visible only to you, and a request for someone else's private station is answered exactly like a request for a station that does not exist.

## Technical Details

- **Models**: `iot/models.py` -- EnvStation (owner, optional property, location, source, visibility flags, latest-reading snapshot), EnvReading (TimescaleDB hypertable, one year retention, all metrics nullable)
- **Ingest**: `iot/ingest_views.py` (device push, no session and no auth header -- devices cannot send one), `iot/env_service.py` (unit normalisation and snapshot refresh), `iot/aqi.py` (US EPA PM2.5 AQI)
- **Poll bridge**: `iot/management/commands/poll_env_stations.py` -- reaches the sensor through the nearest mesh node, on a timer
- **API**: `iot/api/env.py` -- public map feed, owner CRUD, reading history, CSV export
- **Live updates**: `parahub/consumers/env.py` -- public WebSocket feed, one connection for the whole map
- **Frontend**: `composables/useMapEnvLiveWs.ts`, `components/map/MapPanelEnvStation.vue`, the Stations tab of `pages/iot/index.vue`
