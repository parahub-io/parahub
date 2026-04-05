/**
 * Routing (directions) panel state + route layers on map.
 *
 * Supports Valhalla (single Feature) and MOTIS (FeatureCollection with per-leg colors).
 */

import { ref } from 'vue'
import type { Ref } from 'vue'
import { useRouting } from '~/composables/useRouting'

const ROUTE_COLORS: Record<string, string> = {
  auto: '#3b82f6',
  pedestrian: '#10b981',
  bicycle: '#f59e0b',
  multimodal: '#8b5cf6',
}

export function useMapRouting(opts: {
  browseVisible: Ref<boolean>
  animationEnabled: { value: boolean }
}) {
  const mapStore = useMapStore()
  const routingVisible = ref(false)
  const {
    origin: routingOrigin,
    destination: routingDest,
    costing: routingCosting,
    routeGeoJSON,
    routeBounds,
    awaitingMapClick,
    clearRoute,
  } = useRouting()

  function clearRouteFromMap() {
    const map = mapStore.mapInstance
    if (!map) return
    for (const id of ['directions-route-line', 'directions-route-walk', 'directions-waypoints']) {
      if (map.getLayer(id)) map.removeLayer(id)
    }
    for (const id of ['directions-route-geom', 'directions-waypoints-src']) {
      if (map.getSource(id)) map.removeSource(id)
    }
  }

  function showRouteOnMap(geojson: any, bounds: [[number, number], [number, number]]) {
    const map = mapStore.mapInstance
    if (!map) return
    clearRouteFromMap()

    map.addSource('directions-route-geom', { type: 'geojson', data: geojson })

    const isFeatureCollection = geojson.type === 'FeatureCollection'

    if (isFeatureCollection) {
      // MOTIS: per-leg coloring with data-driven style
      // Solid lines for transit legs
      map.addLayer({
        id: 'directions-route-line',
        type: 'line',
        source: 'directions-route-geom',
        filter: ['!=', ['get', 'isWalk'], true],
        paint: {
          'line-color': ['get', 'color'],
          'line-width': 5,
          'line-opacity': 0.85,
        },
        layout: { 'line-cap': 'round', 'line-join': 'round' },
      })
      // Dashed lines for walk legs
      map.addLayer({
        id: 'directions-route-walk',
        type: 'line',
        source: 'directions-route-geom',
        filter: ['==', ['get', 'isWalk'], true],
        paint: {
          'line-color': ['get', 'color'],
          'line-width': 4,
          'line-opacity': 0.7,
          'line-dasharray': [2, 2],
        },
        layout: { 'line-cap': 'round', 'line-join': 'round' },
      })
    } else {
      // Valhalla: single color
      map.addLayer({
        id: 'directions-route-line',
        type: 'line',
        source: 'directions-route-geom',
        paint: {
          'line-color': ROUTE_COLORS[routingCosting.value] || '#3b82f6',
          'line-width': 5,
          'line-opacity': 0.8,
        },
        layout: { 'line-cap': 'round', 'line-join': 'round' },
      })
    }

    if (routingOrigin.value && routingDest.value) {
      const waypointsGeoJSON = {
        type: 'FeatureCollection',
        features: [
          { type: 'Feature', properties: { type: 'origin' }, geometry: { type: 'Point', coordinates: [routingOrigin.value.lon, routingOrigin.value.lat] } },
          { type: 'Feature', properties: { type: 'destination' }, geometry: { type: 'Point', coordinates: [routingDest.value.lon, routingDest.value.lat] } },
        ],
      }
      map.addSource('directions-waypoints-src', { type: 'geojson', data: waypointsGeoJSON })
      map.addLayer({
        id: 'directions-waypoints',
        type: 'circle',
        source: 'directions-waypoints-src',
        paint: {
          'circle-radius': 7,
          'circle-color': ['case', ['==', ['get', 'type'], 'origin'], '#22c55e', '#ef4444'],
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 2,
        },
      })
    }

    map.fitBounds(bounds, { padding: 80, duration: opts.animationEnabled.value ? 500 : 0 })
  }

  function togglePanel() {
    routingVisible.value = !routingVisible.value
    if (routingVisible.value) {
      opts.browseVisible.value = false
    } else {
      clearRouteFromMap()
      clearRoute()
    }
  }

  function closePanel() {
    routingVisible.value = false
    clearRouteFromMap()
  }

  return {
    routingVisible,
    routingOrigin,
    routingDest,
    routingCosting,
    routeGeoJSON,
    routeBounds,
    awaitingMapClick,
    clearRoute,
    showRouteOnMap,
    clearRouteFromMap,
    togglePanel,
    closePanel,
  }
}
