import { ref, watch } from 'vue'

interface RoutePoint {
  lat: number
  lon: number
  name: string
}

// --- Valhalla types ---

interface TransitStop {
  name: string
  arrival_date_time?: string
  departure_date_time?: string
  lat: number
  lon: number
}

interface TransitInfo {
  short_name?: string
  long_name?: string
  headsign?: string
  color?: number
  text_color?: number
  operator?: string
  transit_stops?: TransitStop[]
}

interface ValhallaManeuver {
  type: number
  instruction: string
  length: number
  time: number
  begin_shape_index: number
  end_shape_index: number
  street_names?: string[]
  transit_info?: TransitInfo
  travel_type?: string
}

interface ValhallaSummary {
  length: number
  time: number
}

interface ValhallaLeg {
  maneuvers: ValhallaManeuver[]
  shape: string
  summary: ValhallaSummary
}

interface ValhallaTrip {
  legs: ValhallaLeg[]
  summary: ValhallaSummary
}

// --- MOTIS types ---

interface MotisPlace {
  name: string
  lat: number
  lon: number
  stopId?: string
  departure?: string
  arrival?: string
}

interface MotisLeg {
  mode: string
  from: MotisPlace
  to: MotisPlace
  duration: number
  distance?: number
  startTime: string
  endTime: string
  legGeometry: { points: string; length: number }
  routeShortName?: string
  routeLongName?: string
  headsign?: string
  agencyName?: string
  routeColor?: string
  routeTextColor?: string
  intermediateStops?: MotisPlace[]
  realTime?: boolean
}

interface MotisItinerary {
  duration: number
  startTime: string
  endTime: string
  transfers: number
  legs: MotisLeg[]
}

// Module-level refs for KeepAlive persistence
const origin = ref<RoutePoint | null>(null)
const destination = ref<RoutePoint | null>(null)
const costing = ref<'auto' | 'pedestrian' | 'bicycle' | 'multimodal'>('multimodal')
const departureTime = ref<string>('')
const routeData = ref<ValhallaTrip | null>(null)
const motisData = ref<{ itineraries: MotisItinerary[] } | null>(null)
const selectedItinerary = ref(0)
const routeGeoJSON = ref<GeoJSON.Feature | GeoJSON.FeatureCollection | null>(null)
const routeBounds = ref<[[number, number], [number, number]] | null>(null)
const decodedShapeCoords = ref<[number, number][]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const awaitingMapClick = ref<'origin' | 'destination' | null>(null)

/** Decode polyline6 to [lng, lat][] coordinates */
function decodePolyline6(encoded: string): [number, number][] {
  const coords: [number, number][] = []
  let index = 0
  let lat = 0
  let lng = 0

  while (index < encoded.length) {
    let shift = 0
    let result = 0
    let byte: number

    do {
      byte = encoded.charCodeAt(index++) - 63
      result |= (byte & 0x1f) << shift
      shift += 5
    } while (byte >= 0x20)
    lat += (result & 1) ? ~(result >> 1) : (result >> 1)

    shift = 0
    result = 0
    do {
      byte = encoded.charCodeAt(index++) - 63
      result |= (byte & 0x1f) << shift
      shift += 5
    } while (byte >= 0x20)
    lng += (result & 1) ? ~(result >> 1) : (result >> 1)

    coords.push([lng / 1e6, lat / 1e6])
  }
  return coords
}

/** Default colors for transit modes */
const MODE_COLORS: Record<string, string> = {
  WALK: '#6b7280',
  BUS: '#ef4444',
  TRAM: '#22c55e',
  SUBWAY: '#8b5cf6',
  RAIL: '#3b82f6',
  FERRY: '#06b6d4',
}

/** Build a FeatureCollection from MOTIS itinerary legs */
function buildMotisGeoJSON(itinerary: MotisItinerary): GeoJSON.FeatureCollection {
  const features: GeoJSON.Feature[] = []
  for (const leg of itinerary.legs) {
    if (!leg.legGeometry?.points) continue
    const coords = decodePolyline6(leg.legGeometry.points)
    if (coords.length < 2) continue

    // Use GTFS route color if available, otherwise mode default
    let color = MODE_COLORS[leg.mode] || '#8b5cf6'
    if (leg.routeColor) {
      const rc = leg.routeColor.replace(/^#/, '')
      color = `#${rc}`
    }

    features.push({
      type: 'Feature',
      properties: {
        mode: leg.mode,
        color,
        isWalk: leg.mode === 'WALK',
        routeShortName: leg.routeShortName || '',
      },
      geometry: { type: 'LineString', coordinates: coords },
    })
  }
  return { type: 'FeatureCollection', features }
}

export function useRouting() {
  const { locale } = useI18n()

  const fetchRoute = async () => {
    if (!origin.value || !destination.value) return

    loading.value = true
    error.value = null
    routeData.value = null
    motisData.value = null
    selectedItinerary.value = 0
    routeGeoJSON.value = null
    routeBounds.value = null

    try {
      if (costing.value === 'multimodal') {
        await fetchMotisRoute()
      } else {
        await fetchValhallaRoute()
      }
    } catch (e: any) {
      console.warn('[useRouting] Route fetch failed:', e)
      error.value = e?.data?.error || e?.data?.message || e?.message || 'Route not found'
    } finally {
      loading.value = false
    }
  }

  const fetchValhallaRoute = async () => {
    const body: Record<string, any> = {
      locations: [
        { lat: origin.value!.lat, lon: origin.value!.lon },
        { lat: destination.value!.lat, lon: destination.value!.lon },
      ],
      costing: costing.value,
      directions_options: { units: 'km', language: locale.value },
    }

    const data = await $fetch<{ trip: ValhallaTrip }>('/api/v1/routing/route', {
      method: 'POST',
      body,
    })

    routeData.value = data.trip

    if (data.trip.legs?.length) {
      const allCoords: [number, number][] = []
      for (const leg of data.trip.legs) {
        allCoords.push(...decodePolyline6(leg.shape))
      }
      decodedShapeCoords.value = allCoords

      routeGeoJSON.value = {
        type: 'Feature',
        properties: {},
        geometry: { type: 'LineString', coordinates: allCoords },
      }

      const lngs = allCoords.map(c => c[0])
      const lats = allCoords.map(c => c[1])
      routeBounds.value = [
        [Math.min(...lngs), Math.min(...lats)],
        [Math.max(...lngs), Math.max(...lats)],
      ]
    }
  }

  const fetchMotisRoute = async () => {
    const dt = departureTime.value
      ? new Date(departureTime.value).toISOString()
      : new Date().toISOString()

    const params = new URLSearchParams({
      fromPlace: `${origin.value!.lat},${origin.value!.lon}`,
      toPlace: `${destination.value!.lat},${destination.value!.lon}`,
      time: dt,
      transitModes: 'TRANSIT',
      preTransitModes: 'WALK',
      postTransitModes: 'WALK',
    })

    const data = await $fetch<{ itineraries: MotisItinerary[] }>(
      `/api/v1/routing/transit?${params.toString()}`
    )

    if (!data.itineraries?.length) {
      throw new Error('No transit routes found')
    }

    motisData.value = data

    // Build GeoJSON from first itinerary
    const geojson = buildMotisGeoJSON(data.itineraries[0])
    routeGeoJSON.value = geojson

    // Compute bounds from all leg coordinates
    const allCoords: [number, number][] = []
    for (const feature of geojson.features) {
      if (feature.geometry.type === 'LineString') {
        allCoords.push(...(feature.geometry.coordinates as [number, number][]))
      }
    }
    if (allCoords.length) {
      const lngs = allCoords.map(c => c[0])
      const lats = allCoords.map(c => c[1])
      routeBounds.value = [
        [Math.min(...lngs), Math.min(...lats)],
        [Math.max(...lngs), Math.max(...lats)],
      ]
    }
  }

  const selectItinerary = (idx: number) => {
    if (!motisData.value || idx < 0 || idx >= motisData.value.itineraries.length) return
    selectedItinerary.value = idx

    const geojson = buildMotisGeoJSON(motisData.value.itineraries[idx])
    routeGeoJSON.value = geojson

    const allCoords: [number, number][] = []
    for (const feature of geojson.features) {
      if (feature.geometry.type === 'LineString') {
        allCoords.push(...(feature.geometry.coordinates as [number, number][]))
      }
    }
    if (allCoords.length) {
      const lngs = allCoords.map(c => c[0])
      const lats = allCoords.map(c => c[1])
      routeBounds.value = [
        [Math.min(...lngs), Math.min(...lats)],
        [Math.max(...lngs), Math.max(...lats)],
      ]
    }
  }

  const swapPoints = () => {
    const tmp = origin.value
    origin.value = destination.value
    destination.value = tmp
  }

  const clearRoute = () => {
    origin.value = null
    destination.value = null
    routeData.value = null
    motisData.value = null
    selectedItinerary.value = 0
    routeGeoJSON.value = null
    routeBounds.value = null
    error.value = null
    awaitingMapClick.value = null
    departureTime.value = ''
  }

  // Auto-fetch when both points are set or costing/departureTime changes
  watch([origin, destination, costing, departureTime], () => {
    if (origin.value && destination.value) {
      fetchRoute()
    }
  })

  return {
    origin,
    destination,
    costing,
    departureTime,
    routeData,
    motisData,
    selectedItinerary,
    routeGeoJSON,
    routeBounds,
    decodedShapeCoords,
    loading,
    error,
    awaitingMapClick,
    fetchRoute,
    selectItinerary,
    swapPoints,
    clearRoute,
    decodePolyline6,
  }
}
