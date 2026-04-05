/**
 * Transit stops/routes/vehicles on map + WebSocket wrapper.
 *
 * Extracted from MapView.vue lines 368-370, 1103-1510.
 */

import { ref, onScopeDispose } from 'vue'
import { attachHoverHex } from '~/composables/useMapHighlight'

export function useMapTransitLayers() {
  const mapStore = useMapStore()
  const { resolveColor } = useTransitHelpers()

  const transitEnabled = useLocalPref('transit_enabled', false)
  const transitExpanded = ref(false)
  const activeRouteFilter = ref<string | null>(null)  // route_source_id for single-route mode
  let transitDataLoaded = false

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

  // ======== Static layers (stops) ========

  function addTransitStopLayers(map: any) {
    for (const id of ['transit-stops-circle', 'transit-stops-label']) {
      if (map.getLayer(id)) map.removeLayer(id)
    }
    if (map.getSource('transit-stops')) map.removeSource('transit-stops')

    const empty = { type: 'FeatureCollection', features: [] }
    map.addSource('transit-stops', { type: 'geojson', data: empty })

    const vis = transitEnabled.value ? 'visible' : 'none'

    map.addLayer({
      id: 'transit-stops-circle',
      type: 'circle',
      source: 'transit-stops',
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 1.5, 14, 4, 18, 7],
        'circle-color': '#3b82f6',
        'circle-stroke-color': '#ffffff',
        'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 10, 0, 14, 1, 18, 2],
      },
      layout: { visibility: vis },
      minzoom: 12,
    })

    map.addLayer({
      id: 'transit-stops-label',
      type: 'symbol',
      source: 'transit-stops',
      layout: {
        'text-field': ['get', 'name'],
        'text-size': 10,
        'text-offset': [0, 1.2],
        'text-anchor': 'top',
        'text-optional': true,
        visibility: vis,
      },
      paint: {
        'text-color': '#1e40af',
        'text-halo-color': '#ffffff',
        'text-halo-width': 1.5,
      },
      minzoom: 15,
    })

    if (transitEnabled.value) {
      loadTransitData(map)
    }
  }

  async function loadTransitData(map: any) {
    if (transitDataLoaded) return
    transitDataLoaded = true

    try {
      const stopsData = await $fetch<any>('/api/v1/geo/transit/stops/geojson/')
      if (map.getSource('transit-stops')) {
        ;(map.getSource('transit-stops') as any).setData(stopsData)
      }
    } catch (e) {
      console.warn('Failed to load transit stops:', e)
    }
  }

  // ======== Route overlay ========

  async function showRouteOnMap(map: any, routeCity: string, routeSlug: string) {
    try {
      let routeDetail = (window as any)._transitRouteData
      if (routeDetail?.slug === routeSlug) {
        delete (window as any)._transitRouteData
      } else {
        routeDetail = await $fetch<any>(`/api/v1/geo/transit/routes/${routeCity}/${routeSlug}/`)
      }

      // Filter vehicles to this route only
      activeRouteFilter.value = routeDetail.source_id || null

      for (const id of ['transit-route-line', 'transit-route-stops']) {
        if (map.getLayer(id)) map.removeLayer(id)
      }
      for (const id of ['transit-route-geom', 'transit-route-stops-src']) {
        if (map.getSource(id)) map.removeSource(id)
      }

      if (routeDetail.geometry) {
        map.addSource('transit-route-geom', {
          type: 'geojson',
          data: { type: 'Feature', geometry: routeDetail.geometry, properties: {} },
        })
        const color = `#${resolveColor(routeDetail)}`
        map.addLayer({
          id: 'transit-route-line',
          type: 'line',
          source: 'transit-route-geom',
          paint: { 'line-color': color, 'line-width': 4, 'line-opacity': 0.85 },
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
            'circle-stroke-color': '#ffffff',
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
        map.fitBounds(bounds, { padding: 60, duration: 0 })
      }
    } catch (e) {
      console.warn('Failed to show transit route on map:', e)
    }
  }

  function removeRouteOverlay(map: any) {
    activeRouteFilter.value = null
    for (const id of ['transit-route-line', 'transit-route-stops']) {
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

  function addTransitVehicleLayers(map: any) {
    if (map.getLayer('transit-vehicles-icon')) map.removeLayer('transit-vehicles-icon')
    if (map.getLayer('transit-vehicles-circle')) map.removeLayer('transit-vehicles-circle')
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
          'icon-size': ['interpolate', ['linear'], ['zoom'], 13, 0.45, 16, 0.65, 18, 0.85],
          'icon-rotate': ['get', 'bearing'],
          'icon-rotation-alignment': 'map',
          'icon-allow-overlap': true,
          'icon-ignore-placement': true,
          visibility: vis,
        },
        paint: {
          'icon-opacity': ['case', ['==', ['get', 'zombie'], 1], 0.6, 1],
        },
        minzoom: 13,
      })
    })

    // Click handler → dispatch to panel callback (no popup)
    const vehicleClickHandler = (e: any) => {
      if (!e.features || !e.features.length) return
      const p = e.features[0].properties
      if (onVehicleClick) {
        onVehicleClick({
          ...p,
          lngLat: { lng: e.lngLat.lng, lat: e.lngLat.lat },
        })
      }
    }
    map.on('click', 'transit-vehicles-circle', vehicleClickHandler)
    map.on('click', 'transit-vehicles-icon', vehicleClickHandler)

    attachHoverHex(map, 'transit-vehicles-circle', 1.9)
    attachHoverHex(map, 'transit-vehicles-icon', 1.9)

    // Start WS if transit is enabled — subscribe with current map bounds
    if (transitEnabled.value) {
      connectTransitWs()
      const bounds = map.getBounds()
      subscribeTransitBbox([bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()])
    }

    // Update bbox on map pan/zoom
    map.on('moveend', () => {
      if (!transitEnabled.value) return
      const b = map.getBounds()
      updateTransitBbox([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()])
    })
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
    if (map.getLayer('transit-stops-circle')) map.setLayoutProperty('transit-stops-circle', 'visibility', vis)
    if (map.getLayer('transit-stops-label')) map.setLayoutProperty('transit-stops-label', 'visibility', vis)
    if (map.getLayer('transit-vehicles-circle')) map.setLayoutProperty('transit-vehicles-circle', 'visibility', vis)
    if (map.getLayer('transit-vehicles-icon')) map.setLayoutProperty('transit-vehicles-icon', 'visibility', vis)

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
      disconnectTransitWs()
    }
  }

  function resetDataLoaded() {
    transitDataLoaded = false
  }

  /** Sync vehicle data from WS to map source via plain callback (bypasses Vue watch). */
  function syncVehicleData() {
    let pendingTransitRaf = false
    const unsub = onTransitUpdate(() => {
      if (pendingTransitRaf) return
      pendingTransitRaf = true
      requestAnimationFrame(() => {
        pendingTransitRaf = false
        const map = mapStore.mapInstance
        if (!map || !transitEnabled.value) return
        const source = map.getSource('transit-vehicles')
        if (source) {
          const geojson = transitToGeoJSON()
          // Filter by active route if set
          if (activeRouteFilter.value && geojson.features) {
            geojson.features = geojson.features.filter(
              (f: any) => f.properties?.route_id === activeRouteFilter.value
            )
          }
          ;(source as any).setData(geojson)
        }
      })
    })
    onScopeDispose(unsub)
  }

  /** Enable transit layers visibility (for pending transit marker). */
  function enableLayerVisibility(map: any) {
    for (const id of ['transit-stops-circle', 'transit-stops-label', 'transit-vehicles-circle', 'transit-vehicles-icon']) {
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
    removeRouteOverlay,
    resetDataLoaded,
    connectWs: connectTransitWs,
    disconnectWs: disconnectTransitWs,
    isWsConnected: isTransitWsConnected,
    syncVehicleData,
    enableLayerVisibility,
    loadTransitData,
    setVehicleClickHandler,
  }
}
