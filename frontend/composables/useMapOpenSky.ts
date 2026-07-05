/**
 * OpenSky aerial imagery tiles + tile grid mission planning + KMZ download.
 *
 * Grid: standard Web Mercator tiles (Z17, same as OSM/Google).
 * User hovers → tile highlights, click → download 5 KMZ flight plans
 * (1_2D nadir + 2_3D-N + 3_3D-E + 4_3D-S + 5_3D-W cardinal obliques).
 * Pilot picks their own flight budget (1/3/5 batteries) per tile.
 */

import { ref, computed } from 'vue'
import type { Ref } from 'vue'

const TILE_ZOOM = 17         // ~305×240m per tile at mid-latitudes
const GRID_MIN_ZOOM = 12     // Don't render grid below this zoom

// Crowdsourced aerial imagery is published under CC BY-SA 4.0. Shown in the
// map AttributionControl whenever the OpenSky raster layer is visible.
const OPENSKY_ATTRIBUTION = 'Aerial imagery © Parahub pilots · <a href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" rel="noopener">CC BY-SA 4.0</a>'

// === Standard slippy map tile math (pure integer, no cos tricks) ===

function lng2tile(lng: number, z: number): number {
  return Math.floor((lng + 180) / 360 * Math.pow(2, z))
}

function lat2tile(lat: number, z: number): number {
  const latRad = lat * Math.PI / 180
  return Math.floor((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2 * Math.pow(2, z))
}

function tile2lng(x: number, z: number): number {
  return x / Math.pow(2, z) * 360 - 180
}

function tile2lat(y: number, z: number): number {
  const n = Math.PI - 2 * Math.PI * y / Math.pow(2, z)
  return 180 / Math.PI * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n)))
}

// Flight budget estimate — matches backend calculate_tile_stats().
// Z17 nadir-only flight at the equator: ~19 min (measured at true 80/80 spacing —
// line spacing 26.6m cross-track). Tiles shrink with cos(lat), so actual time scales
// down roughly linearly. NS/EW lawnmower are nearly symmetric for square-ish tiles,
// so we use a single per-mission nadir time.
//
// Oblique missions use 70% overlap (vs 80% nadir) — ~1.5× wider line spacing means
// ~32% less flight time per oblique. Measured ratio across latitudes: ~0.68.
//
// Rough client-side estimate only — authoritative value comes from backend preview endpoint.
const NADIR_TIME_MIN_EQUATOR = 19
const OBLIQUE_TIME_FRACTION = 0.68

function estimateBudget(lat: number) {
  const scale = Math.max(0.3, Math.cos(lat * Math.PI / 180))
  const nadir = NADIR_TIME_MIN_EQUATOR * scale
  const oblique = nadir * OBLIQUE_TIME_FRACTION
  return {
    battery1: Math.round(nadir),
    battery3: Math.round(nadir + 2 * oblique),
    battery5: Math.round(nadir + 4 * oblique),
  }
}

export function useMapOpenSky(currentMissionFilter: Ref<string | undefined>) {
  const authStore = useAuthStore()
  const mapStore = useMapStore()

  const openSkyEnabled = useLocalPref('opensky_enabled', false)
  const openSkyMode = useLocalPref('opensky_mode', false)
  const missionGenerating = ref(false)
  const tileGridMode = ref(false)

  // Budget estimate for the currently hovered tile, shown in an info card
  // in mission planning mode. Null when nothing hovered / grid mode off.
  const hoveredTileBudget = ref<{ battery1: number; battery3: number; battery5: number; x: number; y: number } | null>(null)

  // OpenSky missions from API
  const openSkyMissions = ref<Array<{
    id: string
    bounds: [number, number, number, number]
    minzoom: number
    maxzoom: number
  }>>([])

  const loadOpenSkyMissions = async () => {
    try {
      const response = await $fetch<{ missions: typeof openSkyMissions.value }>('/api/v1/geo/opensky/published-bounds/')
      openSkyMissions.value = response.missions
    } catch (error) {
      console.warn('[OpenSky] Failed to load missions:', error)
      openSkyMissions.value = [{
        id: 'podame',
        bounds: [-8.379033, 42.024431, -8.375944, 42.026092],
        minzoom: 11,
        maxzoom: 22
      }]
    }
  }

  // ======== Tile Layers ========

  async function setupLayers(map: any, missionId?: string) {
    if (openSkyMissions.value.length === 0) {
      await loadOpenSkyMissions()
    }

    const unifiedSourceId = 'opensky-latest'
    const unifiedLayerId = 'opensky-latest-layer'

    const tileUrl = missionId
      ? `/api/v1/geo/opensky/tiles/{z}/{x}/{y}.webp?mission_id=${missionId}`
      : '/api/v1/geo/opensky/tiles/{z}/{x}/{y}.webp'

    if (map.getLayer(unifiedLayerId)) map.removeLayer(unifiedLayerId)
    if (map.getSource(unifiedSourceId)) map.removeSource(unifiedSourceId)

    const missionBounds = missionId
      ? openSkyMissions.value.find(m => m.id === missionId)?.bounds
      : undefined

    map.addSource(unifiedSourceId, {
      type: 'raster',
      tiles: [tileUrl],
      tileSize: 256,
      minzoom: 11,
      // Pyramid ends at z22 (see published-bounds); 23 here made every pan at
      // max zoom fire guaranteed-404 volleys through nginx→WireGuard→skystore.
      // MapLibre overzooms z22 tiles for display beyond.
      maxzoom: 22,
      attribution: OPENSKY_ATTRIBUTION,
      ...(missionBounds ? { bounds: missionBounds } : {})
    })

    const shouldBeVisible = missionId ? true : openSkyEnabled.value

    // Place OpenSky raster below ALL custom overlays so interactive layers
    // (measure ruler, transit, isochrone, IoT, mesh, etc.) stay visible on top.
    const overlayPrefixes = [
      'highlight-', 'measure-', 'transit-', 'isochrone-', 'sun-', 'browse-',
      'iot-', 'mesh-', 'condo-', 'hub-', 'gov-', 'church-',
      'trackers-', 'energy-cells-', 'poi-hover-',
    ]
    // -hover/-active suffixes: building/road feature-state highlight layers (useMapHighlight)
    const beforeId = map.getStyle().layers.find((l: any) =>
      overlayPrefixes.some(p => l.id.startsWith(p)) || l.id.endsWith('-hover') || l.id.endsWith('-active')
    )?.id

    map.addLayer({
      id: unifiedLayerId,
      type: 'raster',
      source: unifiedSourceId,
      minzoom: 11,
      maxzoom: 23,
      layout: { visibility: shouldBeVisible ? 'visible' : 'none' },
      paint: { 'raster-opacity': 1 }
    }, beforeId)

    if (missionId && !openSkyEnabled.value) {
      openSkyEnabled.value = true
    }

    openSkyMissions.value.forEach(mission => {
      const sourceId = `opensky-${mission.id}`
      if (!map.getSource(sourceId)) {
        map.addSource(sourceId, {
          type: 'raster',
          tiles: [`/api/v1/geo/opensky/tiles/{z}/{x}/{y}.webp`],
          tileSize: 256,
          bounds: mission.bounds,
          minzoom: mission.minzoom,
          maxzoom: mission.maxzoom,
          attribution: OPENSKY_ATTRIBUTION
        })
      }
    })
  }

  function toggleLayer() {
    openSkyEnabled.value = !openSkyEnabled.value
    const map = mapStore.mapInstance
    if (map) {
      const unifiedLayerId = 'opensky-latest-layer'
      if (map.getLayer(unifiedLayerId)) {
        map.setLayoutProperty(unifiedLayerId, 'visibility', openSkyEnabled.value ? 'visible' : 'none')
      }
    }
  }

  // ======== Tile Grid Mode ========

  let _gridHandlers: { mousemove: any, click: any, moveend: any } | null = null
  let _hoveredTileX: number | null = null
  let _hoveredTileY: number | null = null
  let _coveredTiles: Map<string, { count: number, dates: string[] }> | null = null

  /** Generate GeoJSON rectangles for all Z17 tiles in viewport */
  function _generateViewportTiles(map: any) {
    const zoom = map.getZoom()
    if (zoom < GRID_MIN_ZOOM) {
      return { type: 'FeatureCollection' as const, features: [] as any[] }
    }

    const bounds = map.getBounds()
    const xMin = lng2tile(bounds.getWest(), TILE_ZOOM)
    const xMax = lng2tile(bounds.getEast(), TILE_ZOOM)
    const yMin = lat2tile(bounds.getNorth(), TILE_ZOOM)  // north = smaller y in slippy map
    const yMax = lat2tile(bounds.getSouth(), TILE_ZOOM)

    const features: any[] = []
    for (let x = xMin; x <= xMax; x++) {
      for (let y = yMin; y <= yMax; y++) {
        const w = tile2lng(x, TILE_ZOOM)
        const e = tile2lng(x + 1, TILE_ZOOM)
        const n = tile2lat(y, TILE_ZOOM)
        const s = tile2lat(y + 1, TILE_ZOOM)
        features.push({
          type: 'Feature' as const,
          properties: { x, y },
          geometry: {
            type: 'Polygon' as const,
            coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]]
          }
        })
        // Separate Point at the tile centre for the coordinate label. A point
        // lands in exactly one MapLibre internal tile, so the symbol renders once;
        // a centroid-on-polygon label gets duplicated wherever the polygon is split.
        // Covered tiles also carry a `dateLabel` — the survey date(s): a single
        // mission shows just its date, several show up to 3 most-recent dates plus
        // the total count in parens (e.g. "2026-06-01 / 2026-06-20 (2)").
        const cov = _coveredTiles?.get(`${x}:${y}`)
        const labelProps: any = { x, y, label: true }
        if (cov && cov.dates.length) {
          labelProps.dateLabel = cov.count > 1
            ? `${cov.dates.join(' / ')} (${cov.count})`
            : cov.dates[0]
        }
        features.push({
          type: 'Feature' as const,
          properties: labelProps,
          geometry: {
            type: 'Point' as const,
            coordinates: [(w + e) / 2, (n + s) / 2]
          }
        })
      }
    }

    return { type: 'FeatureCollection' as const, features }
  }

  function _generateHighlight(x: number, y: number) {
    const w = tile2lng(x, TILE_ZOOM)
    const e = tile2lng(x + 1, TILE_ZOOM)
    const n = tile2lat(y, TILE_ZOOM)
    const s = tile2lat(y + 1, TILE_ZOOM)
    return {
      type: 'FeatureCollection' as const,
      features: [{
        type: 'Feature' as const,
        properties: {},
        geometry: {
          type: 'Polygon' as const,
          coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]]
        }
      }]
    }
  }

  async function _loadCoveredTiles(map: any) {
    const bounds = map.getBounds()
    try {
      const data = await $fetch<{ tiles: Array<{ x: number, y: number, count: number, dates: string[] }> }>(
        '/api/v1/geo/opensky/covered-tiles/', {
          params: {
            west: bounds.getWest(),
            south: bounds.getSouth(),
            east: bounds.getEast(),
            north: bounds.getNorth(),
          },
        }
      )
      _coveredTiles = new Map(data.tiles.map(t => [`${t.x}:${t.y}`, { count: t.count, dates: t.dates }]))
    } catch (e) {
      console.warn('[OpenSky] Failed to load covered tiles:', e)
      _coveredTiles = new Map()
    }
  }

  function _generateCoveredTilesGeoJSON() {
    if (!_coveredTiles || _coveredTiles.size === 0) {
      return { type: 'FeatureCollection' as const, features: [] as any[] }
    }
    const features: any[] = []
    for (const key of _coveredTiles.keys()) {
      const [x, y] = key.split(':').map(Number)
      const w = tile2lng(x, TILE_ZOOM)
      const e = tile2lng(x + 1, TILE_ZOOM)
      const n = tile2lat(y, TILE_ZOOM)
      const s = tile2lat(y + 1, TILE_ZOOM)
      features.push({
        type: 'Feature' as const,
        properties: { x, y },
        geometry: {
          type: 'Polygon' as const,
          coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]]
        }
      })
    }
    return { type: 'FeatureCollection' as const, features }
  }

  async function _enableTileGrid(map: any) {
    map.addSource('opensky-tile-grid', {
      type: 'geojson',
      data: _generateViewportTiles(map)
    })
    map.addLayer({
      id: 'opensky-tile-grid-outline',
      type: 'line',
      source: 'opensky-tile-grid',
      filter: ['==', ['geometry-type'], 'Polygon'],
      paint: { 'line-color': '#6b7280', 'line-width': 0.5, 'line-opacity': 0.4 }
    })

    // Tile coordinate label at each tile center — x over y (same numbers as the
    // mission filename OpenSky_Z17_{x}_{y}, without the zoom). Only from z15: below
    // that the tiles are too small for 6-digit labels and they'd just collide-cull.
    map.addLayer({
      id: 'opensky-tile-grid-label',
      type: 'symbol',
      source: 'opensky-tile-grid',
      minzoom: 15,
      filter: ['==', ['geometry-type'], 'Point'],
      layout: {
        'text-field': ['concat', ['to-string', ['get', 'x']], '\n', ['to-string', ['get', 'y']]],
        'text-font': ['Noto Sans Regular'],
        'text-size': ['interpolate', ['linear'], ['zoom'], 15, 9, 17, 11, 19, 13],
        'text-line-height': 1.05,
        'text-allow-overlap': false,
      },
      paint: {
        'text-color': '#6b7280',
        'text-halo-color': 'rgba(255, 255, 255, 0.9)',
        'text-halo-width': 1.2,
      }
    })

    // Third label line — survey date(s) — only on covered tiles. A SEPARATE
    // symbol layer (not a third line folded into the x/y label) so the longer
    // multi-date string can collide-cull on its own without dragging the x/y
    // coordinate label down with it. Amber ties it to the yellow covered fill.
    // From z16: a single date fits a tile here, the long multi-date strings
    // surface once the tile is big enough (z17+).
    map.addLayer({
      id: 'opensky-tile-grid-date',
      type: 'symbol',
      source: 'opensky-tile-grid',
      minzoom: 16,
      filter: ['all', ['==', ['geometry-type'], 'Point'], ['has', 'dateLabel']],
      layout: {
        'text-field': ['get', 'dateLabel'],
        'text-font': ['Noto Sans Regular'],
        'text-size': ['interpolate', ['linear'], ['zoom'], 16, 8, 19, 11],
        'text-offset': [0, 1.9],
        'text-anchor': 'top',
        'text-allow-overlap': false,
        'text-max-width': 20,
      },
      paint: {
        'text-color': '#b45309',
        'text-halo-color': 'rgba(255, 255, 255, 0.95)',
        'text-halo-width': 1.4,
      }
    })

    // Covered (published) tiles — yellow fill
    await _loadCoveredTiles(map)
    // Re-emit the grid now that covered-tile dates are known, so the date label
    // line shows on first enable (not only after the first pan).
    map.getSource('opensky-tile-grid')?.setData(_generateViewportTiles(map))
    map.addSource('opensky-covered-tiles', {
      type: 'geojson',
      data: _generateCoveredTilesGeoJSON()
    })
    map.addLayer({
      id: 'opensky-covered-tiles-fill',
      type: 'fill',
      source: 'opensky-covered-tiles',
      paint: { 'fill-color': '#facc15', 'fill-opacity': 0.25 }
    }, 'opensky-tile-grid-outline')
    map.addLayer({
      id: 'opensky-covered-tiles-outline',
      type: 'line',
      source: 'opensky-covered-tiles',
      paint: { 'line-color': '#eab308', 'line-width': 1, 'line-opacity': 0.6 }
    }, 'opensky-tile-grid-outline')

    map.addSource('opensky-tile-highlight', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] }
    })
    map.addLayer({
      id: 'opensky-tile-highlight-fill',
      type: 'fill',
      source: 'opensky-tile-highlight',
      paint: { 'fill-color': '#3b82f6', 'fill-opacity': 0.2 }
    })
    map.addLayer({
      id: 'opensky-tile-highlight-outline',
      type: 'line',
      source: 'opensky-tile-highlight',
      paint: { 'line-color': '#3b82f6', 'line-width': 2 }
    })

    const onMouseMove = (e: any) => {
      if (map.getZoom() < GRID_MIN_ZOOM) return
      const x = lng2tile(e.lngLat.lng, TILE_ZOOM)
      const y = lat2tile(e.lngLat.lat, TILE_ZOOM)
      if (x === _hoveredTileX && y === _hoveredTileY) return
      _hoveredTileX = x
      _hoveredTileY = y
      map.getSource('opensky-tile-highlight')?.setData(_generateHighlight(x, y))
      // Latitude of tile center used for flight-time estimate — tile height is constant,
      // width scales with cos(lat). Center latitude is a good proxy.
      const tileCenterLat = (tile2lat(y, TILE_ZOOM) + tile2lat(y + 1, TILE_ZOOM)) / 2
      hoveredTileBudget.value = { ...estimateBudget(tileCenterLat), x, y }
    }

    const onClick = (e: any) => {
      if (_hoveredTileX === null || _hoveredTileY === null || missionGenerating.value) return
      if (map.getZoom() < GRID_MIN_ZOOM) return
      _downloadMission(
        `/api/v1/geo/opensky/mission/?tile_z=${TILE_ZOOM}&tile_x=${_hoveredTileX}&tile_y=${_hoveredTileY}`,
        `OpenSky_Z${TILE_ZOOM}_${_hoveredTileX}_${_hoveredTileY}.zip`
      )
    }

    const onMoveEnd = async () => {
      // Refresh covered tiles for the new viewport first, so both the yellow
      // fill and the date labels (derived from _coveredTiles) stay correct on pan.
      await _loadCoveredTiles(map)
      map.getSource('opensky-covered-tiles')?.setData(_generateCoveredTilesGeoJSON())
      map.getSource('opensky-tile-grid')?.setData(_generateViewportTiles(map))
    }

    map.on('mousemove', onMouseMove)
    map.on('click', onClick)
    map.on('moveend', onMoveEnd)

    _gridHandlers = { mousemove: onMouseMove, click: onClick, moveend: onMoveEnd }
    map.getCanvas().style.cursor = 'crosshair'
  }

  function _disableTileGrid(map: any) {
    for (const id of ['opensky-tile-highlight-outline', 'opensky-tile-highlight-fill', 'opensky-covered-tiles-outline', 'opensky-covered-tiles-fill', 'opensky-tile-grid-date', 'opensky-tile-grid-label', 'opensky-tile-grid-outline']) {
      if (map.getLayer(id)) map.removeLayer(id)
    }
    for (const id of ['opensky-tile-highlight', 'opensky-covered-tiles', 'opensky-tile-grid']) {
      if (map.getSource(id)) map.removeSource(id)
    }
    _coveredTiles = null

    if (_gridHandlers) {
      map.off('mousemove', _gridHandlers.mousemove)
      map.off('click', _gridHandlers.click)
      map.off('moveend', _gridHandlers.moveend)
      _gridHandlers = null
    }

    _hoveredTileX = null
    _hoveredTileY = null
    hoveredTileBudget.value = null
    map.getCanvas().style.cursor = ''
  }

  async function toggleTileGrid() {
    const map = mapStore.mapInstance
    if (!map) return

    tileGridMode.value = !tileGridMode.value

    if (tileGridMode.value) {
      await _enableTileGrid(map)
    } else {
      _disableTileGrid(map)
    }
  }

  // ======== Download ========

  async function _downloadMission(url: string, fallbackFilename: string) {
    if (missionGenerating.value) return
    missionGenerating.value = true

    try {
      await authStore.ensureToken()

      const response = await fetch(url, {
        credentials: 'include',
        headers: { 'Authorization': `Bearer ${authStore.token}` }
      })

      if (!response.ok) throw new Error(`HTTP ${response.status}`)

      const disposition = response.headers.get('content-disposition')
      const filenameMatch = disposition?.match(/filename="(.+)"/)
      const filename = filenameMatch ? filenameMatch[1] : fallbackFilename

      const blob = await response.blob()
      const a = document.createElement('a')
      const blobUrl = URL.createObjectURL(blob)
      a.href = blobUrl
      a.download = filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(blobUrl)

      useToastStore().success('Mission downloaded! ZIP contains 5 flight plans (1/3/5 battery budget — see README). Import the KMZ files into DJI Fly.')
    } catch (error: any) {
      console.error('Failed to download mission:', error)
      useToastStore().error('Failed to generate mission')
    } finally {
      missionGenerating.value = false
    }
  }

  async function downloadMissionKMZ() {
    const map = mapStore.mapInstance
    if (!map) return
    const center = map.getCenter()
    const x = lng2tile(center.lng, TILE_ZOOM)
    const y = lat2tile(center.lat, TILE_ZOOM)
    _downloadMission(
      `/api/v1/geo/opensky/mission/?tile_z=${TILE_ZOOM}&tile_x=${x}&tile_y=${y}`,
      `OpenSky_Z${TILE_ZOOM}_${x}_${y}.zip`
    )
  }

  function toggleMissionArea() {
    toggleTileGrid()
  }

  /**
   * Frame a mission's tile so it sits centered in the *visible* map area.
   * Uses fitBounds (not a fixed center+zoom) so the whole tile is framed on any
   * screen size; the padding keeps it clear of the top nav and floating controls.
   * Returns false when the mission's bounds are unknown (caller can fall back).
   */
  async function fitMissionBounds(
    map: any,
    missionId: string,
    opts: { animate?: boolean } = {}
  ): Promise<boolean> {
    if (!map || !missionId) return false
    if (openSkyMissions.value.length === 0) await loadOpenSkyMissions()
    const b = openSkyMissions.value.find(m => m.id === missionId)?.bounds
    if (!b) return false
    const animate = opts.animate !== false
    map.fitBounds(
      [[b[0], b[1]], [b[2], b[3]]],
      {
        // top a touch larger to clear the floating search box / layer controls
        padding: { top: 100, bottom: 80, left: 80, right: 80 },
        maxZoom: 19,
        animate,
        duration: animate ? 900 : 0,
      }
    )
    return true
  }

  return {
    openSkyEnabled,
    openSkyMode,
    missionGenerating,
    tileGridMode,
    hoveredTileBudget,
    setupLayers,
    fitMissionBounds,
    toggleLayer,
    toggleMissionArea,
    toggleTileGrid,
    downloadMissionKMZ,
  }
}
