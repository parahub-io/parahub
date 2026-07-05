/**
 * Transit stops/routes/vehicles on map + WebSocket wrapper.
 *
 * Extracted from MapView.vue lines 368-370, 1103-1510.
 */

import { ref, onScopeDispose } from 'vue'
import { attachHoverHex } from '~/composables/useMapHighlight'
import { createVehicleAnimator } from '~/utils/vehicleAnimator'

export function useMapTransitLayers() {
  const mapStore = useMapStore()
  const { resolveColor } = useTransitHelpers()
  const colorMode = useColorMode()

  const transitEnabled = useLocalPref('transit_enabled', false)
  const transitExpanded = ref(false)
  const activeRouteFilter = ref<string | null>(null)  // route_source_id for single-route mode
  // Last drawn single-route overlay — kept so the overlay can be redrawn after a
  // style change (setStyle wipes it) without re-fetching or re-fitting the camera.
  let lastRouteDetail: any = null
  let lastRouteCity: string | null = null
  let lastRouteSlug: string | null = null
  let transitDataLoaded = false
  let lastStopsBbox: string | null = null  // last fetched stops-geojson bbox (cache-grid aligned)

  // Stored handler refs for cleanup on re-init (prevents accumulation on style change)
  let _moveendHandler: (() => void) | null = null
  let _imageMissingHandler: ((e: any) => void) | null = null
  let _vehicleClickHandler: ((e: any) => void) | null = null
  const VEHICLE_CLICK_LAYERS = [
    'transit-vehicles-circle', 'transit-vehicles-icon',
    'transit-vehicles-heading', 'transit-vehicles-bar',
  ]

  // Vehicle click callback — set by MapView to dispatch to panel
  let onVehicleClick: ((vehicle: any) => void) | null = null
  function setVehicleClickHandler(handler: (vehicle: any) => void) {
    onVehicleClick = handler
  }

  // Transit vehicles WebSocket (public, no auth)
  const {
    connect: connectTransitWs,
    disconnect: disconnectTransitWs,
    subscribeBbox: subscribeTransitBbox,
    updateBbox: updateTransitBbox,
    toGeoJSON: transitToGeoJSON,
    isConnected: isTransitWsConnected,
    onUpdate: onTransitUpdate,
  } = useTransitVehicles()

  // Glide vehicle icons to each new WS position over 1s instead of snapping.
  const vehicleAnimator = createVehicleAnimator({
    getKey: (f: any) => f.properties.vehicle_id,
    apply: (fc: any) => {
      const map = mapStore.mapInstance
      const source = map?.getSource('transit-vehicles')
      if (source) (source as any).setData(fc)
    },
  })

  // ======== Static layers (stops) ========

  // Zoom policy: below STOP_DETAIL_ZOOM one virtual pin per stop group (plus
  // ungrouped physical stops); above it the real poles — street navigation
  // needs the road side. See PK/transit-system.md § Virtual stops.
  const STOP_DETAIL_ZOOM = 17

  function addTransitStopLayers(map: any) {
    for (const id of ['transit-stops-circle', 'transit-stops-label',
                      'transit-stops-virtual-circle', 'transit-stops-virtual-label']) {
      if (map.getLayer(id)) map.removeLayer(id)
    }
    if (map.getSource('transit-stops')) map.removeSource('transit-stops')

    const empty = { type: 'FeatureCollection', features: [] }
    map.addSource('transit-stops', { type: 'geojson', data: empty })

    const vis = transitEnabled.value ? 'visible' : 'none'
    // Virtual stops + physical stops that belong to no group
    const collapsedFilter = ['any',
      ['==', ['get', 'kind'], 'virtual'],
      ['!', ['has', 'group_id']],
    ]
    // Real poles/platforms only (the virtual features drop out)
    const physicalFilter = ['!=', ['get', 'kind'], 'virtual']

    const circlePaint = {
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 1.5, 14, 4, 18, 7],
      'circle-color': '#3b82f6',
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 10, 0, 14, 1, 18, 2],
    }
    const labelLayout = {
      'text-field': ['get', 'name'],
      'text-size': 10,
      'text-offset': [0, 1.2],
      'text-anchor': 'top',
      'text-optional': true,
      visibility: vis,
    }
    const labelPaint = {
      'text-color': '#1e40af',
      'text-halo-color': '#ffffff',
      'text-halo-width': 1.5,
    }

    map.addLayer({
      id: 'transit-stops-virtual-circle',
      type: 'circle',
      source: 'transit-stops',
      filter: collapsedFilter,
      paint: circlePaint,
      layout: { visibility: vis },
      minzoom: 12,
      maxzoom: STOP_DETAIL_ZOOM,
    })

    map.addLayer({
      id: 'transit-stops-virtual-label',
      type: 'symbol',
      source: 'transit-stops',
      filter: collapsedFilter,
      layout: labelLayout,
      paint: labelPaint,
      minzoom: 15,
      maxzoom: STOP_DETAIL_ZOOM,
    })

    map.addLayer({
      id: 'transit-stops-circle',
      type: 'circle',
      source: 'transit-stops',
      filter: physicalFilter,
      paint: circlePaint,
      layout: { visibility: vis },
      minzoom: STOP_DETAIL_ZOOM,
    })

    map.addLayer({
      id: 'transit-stops-label',
      type: 'symbol',
      source: 'transit-stops',
      filter: physicalFilter,
      layout: labelLayout,
      paint: labelPaint,
      minzoom: STOP_DETAIL_ZOOM,
    })

    if (transitEnabled.value) {
      loadTransitData(map)
    }
  }

  /** Viewport bbox padded outward to the backend's 2-decimal cache grid —
   * stable cache keys, no edge stops lost to rounding. */
  function stopsBboxParam(map: any): string | null {
    const zoom = map.getZoom?.()
    if (zoom != null && zoom < 10) return null  // stop layers invisible below 12 — skip churn
    const b = map.getBounds()
    const f = (v: number, up: boolean) => ((up ? Math.ceil : Math.floor)(v * 100) / 100).toFixed(2)
    return `${f(b.getWest(), false)},${f(b.getSouth(), false)},${f(b.getEast(), true)},${f(b.getNorth(), true)}`
  }

  async function loadTransitData(map: any) {
    const bbox = stopsBboxParam(map)
    if (bbox === lastStopsBbox && transitDataLoaded) return
    transitDataLoaded = true
    lastStopsBbox = bbox

    try {
      const stopsData = await $fetch<any>('/api/v1/geo/transit/stops/geojson/',
        bbox ? { params: { bbox } } : undefined)
      if (map.getSource('transit-stops')) {
        ;(map.getSource('transit-stops') as any).setData(stopsData)
      }
    } catch (e) {
      console.warn('Failed to load transit stops:', e)
    }
  }

  // ======== Route overlay ========

  async function showRouteOnMap(map: any, routeCity: string, routeSlug: string, opts: { fitBounds?: boolean } = {}) {
    const { fitBounds = true } = opts
    try {
      let routeDetail = (window as any)._transitRouteData
      if (routeDetail?.slug === routeSlug) {
        delete (window as any)._transitRouteData
      } else if (lastRouteDetail && lastRouteCity === routeCity && lastRouteSlug === routeSlug) {
        routeDetail = lastRouteDetail  // redraw (e.g. after style change) — no refetch
      } else {
        routeDetail = await $fetch<any>(`/api/v1/geo/transit/routes/${routeCity}/${routeSlug}/`)
      }
      lastRouteDetail = routeDetail
      lastRouteCity = routeCity
      lastRouteSlug = routeSlug

      // Filter vehicles to this route only
      activeRouteFilter.value = routeDetail.source_id || null
      applyVehicleIconZoomRange(map)  // show icons at the route-fit zoom (often <13)

      for (const id of ['transit-route-line', 'transit-route-line-casing', 'transit-route-stops']) {
        if (map.getLayer(id)) map.removeLayer(id)
      }
      for (const id of ['transit-route-geom', 'transit-route-stops-src']) {
        if (map.getSource(id)) map.removeSource(id)
      }

      // Casing/outline color contrasting with the basemap (dark on light theme,
      // light on dark) so colorless feeds (default bus yellow) stay visible —
      // for both the route line and the stop dots. See mini-map note in [slug].vue.
      const lineCasing = colorMode.value === 'dark' ? '#f1f5f9' : '#1e293b'

      if (routeDetail.geometry) {
        map.addSource('transit-route-geom', {
          type: 'geojson',
          data: { type: 'Feature', geometry: routeDetail.geometry, properties: {} },
        })
        const color = `#${resolveColor(routeDetail)}`
        map.addLayer({
          id: 'transit-route-line-casing',
          type: 'line',
          source: 'transit-route-geom',
          paint: { 'line-color': lineCasing, 'line-width': 7, 'line-opacity': 0.9 },
          layout: { 'line-cap': 'round', 'line-join': 'round' },
        })
        map.addLayer({
          id: 'transit-route-line',
          type: 'line',
          source: 'transit-route-geom',
          paint: { 'line-color': color, 'line-width': 4, 'line-opacity': 1 },
          layout: { 'line-cap': 'round', 'line-join': 'round' },
        })
      }

      if (routeDetail.stops?.length) {
        const stopsGeoJSON = {
          type: 'FeatureCollection',
          features: routeDetail.stops.map((s: any) => ({
            type: 'Feature',
            geometry: { type: 'Point', coordinates: [s.lon, s.lat] },
            properties: { name: s.name, sequence: s.sequence },
          })),
        }
        map.addSource('transit-route-stops-src', { type: 'geojson', data: stopsGeoJSON })
        const color = `#${resolveColor(routeDetail)}`
        map.addLayer({
          id: 'transit-route-stops',
          type: 'circle',
          source: 'transit-route-stops-src',
          paint: {
            'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 3, 14, 6, 18, 9],
            'circle-color': color,
            'circle-stroke-color': lineCasing,
            'circle-stroke-width': 2,
          },
        })

        const coords = routeDetail.stops.map((s: any) => [s.lon, s.lat])
        if (routeDetail.geometry?.coordinates?.length) {
          coords.push(...routeDetail.geometry.coordinates)
        }
        const bounds = coords.reduce(
          (b: any, c: [number, number]) => {
            return [
              [Math.min(b[0][0], c[0]), Math.min(b[0][1], c[1])],
              [Math.max(b[1][0], c[0]), Math.max(b[1][1], c[1])],
            ]
          },
          [[Infinity, Infinity], [-Infinity, -Infinity]]
        )
        if (fitBounds) map.fitBounds(bounds, { padding: 60, duration: 0 })
      }
    } catch (e) {
      console.warn('Failed to show transit route on map:', e)
    }
  }

  // Re-add the single-route overlay after a style change wiped it, reusing the
  // cached detail (no refetch) and leaving the camera where the user left it.
  // No-op when no route overlay is active.
  function redrawActiveRoute(map: any) {
    if (lastRouteDetail && lastRouteCity && lastRouteSlug) {
      showRouteOnMap(map, lastRouteCity, lastRouteSlug, { fitBounds: false })
    }
  }

  function removeRouteOverlay(map: any) {
    activeRouteFilter.value = null
    lastRouteDetail = null
    lastRouteCity = null
    lastRouteSlug = null
    applyVehicleIconZoomRange(map)  // restore global z13 icon threshold
    for (const id of ['transit-route-line', 'transit-route-line-casing', 'transit-route-stops']) {
      if (map.getLayer(id)) map.removeLayer(id)
    }
    for (const id of ['transit-route-geom', 'transit-route-stops-src']) {
      if (map.getSource(id)) map.removeSource(id)
    }
  }

  // ======== Live vehicles ========

  // Map GTFS route_type → icon name
  const ROUTE_TYPE_ICON: Record<number, string> = {
    0: 'tram', 1: 'metro', 2: 'train', 3: 'bus', 4: 'ferry',
    7: 'train', 11: 'trolleybus', 200: '2bus', 1100: 'airplane', 1501: 'bus-taxi',
  }

  function resolveIconName(routeType: number): string {
    if (ROUTE_TYPE_ICON[routeType]) return ROUTE_TYPE_ICON[routeType]
    if (routeType >= 200 && routeType <= 299) return '2bus'
    if (routeType >= 900 && routeType <= 999) return 'tram'
    if (routeType >= 100 && routeType <= 199) return 'train'
    if (routeType >= 400 && routeType <= 499) return 'metro'
    if (routeType >= 700 && routeType <= 799) return 'bus'
    if (routeType >= 1500 && routeType <= 1599) return 'bus-taxi'
    return 'bus'
  }

  /** Load a single SVG as a MapLibre image via canvas rendering. */
  function loadSvgIcon(map: any, imageId: string, url: string, size: number, grayscale = false): Promise<void> {
    return new Promise((resolve) => {
      if (map.hasImage(imageId)) { resolve(); return }
      const img = new Image(size, size)
      img.crossOrigin = 'anonymous'
      img.onload = () => {
        const canvas = document.createElement('canvas')
        canvas.width = size
        canvas.height = size
        const ctx = canvas.getContext('2d')!
        if (grayscale) ctx.filter = 'grayscale(100%) brightness(0.8)'
        ctx.drawImage(img, 0, 0, size, size)
        const imageData = ctx.getImageData(0, 0, size, size)
        map.addImage(imageId, { width: size, height: size, data: new Uint8Array(imageData.data.buffer) })
        resolve()
      }
      img.onerror = () => resolve()
      img.src = url
    })
  }

  /** Load all transit vehicle type icons into MapLibre (colored + grayscale for stationary). */
  async function ensureTransitIcons(map: any) {
    const iconNames = ['bus', 'tram', 'metro', 'train', 'ferry', 'trolleybus', 'bus-taxi', '2bus', 'airplane']
    const size = 48
    await Promise.all([
      ...iconNames.map(name => loadSvgIcon(map, `transit-${name}`, `/img/transit/${name}.svg`, size)),
      ...iconNames.map(name => loadSvgIcon(map, `transit-${name}-gray`, `/img/transit/${name}.svg`, size, true)),
    ])
  }

  /** Direction chevron — two sides of the brand flat-top hexagon (same corner
   * geometry as the lock-on marker: 120° apex, arms at 30°). The vehicle icon
   * stays upright; this chevron alone rotates by bearing. 2x raster, logical 48x20. */
  function ensureHeadingChevron(map: any) {
    if (map.hasImage('transit-heading')) return
    const W = 96, H = 40
    const canvas = document.createElement('canvas')
    canvas.width = W
    canvas.height = H
    const ctx = canvas.getContext('2d')!
    ctx.strokeStyle = '#f4c110'
    ctx.lineWidth = 8
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'
    ctx.beginPath()
    ctx.moveTo(6, 30)
    ctx.lineTo(48, 6)
    ctx.lineTo(90, 30)
    ctx.stroke()
    const data = ctx.getImageData(0, 0, W, H)
    map.addImage('transit-heading', { width: W, height: H, data: new Uint8Array(data.data.buffer) }, { pixelRatio: 2 })
  }

  /** Route-color bar under the icon — generated lazily per color (2x raster, logical 44x6). */
  function makeRouteBarImage(map: any, imageId: string, color: string) {
    if (map.hasImage(imageId)) return
    const W = 88, H = 12
    const canvas = document.createElement('canvas')
    canvas.width = W
    canvas.height = H
    const ctx = canvas.getContext('2d')!
    if (/^[0-9a-fA-F]{6}$/.test(color)) {
      ctx.fillStyle = `#${color}`
      ctx.fillRect(0, 0, W, H)
    }
    // Malformed feed color → transparent image (still registered, stops styleimagemissing refiring)
    const data = ctx.getImageData(0, 0, W, H)
    map.addImage(imageId, { width: W, height: H, data: new Uint8Array(data.data.buffer) }, { pixelRatio: 2 })
  }

  // Single-route focus shows only a handful of vehicles, so transit icons render
  // at every zoom (matches the route-page mini-map). The global view keeps a z13
  // threshold so hundreds of icons don't clutter / thrash at low zoom.
  const VEHICLE_ICON_MIN_ZOOM = 13
  const VEHICLE_SYMBOL_LAYERS = ['transit-vehicles-icon', 'transit-vehicles-heading', 'transit-vehicles-bar']
  function applyVehicleIconZoomRange(map: any) {
    if (!map) return
    const minzoom = activeRouteFilter.value ? 0 : VEHICLE_ICON_MIN_ZOOM
    for (const id of VEHICLE_SYMBOL_LAYERS) {
      if (map.getLayer(id)) map.setLayerZoomRange(id, minzoom, 24)
    }
  }

  function addTransitVehicleLayers(map: any) {
    for (const id of [...VEHICLE_SYMBOL_LAYERS, 'transit-vehicles-circle']) {
      if (map.getLayer(id)) map.removeLayer(id)
    }
    if (map.getSource('transit-vehicles')) map.removeSource('transit-vehicles')

    const empty = { type: 'FeatureCollection', features: [] }
    map.addSource('transit-vehicles', { type: 'geojson', data: empty })

    const vis = transitEnabled.value ? 'visible' : 'none'

    // Small colored circles at low zoom (gray for stationary/zombie vehicles)
    map.addLayer({
      id: 'transit-vehicles-circle',
      type: 'circle',
      source: 'transit-vehicles',
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 3, 13, 5],
        'circle-color': ['case', ['==', ['get', 'zombie'], 1], '#888888', ['concat', '#', ['get', 'route_color']]],
        'circle-stroke-color': ['case', ['==', ['get', 'zombie'], 1], '#666666', '#ffffff'],
        'circle-stroke-width': 1.5,
        'circle-opacity': ['case', ['==', ['get', 'zombie'], 1], 0.6, 1],
      },
      layout: { visibility: vis },
      minzoom: 10,
      maxzoom: 13,
    })

    // Lazy per-color bar images (route colors arrive with WS data, unbounded set)
    if (_imageMissingHandler) map.off('styleimagemissing', _imageMissingHandler)
    _imageMissingHandler = (e: any) => {
      if (!e.id.startsWith('transit-bar-')) return
      makeRouteBarImage(map, e.id, e.id.slice('transit-bar-'.length))
    }
    map.on('styleimagemissing', _imageMissingHandler)

    const symbolSize = ['interpolate', ['linear'], ['zoom'], 13, 0.45, 16, 0.65, 18, 0.85]

    // Direction chevron above the icon — icon-offset rotates together with
    // icon-rotate, so the chevron orbits the vehicle point and points along
    // the bearing. Hidden for stationary (zombie) vehicles.
    ensureHeadingChevron(map)
    map.addLayer({
      id: 'transit-vehicles-heading',
      type: 'symbol',
      source: 'transit-vehicles',
      // Skip stationary (zombie) vehicles AND any without a real GTFS-RT heading —
      // otherwise a missing bearing renders as a spurious north-pointing chevron.
      filter: ['all', ['!=', ['get', 'zombie'], 1], ['==', ['get', 'has_bearing'], 1]],
      layout: {
        'icon-image': 'transit-heading',
        'icon-size': symbolSize,
        'icon-rotate': ['get', 'bearing'],
        'icon-rotation-alignment': 'map',
        'icon-offset': [0, -34],
        'icon-allow-overlap': true,
        'icon-ignore-placement': true,
        visibility: vis,
      },
      minzoom: 13,
    })

    // Route-color bar under the icon (route identity) — only when the feed
    // actually defines route_color; no outline, pure color block.
    map.addLayer({
      id: 'transit-vehicles-bar',
      type: 'symbol',
      source: 'transit-vehicles',
      filter: ['==', ['get', 'route_color_set'], 1],
      layout: {
        'icon-image': ['concat', 'transit-bar-', ['get', 'route_color']],
        'icon-size': symbolSize,
        'icon-rotation-alignment': 'viewport',
        'icon-offset': [0, 32],
        'icon-allow-overlap': true,
        'icon-ignore-placement': true,
        visibility: vis,
      },
      paint: {
        'icon-opacity': ['case', ['==', ['get', 'zombie'], 1], 0.6, 1],
      },
      minzoom: 13,
    })

    // Vehicle type icons at higher zoom
    ensureTransitIcons(map).then(() => {
      const rt = ['get', 'route_type']
      const range = (lo: number, hi: number) => ['all', ['>=', rt, lo], ['<=', rt, hi]]

      // case expression: exact matches first, then extended GTFS ranges, fallback bus
      const iconExpr: any[] = ['case',
        ['==', rt, 0], 'transit-tram',
        ['==', rt, 1], 'transit-metro',
        ['==', rt, 2], 'transit-train',
        ['==', rt, 3], 'transit-bus',
        ['==', rt, 4], 'transit-ferry',
        ['==', rt, 7], 'transit-train',
        ['==', rt, 11], 'transit-trolleybus',
        ['==', rt, 200], 'transit-2bus',
        ['==', rt, 1100], 'transit-airplane',
        ['==', rt, 1501], 'transit-bus-taxi',
        range(100, 199), 'transit-train',
        range(200, 299), 'transit-2bus',
        range(400, 499), 'transit-metro',
        range(700, 799), 'transit-bus',
        range(900, 999), 'transit-tram',
        range(1500, 1599), 'transit-bus-taxi',
        'transit-bus',
      ]

      // Append '-gray' suffix for stationary/zombie vehicles
      const iconWithZombie = ['concat', iconExpr, ['case', ['==', ['get', 'zombie'], 1], '-gray', '']]

      map.addLayer({
        id: 'transit-vehicles-icon',
        type: 'symbol',
        source: 'transit-vehicles',
        layout: {
          'icon-image': iconWithZombie,
          'icon-size': symbolSize,
          // Always upright — travel direction is shown by the heading chevron layer
          'icon-rotation-alignment': 'viewport',
          'icon-allow-overlap': true,
          'icon-ignore-placement': true,
          visibility: vis,
        },
        paint: {
          'icon-opacity': ['case', ['==', ['get', 'zombie'], 1], 0.6, 1],
        },
        minzoom: 13,
      })
      // Respect an already-active route focus (icons load async after setup)
      applyVehicleIconZoomRange(map)
    })

    // Click handler → dispatch to panel callback (no popup).
    // Named ref + off-before-on (same as _moveendHandler below): setupLayers
    // re-runs on style reloads, and the KeepAlive'd map would otherwise
    // accumulate a duplicate handler — and open N panels — per re-run.
    if (_vehicleClickHandler) {
      for (const layer of VEHICLE_CLICK_LAYERS) map.off('click', layer, _vehicleClickHandler)
    }
    _vehicleClickHandler = (e: any) => {
      if (!e.features || !e.features.length) return
      const p = e.features[0].properties
      if (onVehicleClick) {
        onVehicleClick({
          ...p,
          lngLat: { lng: e.lngLat.lng, lat: e.lngLat.lat },
        })
      }
    }
    for (const layer of VEHICLE_CLICK_LAYERS) map.on('click', layer, _vehicleClickHandler)

    attachHoverHex(map, 'transit-vehicles-circle', 1.9)
    attachHoverHex(map, 'transit-vehicles-icon', 1.9)

    // Start WS if transit is enabled — subscribe with current map bounds
    if (transitEnabled.value) {
      connectTransitWs()
      const bounds = map.getBounds()
      subscribeTransitBbox([bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()])
    }

    // Update bbox on map pan/zoom (named ref so we can remove on re-init)
    if (_moveendHandler) map.off('moveend', _moveendHandler)
    _moveendHandler = () => {
      if (!transitEnabled.value) return
      const b = map.getBounds()
      updateTransitBbox([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()])
      loadTransitData(map)  // refetch stops when the cache-grid bbox changed (no-op otherwise)
    }
    map.on('moveend', _moveendHandler)
  }

  // ======== Combined setup ========

  function setupLayers(map: any) {
    addTransitStopLayers(map)
    addTransitVehicleLayers(map)
  }

  function toggleLayer() {
    // If route filter active, first click clears it (shows all vehicles)
    if (activeRouteFilter.value && transitEnabled.value) {
      activeRouteFilter.value = null
      const map = mapStore.mapInstance
      if (map) removeRouteOverlay(map)
      return
    }
    transitEnabled.value = !transitEnabled.value
    const map = mapStore.mapInstance
    if (!map) return
    const vis = transitEnabled.value ? 'visible' : 'none'
    for (const id of ['transit-stops-circle', 'transit-stops-label',
                      'transit-stops-virtual-circle', 'transit-stops-virtual-label',
                      'transit-vehicles-circle', ...VEHICLE_SYMBOL_LAYERS]) {
      if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', vis)
    }

    if (transitEnabled.value && !transitDataLoaded) {
      const map2 = mapStore.mapInstance
      if (map2) loadTransitData(map2)
    }

    if (transitEnabled.value) {
      connectTransitWs()
      const map2 = mapStore.mapInstance
      if (map2) {
        const b = map2.getBounds()
        subscribeTransitBbox([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()])
      }
    } else {
      disconnectWs()
    }
  }

  // Disconnect + forget shown positions, so a later reconnect appears in place
  // (real positions) rather than sliding from stale coords.
  function disconnectWs() {
    disconnectTransitWs()
    vehicleAnimator.stop()
  }

  function resetDataLoaded() {
    transitDataLoaded = false
    lastStopsBbox = null
  }

  /** Sync vehicle data from WS to map source via plain callback (bypasses Vue watch).
   * The animator owns its own rAF loop (1s glide per tick), so no manual rAF gate. */
  function syncVehicleData() {
    const unsub = onTransitUpdate(() => {
      const map = mapStore.mapInstance
      if (!map || !transitEnabled.value) return
      const geojson = transitToGeoJSON()
      // Filter by active route if set
      if (activeRouteFilter.value && geojson.features) {
        geojson.features = geojson.features.filter(
          (f: any) => f.properties?.route_id === activeRouteFilter.value
        )
      }
      vehicleAnimator.setTarget(geojson)
    })
    onScopeDispose(unsub)
  }

  /** Enable transit layers visibility (for pending transit marker). */
  function enableLayerVisibility(map: any) {
    for (const id of ['transit-stops-circle', 'transit-stops-label',
                      'transit-stops-virtual-circle', 'transit-stops-virtual-label',
                      'transit-vehicles-circle', ...VEHICLE_SYMBOL_LAYERS]) {
      if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', 'visible')
    }
    loadTransitData(map)
  }

  return {
    transitEnabled,
    transitExpanded,
    activeRouteFilter,
    setupLayers,
    toggleLayer,
    showRouteOnMap,
    redrawActiveRoute,
    removeRouteOverlay,
    resetDataLoaded,
    connectWs: connectTransitWs,
    disconnectWs,
    isWsConnected: isTransitWsConnected,
    syncVehicleData,
    enableLayerVisibility,
    loadTransitData,
    setVehicleClickHandler,
  }
}
