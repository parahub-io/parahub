/**
 * DGT orthophoto satellite basemap (Portugal Continental).
 *
 * Official aerial orthophotos published by Direção-Geral do Território under
 * CC BY 4.0. Used as an opt-in imagery basemap that fills in where our own
 * crowdsourced OpenSky tiles don't exist yet. PT-only for now (the DGT service
 * is continental Portugal); a lower-res global layer can slot beneath this later.
 *
 * The DGT WMTS is only published in the national grid (EPSG:3763), so a direct
 * XYZ template can't be used. Its WMS *does* offer EPSG:3857, so we drive it as
 * a MapLibre raster source via the `{bbox-epsg-3857}` GetMap token.
 *
 * We go through a SAME-ORIGIN nginx reverse-proxy (`/basemap/ortos2021`, see the
 * parahub.io site config) rather than hitting DGT directly: DGT sends no CORS
 * header, which would both fail MapLibre's fetch()-based raster load AND taint
 * the map canvas (breaking getCanvas().toDataURL() snapshots). The proxy also
 * caches 30d, so we stay off DGT's servers. `bounds` keeps requests inside PT.
 */

// PNG + transparent so nodata (ocean / uncovered gaps) falls through to the
// vector base instead of painting white boxes.
// `Ortos2021-RGB` = natural true-color child layer. The parent `Ortos2021`
// group renders the `-IRG` false-color variant (vegetation → red) — not what a
// basemap wants.
const DGT_WMS_TILE_URL =
  '/basemap/ortos2021' +
  '?service=WMS&version=1.3.0&request=GetMap&layers=Ortos2021-RGB&styles=' +
  '&format=image/png&transparent=true&crs=EPSG:3857&width=256&height=256' +
  '&bbox={bbox-epsg-3857}'

// Portugal Continental bounding box — restricts tile requests to the DGT coverage.
const PT_CONTINENTAL_BOUNDS: [number, number, number, number] = [-9.75, 36.85, -6.15, 42.20]

// Shown in the AttributionControl whenever this layer is visible (CC BY 4.0
// mandates naming DGT as the source).
const DGT_ATTRIBUTION =
  'Ortofotos © <a href="https://www.dgterritorio.gov.pt" target="_blank" rel="noopener">DGT</a> · ' +
  '<a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener">CC BY 4.0</a>'

const SOURCE_ID = 'satellite-dgt'
const LAYER_ID = 'satellite-dgt-layer'
// OpenSky raster sits directly above this, so our own higher-res tiles win.
const OPENSKY_LAYER_ID = 'opensky-latest-layer'

// Custom-overlay prefixes (mirror useMapOpenSky) — used to find the bottom of
// the overlay band when the OpenSky layer isn't present yet.
const OVERLAY_PREFIXES = [
  'highlight-', 'measure-', 'transit-', 'isochrone-', 'sun-', 'browse-',
  'iot-', 'mesh-', 'condo-', 'hub-', 'gov-', 'church-', 'opensky-',
  'trackers-', 'energy-cells-', 'poi-hover-',
]

export function useMapSatelliteLayer() {
  const satelliteEnabled = useLocalPref('satellite_enabled', false)

  function setupLayer(map: any) {
    if (!map) return

    if (map.getLayer(LAYER_ID)) map.removeLayer(LAYER_ID)
    if (map.getSource(SOURCE_ID)) map.removeSource(SOURCE_ID)

    map.addSource(SOURCE_ID, {
      type: 'raster',
      tiles: [DGT_WMS_TILE_URL],
      tileSize: 256,
      minzoom: 5,
      // DGT ortho native ~0.25 m/px ≈ z19–z20; MapLibre overzooms past this.
      maxzoom: 20,
      bounds: PT_CONTINENTAL_BOUNDS,
      attribution: DGT_ATTRIBUTION,
    })

    // Insert directly below the OpenSky raster (so OpenSky wins where it exists);
    // if OpenSky isn't set up yet, drop it at the bottom of the overlay band —
    // OpenSky, added later before the same band, still ends up on top.
    let beforeId: string | undefined
    if (map.getLayer(OPENSKY_LAYER_ID)) {
      beforeId = OPENSKY_LAYER_ID
    } else {
      beforeId = map.getStyle().layers.find((l: any) =>
        OVERLAY_PREFIXES.some(p => l.id.startsWith(p)) || l.id.endsWith('-hover') || l.id.endsWith('-active')
      )?.id
    }

    map.addLayer({
      id: LAYER_ID,
      type: 'raster',
      source: SOURCE_ID,
      minzoom: 5,
      maxzoom: 23,
      layout: { visibility: satelliteEnabled.value ? 'visible' : 'none' },
      paint: { 'raster-opacity': 1 },
    }, beforeId)
  }

  function toggleLayer() {
    satelliteEnabled.value = !satelliteEnabled.value
    const map = useMapStore().mapInstance
    if (map && map.getLayer(LAYER_ID)) {
      map.setLayoutProperty(LAYER_ID, 'visibility', satelliteEnabled.value ? 'visible' : 'none')
    }
  }

  return {
    satelliteEnabled,
    setupLayer,
    toggleLayer,
  }
}
