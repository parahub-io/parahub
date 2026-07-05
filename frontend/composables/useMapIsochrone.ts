/**
 * Isochrone (travel time) visualization for the map.
 * Click a point → shows walking accessibility zones (5/10/15 min).
 * Uses Valhalla isochrone API via /api/v1/routing/isochrone.
 */

import { ref, computed } from 'vue'
import { createDrawTool, EMPTY_FC } from '~/composables/useMapDrawTool'

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

export function useMapIsochrone() {
  const mapStore = useMapStore()

  // ======== State ========

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

  function _buildLabelFeatures(geojson: GeoJSON.FeatureCollection): GeoJSON.FeatureCollection {
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
    map.getSource(SRC_ISOCHRONE_CENTER)?.setData({
      type: 'FeatureCollection',
      features: [{
        type: 'Feature',
        properties: {},
        geometry: { type: 'Point', coordinates: [lng, lat] },
      }],
    })

    try {
      const geojson = await fetchIsochrone(lng, lat)
      map.getSource(SRC_ISOCHRONE)?.setData(geojson)
      map.getSource(SRC_LABELS)?.setData(_buildLabelFeatures(geojson))
    } catch (e) {
      console.warn('[Isochrone] Failed to fetch:', e)
    } finally {
      isochroneLoading.value = false
    }
  }

  // ======== Lifecycle (via createDrawTool) ========

  const tool = createDrawTool({
    tag: 'isochrone',
    sources: [SRC_ISOCHRONE, SRC_ISOCHRONE_CENTER, SRC_LABELS],
    layers: [
      // 15-min fill (outermost, drawn first)
      {
        id: LYR_FILL_15,
        type: 'fill',
        source: SRC_ISOCHRONE,
        filter: ['==', ['get', 'contour'], 15],
        paint: {
          'fill-color': CONTOUR_COLORS[15],
          'fill-opacity': 0.12,
        },
      },
      // 10-min fill
      {
        id: LYR_FILL_10,
        type: 'fill',
        source: SRC_ISOCHRONE,
        filter: ['==', ['get', 'contour'], 10],
        paint: {
          'fill-color': CONTOUR_COLORS[10],
          'fill-opacity': 0.18,
        },
      },
      // 5-min fill (innermost, on top)
      {
        id: LYR_FILL_5,
        type: 'fill',
        source: SRC_ISOCHRONE,
        filter: ['==', ['get', 'contour'], 5],
        paint: {
          'fill-color': CONTOUR_COLORS[5],
          'fill-opacity': 0.22,
        },
      },
      // Outlines for all contours
      {
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
      },
      // Center point marker
      {
        id: LYR_CENTER,
        type: 'circle',
        source: SRC_ISOCHRONE_CENTER,
        paint: {
          'circle-radius': 8,
          'circle-color': '#3b82f6',
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 3,
        },
      },
      // Contour time labels
      {
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
      },
    ],
    events: {
      click: (e: any) => {
        showIsochrone(e.lngLat.lng, e.lngLat.lat)
      },
    },
    onStart: () => {
      isochroneCenter.value = null
    },
    onStop: () => {
      isochroneCenter.value = null
    },
  })

  function setCostingMode(mode: CostingMode) {
    costingMode.value = mode
    // Re-fetch if we have an active center
    if (isochroneCenter.value) {
      showIsochrone(isochroneCenter.value[0], isochroneCenter.value[1])
    }
  }

  return {
    isochroneActive: tool.active,
    isochroneLoading,
    isochroneCenter,
    costingMode,
    costingLabel,
    setupLayers: tool.setupLayers,
    startIsochrone: tool.start,
    stopIsochrone: tool.stop,
    toggleIsochrone: tool.toggle,
    setCostingMode,
    showIsochrone,
  }
}
