/**
 * OpenSky aerial imagery tiles + tile grid mission planning + KMZ download.
 *
 * Grid: standard Web Mercator tiles (Z17, same as OSM/Google).
 * User hovers → tile highlights, click → download 2 KMZ (nadir + oblique).
 */

import { ref, computed } from 'vue'
import type { Ref } from 'vue'

const TILE_ZOOM = 17         // ~305×240m per tile at mid-latitudes
const GRID_MIN_ZOOM = 12     // Don't render grid below this zoom

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

export function useMapOpenSky(currentMissionFilter: Ref<string | undefined>) {
  const authStore = useAuthStore()
  const mapStore = useMapStore()

  const openSkyEnabled = useLocalPref('opensky_enabled', false)
  const openSkyMode = useLocalPref('opensky_mode', false)
  const missionGenerating = ref(false)
  const tileGridMode = ref(false)

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
        minzoom: 13,
        maxzoom: 23
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
      minzoom: 13,
      maxzoom: 23,
      ...(missionBounds ? { bounds: missionBounds } : {})
    })

    const shouldBeVisible = missionId ? true : openSkyEnabled.value

    const overlayLayers = ['trackers-circle', 'energy-cells-circle', 'mesh-public-icon']
    const beforeId = overlayLayers.find(id => map.getLayer(id))

    map.addLayer({
      id: unifiedLayerId,
      type: 'raster',
      source: unifiedSourceId,
      minzoom: 13,
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
          maxzoom: mission.maxzoom
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
  let _coveredTiles: Set<string> | null = null

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
      const data = await $fetch<{ tiles: Array<{ x: number, y: number }> }>(
        '/api/v1/geo/opensky/covered-tiles/', {
          params: {
            west: bounds.getWest(),
            south: bounds.getSouth(),
            east: bounds.getEast(),
            north: bounds.getNorth(),
          },
        }
      )
      _coveredTiles = new Set(data.tiles.map(t => `${t.x}:${t.y}`))
    } catch (e) {
      console.warn('[OpenSky] Failed to load covered tiles:', e)
      _coveredTiles = new Set()
    }
  }

  function _generateCoveredTilesGeoJSON() {
    if (!_coveredTiles || _coveredTiles.size === 0) {
      return { type: 'FeatureCollection' as const, features: [] as any[] }
    }
    const features: any[] = []
    for (const key of _coveredTiles) {
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
      paint: { 'line-color': '#6b7280', 'line-width': 0.5, 'line-opacity': 0.4 }
    })

    // Covered (published) tiles — yellow fill
    await _loadCoveredTiles(map)
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
    }

    const onClick = (e: any) => {
      if (_hoveredTileX === null || _hoveredTileY === null || missionGenerating.value) return
      if (map.getZoom() < GRID_MIN_ZOOM) return
      _downloadMission(
        `/api/v1/geo/opensky/mission/?tile_z=${TILE_ZOOM}&tile_x=${_hoveredTileX}&tile_y=${_hoveredTileY}`,
        `OpenSky_Z${TILE_ZOOM}_${_hoveredTileX}_${_hoveredTileY}.zip`
      )
    }

    const onMoveEnd = () => {
      map.getSource('opensky-tile-grid')?.setData(_generateViewportTiles(map))
    }

    map.on('mousemove', onMouseMove)
    map.on('click', onClick)
    map.on('moveend', onMoveEnd)

    _gridHandlers = { mousemove: onMouseMove, click: onClick, moveend: onMoveEnd }
    map.getCanvas().style.cursor = 'crosshair'
  }

  function _disableTileGrid(map: any) {
    for (const id of ['opensky-tile-highlight-outline', 'opensky-tile-highlight-fill', 'opensky-covered-tiles-outline', 'opensky-covered-tiles-fill', 'opensky-tile-grid-outline']) {
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

      useToastStore().success('Mission downloaded! ZIP contains nadir + oblique KMZ. Import to DJI Fly app.')
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

  return {
    openSkyEnabled,
    openSkyMode,
    missionGenerating,
    tileGridMode,
    setupLayers,
    toggleLayer,
    toggleMissionArea,
    toggleTileGrid,
    downloadMissionKMZ,
  }
}
