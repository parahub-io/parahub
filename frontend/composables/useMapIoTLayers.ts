/**
 * IoT map layers: GPS Trackers + Mesh Routers + Energy Cells.
 *
 * Extracted from MapView.vue lines 347-366, 582-1101.
 */

import { ref, nextTick } from 'vue'
import { attachHoverHex } from '~/composables/useMapHighlight'

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

export function useMapIoTLayers() {
  const authStore = useAuthStore()
  const mapStore = useMapStore()

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

  const showIoTLockOn = async (lat: number, lon: number) => {
    hideIoTLockOn()
    const map = mapStore.mapInstance
    if (!map) return
    if (!maplibreglCache) maplibreglCache = await import('maplibre-gl').then(m => m.default || m)
    const { createLockOnElement, flashCrosshair } = await import('~/utils/lockOnMarker')
    iotLockOnMarker = new maplibreglCache.Marker({ element: createLockOnElement({ noDot: true }), anchor: 'center' })
      .setLngLat([lon, lat])
      .addTo(map)
    // Flash crosshair when lock-in animation finishes
    setTimeout(() => {
      if (!iotLockOnMarker) return // already hidden
      const pt = map.project([lon, lat])
      flashCrosshair(map.getContainer(), Math.round(pt.x), Math.round(pt.y))
    }, 450)
  }

  const hideIoTLockOn = () => {
    if (iotLockOnMarker) { iotLockOnMarker.remove(); iotLockOnMarker = null }
  }

  /** Move existing lock-on marker without restarting animation. */
  const moveIoTLockOn = (lat: number, lon: number) => {
    if (iotLockOnMarker) {
      iotLockOnMarker.setLngLat([lon, lat])
    }
  }

  /** Remove + recreate lock-on to replay CSS animation. */
  const replayIoTLockOn = async (lat: number, lon: number) => {
    hideIoTLockOn()
    await nextTick()
    showIoTLockOn(lat, lon)
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
    iotPreviewMarker = new maplibreglCache.Marker({ element: createLockOnElement({ noDot: true }), anchor: 'center' })
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
      <div class="edge-ind-lock edge-ind-lock-b1"></div>
      <div class="edge-ind-lock edge-ind-lock-b2"></div>
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
      return positions
    } catch (e) {
      console.warn('[IoTLayers] Failed to fetch tracker positions:', e)
      return []
    }
  }

  /** Generate a flat-top hexagon icon on canvas and add to the map. */
  const _ensureHexIcon = (map: any, id: string, fill: string, size = 18) => {
    if (map.hasImage(id)) return
    const s = size * 2 // draw at 2x for retina
    const r = s / 2
    const canvas = document.createElement('canvas')
    canvas.width = s
    canvas.height = s
    const ctx = canvas.getContext('2d')!
    ctx.beginPath()
    for (let i = 0; i < 6; i++) {
      const angle = (Math.PI / 3) * i
      const x = r + (r - 3) * Math.cos(angle)
      const y = r + (r - 3) * Math.sin(angle)
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
    }
    ctx.closePath()
    ctx.fillStyle = fill
    ctx.fill()
    map.addImage(id, { width: s, height: s, data: ctx.getImageData(0, 0, s, s).data }, { pixelRatio: 2 })
  }

  const addTrackerLayers = async (map: any) => {
    if (!authStore.isAuthenticated) return

    const positions = await loadTrackerPositions()
    const geojson = {
      type: 'FeatureCollection' as const,
      features: positions.map((p: any) => ({
        type: 'Feature' as const,
        properties: {
          device_id: p.device_id,
          name: p.name,
          speed: p.speed ? `${Math.round(p.speed)} km/h` : '',
          status: p.traccar_status || 'unknown',
        },
        geometry: { type: 'Point' as const, coordinates: [p.longitude, p.latitude] },
      })),
    }

    if (map.getSource('trackers')) {
      ;(map.getSource('trackers') as any).setData(geojson)
      return
    }

    // Generate hexagon icons for each status
    _ensureHexIcon(map, 'tracker-hex-online', '#4E4EC8')
    _ensureHexIcon(map, 'tracker-hex-unknown', '#a3a3a3')
    _ensureHexIcon(map, 'tracker-hex-offline', '#ef4444')

    map.addSource('trackers', { type: 'geojson', data: geojson })

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
        'icon-allow-overlap': true,
        visibility: trackersEnabled.value ? 'visible' : 'none',
      },
    })

    map.addLayer({
      id: 'trackers-label',
      type: 'symbol',
      source: 'trackers',
      layout: {
        'text-field': ['get', 'name'],
        'text-size': 11,
        'text-offset': [0, 1.5],
        'text-anchor': 'top',
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
    const geojson = {
      type: 'FeatureCollection' as const,
      features: positions.map((p: any) => ({
        type: 'Feature' as const,
        properties: {
          device_id: p.device_id,
          name: p.name,
          speed: p.speed ? `${Math.round(p.speed)} km/h` : '',
          status: p.traccar_status || 'unknown',
        },
        geometry: { type: 'Point' as const, coordinates: [p.longitude, p.latitude] },
      })),
    }
    ;(map.getSource('trackers') as any).setData(geojson)
  }

  const toggleTrackers = () => {
    trackersEnabled.value = !trackersEnabled.value
    const map = mapStore.mapInstance
    if (!map) return
    const vis = trackersEnabled.value ? 'visible' : 'none'
    if (map.getLayer('trackers-circle')) map.setLayoutProperty('trackers-circle', 'visibility', vis)
    if (map.getLayer('trackers-label')) map.setLayoutProperty('trackers-label', 'visibility', vis)

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

  const STATUS_COLORS: Record<string, string> = {
    GREEN: '#22c55e', YELLOW: '#eab308', RED: '#ef4444', OFFLINE: '#6b7280',
  }

  const loadEnergyCells = async (): Promise<any[]> => {
    try {
      const data = await $fetch<any[]>('/api/v1/energy/cells/map/')
      energyCellsList.value = data || []
      return energyCellsList.value
    } catch (e) {
      console.warn('[IoTLayers] Failed to fetch energy cells:', e)
      return []
    }
  }

  const addEnergyCellLayers = async (map: any) => {
    const cells = await loadEnergyCells()

    const radiusFeatures = cells.map((c: any) => ({
      type: 'Feature' as const,
      properties: { id: c.id, name: c.name, status: c.status, price: c.current_price_eur, color: STATUS_COLORS[c.status] || '#6b7280' },
      geometry: _geojsonCircle(c.longitude, c.latitude, c.radius_km),
    }))

    const pointFeatures = cells.map((c: any) => ({
      type: 'Feature' as const,
      properties: { id: c.id, name: c.name, status: c.status, price: c.current_price_eur, color: STATUS_COLORS[c.status] || '#6b7280' },
      geometry: { type: 'Point' as const, coordinates: [c.longitude, c.latitude] },
    }))

    const radiusGeoJSON = { type: 'FeatureCollection' as const, features: radiusFeatures }
    const pointGeoJSON = { type: 'FeatureCollection' as const, features: pointFeatures }
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
    })

    map.addLayer({
      id: 'energy-cells-border', type: 'line', source: 'energy-cells-radius',
      paint: { 'line-color': ['get', 'color'], 'line-width': 1.5, 'line-dasharray': [4, 3], 'line-opacity': 0.6 },
      layout: { visibility: vis },
    })

    // Generate hex icons for each energy status
    for (const [status, color] of Object.entries(STATUS_COLORS)) {
      _ensureHexIcon(map, `energy-hex-${status}`, color)
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
        'icon-allow-overlap': true,
        visibility: vis,
      },
    })

    map.addLayer({
      id: 'energy-cells-label', type: 'symbol', source: 'energy-cells-points',
      layout: {
        'text-field': ['case', ['!=', ['get', 'price'], null], ['concat', ['get', 'name'], '\n', ['to-string', ['get', 'price']], '€/kWh'], ['get', 'name']],
        'text-size': 11, 'text-offset': [0, 1.4], 'text-anchor': 'top', 'text-optional': true,
        visibility: vis,
      },
      paint: { 'text-color': '#111827', 'text-halo-color': '#ffffff', 'text-halo-width': 1.5 },
      minzoom: 11,
    })

    attachHoverHex(map, 'energy-cells-circle', 1.2, () => iotLockOnMarker)
  }

  const refreshEnergyCells = async () => {
    const map = mapStore.mapInstance
    if (!map || !map.getSource('energy-cells-radius')) return
    const cells = await loadEnergyCells()

    const radiusFeatures = cells.map((c: any) => ({
      type: 'Feature' as const,
      properties: { id: c.id, name: c.name, status: c.status, price: c.current_price_eur, color: STATUS_COLORS[c.status] || '#6b7280' },
      geometry: _geojsonCircle(c.longitude, c.latitude, c.radius_km),
    }))
    const pointFeatures = cells.map((c: any) => ({
      type: 'Feature' as const,
      properties: { id: c.id, name: c.name, status: c.status, price: c.current_price_eur, color: STATUS_COLORS[c.status] || '#6b7280' },
      geometry: { type: 'Point' as const, coordinates: [c.longitude, c.latitude] },
    }))

    ;(map.getSource('energy-cells-radius') as any).setData({ type: 'FeatureCollection', features: radiusFeatures })
    ;(map.getSource('energy-cells-points') as any).setData({ type: 'FeatureCollection', features: pointFeatures })
  }

  const toggleEnergyCells = () => {
    energyCellsEnabled.value = !energyCellsEnabled.value
    const map = mapStore.mapInstance
    if (!map) return
    const vis = energyCellsEnabled.value ? 'visible' : 'none'
    for (const id of ['energy-cells-fill', 'energy-cells-border', 'energy-cells-circle', 'energy-cells-label']) {
      if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', vis)
    }
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
  }

  /** Re-add layers after style change (no intervals — they persist). */
  function setupLayersOnly(map: any) {
    addTrackerLayers(map)
    addEnergyCellLayers(map)
  }

  function pauseRefresh() {
    if (trackerRefreshInterval) { clearInterval(trackerRefreshInterval); trackerRefreshInterval = null }
    if (energyCellsRefreshInterval) { clearInterval(energyCellsRefreshInterval); energyCellsRefreshInterval = null }
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
    // Update map source
    if (!map || !map.getSource('trackers')) return
    const geojson = {
      type: 'FeatureCollection' as const,
      features: trackerPositionsList.value.map((p: any) => ({
        type: 'Feature' as const,
        properties: {
          device_id: p.device_id,
          name: p.name,
          speed: p.speed ? `${Math.round(p.speed)} km/h` : '',
          status: p.traccar_status || 'unknown',
        },
        geometry: { type: 'Point' as const, coordinates: [p.longitude, p.latitude] },
      })),
    }
    ;(map.getSource('trackers') as any).setData(geojson)
  }

  function cleanup() {
    pauseRefresh()
    hideIoTPreview()
    hideIoTLockOn()
  }

  return {
    // State (for template)
    trackersEnabled,
    trackerPositionsList,
    meshRouterPositionsList,
    energyCellsEnabled,
    energyCellsList,
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
    flyToTracker,
    flyToMeshRouter,
    flyToEnergyCell,
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
