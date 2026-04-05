/**
 * Isochrone (travel time) visualization for the map.
 * Click a point → shows walking accessibility zones (5/10/15 min).
 * Uses Valhalla isochrone API via /api/v1/routing/isochrone.
 */

import { ref, computed } from 'vue'

const EMPTY_FC: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] }

// Layer / source IDs
const SRC_ISOCHRONE = 'isochrone-polygons'
const SRC_ISOCHRONE_CENTER = 'isochrone-center'
const LYR_FILL_15 = 'isochrone-fill-15'
const LYR_FILL_10 = 'isochrone-fill-10'
const LYR_FILL_5 = 'isochrone-fill-5'
const LYR_OUTLINE = 'isochrone-outline'
const LYR_CENTER = 'isochrone-center-point'
const LYR_LABELS = 'isochrone-labels'
const SRC_LABELS = 'isochrone-labels'

// Colors for contours (outermost → innermost)
const CONTOUR_COLORS: Record<number, string> = {
  15: '#ef4444', // red
  10: '#f59e0b', // amber
  5: '#22c55e',  // green
}

type CostingMode = 'pedestrian' | 'bicycle' | 'auto'

// Module-level handler for cleanup
let _clickHandler: ((e: any) => void) | null = null

export function useMapIsochrone() {
  const mapStore = useMapStore()

  // ======== State ========

  const isochroneActive = ref(false)
  const isochroneLoading = ref(false)
  const isochroneCenter = ref<[number, number] | null>(null) // [lng, lat]
  const costingMode = ref<CostingMode>('pedestrian')
  const contourMinutes = [5, 10, 15]

  const costingLabel = computed(() => {
    switch (costingMode.value) {
      case 'pedestrian': return '🚶'
      case 'bicycle': return '🚲'
      case 'auto': return '🚗'
    }
  })

  // ======== API ========

  async function fetchIsochrone(lng: number, lat: number): Promise<GeoJSON.FeatureCollection> {
    const body = {
      locations: [{ lat, lon: lng }],
      costing: costingMode.value,
      contours: contourMinutes.map(t => ({ time: t })),
      polygons: true,
    }

    const resp = await $fetch<any>('/api/v1/routing/isochrone', {
      method: 'POST',
      body,
    })

    // Valhalla returns a FeatureCollection with polygon features
    // Each feature has properties.contour (time in minutes)
    if (resp?.features) {
      return resp as GeoJSON.FeatureCollection
    }
    return EMPTY_FC
  }

  // ======== Layer Management ========

  function setupLayers(map: any) {
    if (map.getSource(SRC_ISOCHRONE)) return

    map.addSource(SRC_ISOCHRONE, { type: 'geojson', data: EMPTY_FC })
    map.addSource(SRC_ISOCHRONE_CENTER, { type: 'geojson', data: EMPTY_FC })
    map.addSource(SRC_LABELS, { type: 'geojson', data: EMPTY_FC })

    // 15-min fill (outermost, drawn first)
    map.addLayer({
      id: LYR_FILL_15,
      type: 'fill',
      source: SRC_ISOCHRONE,
      filter: ['==', ['get', 'contour'], 15],
      paint: {
        'fill-color': CONTOUR_COLORS[15],
        'fill-opacity': 0.12,
      },
    })

    // 10-min fill
    map.addLayer({
      id: LYR_FILL_10,
      type: 'fill',
      source: SRC_ISOCHRONE,
      filter: ['==', ['get', 'contour'], 10],
      paint: {
        'fill-color': CONTOUR_COLORS[10],
        'fill-opacity': 0.18,
      },
    })

    // 5-min fill (innermost, on top)
    map.addLayer({
      id: LYR_FILL_5,
      type: 'fill',
      source: SRC_ISOCHRONE,
      filter: ['==', ['get', 'contour'], 5],
      paint: {
        'fill-color': CONTOUR_COLORS[5],
        'fill-opacity': 0.22,
      },
    })

    // Outlines for all contours
    map.addLayer({
      id: LYR_OUTLINE,
      type: 'line',
      source: SRC_ISOCHRONE,
      paint: {
        'line-color': ['match', ['get', 'contour'],
          5, CONTOUR_COLORS[5],
          10, CONTOUR_COLORS[10],
          15, CONTOUR_COLORS[15],
          '#888',
        ],
        'line-width': 2,
        'line-opacity': 0.7,
      },
    })

    // Center point marker
    map.addLayer({
      id: LYR_CENTER,
      type: 'circle',
      source: SRC_ISOCHRONE_CENTER,
      paint: {
        'circle-radius': 8,
        'circle-color': '#3b82f6',
        'circle-stroke-color': '#ffffff',
        'circle-stroke-width': 3,
      },
    })

    // Contour time labels
    map.addLayer({
      id: LYR_LABELS,
      type: 'symbol',
      source: SRC_LABELS,
      layout: {
        'text-field': ['get', 'label'],
        'text-size': 12,
        'text-font': ['Noto Sans Bold'],
        'text-allow-overlap': false,
      },
      paint: {
        'text-color': ['get', 'color'],
        'text-halo-color': '#ffffff',
        'text-halo-width': 2,
      },
    })
  }

  function _buildLabelFeatures(geojson: GeoJSON.FeatureCollection, center: [number, number]): GeoJSON.FeatureCollection {
    // Place labels at the topmost point of each contour polygon (northernmost)
    const features: GeoJSON.Feature[] = []

    for (const feature of geojson.features) {
      const contour = (feature.properties as any)?.contour
      if (!contour) continue

      // Find the northernmost point of the polygon
      const coords = (feature.geometry as any)?.coordinates?.[0]
      if (!coords || coords.length === 0) continue

      let northPoint = coords[0]
      for (const c of coords) {
        if (c[1] > northPoint[1]) northPoint = c
      }

      features.push({
        type: 'Feature',
        properties: {
          label: `${contour} min`,
          color: CONTOUR_COLORS[contour] || '#888',
        },
        geometry: { type: 'Point', coordinates: northPoint },
      })
    }

    return { type: 'FeatureCollection', features }
  }

  async function showIsochrone(lng: number, lat: number) {
    const map = mapStore.mapInstance
    if (!map) return

    isochroneLoading.value = true
    isochroneCenter.value = [lng, lat]

    // Show center marker immediately
    const centerSrc = map.getSource(SRC_ISOCHRONE_CENTER)
    if (centerSrc) {
      centerSrc.setData({
        type: 'FeatureCollection',
        features: [{
          type: 'Feature',
          properties: {},
          geometry: { type: 'Point', coordinates: [lng, lat] },
        }],
      })
    }

    try {
      const geojson = await fetchIsochrone(lng, lat)
      const src = map.getSource(SRC_ISOCHRONE)
      if (src) src.setData(geojson)

      const labelsSrc = map.getSource(SRC_LABELS)
      if (labelsSrc) labelsSrc.setData(_buildLabelFeatures(geojson, [lng, lat]))
    } catch (e) {
      console.warn('[Isochrone] Failed to fetch:', e)
    } finally {
      isochroneLoading.value = false
    }
  }

  function clearVisualization() {
    const map = mapStore.mapInstance
    if (!map) return
    const src = map.getSource(SRC_ISOCHRONE)
    const centerSrc = map.getSource(SRC_ISOCHRONE_CENTER)
    const labelsSrc = map.getSource(SRC_LABELS)
    if (src) src.setData(EMPTY_FC)
    if (centerSrc) centerSrc.setData(EMPTY_FC)
    if (labelsSrc) labelsSrc.setData(EMPTY_FC)
  }

  // ======== Interaction ========

  function _attachHandlers(map: any) {
    _clickHandler = (e: any) => {
      showIsochrone(e.lngLat.lng, e.lngLat.lat)
    }
    map.on('click', _clickHandler)
  }

  function _detachHandlers(map: any) {
    if (_clickHandler) { map.off('click', _clickHandler); _clickHandler = null }
  }

  function startIsochrone() {
    const map = mapStore.mapInstance
    if (!map) return
    isochroneActive.value = true
    isochroneCenter.value = null
    clearVisualization()
    map.getCanvas().style.cursor = 'crosshair'
    _attachHandlers(map)
  }

  function stopIsochrone() {
    const map = mapStore.mapInstance
    if (!map) return
    isochroneActive.value = false
    isochroneCenter.value = null
    map.getCanvas().style.cursor = ''
    _detachHandlers(map)
    clearVisualization()
  }

  function toggleIsochrone() {
    if (isochroneActive.value) stopIsochrone()
    else startIsochrone()
  }

  function setCostingMode(mode: CostingMode) {
    costingMode.value = mode
    // Re-fetch if we have an active center
    if (isochroneCenter.value) {
      showIsochrone(isochroneCenter.value[0], isochroneCenter.value[1])
    }
  }

  return {
    isochroneActive,
    isochroneLoading,
    isochroneCenter,
    costingMode,
    costingLabel,
    setupLayers,
    startIsochrone,
    stopIsochrone,
    toggleIsochrone,
    setCostingMode,
    showIsochrone,
  }
}
