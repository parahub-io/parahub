/**
 * Transit stops/routes/vehicles on map + WebSocket wrapper.
 *
 * Extracted from MapView.vue lines 368-370, 1103-1510.
 */

import { ref, watch, onScopeDispose } from 'vue'
import { createVehicleAnimator } from '~/utils/vehicleAnimator'
import { createTransitDeckOverlay } from '~/utils/transitDeckOverlay'

export function useMapTransitLayers() {
  const mapStore = useMapStore()
  const { resolveColor } = useTransitHelpers()
  const colorMode = useColorMode()

  const transitEnabled = useLocalPref('transit_enabled', false)
  const transitExpanded = ref(false)
  const activeRouteFilter = ref<string | null>(null)  // route_source_id for single-route mode
  // Display info for the on-map active-route chip (badge + name + dismiss);
  // null when no single-route overlay is drawn.
  const activeRouteInfo = ref<{ short_name: string, long_name: string, route_color?: string, route_type?: number } | null>(null)
  // Last drawn single-route overlay — kept so the overlay can be redrawn after a
  // style change (setStyle wipes it) without re-fetching or re-fitting the camera.
  let lastRouteDetail: any = null
  let lastRouteCity: string | null = null
  let lastRouteSlug: string | null = null
  let lastRouteBounds: any = null  // overlay extent, for chip-tap re-fit
  let transitDataLoaded = false
  let lastStopsBbox: string | null = null  // last fetched stops-geojson bbox (cache-grid aligned)

  // Staggered stop-reveal sweep bookkeeping (transient hex markers + their
  // timers, plus the map-idle listener that delays the sweep start)
  let stopRevealTimers: ReturnType<typeof setTimeout>[] = []
  let stopRevealMarkers: any[] = []
  let stopRevealIdleCancel: (() => void) | null = null
  function cancelStopReveal() {
    stopRevealIdleCancel?.()
    stopRevealIdleCancel = null
    for (const t of stopRevealTimers) clearTimeout(t)
    stopRevealTimers = []
    for (const m of stopRevealMarkers) { try { m.remove() } catch { /* already gone */ } }
    stopRevealMarkers = []
  }

  // Stored handler ref for cleanup on re-init (prevents accumulation on style change)
  let _moveendHandler: (() => void) | null = null

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

  // Shared deck.gl overlaid canvas for all live-transit rendering: comet
  // trails below, vehicle icons above. Everything animated lives on deck so
  // per-frame updates never force a full MapLibre scene repaint; MapLibre
  // keeps only the static layers (stops, route overlay). The deck chunks
  // load lazily with the transit toggle, never for transit-off visitors.
  const deckOverlay = createTransitDeckOverlay()
  const transitTrails = useTransitTrails(deckOverlay)
  const transitVehicles = useTransitVehiclesDeck(deckOverlay)

  // Comet-trails preference (profile → Advanced). The watch applies
  // profile-page toggles to the KeepAlive'd live map without a reload.
  const trailsEnabled = useLocalPref('transit_trails_enabled', true)
  watch(trailsEnabled, (on) => {
    if (!on) {
      transitTrails.stop()
    } else if (transitEnabled.value && mapStore.mapInstance) {
      transitTrails.start(mapStore.mapInstance)
    }
  })

  // Glide vehicle icons to each new WS position over 1s instead of snapping.
  const vehicleAnimator = createVehicleAnimator({
    // Feed-namespaced key ({ds}:{vid}) — raw fleet numbers collide across
    // operators, and a shared key glides one icon between two cities' buses.
    getKey: (f: any) => f.properties.uid || f.properties.vehicle_id,
    apply: (fc: any) => {
      transitVehicles.update(fc)
      // Comet heads follow the gliding icons, not the raw 30s tick jumps
      transitTrails.updateLive(fc)
    },
  })

  // Vehicle panel dispatch, stable closure over the mutable handler above
  const dispatchVehicleClick = (vehicle: any) => { onVehicleClick?.(vehicle) }

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

  async function showRouteOnMap(map: any, routeCity: string, routeSlug: string, opts: { fitBounds?: boolean, animate?: boolean } = {}) {
    const { fitBounds = true, animate = true } = opts
    cancelStopReveal()  // kill any in-flight sweep from a previous route
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
      activeRouteInfo.value = {
        short_name: routeDetail.short_name || routeSlug,
        long_name: routeDetail.long_name || '',
        route_color: routeDetail.route_color,
        route_type: routeDetail.route_type,
      }

      // Filter vehicles to this route only
      activeRouteFilter.value = routeDetail.source_id || null
      applyRouteFocus()  // show icons at the route-fit zoom (often <13)
      // Street-following comet trails along the focused route's shape
      transitTrails.setRouteGeometry(routeDetail.source_id || null, routeDetail.geometry || null)

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
      // Live vehicles render on the deck canvas above every MapLibre layer,
      // so the route line needs no before-anchor — buses always sit on top.

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

      // Both directions' stops render (dir1 poles usually sit across the
      // street). Dir0 falls back to dir1 for dir1-only routes (circulars —
      // mirrors primaryStops on the route page); dir1 poles already drawn by
      // dir0 (shared termini) are deduped so they don't double-render.
      const stopsDir0: any[] = routeDetail.stops?.length
        ? routeDetail.stops : (routeDetail.stops_dir1 || [])
      const dir0Ids = new Set(stopsDir0.map((s: any) => s.id))
      const stopsDir1: any[] = routeDetail.stops?.length
        ? (routeDetail.stops_dir1 || []).filter((s: any) => !dir0Ids.has(s.id)) : []
      const allStops = [
        ...stopsDir0.map((s: any) => ({ ...s, dir: 0 })),
        ...stopsDir1.map((s: any) => ({ ...s, dir: 1 })),
      ]

      if (allStops.length) {
        // Feature id (index) lets the reveal sweep flip per-stop opacity via
        // feature-state so dots materialise one-by-one, origin → terminus.
        const stopsGeoJSON = {
          type: 'FeatureCollection',
          features: allStops.map((s: any, i: number) => ({
            type: 'Feature',
            id: i,
            geometry: { type: 'Point', coordinates: [s.lon, s.lat] },
            properties: { name: s.name, sequence: s.sequence, dir: s.dir },
          })),
        }
        map.addSource('transit-route-stops-src', { type: 'geojson', data: stopsGeoJSON })
        const color = `#${resolveColor(routeDetail)}`

        // One-shot brand-hex reveal — only on a fresh user "show on map"
        // (animate), never on a silent style-reload redraw, and honoured off for
        // prefers-reduced-motion / single-stop routes.
        const reduceMotion = typeof window !== 'undefined'
          && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
        const doReveal = animate && !reduceMotion && allStops.length > 1

        const stopPaint: any = {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 3, 14, 6, 18, 9],
          'circle-color': color,
          'circle-stroke-color': lineCasing,
          'circle-stroke-width': 2,
        }
        if (doReveal) {
          const revealed = ['case', ['boolean', ['feature-state', 'revealed'], false], 1, 0]
          stopPaint['circle-opacity'] = revealed
          stopPaint['circle-stroke-opacity'] = revealed
          stopPaint['circle-opacity-transition'] = { duration: 300, delay: 0 }
          stopPaint['circle-stroke-opacity-transition'] = { duration: 300, delay: 0 }
        }
        map.addLayer({
          id: 'transit-route-stops',
          type: 'circle',
          source: 'transit-route-stops-src',
          paint: stopPaint,
        })

        if (doReveal) {
          const src = 'transit-route-stops-src'
          const feats: any[] = stopsGeoJSON.features
          // One pass per direction, each in stop-sequence order (fall back to
          // array index). Dir1 sweeps back after a beat — outbound, pause,
          // return — so the second direction reads as its own pass.
          const bySeq = (a: number, b: number) =>
            (feats[a].properties.sequence ?? a) - (feats[b].properties.sequence ?? b)
          const order0 = feats.map((_: any, i: number) => i)
            .filter(i => feats[i].properties.dir === 0).sort(bySeq)
          const order1 = feats.map((_: any, i: number) => i)
            .filter(i => feats[i].properties.dir === 1).sort(bySeq)
          const DIR_PAUSE = 650
          // Rapid-fire; cap each direction's sweep ≈3s
          const stag = (n: number) => Math.min(100, Math.round(3000 / Math.max(n, 1)))
          const stagger0 = stag(order0.length)
          const stagger1 = stag(order1.length)
          const dir1Base = order0.length * stagger0 + (order1.length ? DIR_PAUSE : 0)
          const mod = await import('maplibre-gl')
          const maplibregl = (mod as any).default || mod
          const { createStopRevealElement } = await import('~/utils/lockOnMarker')

          const revealAt = (fid: number, delay: number) => {
            const t = setTimeout(() => {
              if (!map.getSource(src)) return
              map.setFeatureState({ source: src, id: fid }, { revealed: true })
              const mk = new maplibregl.Marker({ element: createStopRevealElement(), anchor: 'center' })
                .setLngLat(feats[fid].geometry.coordinates as [number, number])
                .addTo(map)
              stopRevealMarkers.push(mk)
              const rmT = setTimeout(() => {
                mk.remove()
                const idx = stopRevealMarkers.indexOf(mk)
                if (idx >= 0) stopRevealMarkers.splice(idx, 1)
              }, 850)  // matches stop-reveal-in duration
              stopRevealTimers.push(rmT)
            }, delay)
            stopRevealTimers.push(t)
          }

          const startSweep = () => {
            order0.forEach((fid, k) => revealAt(fid, k * stagger0))
            order1.forEach((fid, k) => revealAt(fid, dir1Base + k * stagger1))
            // Safety net: guarantee every dot ends visible even if a timer is lost
            const safety = setTimeout(() => {
              if (!map.getSource(src)) return
              for (let i = 0; i < feats.length; i++) map.setFeatureState({ source: src, id: i }, { revealed: true })
            }, dir1Base + order1.length * stagger1 + 500)
            stopRevealTimers.push(safety)
          }

          // Hold the one-shot sweep until the basemap has actually rendered the
          // (post-fitBounds) viewport — on a cold load the map is still blank
          // when this code runs, and an immediate sweep plays to nobody. Two
          // escape hatches guard the 'idle' wait: triggerRepaint forces a
          // render cycle so 'idle' re-fires even when the map went idle before
          // this listener attached (possible while the chunk imports above were
          // in flight — without it the sweep hangs until the next repaint,
          // i.e. a mouse hover); and a hard cap starts the sweep anyway when
          // slow tile loads hold 'idle' hostage (a metro-area viewport can
          // take 10s+ to settle on a cold tile cache).
          let sweepStarted = false
          const begin = () => {
            if (sweepStarted) return
            sweepStarted = true
            map.off('idle', onIdle)
            clearTimeout(sweepCap)
            stopRevealIdleCancel = null
            startSweep()
          }
          const onIdle = () => begin()
          const sweepCap = setTimeout(begin, 3500)
          stopRevealIdleCancel = () => { map.off('idle', onIdle); clearTimeout(sweepCap) }
          map.once('idle', onIdle)
          map.triggerRepaint()
        }

        const coords = allStops.map((s: any) => [s.lon, s.lat])
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
        lastRouteBounds = bounds
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
      showRouteOnMap(map, lastRouteCity, lastRouteSlug, { fitBounds: false, animate: false })
    }
  }

  /** Re-frame the camera on the active route overlay (chip tap). */
  function fitActiveRoute(map: any) {
    if (lastRouteBounds) map.fitBounds(lastRouteBounds, { padding: 60 })
  }

  function removeRouteOverlay(map: any) {
    cancelStopReveal()
    activeRouteFilter.value = null
    activeRouteInfo.value = null
    lastRouteDetail = null
    lastRouteCity = null
    lastRouteSlug = null
    lastRouteBounds = null
    applyRouteFocus()  // restore global z13 icon threshold
    transitTrails.setRouteGeometry(null, null)
    for (const id of ['transit-route-line', 'transit-route-line-casing', 'transit-route-stops']) {
      if (map.getLayer(id)) map.removeLayer(id)
    }
    for (const id of ['transit-route-geom', 'transit-route-stops-src']) {
      if (map.getSource(id)) map.removeSource(id)
    }
  }

  // ======== Live vehicles (deck.gl — see useTransitVehiclesDeck) ========

  // Called from every activeRouteFilter mutation site. Single-route focus
  // shows icons at every zoom (matches the route-page mini-map); the global
  // view keeps the z13 icon threshold. Trails sync in the same breath so
  // other routes' tails vanish on focus instead of lingering a tick.
  function applyRouteFocus() {
    transitVehicles.setRouteFocus(!!activeRouteFilter.value)
    transitTrails.setRouteFilter(activeRouteFilter.value)
  }

  /** Connect the realtime feed and bring up the deck overlay (idempotent —
   * WS reconnects are no-ops while connected, deck start reuses the overlay). */
  function startLive(map: any) {
    connectTransitWs()
    const b = map.getBounds()
    subscribeTransitBbox([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()])
    transitVehicles.start(map, dispatchVehicleClick)
    if (trailsEnabled.value) transitTrails.start(map)
  }

  function setupVehicleLayer(map: any) {
    // The deck overlay is a map control, not a style layer — it survives
    // setStyle, so a style reload needs no vehicle re-init here.
    if (transitEnabled.value) startLive(map)

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

  const STOP_LAYERS = ['transit-stops-circle', 'transit-stops-label',
                       'transit-stops-virtual-circle', 'transit-stops-virtual-label']

  function setupLayers(map: any) {
    addTransitStopLayers(map)
    setupVehicleLayer(map)
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
    for (const id of STOP_LAYERS) {
      if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', vis)
    }

    if (transitEnabled.value && !transitDataLoaded) {
      loadTransitData(map)
    }

    if (transitEnabled.value) {
      startLive(map)
    } else {
      disconnectWs()
    }
  }

  // Disconnect + forget shown positions, so a later reconnect appears in place
  // (real positions) rather than sliding from stale coords.
  function disconnectWs() {
    disconnectTransitWs()
    vehicleAnimator.stop()
    transitVehicles.stop()
    transitTrails.stop()
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
      // Order matters: ingest pins the currently *displayed* head position
      // into trail history before setTarget re-aims the glide at the new one.
      transitTrails.ingest(geojson.features as any[])
      vehicleAnimator.setTarget(geojson)
    })
    onScopeDispose(unsub)
  }

  /** Enable transit layers visibility (for pending transit marker). */
  function enableLayerVisibility(map: any) {
    for (const id of STOP_LAYERS) {
      if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', 'visible')
    }
    // Live vehicles flow only while the transit toggle is on (parity with the
    // former layer-visibility behavior: WS data was gated the same way).
    if (transitEnabled.value) startLive(map)
    loadTransitData(map)
  }

  /** Active single-route overlay (city/slug), for URL persistence — lets the
   * map query string keep the route across F5 and shared links. */
  function getActiveRoute(): { city: string, slug: string } | null {
    return lastRouteCity && lastRouteSlug ? { city: lastRouteCity, slug: lastRouteSlug } : null
  }

  return {
    transitEnabled,
    transitExpanded,
    activeRouteFilter,
    activeRouteInfo,
    getActiveRoute,
    setupLayers,
    toggleLayer,
    showRouteOnMap,
    redrawActiveRoute,
    fitActiveRoute,
    removeRouteOverlay,
    resetDataLoaded,
    connectWs: connectTransitWs,
    disconnectWs,
    isWsConnected: isTransitWsConnected,
    syncVehicleData,
    enableLayerVisibility,
    loadTransitData,
    setVehicleClickHandler,
    // Deck-overlay picking for the map click dispatcher (vehicles are no
    // longer MapLibre layers, queryRenderedFeatures can't see them)
    hasVehicleAt: transitVehicles.hasVehicleAt,
  }
}
