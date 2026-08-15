/**
 * IoT map layers: GPS Trackers + Mesh Routers + Energy Cells.
 *
 * Extracted from MapView.vue lines 347-366, 582-1101.
 */

import { ref, nextTick } from 'vue'
import { attachHoverHex } from '~/composables/useMapHighlight'
import {
  DEVICE_HEX_SIZE, DEVICE_MINZOOM, DEVICE_LABEL_MINZOOM,
  hexagonPath, strokeMarkerOutline, glyphColorFor, drawLucideGlyph,
  ZAP_GLYPH, LEAF_GLYPH, WIND_GLYPH, NAVIGATION_GLYPH,
} from '~/composables/useMapToggleableLayer'
import {
  setEnsembleSegment, setEnsembleScale, ensemblePlacement, onEnsembleChange, ENSEMBLE_ICON_SCALE,
  type EnsembleMemberInput, type EnsemblePlacement,
} from '~/composables/useMapDeviceEnsembles'

/** Compute a GeoJSON Polygon approximating a circle of `radiusKm` around [lng, lat]. */
function _geojsonCircle(lng: number, lat: number, radiusKm: number, steps = 64) {
  const coords = []
  for (let i = 0; i <= steps; i++) {
    const angle = (i / steps) * 2 * Math.PI
    const dLng = (radiusKm / (111.32 * Math.cos(lat * Math.PI / 180))) * Math.cos(angle)
    const dLat = (radiusKm / 110.574) * Math.sin(angle)
    coords.push([lng + dLng, lat + dLat])
  }
  return { type: 'Polygon' as const, coordinates: [coords] }
}

/** Energy cell status → fill color, shared by the GL layer, the map legend,
 *  and card snapshot markers (PK/design-system.md § Map Markers). */
export const ENERGY_STATUS_COLORS: Record<string, string> = {
  GREEN: '#22c55e', YELLOW: '#eab308', RED: '#ef4444', OFFLINE: '#6b7280',
}

/** Env station fill when there is no AQI reading (weather-only / no data yet). */
export const ENV_WEATHER_COLOR = '#38bdf8'

export function useMapIoTLayers() {
  const authStore = useAuthStore()
  const mapStore = useMapStore()
  const { t } = useI18n()

  // IoT popover state
  const iotPopoverOpen = ref(false)
  const iotRoutersExpanded = ref(true)
  const iotTrackersExpanded = ref(true)
  const iotEnergyCellsExpanded = ref(true)

  // GPS Tracker state
  const trackersEnabled = useLocalPref('trackers_enabled', true)
  const trackerPositionsList = ref<any[]>([])
  let trackerRefreshInterval: ReturnType<typeof setInterval> | null = null

  // Mesh Router state (data for IoT popover — map layer is public, see useMapMeshLayer)
  const meshRouterPositionsList = ref<any[]>([])

  // Energy Cells state
  const energyCellsEnabled = useLocalPref('energy_cells_enabled', true)
  const energyCellsList = ref<any[]>([])
  let energyCellsRefreshInterval: ReturnType<typeof setInterval> | null = null

  // Environmental stations (weather + air quality) state — public layer
  const envStationsEnabled = useLocalPref('env_stations_enabled', true)
  const envStationsList = ref<any[]>([])
  let envStationsRefreshInterval: ReturnType<typeof setInterval> | null = null

  // Animation preference
  const animationEnabledCookie = useLocalPref('animation_enabled', true)

  /**
   * Camera padding to keep the target visible in the part of the map
   * not covered by MapFeaturePanel (mobile: bottom sheet ≈50vh, desktop: 384px left).
   */
  const getPanelPadding = () => {
    if (typeof window === 'undefined') return undefined
    if (window.innerWidth < 768) {
      return { top: 0, bottom: Math.round(window.innerHeight * 0.5), left: 0, right: 0 }
    }
    return { top: 0, bottom: 0, left: 384, right: 0 }
  }

  // ======== Follow mode (camera tracks device in real-time) ========

  const isFollowing = ref(false)

  const enableFollow = () => { isFollowing.value = true }
  const disableFollow = () => { isFollowing.value = false }

  /** Smoothly pan camera to device position if follow mode is active. */
  const followToPosition = (lat: number, lon: number) => {
    if (!isFollowing.value) return
    const map = mapStore.mapInstance
    if (!map) return
    map.easeTo({ center: [lon, lat], duration: 1000, padding: getPanelPadding() })
  }

  // ======== IoT Lock-on (persistent marker on selected device) ========

  let iotLockOnMarker: any = null
  /** Ensemble member under the lock-on, so it can follow a regrouping. */
  let iotLockOnRef: { segment: string, id: string } | null = null

  /**
   * offsetPx: constant screen-px fan-out of ensemble members (data-driven
   * `icon-offset`). Passed as the Marker's own px offset so the bracket stays
   * glued to the icon at every zoom — baking it into lngLat would fix it in
   * geo space and drift off the icon when the zoom changes.
   * ref: the locked device's ensemble identity. Ensembles regroup with the
   * map scale, so anchor+offset are only valid for the current grouping —
   * without the ref the bracket is left behind the next time the lattice
   * re-forms (see _resyncIoTLockOn).
   */
  const showIoTLockOn = async (
    lat: number, lon: number, offsetPx?: [number, number] | null,
    ref?: { segment: string, id: string } | null,
  ) => {
    hideIoTLockOn()
    iotLockOnRef = ref || null
    const map = mapStore.mapInstance
    if (!map) return
    // With a ref the current placement is authoritative — callers that only
    // know the device (popover list, deep link) get the lattice slot for free
    const pl = ref ? ensemblePlacement(ref.segment, ref.id) : undefined
    const at: [number, number] = pl ? pl.anchor : [lon, lat]
    const off = pl ? pl.offset : (offsetPx || null)
    if (!maplibreglCache) maplibreglCache = await import('maplibre-gl').then(m => m.default || m)
    const { createLockOnElement, flashCrosshair } = await import('~/utils/lockOnMarker')
    iotLockOnMarker = new maplibreglCache.Marker({
      element: createLockOnElement(),
      anchor: 'center',
      ...(off ? { offset: off } : {}),
    })
      .setLngLat(at)
      .addTo(map)
    // Flash crosshair when lock-in animation finishes
    setTimeout(() => {
      if (!iotLockOnMarker) return // already hidden
      const pt = map.project(at)
      flashCrosshair(map.getContainer(), Math.round(pt.x + (off?.[0] || 0)), Math.round(pt.y + (off?.[1] || 0)))
    }, 450)
  }

  const hideIoTLockOn = () => {
    if (iotLockOnMarker) { iotLockOnMarker.remove(); iotLockOnMarker = null }
    iotLockOnRef = null
  }

  /** Move existing lock-on marker without restarting animation. */
  const moveIoTLockOn = (lat: number, lon: number) => {
    if (!iotLockOnMarker) return
    // A tracker that starts moving leaves the lattice — follow it to its true
    // point and drop the slot offset with it (an ensemble member keeps both)
    const pl = iotLockOnRef ? ensemblePlacement(iotLockOnRef.segment, iotLockOnRef.id) : undefined
    iotLockOnMarker.setLngLat(pl ? pl.anchor : [lon, lat])
    if (iotLockOnRef) iotLockOnMarker.setOffset(pl ? pl.offset : [0, 0])
  }

  /** Follow the locked device through an ensemble regrouping (zoom, toggle). */
  const _resyncIoTLockOn = () => {
    if (!iotLockOnMarker || !iotLockOnRef) return
    const pl = ensemblePlacement(iotLockOnRef.segment, iotLockOnRef.id)
    if (!pl) return
    iotLockOnMarker.setLngLat(pl.anchor)
    iotLockOnMarker.setOffset(pl.offset)
  }

  /** Remove + recreate lock-on to replay CSS animation. */
  const replayIoTLockOn = async (
    lat: number, lon: number, offsetPx?: [number, number] | null,
    ref?: { segment: string, id: string } | null,
  ) => {
    const keep = ref === undefined ? iotLockOnRef : ref
    hideIoTLockOn()
    await nextTick()
    showIoTLockOn(lat, lon, offsetPx, keep)
  }

  // ======== IoT Preview (lock-on marker + edge indicator on hover) ========

  let iotPreviewMarker: any = null
  let iotEdgeIndicatorEl: HTMLElement | null = null
  let maplibreglCache: any = null
  let iotMarkerSeq = 0

  const haversineKm = (lat1: number, lon1: number, lat2: number, lon2: number): number => {
    const R = 6371
    const toRad = (d: number) => d * Math.PI / 180
    const dLat = toRad(lat2 - lat1)
    const dLon = toRad(lon2 - lon1)
    const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
  }

  const hideIoTPreview = () => {
    if (iotPreviewMarker) { iotPreviewMarker.remove(); iotPreviewMarker = null }
    if (iotEdgeIndicatorEl) { iotEdgeIndicatorEl.remove(); iotEdgeIndicatorEl = null }
  }

  const showIoTPreview = async (lat: number, lon: number) => {
    hideIoTPreview()
    const map = mapStore.mapInstance
    if (!map) return

    // Lock-on bracket marker
    const seq = ++iotMarkerSeq
    if (!maplibreglCache) maplibreglCache = await import('maplibre-gl').then(m => m.default || m)
    if (seq !== iotMarkerSeq) return
    const { createLockOnElement } = await import('~/utils/lockOnMarker')
    if (seq !== iotMarkerSeq) return
    iotPreviewMarker = new maplibreglCache.Marker({ element: createLockOnElement(), anchor: 'center' })
      .setLngLat([lon, lat])
      .addTo(map)

    // Edge indicator (only when off-screen)
    const bounds = map.getBounds()
    if (bounds.contains([lon, lat] as [number, number])) return

    const container = map.getContainer()
    const w = container.clientWidth
    const h = container.clientHeight
    const cx = w / 2
    const cy = h / 2
    const px = map.project([lon, lat])
    const dx = px.x - cx
    const dy = px.y - cy
    if (Math.abs(dx) < 1 && Math.abs(dy) < 1) return

    const padL = 60, padR = 60, padT = 80, padB = 60
    const sx = dx > 0 ? (w - padR - cx) / dx : dx < 0 ? (padL - cx) / dx : Infinity
    const sy = dy > 0 ? (h - padB - cy) / dy : dy < 0 ? (padT - cy) / dy : Infinity
    const s = Math.min(sx, sy)
    const ex = cx + dx * s
    const ey = cy + dy * s

    const center = map.getCenter()
    const dist = haversineKm(center.lat, center.lng, lat, lon)
    const distText = dist >= 1 ? `${Math.round(dist)} km` : `${Math.round(dist * 1000)} m`
    const angle = Math.atan2(dy, dx) * 180 / Math.PI

    iotEdgeIndicatorEl = document.createElement('div')
    iotEdgeIndicatorEl.className = 'edge-distance-indicator'
    iotEdgeIndicatorEl.style.cssText = `left:${ex}px;top:${ey}px`
    iotEdgeIndicatorEl.innerHTML = `
      <div class="edge-ind-pill">
        <svg class="edge-ind-arrow" viewBox="0 0 16 16" width="14" height="14" style="transform:rotate(${angle}deg)">
          <path d="M2 8h10M8 4l4 4-4 4" stroke="currentColor" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        <span class="edge-ind-dist">${distText}</span>
      </div>
    `
    container.appendChild(iotEdgeIndicatorEl)
  }

  // ======== GPS Trackers ========

  // Below this speed a parked tracker's GPS jitter reports arbitrary course values
  const TRACKER_MOVING_MIN_KMH = 3

  const _trackerMoving = (p: any) =>
    p.traccar_status === 'online' && (p.speed ?? 0) >= TRACKER_MOVING_MIN_KMH

  const _trackerFeature = (p: any) => {
    const pl = ensemblePlacement('tracker', p.device_id)
    return {
      type: 'Feature' as const,
      properties: {
        device_id: p.device_id,
        name: p.name,
        speed: p.speed ? `${Math.round(p.speed)} km/h` : '',
        status: p.traccar_status || 'unknown',
        heading: p.heading ?? 0,
        moving: _trackerMoving(p) && p.heading != null,
        iconOffset: pl?.offset || [0, 0],
        glIconOffset: pl?.glOffset || [0, 0],
        ensemble: (pl?.groupSize || 1) > 1,
        labelHidden: pl ? pl.labelPos === null : false,
        // The label carries the member's slot offset itself (icon-offset moves
        // the icon only) — see EnsemblePlacement.labelOffset
        ...((pl?.groupSize || 1) > 1 && pl?.labelOffset
          ? { labelOffset: pl.labelOffset, labelAnchor: pl.labelAnchor }
          : {}),
      },
      geometry: { type: 'Point' as const, coordinates: pl?.anchor || [p.longitude, p.latitude] },
    }
  }

  const _trackerGeoJSON = (positions: any[]) => ({
    type: 'FeatureCollection' as const,
    features: positions.map(_trackerFeature),
  })

  /**
   * A parked tracker is just another device standing at the house — it docks
   * into the co-located ensemble so it stops landing on top of the routers.
   * A moving one leaves the lattice: its marker is already travelling, and a
   * slot offset would fight the motion (and re-slot the whole group on every
   * position tick).
   */
  const _trackerMembers = (positions: any[]): EnsembleMemberInput[] =>
    trackersEnabled.value
      ? positions
          .filter((p: any) => p.latitude != null && p.longitude != null && !_trackerMoving(p))
          .map((p: any) => ({
            id: p.device_id,
            lat: p.latitude,
            lon: p.longitude,
            role: 'other' as const,
            mobile: true,
          }))
      : []

  const _publishTrackerMembers = () =>
    setEnsembleSegment('tracker', _trackerMembers(trackerPositionsList.value))

  const loadTrackerPositions = async (): Promise<any[]> => {
    if (!authStore.isAuthenticated) return []
    try {
      await authStore.ensureToken()
      const data = await $fetch<any[]>('/api/v1/iot/tracker-positions', {
        credentials: 'include',
        headers: { 'Authorization': `Bearer ${authStore.token}` },
      })
      const positions = data || []
      trackerPositionsList.value = positions
      _publishTrackerMembers()
      return positions
    } catch (e) {
      console.warn('[IoTLayers] Failed to fetch tracker positions:', e)
      return []
    }
  }

  /** Standard device hexagon: fill + unified dark outline + optional type glyph. */
  const _ensureHexIcon = (map: any, id: string, fill: string, glyphPaths?: string[]) => {
    if (map.hasImage(id)) return
    const s = DEVICE_HEX_SIZE * 2 // draw at 2x for retina
    const canvas = document.createElement('canvas')
    canvas.width = s
    canvas.height = s
    const ctx = canvas.getContext('2d')!
    hexagonPath(ctx, s)
    ctx.fillStyle = fill
    ctx.fill()
    strokeMarkerOutline(ctx)
    if (glyphPaths) drawLucideGlyph(ctx, s, glyphPaths, 24, glyphColorFor(fill))
    map.addImage(id, { width: s, height: s, data: ctx.getImageData(0, 0, s, s).data }, { pixelRatio: 2 })
  }

  /** Course pointer: up-pointing triangle on an oversized canvas whose center is
   * the marker center, so icon-rotate (= course) orbits it around the hex rim. */
  const _ensureHeadingPointerIcon = (map: any, id: string, fill: string) => {
    if (map.hasImage(id)) return
    const s = 64 // 2x (32px at 1x): base tucks under the hex edge, tip clears it
    const canvas = document.createElement('canvas')
    canvas.width = s
    canvas.height = s
    const ctx = canvas.getContext('2d')!
    const cx = s / 2
    ctx.beginPath()
    ctx.moveTo(cx, 5)
    ctx.lineTo(cx - 7, 17)
    ctx.lineTo(cx + 7, 17)
    ctx.closePath()
    ctx.fillStyle = fill
    ctx.fill()
    ctx.lineJoin = 'round'
    strokeMarkerOutline(ctx)
    map.addImage(id, { width: s, height: s, data: ctx.getImageData(0, 0, s, s).data }, { pixelRatio: 2 })
  }

  const addTrackerLayers = async (map: any) => {
    if (!authStore.isAuthenticated) return

    const positions = await loadTrackerPositions()
    const geojson = _trackerGeoJSON(positions)

    if (map.getSource('trackers')) {
      ;(map.getSource('trackers') as any).setData(geojson)
      return
    }

    // Generate hexagon icons for each status
    _ensureHexIcon(map, 'tracker-hex-online', '#4E4EC8', NAVIGATION_GLYPH)
    _ensureHexIcon(map, 'tracker-hex-unknown', '#a3a3a3', NAVIGATION_GLYPH)
    _ensureHexIcon(map, 'tracker-hex-offline', '#ef4444', NAVIGATION_GLYPH)
    _ensureHeadingPointerIcon(map, 'tracker-heading-pointer', '#4E4EC8')

    map.addSource('trackers', { type: 'geojson', data: geojson })

    // Course pointer under the hex (moving = online + real speed only)
    map.addLayer({
      id: 'trackers-heading',
      type: 'symbol',
      source: 'trackers',
      filter: ['==', ['get', 'moving'], true],
      layout: {
        'icon-image': 'tracker-heading-pointer',
        'icon-rotate': ['get', 'heading'],
        'icon-rotation-alignment': 'map',
        'icon-allow-overlap': true,
        'icon-ignore-placement': true,
        visibility: trackersEnabled.value ? 'visible' : 'none',
      },
    })

    map.addLayer({
      id: 'trackers-circle',
      type: 'symbol',
      source: 'trackers',
      layout: {
        'icon-image': [
          'case',
          ['==', ['get', 'status'], 'online'], 'tracker-hex-online',
          ['==', ['get', 'status'], 'unknown'], 'tracker-hex-unknown',
          'tracker-hex-offline',
        ],
        'icon-offset': ['get', 'glIconOffset'],
        'icon-size': ['case', ['get', 'ensemble'], ENSEMBLE_ICON_SCALE, 1],
        'icon-allow-overlap': true,
        visibility: trackersEnabled.value ? 'visible' : 'none',
      },
    })

    map.addLayer({
      id: 'trackers-label',
      type: 'symbol',
      source: 'trackers',
      layout: {
        'text-field': ['case', ['get', 'labelHidden'], '', ['get', 'name']],
        'text-size': 11,
        'text-offset': ['coalesce', ['get', 'labelOffset'], ['literal', [0, 1.5]]],
        'text-anchor': ['coalesce', ['get', 'labelAnchor'], 'top'],
        'text-optional': true,
        visibility: trackersEnabled.value ? 'visible' : 'none',
      },
      paint: {
        'text-color': '#374151',
        'text-halo-color': '#ffffff',
        'text-halo-width': 1.5,
      },
    })

    attachHoverHex(map, 'trackers-circle', 1.2, () => iotLockOnMarker)
  }

  const refreshTrackerPositions = async () => {
    const map = mapStore.mapInstance
    if (!map || !map.getSource('trackers')) return
    const positions = await loadTrackerPositions()
    ;(map.getSource('trackers') as any).setData(_trackerGeoJSON(positions))
  }

  const toggleTrackers = () => {
    trackersEnabled.value = !trackersEnabled.value
    const map = mapStore.mapInstance
    if (!map) return
    const vis = trackersEnabled.value ? 'visible' : 'none'
    if (map.getLayer('trackers-heading')) map.setLayoutProperty('trackers-heading', 'visibility', vis)
    if (map.getLayer('trackers-circle')) map.setLayoutProperty('trackers-circle', 'visibility', vis)
    if (map.getLayer('trackers-label')) map.setLayoutProperty('trackers-label', 'visibility', vis)

    // Regroup the shared ensemble: trackers leave on hide, rejoin on show
    // (the change listener re-renders this and every co-located layer)
    _publishTrackerMembers()

    if (trackersEnabled.value && !trackerRefreshInterval) {
      trackerRefreshInterval = setInterval(refreshTrackerPositions, 30000)
    } else if (!trackersEnabled.value && trackerRefreshInterval) {
      clearInterval(trackerRefreshInterval)
      trackerRefreshInterval = null
    }
  }

  const flyToTracker = (lat: number, lng: number, _name: string) => {
    hideIoTPreview()
    const map = mapStore.mapInstance
    if (!map) return
    if (!trackersEnabled.value) toggleTrackers()
    const padding = getPanelPadding()
    if (animationEnabledCookie.value !== false) {
      map.flyTo({ center: [lng, lat], zoom: 17, essential: true, speed: 4.5, padding })
    } else {
      map.jumpTo({ center: [lng, lat], zoom: 17, padding })
    }
    iotPopoverOpen.value = false
  }

  // ======== Mesh Routers (data for IoT popover list — map layer is public, see useMapMeshLayer) ========

  const loadMeshRouterPositions = async (): Promise<any[]> => {
    if (!authStore.isAuthenticated) return []
    try {
      await authStore.ensureToken()
      const data = await $fetch<any[]>('/api/v1/iot/mesh-router-positions', {
        credentials: 'include',
        headers: { 'Authorization': `Bearer ${authStore.token}` },
      })
      const positions = data || []
      meshRouterPositionsList.value = positions
      return positions
    } catch (e) {
      console.warn('[IoTLayers] Failed to fetch mesh router positions:', e)
      return []
    }
  }

  const flyToMeshRouter = (lat: number, lng: number, _name: string) => {
    hideIoTPreview()
    const map = mapStore.mapInstance
    if (!map) return
    const padding = getPanelPadding()
    if (animationEnabledCookie.value !== false) {
      map.flyTo({ center: [lng, lat], zoom: 17, essential: true, speed: 4.5, padding })
    } else {
      map.jumpTo({ center: [lng, lat], zoom: 17, padding })
    }
    iotPopoverOpen.value = false
  }

  // ======== Energy Cells ========

  const loadEnergyCells = async (): Promise<any[]> => {
    try {
      const data = await $fetch<any[]>('/api/v1/energy/cells/map/')
      energyCellsList.value = data || []
    } catch (e) {
      console.warn('[IoTLayers] Failed to fetch energy cells:', e)
      return []
    }
    _publishEnergyMembers()
    return energyCellsList.value
  }

  // Energy cells are static devices — they join the co-located ensemble
  // (useMapDeviceEnsembles) as label-only members and may take the center slot
  const _energyMembers = (cells: any[]): EnsembleMemberInput[] =>
    energyCellsEnabled.value
      ? cells
          .filter((c: any) => c.latitude != null && c.longitude != null)
          .map((c: any) => ({ id: c.id, lat: c.latitude, lon: c.longitude, role: 'other' as const }))
      : []

  const _publishEnergyMembers = () => setEnsembleSegment('energy', _energyMembers(energyCellsList.value))

  const _energyRadiusFeatures = (cells: any[]) => ({
    type: 'FeatureCollection' as const,
    features: cells.map((c: any) => ({
      type: 'Feature' as const,
      properties: { id: c.id, name: c.name, status: c.status, price: c.current_price_eur, color: ENERGY_STATUS_COLORS[c.status] || '#6b7280' },
      geometry: _geojsonCircle(c.longitude, c.latitude, c.radius_km),
    })),
  })

  const _energyPointFeatures = (cells: any[]) => ({
    type: 'FeatureCollection' as const,
    features: cells.map((c: any) => {
      const pl = ensemblePlacement('energy', c.id)
      return {
        type: 'Feature' as const,
        properties: {
          id: c.id,
          name: c.name,
          status: c.status,
          price: c.current_price_eur,
          color: ENERGY_STATUS_COLORS[c.status] || '#6b7280',
          iconOffset: pl?.offset || [0, 0],
          glIconOffset: pl?.glOffset || [0, 0],
          ensemble: (pl?.groupSize || 1) > 1,
          labelHidden: pl ? pl.labelPos === null : false,
          // The label carries the member's slot offset itself (icon-offset
          // moves the icon only) — see EnsemblePlacement.labelOffset
          ...((pl?.groupSize || 1) > 1 && pl?.labelOffset
            ? { labelOffset: pl.labelOffset, labelAnchor: pl.labelAnchor }
            : {}),
        },
        geometry: { type: 'Point' as const, coordinates: pl?.anchor || [c.longitude, c.latitude] },
      }
    }),
  })

  const addEnergyCellLayers = async (map: any) => {
    const cells = await loadEnergyCells()

    const radiusGeoJSON = _energyRadiusFeatures(cells)
    const pointGeoJSON = _energyPointFeatures(cells)
    const vis = energyCellsEnabled.value ? 'visible' : 'none'

    if (map.getSource('energy-cells-radius')) {
      ;(map.getSource('energy-cells-radius') as any).setData(radiusGeoJSON)
      ;(map.getSource('energy-cells-points') as any).setData(pointGeoJSON)
      return
    }

    map.addSource('energy-cells-radius', { type: 'geojson', data: radiusGeoJSON })
    map.addSource('energy-cells-points', { type: 'geojson', data: pointGeoJSON })

    map.addLayer({
      id: 'energy-cells-fill', type: 'fill', source: 'energy-cells-radius',
      paint: { 'fill-color': ['get', 'color'], 'fill-opacity': 0.08 },
      layout: { visibility: vis },
      minzoom: DEVICE_MINZOOM,
    })

    map.addLayer({
      id: 'energy-cells-border', type: 'line', source: 'energy-cells-radius',
      paint: { 'line-color': ['get', 'color'], 'line-width': 1.5, 'line-dasharray': [4, 3], 'line-opacity': 0.6 },
      layout: { visibility: vis },
      minzoom: DEVICE_MINZOOM,
    })

    // Generate hex icons for each energy status
    for (const [status, color] of Object.entries(ENERGY_STATUS_COLORS)) {
      _ensureHexIcon(map, `energy-hex-${status}`, color, ZAP_GLYPH)
    }

    map.addLayer({
      id: 'energy-cells-circle', type: 'symbol', source: 'energy-cells-points',
      layout: {
        'icon-image': [
          'match', ['get', 'status'],
          'GREEN', 'energy-hex-GREEN',
          'YELLOW', 'energy-hex-YELLOW',
          'RED', 'energy-hex-RED',
          'energy-hex-OFFLINE',
        ],
        'icon-offset': ['get', 'glIconOffset'],
        'icon-size': ['case', ['get', 'ensemble'], ENSEMBLE_ICON_SCALE, 1],
        'icon-allow-overlap': true,
        visibility: vis,
      },
      minzoom: DEVICE_MINZOOM,
    })

    map.addLayer({
      id: 'energy-cells-label', type: 'symbol', source: 'energy-cells-points',
      layout: {
        'text-field': ['case', ['get', 'labelHidden'], '', ['case', ['!=', ['get', 'price'], null], ['concat', ['get', 'name'], '\n', ['to-string', ['get', 'price']], '€/kWh'], ['get', 'name']]],
        'text-size': 11,
        'text-offset': ['coalesce', ['get', 'labelOffset'], ['literal', [0, 1.4]]],
        'text-anchor': ['coalesce', ['get', 'labelAnchor'], 'top'],
        'text-optional': true,
        visibility: vis,
      },
      paint: { 'text-color': '#111827', 'text-halo-color': '#ffffff', 'text-halo-width': 1.5 },
      minzoom: DEVICE_LABEL_MINZOOM,
    })

    attachHoverHex(map, 'energy-cells-circle', 1.2, () => iotLockOnMarker)
  }

  const refreshEnergyCells = async () => {
    const map = mapStore.mapInstance
    if (!map || !map.getSource('energy-cells-radius')) return
    const cells = await loadEnergyCells()
    ;(map.getSource('energy-cells-radius') as any).setData(_energyRadiusFeatures(cells))
    ;(map.getSource('energy-cells-points') as any).setData(_energyPointFeatures(cells))
  }

  const toggleEnergyCells = () => {
    energyCellsEnabled.value = !energyCellsEnabled.value
    const map = mapStore.mapInstance
    if (!map) return
    const vis = energyCellsEnabled.value ? 'visible' : 'none'
    for (const id of ['energy-cells-fill', 'energy-cells-border', 'energy-cells-circle', 'energy-cells-label']) {
      if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', vis)
    }
    // Regroup the shared ensemble: cells leave on hide, rejoin on show
    _publishEnergyMembers()
    if (energyCellsEnabled.value && !energyCellsRefreshInterval) {
      energyCellsRefreshInterval = setInterval(refreshEnergyCells, 120000)
    } else if (!energyCellsEnabled.value && energyCellsRefreshInterval) {
      clearInterval(energyCellsRefreshInterval)
      energyCellsRefreshInterval = null
    }
  }

  const flyToEnergyCell = (lat: number, lng: number, _name: string) => {
    hideIoTPreview()
    const map = mapStore.mapInstance
    if (!map) return
    if (!energyCellsEnabled.value) toggleEnergyCells()
    const padding = getPanelPadding()
    if (animationEnabledCookie.value !== false) {
      map.flyTo({ center: [lng, lat], zoom: 17, essential: true, speed: 4.5, padding })
    } else {
      map.jumpTo({ center: [lng, lat], zoom: 17, padding })
    }
    iotPopoverOpen.value = false
  }

  // ======== Environmental Stations (weather + air quality) ========

  // US EPA AQI category → color. Weather-only stations (no PM2.5) use sky blue.
  const AQI_COLORS: Record<string, string> = {
    good: '#22c55e',
    moderate: '#eab308',
    unhealthy_sensitive: '#f97316',
    unhealthy: '#ef4444',
    very_unhealthy: '#a855f7',
    hazardous: '#7f1d1d',
  }
  const _envColor = (latest: any): string =>
    (latest?.aqi_category && AQI_COLORS[latest.aqi_category]) || ENV_WEATHER_COLOR

  const _envVisible = (list: any[]) => list.filter((s: any) => s.latitude != null && s.longitude != null)

  // Co-located devices (env stations + mesh routers + energy cells within
  // ≤5 m — one mast / one home is a normal setup) compose into a hexagonal
  // ensemble via the shared layout (useMapDeviceEnsembles): screen-space
  // offsets, coordinates stay truthful, pattern constant across zooms. The
  // HUD markers reuse the same placements so each readout hugs its hexagon.
  const _envMembers = (list: any[]): EnsembleMemberInput[] =>
    envStationsEnabled.value
      ? _envVisible(list).map((s: any) => ({
          id: s.id,
          lat: s.latitude,
          lon: s.longitude,
          role: s.latest?.aqi != null ? 'air' as const : 'weather' as const,
          hud: true,
          wind: s.latest?.wind_dir != null,
        }))
      : []

  const _publishEnvMembers = () => setEnsembleSegment('env', _envMembers(envStationsList.value))

  const _envFeatures = (list: any[]) => {
    const visible = _envVisible(list)
    return {
      type: 'FeatureCollection' as const,
      features: visible.map((s: any) => {
        const pl = ensemblePlacement('env', s.id)
        return {
          type: 'Feature' as const,
          properties: {
            id: s.id,
            name: s.name,
            source: s.source,
            color: _envColor(s.latest),
            aqiCategory: s.latest?.aqi_category || '',
            stale: !!s.stale,
            latestJson: JSON.stringify(s.latest || {}),
            lastReadingAt: s.last_reading_at || '',
            publicUrl: s.public_url || '',
            ownerName: s.owner_name || '',
            ownerCri: s.owner_cri || '',
            iconOffset: pl?.offset || [0, 0],
            glIconOffset: pl?.glOffset || [0, 0],
            ensemble: (pl?.groupSize || 1) > 1,
          },
          // Group members render from the shared centroid anchor (see
          // useMapDeviceEnsembles.ts) so the lattice stays intact at high zoom
          geometry: { type: 'Point' as const, coordinates: pl?.anchor || [s.longitude, s.latitude] },
        }
      }),
    }
  }

  /** Standard device hexes: AQI-colored + leaf for air stations, sky-blue + wind for weather-only. */
  const _ensureEnvIcons = (map: any) => {
    for (const [cat, color] of Object.entries(AQI_COLORS)) {
      _ensureHexIcon(map, `env-hex-${cat}`, color, LEAF_GLYPH)
    }
    _ensureHexIcon(map, 'env-hex-weather', ENV_WEATHER_COLOR, WIND_GLYPH)
  }

  const ENV_ICON_IMAGE = [
    'match', ['get', 'aqiCategory'],
    ...Object.keys(AQI_COLORS).flatMap((cat) => [cat, `env-hex-${cat}`]),
    'env-hex-weather',
  ]

  const loadEnvStations = async (): Promise<any[]> => {
    try {
      const data = await $fetch<any[]>('/api/v1/iot/env-stations/map')
      envStationsList.value = data || []
    } catch (e) {
      console.warn('[IoTLayers] Failed to fetch env stations:', e)
      return []
    }
    _publishEnvMembers()
    return envStationsList.value
  }

  const addEnvStationLayers = async (map: any) => {
    const list = await loadEnvStations()
    const geojson = _envFeatures(list)
    const vis = envStationsEnabled.value ? 'visible' : 'none'

    if (map.getSource('env-stations')) {
      ;(map.getSource('env-stations') as any).setData(geojson)
      void _syncEnvHud(map)
      return
    }

    _ensureEnvIcons(map)
    map.addSource('env-stations', { type: 'geojson', data: geojson })

    map.addLayer({
      id: 'env-stations-icon', type: 'symbol', source: 'env-stations',
      layout: {
        'icon-image': ENV_ICON_IMAGE,
        'icon-offset': ['get', 'glIconOffset'],
        'icon-size': ['case', ['get', 'ensemble'], ENSEMBLE_ICON_SCALE, 1],
        'icon-allow-overlap': true,
        visibility: vis,
      },
      paint: { 'icon-opacity': ['case', ['get', 'stale'], 0.45, 1] },
      minzoom: DEVICE_MINZOOM,
    })

    // Click opens the standard MapFeaturePanel (dispatched in useMapClickDispatcher).
    attachHoverHex(map, 'env-stations-icon', 1.2, () => iotLockOnMarker)
    void _syncEnvHud(map)
  }

  // ---- HUD markers (instrument readout beside each hexagon; no GL label) ----
  // DOM overlays (utils/envHudMarker.ts): instrument column + compass bezel,
  // updated on every reading via the env WS. pointer-events: none — the
  // hexagon stays the sole click/hover target. Hidden below ENV_HUD_MINZOOM
  // (container class, shared with the mesh routers' HUD markers).
  const ENV_HUD_MINZOOM = 12
  /** Stations this close share a mast/wall — near enough for sensor rivalry. */
  const CO_LOCATED_M = 25
  const envHudMarkers = new Map<string, { marker: any, update: (v: any) => void }>()
  let envHudHandlersBound = false
  let envHudLockDimId: string | null = null

  /**
   * While a station is under the lock-on hex, mute its compass bezel (ring +
   * ticks — the wind pointer stays live): three concentric outlines within a
   * couple px of each other read as visual noise. null restores all bezels.
   */
  const setEnvHudLockDim = (id: string | null) => {
    envHudLockDimId = id
    for (const [sid, rec] of envHudMarkers) {
      rec.marker.getElement().classList.toggle('env-hud-lockdim', sid === id)
    }
  }

  const _removeEnvHud = () => {
    for (const rec of envHudMarkers.values()) rec.marker.remove()
    envHudMarkers.clear()
  }

  const _envHudViewSync = (map: any) => {
    const container = map.getContainer()
    container.classList.toggle('env-hud-below-zoom', map.getZoom() < ENV_HUD_MINZOOM)
    // Bezels counter-rotate so the north tick keeps its true geographic bearing
    container.style.setProperty('--map-bearing-neg', `${-map.getBearing()}deg`)
  }

  /**
   * Feed the ensemble layout the map scale — devices dock into one honeycomb
   * while they are closer than a lattice cell on screen, so the threshold has
   * to follow the zoom. Measured off the projection at the viewport center
   * rather than assumed from the zoom number (no tile-size constant).
   */
  const _syncEnsembleScale = (map: any) => {
    const center = map.getCenter()
    const p = map.project(center)
    const a = map.unproject([p.x - 32, p.y])
    const b = map.unproject([p.x + 32, p.y])
    setEnsembleScale(a.distanceTo(b) / 64)
  }

  /** Container-level zoom/bearing sync for ALL device HUDs (env + mesh). */
  const _bindHudViewSync = (map: any) => {
    if (!envHudHandlersBound) {
      map.on('zoom', () => { _envHudViewSync(map); _syncEnsembleScale(map) })
      map.on('rotate', () => _envHudViewSync(map))
      // Latitude changes the scale too — a long pan north or south moves it
      map.on('moveend', () => _syncEnsembleScale(map))
      envHudHandlersBound = true
    }
    _envHudViewSync(map)
    _syncEnsembleScale(map)
  }

  /** Instrument readout content for one station (+ its ensemble placement). */
  const _envHudView = (s: any, pl?: EnsemblePlacement, hideTemp = false) => {
    const latest = s.latest || {}
    const rows: Array<[string, string]> = []
    let primary = ''
    const temp = latest.temperature != null ? `${Number(latest.temperature).toFixed(1)}°` : ''
    if (latest.aqi != null) {
      const cat = latest.aqi_category ? t(`map.env.aqi.${latest.aqi_category}`) : ''
      primary = `AQI ${latest.aqi}${cat ? ` · ${cat}` : ''}`
      if (latest.pm25 != null) rows.push(['PM2.5', String(Math.round(latest.pm25))])
      if (latest.co2 != null) rows.push(['CO2', String(Math.round(latest.co2))])
      if (temp && !hideTemp) rows.push(['TEMP', temp])
    } else {
      primary = temp
      if (latest.wind_speed != null) {
        const spd = Math.round(latest.wind_speed)
        const gust = latest.wind_gust != null ? Math.round(latest.wind_gust) : null
        rows.push(['WIND', `${spd}${gust != null && gust > spd ? ` G${gust}` : ''}`])
      }
      if (latest.uv != null) rows.push(['UV', String(Math.round(latest.uv))])
      if (latest.humidity != null) rows.push(['RH', String(Math.round(latest.humidity))])
    }
    return {
      primary,
      rows,
      windDir: latest.wind_dir != null ? Number(latest.wind_dir) : null,
      stale: !!s.stale,
      ensemble: (pl?.groupSize || 1) > 1,
      side: pl?.side || 'right',
      topSlot: pl?.topSlot || false,
      nudge: pl?.nudge || null,
      hudLeft: pl?.hudLeft ?? null,
    }
  }

  const _syncEnvHud = async (map: any) => {
    if (typeof window === 'undefined') return
    if (!envStationsEnabled.value) { _removeEnvHud(); return }
    const maplibregl = ((await import('maplibre-gl')) as any).default || (await import('maplibre-gl'))
    const { createDeviceHudElement } = await import('~/utils/envHudMarker')
    // Re-check: the layer may have been toggled off while the imports resolved
    if (!envStationsEnabled.value) { _removeEnvHud(); return }
    const visible = _envVisible(envStationsList.value)
    const liveIds = new Set(visible.map((s: any) => s.id))
    for (const [id, rec] of envHudMarkers) {
      if (!liveIds.has(id)) { rec.marker.remove(); envHudMarkers.delete(id) }
    }
    // An air station's auxiliary TEMP loses to a co-located weather station's
    // shielded sensor (self-heating bias) — the clashing pair reads as a
    // contradiction, so only the weather column shows it. "Co-located" is
    // metric on purpose: ensemble membership is screen-space and spans
    // kilometres at low zoom, which says nothing about a shared shelter.
    const weatherTempStations = visible.filter(
      (s: any) => s.latest?.aqi == null && s.latest?.temperature != null,
    )
    const hasShieldedNeighbour = (s: any) => weatherTempStations.some((w: any) => {
      if (w.id === s.id) return false
      const dLat = (w.latitude - s.latitude) * 111320
      const dLon = (w.longitude - s.longitude) * 111320 * Math.cos(s.latitude * Math.PI / 180)
      return dLat * dLat + dLon * dLon <= CO_LOCATED_M * CO_LOCATED_M
    })
    for (const s of visible) {
      const pl = ensemblePlacement('env', s.id)
      const lngLat = pl?.anchor || [s.longitude, s.latitude]
      let rec = envHudMarkers.get(s.id)
      if (!rec) {
        const { el, update } = createDeviceHudElement()
        el.classList.toggle('env-hud-lockdim', s.id === envHudLockDimId)
        const marker = new maplibregl.Marker({ element: el, anchor: 'center', offset: pl?.offset || [0, 0] })
          .setLngLat(lngLat)
          .addTo(map)
        rec = { marker, update }
        envHudMarkers.set(s.id, rec)
      } else {
        rec.marker.setLngLat(lngLat)
        rec.marker.setOffset(pl?.offset || [0, 0])
      }
      const hideTemp = hasShieldedNeighbour(s)
      rec.update(_envHudView(s, pl, hideTemp))
    }
    _bindHudViewSync(map)
  }

  const refreshEnvStations = async () => {
    const map = mapStore.mapInstance
    if (!map || !map.getSource('env-stations')) return
    const list = await loadEnvStations()
    ;(map.getSource('env-stations') as any).setData(_envFeatures(list))
    void _syncEnvHud(map)
  }

  /** Patch a single station in-memory (from WS) and refresh its map dot. */
  const updateSingleEnvStation = (id: string, latest: any, lastReadingAt: string) => {
    const entry = envStationsList.value.find((s: any) => s.id === id)
    if (entry) {
      entry.latest = latest || {}
      entry.last_reading_at = lastReadingAt
      entry.stale = false
    }
    // First readings can flip a station's ensemble role (air/weather, wind)
    _publishEnvMembers()
    const map = mapStore.mapInstance
    if (!map || !map.getSource('env-stations')) return
    ;(map.getSource('env-stations') as any).setData(_envFeatures(envStationsList.value))
    void _syncEnvHud(map)
  }

  const toggleEnvStations = () => {
    envStationsEnabled.value = !envStationsEnabled.value
    const map = mapStore.mapInstance
    if (!map) return
    const vis = envStationsEnabled.value ? 'visible' : 'none'
    if (map.getLayer('env-stations-icon')) map.setLayoutProperty('env-stations-icon', 'visibility', vis)
    // Regroup the shared ensemble: stations leave on hide, rejoin on show
    _publishEnvMembers()
    void _syncEnvHud(map)
    if (envStationsEnabled.value && !envStationsRefreshInterval) {
      envStationsRefreshInterval = setInterval(refreshEnvStations, 120000)
    } else if (!envStationsEnabled.value && envStationsRefreshInterval) {
      clearInterval(envStationsRefreshInterval)
      envStationsRefreshInterval = null
    }
  }

  const flyToEnvStation = (lat: number, lng: number, _name: string) => {
    hideIoTPreview()
    const map = mapStore.mapInstance
    if (!map) return
    if (!envStationsEnabled.value) toggleEnvStations()
    const padding = getPanelPadding()
    if (animationEnabledCookie.value !== false) {
      map.flyTo({ center: [lng, lat], zoom: 15, essential: true, speed: 4.5, padding })
    } else {
      map.jumpTo({ center: [lng, lat], zoom: 15, padding })
    }
    iotPopoverOpen.value = false
  }

  // ======== Tracker Trail ========

  const trailVisible = ref(false)

  const showTrail = (map: any, geojson: any) => {
    clearTrail(map)
    if (!geojson) return

    map.addSource('tracker-trail', { type: 'geojson', data: geojson, lineMetrics: true })

    map.addLayer({
      id: 'tracker-trail-casing',
      type: 'line',
      source: 'tracker-trail',
      filter: ['==', ['get', 'role'], 'trail'],
      paint: {
        'line-color': '#000000',
        'line-width': 5,
        'line-opacity': 0.2,
        'line-gradient': [
          'interpolate', ['linear'], ['line-progress'],
          0, 'rgba(0,0,0,0.2)',
          1, 'rgba(0,0,0,0.35)',
        ],
      },
      layout: { 'line-cap': 'round', 'line-join': 'round' },
    })

    map.addLayer({
      id: 'tracker-trail-line',
      type: 'line',
      source: 'tracker-trail',
      filter: ['==', ['get', 'role'], 'trail'],
      paint: {
        'line-width': 3,
        'line-opacity': 0.9,
        'line-gradient': [
          'interpolate', ['linear'], ['line-progress'],
          0, '#06b6d4',    // cyan (start)
          0.5, '#8b5cf6',  // violet (midpoint)
          1, '#ec4899',    // magenta (end)
        ],
      },
      layout: { 'line-cap': 'round', 'line-join': 'round' },
    })

    map.addLayer({
      id: 'tracker-trail-start',
      type: 'circle',
      source: 'tracker-trail',
      filter: ['==', ['get', 'role'], 'start'],
      paint: { 'circle-radius': 6, 'circle-color': '#06b6d4', 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 2 },
    })

    map.addLayer({
      id: 'tracker-trail-end',
      type: 'circle',
      source: 'tracker-trail',
      filter: ['==', ['get', 'role'], 'end'],
      paint: { 'circle-radius': 6, 'circle-color': '#ec4899', 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 2 },
    })

    trailVisible.value = true
  }

  const clearTrail = (map: any) => {
    for (const id of ['tracker-trail-cursor', 'tracker-trail-end', 'tracker-trail-start', 'tracker-trail-line', 'tracker-trail-casing']) {
      if (map.getLayer(id)) map.removeLayer(id)
    }
    if (map.getSource('tracker-trail-cursor')) map.removeSource('tracker-trail-cursor')
    if (map.getSource('tracker-trail')) map.removeSource('tracker-trail')
    trailVisible.value = false
  }

  /** Update playback cursor position on the trail. */
  const updateTrailCursor = (map: any, lng: number, lat: number, heading: number | null) => {
    const geojson = {
      type: 'FeatureCollection' as const,
      features: [{
        type: 'Feature' as const,
        properties: { heading: heading ?? 0 },
        geometry: { type: 'Point' as const, coordinates: [lng, lat] },
      }],
    }

    if (map.getSource('tracker-trail-cursor')) {
      ;(map.getSource('tracker-trail-cursor') as any).setData(geojson)
      return
    }

    map.addSource('tracker-trail-cursor', { type: 'geojson', data: geojson })
    map.addLayer({
      id: 'tracker-trail-cursor',
      type: 'circle',
      source: 'tracker-trail-cursor',
      paint: {
        'circle-radius': 8,
        'circle-color': '#ffffff',
        'circle-stroke-color': '#000000',
        'circle-stroke-width': 2.5,
      },
    })
  }

  // ======== Lifecycle ========

  // Other layers' ensemble publishes (mesh toggling, a router going live)
  // regroup our members — re-render env + energy from cache. Listeners never
  // publish (see useMapDeviceEnsembles.ts).
  onEnsembleChange('iot-layers', () => {
    const map = mapStore.mapInstance
    if (!map) return
    const envSrc = map.getSource('env-stations')
    if (envSrc) {
      ;(envSrc as any).setData(_envFeatures(envStationsList.value))
      void _syncEnvHud(map)
    }
    const energySrc = map.getSource('energy-cells-points')
    if (energySrc) (energySrc as any).setData(_energyPointFeatures(energyCellsList.value))
    const trackerSrc = map.getSource('trackers')
    if (trackerSrc) (trackerSrc as any).setData(_trackerGeoJSON(trackerPositionsList.value))
    _resyncIoTLockOn()
  })

  function setupLayers(map: any) {
    addTrackerLayers(map)
    if (trackersEnabled.value) {
      trackerRefreshInterval = setInterval(refreshTrackerPositions, 30000)
    }
    // Load mesh router data for IoT popover list (map layer is public, see useMapMeshLayer)
    loadMeshRouterPositions()
    addEnergyCellLayers(map)
    if (energyCellsEnabled.value) {
      energyCellsRefreshInterval = setInterval(refreshEnergyCells, 120000)
    }
    addEnvStationLayers(map)
    if (envStationsEnabled.value) {
      envStationsRefreshInterval = setInterval(refreshEnvStations, 120000)
    }
    // Zoom/bearing sync for all device HUD markers (env + mesh) — bound even
    // when the env layer starts toggled off
    _bindHudViewSync(map)
  }

  /** Re-add layers after style change (no intervals — they persist). */
  function setupLayersOnly(map: any) {
    addTrackerLayers(map)
    addEnergyCellLayers(map)
    addEnvStationLayers(map)
    _bindHudViewSync(map)
  }

  function pauseRefresh() {
    if (trackerRefreshInterval) { clearInterval(trackerRefreshInterval); trackerRefreshInterval = null }
    if (energyCellsRefreshInterval) { clearInterval(energyCellsRefreshInterval); energyCellsRefreshInterval = null }
    if (envStationsRefreshInterval) { clearInterval(envStationsRefreshInterval); envStationsRefreshInterval = null }
  }

  function resumeRefresh() {
    if (trackersEnabled.value && !trackerRefreshInterval) {
      trackerRefreshInterval = setInterval(refreshTrackerPositions, 30000)
      refreshTrackerPositions()
    }
    if (energyCellsEnabled.value && !energyCellsRefreshInterval) {
      energyCellsRefreshInterval = setInterval(refreshEnergyCells, 120000)
      refreshEnergyCells()
    }
    if (envStationsEnabled.value && !envStationsRefreshInterval) {
      envStationsRefreshInterval = setInterval(refreshEnvStations, 120000)
      refreshEnvStations()
    }
  }

  /** Update a single tracker position in-memory (from WS) without full HTTP fetch. */
  const updateSingleTracker = (deviceId: string, lat: number, lon: number, speed: number, status: string) => {
    const map = mapStore.mapInstance
    // Update list
    const entry = trackerPositionsList.value.find((t: any) => t.device_id === deviceId)
    if (entry) {
      entry.latitude = lat
      entry.longitude = lon
      entry.speed = speed
      entry.traccar_status = status
    }
    // A tracker that started (or stopped) moving joins or leaves the ensemble;
    // the change listener re-renders this source and the co-located layers
    _publishTrackerMembers()
    // Update map source
    if (!map || !map.getSource('trackers')) return
    ;(map.getSource('trackers') as any).setData(_trackerGeoJSON(trackerPositionsList.value))
  }

  function cleanup() {
    pauseRefresh()
    hideIoTPreview()
    hideIoTLockOn()
    _removeEnvHud()
  }

  return {
    // State (for template)
    trackersEnabled,
    trackerPositionsList,
    meshRouterPositionsList,
    energyCellsEnabled,
    energyCellsList,
    envStationsEnabled,
    envStationsList,
    iotPopoverOpen,
    iotRoutersExpanded,
    iotTrackersExpanded,
    iotEnergyCellsExpanded,
    // Setup
    setupLayers,
    setupLayersOnly,
    // Actions
    toggleTrackers,
    toggleEnergyCells,
    toggleEnvStations,
    flyToTracker,
    flyToMeshRouter,
    flyToEnergyCell,
    flyToEnvStation,
    updateSingleEnvStation,
    setEnvHudLockDim,
    getPanelPadding,
    showIoTPreview,
    hideIoTPreview,
    showIoTLockOn,
    hideIoTLockOn,
    moveIoTLockOn,
    replayIoTLockOn,
    updateSingleTracker,
    // Follow mode
    isFollowing,
    enableFollow,
    disableFollow,
    followToPosition,
    // Trail
    trailVisible,
    showTrail,
    clearTrail,
    updateTrailCursor,
    // Lifecycle
    pauseRefresh,
    resumeRefresh,
    cleanup,
  }
}
