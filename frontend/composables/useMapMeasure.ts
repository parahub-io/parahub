/**
 * Map measurement tool — distance (polyline) and area (polygon).
 * Click points on map, double-click to finish. Undo / Clear supported.
 */

import { ref, computed } from 'vue'
import distance from '@turf/distance'
import turfArea from '@turf/area'
import { point, polygon as turfPolygon } from '@turf/helpers'

const EMPTY_FC: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] }

// Layer / source IDs
const SRC_LINE = 'measure-line'
const SRC_POINTS = 'measure-points'
const SRC_LABELS = 'measure-labels'
const SRC_POLYGON = 'measure-polygon'
const LYR_LINE = 'measure-line-layer'
const LYR_LINE_OUTLINE = 'measure-line-outline'
const LYR_POINTS = 'measure-points-layer'
const LYR_LABELS = 'measure-labels-layer'
const LYR_POLYGON_FILL = 'measure-polygon-fill'
const LYR_POLYGON_OUTLINE = 'measure-polygon-outline'

// Module-level handler refs for cleanup
let _clickHandler: ((e: any) => void) | null = null
let _dblClickHandler: ((e: any) => void) | null = null
let _mouseMoveHandler: ((e: any) => void) | null = null

export type MeasureMode = 'distance' | 'area'

export function useMapMeasure() {
  const mapStore = useMapStore()

  // ======== State ========

  const measureActive = ref(false)
  const measureMode = ref<MeasureMode>('distance')
  const measurePoints = ref<[number, number][]>([]) // [lng, lat]
  const cursorPoint = ref<[number, number] | null>(null) // live cursor for rubber-band

  const segmentDistances = computed(() => {
    const pts = measurePoints.value
    const dists: number[] = []
    for (let i = 1; i < pts.length; i++) {
      const d = distance(point(pts[i - 1]), point(pts[i]), { units: 'meters' })
      dists.push(d)
    }
    return dists
  })

  const totalDistance = computed(() => {
    return segmentDistances.value.reduce((sum, d) => sum + d, 0)
  })

  const perimeter = computed(() => {
    if (measureMode.value !== 'area' || measurePoints.value.length < 3) return 0
    const pts = measurePoints.value
    let total = totalDistance.value
    // Add closing segment (last → first)
    total += distance(point(pts[pts.length - 1]), point(pts[0]), { units: 'meters' })
    return total
  })

  const totalArea = computed(() => {
    if (measureMode.value !== 'area' || measurePoints.value.length < 3) return 0
    const pts = measurePoints.value
    const ring = [...pts, pts[0]] // close the ring
    try {
      const poly = turfPolygon([ring])
      return turfArea(poly)
    } catch {
      return 0
    }
  })

  const formattedTotal = computed(() => formatDist(totalDistance.value))
  const formattedArea = computed(() => formatArea(totalArea.value))
  const formattedPerimeter = computed(() => formatDist(perimeter.value))

  // ======== Helpers ========

  function formatDist(meters: number): string {
    if (meters < 1000) return `${Math.round(meters)} m`
    return `${(meters / 1000).toFixed(2)} km`
  }

  function formatArea(sqMeters: number): string {
    if (sqMeters === 0) return '0 m²'
    if (sqMeters < 10000) return `${Math.round(sqMeters)} m²`
    if (sqMeters < 1000000) return `${(sqMeters / 10000).toFixed(2)} ha`
    return `${(sqMeters / 1000000).toFixed(2)} km²`
  }

  // ======== GeoJSON Builders ========

  function buildLineGeoJSON(): GeoJSON.FeatureCollection {
    const pts = measurePoints.value
    const coords = [...pts]
    if (cursorPoint.value && pts.length > 0) coords.push(cursorPoint.value)

    // In area mode, close the shape visually when 3+ points
    if (measureMode.value === 'area' && coords.length >= 3) {
      coords.push(coords[0])
    }

    if (coords.length < 2) return EMPTY_FC
    return {
      type: 'FeatureCollection',
      features: [{
        type: 'Feature',
        properties: {},
        geometry: { type: 'LineString', coordinates: coords },
      }],
    }
  }

  function buildPolygonGeoJSON(): GeoJSON.FeatureCollection {
    if (measureMode.value !== 'area') return EMPTY_FC
    const pts = measurePoints.value
    const coords = [...pts]
    if (cursorPoint.value && pts.length > 0) coords.push(cursorPoint.value)
    if (coords.length < 3) return EMPTY_FC

    const ring = [...coords, coords[0]] // close the ring
    return {
      type: 'FeatureCollection',
      features: [{
        type: 'Feature',
        properties: {},
        geometry: { type: 'Polygon', coordinates: [ring] },
      }],
    }
  }

  function buildPointsGeoJSON(): GeoJSON.FeatureCollection {
    return {
      type: 'FeatureCollection',
      features: measurePoints.value.map((coord, i) => ({
        type: 'Feature' as const,
        properties: { index: i },
        geometry: { type: 'Point' as const, coordinates: coord },
      })),
    }
  }

  function buildLabelsGeoJSON(): GeoJSON.FeatureCollection {
    const pts = measurePoints.value
    const dists = segmentDistances.value
    const features: GeoJSON.Feature[] = []
    for (let i = 0; i < dists.length; i++) {
      const midLng = (pts[i][0] + pts[i + 1][0]) / 2
      const midLat = (pts[i][1] + pts[i + 1][1]) / 2
      features.push({
        type: 'Feature',
        properties: { label: formatDist(dists[i]) },
        geometry: { type: 'Point', coordinates: [midLng, midLat] },
      })
    }

    // In area mode, add closing segment label
    if (measureMode.value === 'area' && pts.length >= 3) {
      const last = pts[pts.length - 1]
      const first = pts[0]
      const closingDist = distance(point(last), point(first), { units: 'meters' })
      features.push({
        type: 'Feature',
        properties: { label: formatDist(closingDist) },
        geometry: { type: 'Point', coordinates: [(last[0] + first[0]) / 2, (last[1] + first[1]) / 2] },
      })
    }

    return { type: 'FeatureCollection', features }
  }

  // ======== Layer Management ========

  function setupLayers(map: any) {
    if (map.getSource(SRC_LINE)) return

    map.addSource(SRC_LINE, { type: 'geojson', data: EMPTY_FC })
    map.addSource(SRC_POINTS, { type: 'geojson', data: EMPTY_FC })
    map.addSource(SRC_LABELS, { type: 'geojson', data: EMPTY_FC })
    map.addSource(SRC_POLYGON, { type: 'geojson', data: EMPTY_FC })

    // Polygon fill (area mode only, semi-transparent)
    map.addLayer({
      id: LYR_POLYGON_FILL,
      type: 'fill',
      source: SRC_POLYGON,
      paint: {
        'fill-color': '#3b82f6',
        'fill-opacity': 0.15,
      },
    })

    // Polygon outline
    map.addLayer({
      id: LYR_POLYGON_OUTLINE,
      type: 'line',
      source: SRC_POLYGON,
      paint: {
        'line-color': '#3b82f6',
        'line-width': 2,
        'line-opacity': 0.4,
      },
    })

    // Line outline (wider, for contrast)
    map.addLayer({
      id: LYR_LINE_OUTLINE,
      type: 'line',
      source: SRC_LINE,
      paint: {
        'line-color': '#ffffff',
        'line-width': 5,
        'line-opacity': 0.7,
      },
      layout: { 'line-cap': 'round', 'line-join': 'round' },
    })

    // Main dashed line
    map.addLayer({
      id: LYR_LINE,
      type: 'line',
      source: SRC_LINE,
      paint: {
        'line-color': '#3b82f6',
        'line-width': 3,
        'line-dasharray': [2, 1.5],
        'line-opacity': 0.9,
      },
      layout: { 'line-cap': 'round', 'line-join': 'round' },
    })

    // Points
    map.addLayer({
      id: LYR_POINTS,
      type: 'circle',
      source: SRC_POINTS,
      paint: {
        'circle-radius': 6,
        'circle-color': '#3b82f6',
        'circle-stroke-color': '#ffffff',
        'circle-stroke-width': 2,
      },
    })

    // Segment distance labels
    map.addLayer({
      id: LYR_LABELS,
      type: 'symbol',
      source: SRC_LABELS,
      layout: {
        'text-field': ['get', 'label'],
        'text-size': 13,
        'text-font': ['Noto Sans Regular'],
        'text-offset': [0, -1.2],
        'text-allow-overlap': true,
      },
      paint: {
        'text-color': '#1e3a5f',
        'text-halo-color': '#ffffff',
        'text-halo-width': 2,
      },
    })
  }

  function updateVisualization() {
    const map = mapStore.mapInstance
    if (!map) return
    const lineSrc = map.getSource(SRC_LINE)
    const pointsSrc = map.getSource(SRC_POINTS)
    const labelsSrc = map.getSource(SRC_LABELS)
    const polygonSrc = map.getSource(SRC_POLYGON)
    if (lineSrc) lineSrc.setData(buildLineGeoJSON())
    if (pointsSrc) pointsSrc.setData(buildPointsGeoJSON())
    if (labelsSrc) labelsSrc.setData(buildLabelsGeoJSON())
    if (polygonSrc) polygonSrc.setData(buildPolygonGeoJSON())
  }

  function clearVisualization() {
    const map = mapStore.mapInstance
    if (!map) return
    const lineSrc = map.getSource(SRC_LINE)
    const pointsSrc = map.getSource(SRC_POINTS)
    const labelsSrc = map.getSource(SRC_LABELS)
    const polygonSrc = map.getSource(SRC_POLYGON)
    if (lineSrc) lineSrc.setData(EMPTY_FC)
    if (pointsSrc) pointsSrc.setData(EMPTY_FC)
    if (labelsSrc) labelsSrc.setData(EMPTY_FC)
    if (polygonSrc) polygonSrc.setData(EMPTY_FC)
  }

  // ======== Interaction ========

  function addPoint(coord: [number, number]) {
    measurePoints.value = [...measurePoints.value, coord]
    cursorPoint.value = null
    updateVisualization()
  }

  function undoLastPoint() {
    if (measurePoints.value.length === 0) return
    measurePoints.value = measurePoints.value.slice(0, -1)
    updateVisualization()
  }

  function clearMeasure() {
    measurePoints.value = []
    cursorPoint.value = null
    clearVisualization()
  }

  function _attachHandlers(map: any) {
    _clickHandler = (e: any) => {
      addPoint([e.lngLat.lng, e.lngLat.lat])
    }

    _dblClickHandler = (e: any) => {
      e.preventDefault()
      // Remove last duplicate point added by the preceding click event
      if (measurePoints.value.length > 1) {
        measurePoints.value = measurePoints.value.slice(0, -1)
        updateVisualization()
      }
    }

    _mouseMoveHandler = (e: any) => {
      if (measurePoints.value.length > 0) {
        cursorPoint.value = [e.lngLat.lng, e.lngLat.lat]
        // Update line + polygon for rubber-band effect
        const lineSrc = map.getSource(SRC_LINE)
        if (lineSrc) lineSrc.setData(buildLineGeoJSON())
        if (measureMode.value === 'area') {
          const polygonSrc = map.getSource(SRC_POLYGON)
          if (polygonSrc) polygonSrc.setData(buildPolygonGeoJSON())
        }
      }
    }

    map.on('click', _clickHandler)
    map.on('dblclick', _dblClickHandler)
    map.on('mousemove', _mouseMoveHandler)
  }

  function _detachHandlers(map: any) {
    if (_clickHandler) { map.off('click', _clickHandler); _clickHandler = null }
    if (_dblClickHandler) { map.off('dblclick', _dblClickHandler); _dblClickHandler = null }
    if (_mouseMoveHandler) { map.off('mousemove', _mouseMoveHandler); _mouseMoveHandler = null }
  }

  function startMeasure(mode: MeasureMode = 'distance') {
    const map = mapStore.mapInstance
    if (!map) return
    measureActive.value = true
    measureMode.value = mode
    measurePoints.value = []
    cursorPoint.value = null
    clearVisualization()
    map.getCanvas().style.cursor = 'crosshair'
    map.doubleClickZoom.disable()
    _attachHandlers(map)
  }

  function stopMeasure() {
    const map = mapStore.mapInstance
    if (!map) return
    measureActive.value = false
    cursorPoint.value = null
    map.getCanvas().style.cursor = ''
    map.doubleClickZoom.enable()
    _detachHandlers(map)
    clearVisualization()
    measurePoints.value = []
  }

  function toggleMeasure(mode: MeasureMode = 'distance') {
    if (measureActive.value && measureMode.value === mode) stopMeasure()
    else {
      if (measureActive.value) stopMeasure()
      startMeasure(mode)
    }
  }

  return {
    measureActive,
    measureMode,
    measurePoints,
    totalDistance,
    totalArea,
    perimeter,
    formattedTotal,
    formattedArea,
    formattedPerimeter,
    segmentDistances,
    setupLayers,
    addPoint,
    undoLastPoint,
    clearMeasure,
    startMeasure,
    stopMeasure,
    toggleMeasure,
    updateVisualization,
  }
}
