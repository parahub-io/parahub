/**
 * Drone reachability for OpenSky mission planning.
 * Click a launch point → backend classifies Z17 tiles via Valhalla /height (SRTM):
 *   green  = capturable
 *   red    = terrain-blocked (hill pierces the constant flight plane elev+AGL)
 *   amber  = RC line-of-sight blocked (drone could fly there, radio can't reach)
 *
 * Unlike useMapIsochrone (road-network isochrone), drone range is a free-space
 * radial disk — backend handles range + terrain ceiling + viewshed.
 * Planning aid only, NOT collision-avoidance (SRTM is coarse, LOS is optical).
 */

import { ref } from 'vue'

const EMPTY_FC: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] }

const TILE_ZOOM = 17

const SRC_TILES = 'dronereach-tiles'
const SRC_LAUNCH = 'dronereach-launch'
const SRC_ZONES = 'dronezones-src'
const LYR_FILL = 'dronereach-fill'
const LYR_OUTLINE = 'dronereach-outline'
const LYR_LAUNCH = 'dronereach-launch-point'
const LYR_ZONES_FILL = 'dronezones-fill'
const LYR_ZONES_OUTLINE = 'dronezones-outline'

const STATUS_COLORS: Record<string, string> = {
  capturable: '#22c55e',
  terrain: '#ef4444',
  los: '#f59e0b',
  restricted: '#7e22ce', // inside a PROHIBITED geo-zone (regulatory no-fly)
}

// ED-269 restriction -> overlay color (PROHIBITED / authorisation / conditional)
const ZONE_COLORS: Record<string, string> = {
  PROHIBITED: '#dc2626',
  REQ_AUTHORISATION: '#f97316',
  CONDITIONAL: '#eab308',
}

// Standard slippy-map tile math (matches backend mission_generator / useMapOpenSky)
function tile2lng(x: number, z: number): number {
  return x / Math.pow(2, z) * 360 - 180
}
function tile2lat(y: number, z: number): number {
  const n = Math.PI - 2 * Math.PI * y / Math.pow(2, z)
  return 180 / Math.PI * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n)))
}

let _clickHandler: ((e: any) => void) | null = null
let _moveHandler: (() => void) | null = null
let _moveTimer: any = null

export function useMapDroneReach() {
  const mapStore = useMapStore()
  const authStore = useAuthStore()

  const droneReachActive = ref(false)
  const droneReachLoading = ref(false)
  const launchPoint = ref<[number, number] | null>(null) // [lng, lat]
  const stats = ref<{ capturable: number; terrain: number; los: number; restricted: number; total: number } | null>(null)
  const launchElev = ref<number | null>(null)

  // Regulatory zones overlay (ED-269)
  const showZones = ref(true)
  const selectedZone = ref<any | null>(null)

  // Tunable params (mirror backend defaults / sliders)
  const agl = ref(100)        // flight height above launch (max 120 = EASA legal)
  const margin = ref(30)      // safety clearance to terrain
  const radiusM = ref(2000)   // disk radius
  const rcHeight = ref(2)     // RC antenna height

  // ======== API ========

  async function fetchReachability(lng: number, lat: number): Promise<GeoJSON.FeatureCollection> {
    await authStore.ensureToken()
    const resp = await $fetch<any>('/api/v1/geo/opensky/reachability/', {
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
      params: {
        lat, lng,
        agl: agl.value, margin: margin.value,
        radius_m: radiusM.value, rc_height: rcHeight.value,
      },
    })
    stats.value = resp?.stats ?? null
    launchElev.value = resp?.launch?.elev ?? null

    const features: GeoJSON.Feature[] = (resp?.tiles ?? []).map((t: any) => {
      const w = tile2lng(t.x, TILE_ZOOM)
      const e = tile2lng(t.x + 1, TILE_ZOOM)
      const n = tile2lat(t.y, TILE_ZOOM)
      const s = tile2lat(t.y + 1, TILE_ZOOM)
      return {
        type: 'Feature' as const,
        properties: { status: t.status, clearance: t.clearance, max_terrain: t.max_terrain },
        geometry: { type: 'Polygon' as const, coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] },
      }
    })
    return { type: 'FeatureCollection', features }
  }

  /** Fetch ED-269 zones for the current map bbox and feed the overlay source. */
  async function fetchZones() {
    const map = mapStore.mapInstance
    if (!map) return
    const src = map.getSource(SRC_ZONES)
    if (!src) return
    if (!showZones.value) { src.setData(EMPTY_FC); return }
    const b = map.getBounds()
    try {
      await authStore.ensureToken()
      const resp = await $fetch<any>('/api/v1/geo/opensky/drone-zones/', {
        credentials: 'include',
        headers: { Authorization: `Bearer ${authStore.token}` },
        params: {
          min_lng: b.getWest(), min_lat: b.getSouth(),
          max_lng: b.getEast(), max_lat: b.getNorth(),
        },
      })
      src.setData(resp ?? EMPTY_FC)
    } catch (e) {
      console.warn('[DroneReach] zones fetch failed:', e)
    }
  }

  // ======== Layers ========

  function setupLayers(map: any) {
    if (map.getSource(SRC_TILES)) return

    map.addSource(SRC_TILES, { type: 'geojson', data: EMPTY_FC })
    map.addSource(SRC_LAUNCH, { type: 'geojson', data: EMPTY_FC })
    map.addSource(SRC_ZONES, { type: 'geojson', data: EMPTY_FC })

    map.addLayer({
      id: LYR_FILL,
      type: 'fill',
      source: SRC_TILES,
      paint: {
        'fill-color': ['match', ['get', 'status'],
          'capturable', STATUS_COLORS.capturable,
          'terrain', STATUS_COLORS.terrain,
          'los', STATUS_COLORS.los,
          'restricted', STATUS_COLORS.restricted,
          '#888888',
        ],
        'fill-opacity': 0.35,
      },
    })
    map.addLayer({
      id: LYR_OUTLINE,
      type: 'line',
      source: SRC_TILES,
      paint: {
        'line-color': ['match', ['get', 'status'],
          'capturable', STATUS_COLORS.capturable,
          'terrain', STATUS_COLORS.terrain,
          'los', STATUS_COLORS.los,
          'restricted', STATUS_COLORS.restricted,
          '#888888',
        ],
        'line-width': 0.6,
        'line-opacity': 0.5,
      },
    })
    map.addLayer({
      id: LYR_ZONES_FILL,
      type: 'fill',
      source: SRC_ZONES,
      paint: {
        'fill-color': ['match', ['get', 'restriction'],
          'PROHIBITED', ZONE_COLORS.PROHIBITED,
          'REQ_AUTHORISATION', ZONE_COLORS.REQ_AUTHORISATION,
          'CONDITIONAL', ZONE_COLORS.CONDITIONAL,
          '#888888',
        ],
        'fill-opacity': 0.12,
      },
    })
    map.addLayer({
      id: LYR_ZONES_OUTLINE,
      type: 'line',
      source: SRC_ZONES,
      paint: {
        'line-color': ['match', ['get', 'restriction'],
          'PROHIBITED', ZONE_COLORS.PROHIBITED,
          'REQ_AUTHORISATION', ZONE_COLORS.REQ_AUTHORISATION,
          'CONDITIONAL', ZONE_COLORS.CONDITIONAL,
          '#888888',
        ],
        'line-width': 1.6,
        'line-opacity': 0.85,
      },
    })
    map.addLayer({
      id: LYR_LAUNCH,
      type: 'circle',
      source: SRC_LAUNCH,
      paint: {
        'circle-radius': 7,
        'circle-color': '#2563eb',
        'circle-stroke-color': '#ffffff',
        'circle-stroke-width': 3,
      },
    })
  }

  async function showReach(lng: number, lat: number) {
    const map = mapStore.mapInstance
    if (!map) return

    droneReachLoading.value = true
    launchPoint.value = [lng, lat]

    const launchSrc = map.getSource(SRC_LAUNCH)
    if (launchSrc) {
      launchSrc.setData({
        type: 'FeatureCollection',
        features: [{ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: [lng, lat] } }],
      })
    }

    try {
      const geojson = await fetchReachability(lng, lat)
      const src = map.getSource(SRC_TILES)
      if (src) src.setData(geojson)
    } catch (e) {
      console.warn('[DroneReach] Failed to fetch:', e)
      useToastStore().error('Failed to compute drone reachability')
    } finally {
      droneReachLoading.value = false
    }
  }

  function clearVisualization() {
    const map = mapStore.mapInstance
    if (!map) return
    const src = map.getSource(SRC_TILES)
    const launchSrc = map.getSource(SRC_LAUNCH)
    const zoneSrc = map.getSource(SRC_ZONES)
    if (src) src.setData(EMPTY_FC)
    if (launchSrc) launchSrc.setData(EMPTY_FC)
    if (zoneSrc) zoneSrc.setData(EMPTY_FC)
    stats.value = null
    launchElev.value = null
    selectedZone.value = null
  }

  // ======== Interaction ========

  function _attachHandlers(map: any) {
    _clickHandler = (e: any) => {
      // Identify a clicked regulatory zone (for the info readout)...
      const hits = map.queryRenderedFeatures(e.point, { layers: [LYR_ZONES_FILL] })
      selectedZone.value = hits.length ? hits[0].properties : null
      // ...and place the launch point / compute reachability.
      showReach(e.lngLat.lng, e.lngLat.lat)
    }
    map.on('click', _clickHandler)
    // Refetch zone overlay for the new viewport (debounced).
    _moveHandler = () => {
      if (_moveTimer) clearTimeout(_moveTimer)
      _moveTimer = setTimeout(() => { fetchZones() }, 300)
    }
    map.on('moveend', _moveHandler)
  }
  function _detachHandlers(map: any) {
    if (_clickHandler) { map.off('click', _clickHandler); _clickHandler = null }
    if (_moveHandler) { map.off('moveend', _moveHandler); _moveHandler = null }
    if (_moveTimer) { clearTimeout(_moveTimer); _moveTimer = null }
  }

  function startDroneReach() {
    const map = mapStore.mapInstance
    if (!map) return
    droneReachActive.value = true
    launchPoint.value = null
    clearVisualization()
    map.getCanvas().style.cursor = 'crosshair'
    _attachHandlers(map)
    fetchZones() // show no-fly zones for the current view immediately
  }

  /** Toggle the regulatory-zones overlay and (re)load or clear it. */
  function setShowZones(value: boolean) {
    showZones.value = value
    const map = mapStore.mapInstance
    if (!map) return
    const vis = value ? 'visible' : 'none'
    if (map.getLayer(LYR_ZONES_FILL)) map.setLayoutProperty(LYR_ZONES_FILL, 'visibility', vis)
    if (map.getLayer(LYR_ZONES_OUTLINE)) map.setLayoutProperty(LYR_ZONES_OUTLINE, 'visibility', vis)
    if (value) fetchZones()
    else selectedZone.value = null
  }

  function stopDroneReach() {
    const map = mapStore.mapInstance
    if (!map) return
    droneReachActive.value = false
    launchPoint.value = null
    map.getCanvas().style.cursor = ''
    _detachHandlers(map)
    clearVisualization()
  }

  function toggleDroneReach() {
    if (droneReachActive.value) stopDroneReach()
    else startDroneReach()
  }

  /** Update a param and re-fetch if a launch point is already placed. */
  function setParam(key: 'agl' | 'margin' | 'radiusM' | 'rcHeight', value: number) {
    if (key === 'agl') agl.value = value
    else if (key === 'margin') margin.value = value
    else if (key === 'radiusM') radiusM.value = value
    else if (key === 'rcHeight') rcHeight.value = value
    if (launchPoint.value) showReach(launchPoint.value[0], launchPoint.value[1])
  }

  return {
    droneReachActive,
    droneReachLoading,
    launchPoint,
    stats,
    launchElev,
    agl, margin, radiusM, rcHeight,
    showZones,
    selectedZone,
    setupLayers,
    startDroneReach,
    stopDroneReach,
    toggleDroneReach,
    setParam,
    setShowZones,
    fetchZones,
    showReach,
  }
}
