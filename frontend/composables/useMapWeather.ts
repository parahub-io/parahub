import { ref } from 'vue'

export interface WeatherData {
  available: boolean
  cell?: { lat: number; lon: number }
  observed_at?: string
  temperature?: number
  apparent_temperature?: number
  weather_code?: number
  is_day?: boolean
  precipitation?: number
  // Meteorological: degrees the wind blows FROM (0 = from north).
  wind_direction?: number
  wind_speed?: number
  wind_gusts?: number
  units?: { temperature: string; wind_speed: string }
  attribution?: { name: string; url: string; license: string }
}

// ~0.1° ≈ 11 km cell, matching the backend grid. Client-side dedup only avoids
// redundant fetches — the server re-snaps authoritatively, so a boundary
// rounding mismatch at worst costs one extra request, never wrong data.
const GRID = 0.1

// Module-level singletons: survive KeepAlive re-activation of MapView, shared
// by the HUD and any other consumer (e.g. transit-stop weather).
const weather = ref<WeatherData | null>(null)
const loading = ref(false)
let lastCell = ''
let lastFetchAt = 0
let inflight = ''

// Re-poll the SAME cell at most this often. Weather isn't a streaming quantity
// (Open-Meteo's `current` refreshes ~15 min, our backend caches 30 min), so a WS
// push would re-send an unchanged value every tick — wrong tool. Instead a timer
// in MapView calls refresh() periodically; this gate lets a same-cell call hit
// the API again once its reading has aged out, while rapid pans (jitter, pan
// away-and-back within the window) still dedup. Cross-cell moves never wait.
const FRESH_MS = 12 * 60 * 1000

function cellKey(lat: number, lon: number): string {
  const snap = (v: number) => (Math.round(v / GRID) * GRID).toFixed(2)
  return `${snap(lat)},${snap(lon)}`
}

export function useMapWeather() {
  /**
   * Fetch current weather for a point, deduped by grid cell. Cheap to call on
   * every map move: it only hits the API when the snapped cell actually changes.
   */
  async function refresh(lat: number, lon: number) {
    const key = cellKey(lat, lon)
    // Skip if this cell's reading is still fresh, or a fetch for it is in flight.
    const sameCellFresh = key === lastCell && weather.value?.available &&
      (Date.now() - lastFetchAt) < FRESH_MS
    if (sameCellFresh || key === inflight) return
    inflight = key
    loading.value = true
    try {
      const data = await $fetch<WeatherData>('/api/v1/geo/weather', {
        params: { lat, lon },
      })
      // Ignore the response if the user has since moved to another cell.
      if (inflight === key) {
        lastCell = key
        if (data?.available) {
          weather.value = data
          lastFetchAt = Date.now()
        }
      }
    } catch {
      // Keep the last known value; transient failures shouldn't blank the HUD.
    } finally {
      if (inflight === key) inflight = ''
      loading.value = false
    }
  }

  return { weather, loading, refresh }
}
