/**
 * Shared display helpers for OpenSky mission cards (recon-instrument design).
 *
 * The card reads like a flight-instrument readout: terse labelled values
 * (place, coordinates, area, frame count, survey date, pilot). These helpers
 * derive those values; engineering artifacts (ortho pixel size, tile indices)
 * are intentionally not surfaced.
 *
 * Pure functions + a couple of composables, auto-imported by Nuxt.
 */
import type { OpenSkyMission } from '~/composables/useOpenSky'

/** Human area readout: "1.4 ha" / "320 m²" / "2.1 km²". Input is m² from the API. */
export function formatArea(m2: number): string | null {
  if (!m2 || m2 <= 0) return null
  if (m2 >= 1_000_000) return `${(m2 / 1_000_000).toFixed(1)} km²`
  if (m2 >= 10_000) return `${(m2 / 10_000).toFixed(1)} ha`
  return `${Math.round(m2)} m²`
}

/** Instrument coordinate readout: "41.9871°N  8.4773°W". */
export function formatCoord(lat: number | null, lng: number | null): string | null {
  if (lat == null || lng == null) return null
  const ns = lat >= 0 ? 'N' : 'S'
  const ew = lng >= 0 ? 'E' : 'W'
  return `${Math.abs(lat).toFixed(4)}°${ns} ${Math.abs(lng).toFixed(4)}°${ew}`
}

export function missionInitials(name?: string | null): string {
  if (!name) return '··'
  const parts = name.trim().split(/\s+/).filter(Boolean)
  return ((parts[0]?.[0] ?? '') + (parts[1]?.[0] ?? '')).toUpperCase() || '··'
}

/** Tile thumbnail URL (Z18), or null when the mission has no published imagery. */
export function missionThumbnailUrl(mission: OpenSkyMission, zoom = 18): string | null {
  if (mission.status !== 'PUBLISHED' || mission.center_lat == null || mission.center_lng == null) return null
  const n = Math.pow(2, zoom)
  const x = Math.floor(((mission.center_lng + 180) / 360) * n)
  const latRad = (mission.center_lat * Math.PI) / 180
  const y = Math.floor(((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * n)
  return `/api/v1/geo/opensky/tiles/${zoom}/${x}/${y}.webp?mission_id=${mission.id}`
}

export function formatShortDate(dateStr: string | null | undefined, locale: string): string {
  if (!dateStr) return ''
  try {
    return new Intl.DateTimeFormat(locale, { day: '2-digit', month: 'short', year: 'numeric' }).format(new Date(dateStr))
  } catch {
    return dateStr.slice(0, 10)
  }
}

export function formatTilesCount(count: number): string {
  if (count >= 1_000_000) return `${(count / 1_000_000).toFixed(1)}M`
  if (count >= 1000) return `${(count / 1000).toFixed(1)}K`
  return String(count)
}

// ===== Reverse geocoding (place designation) =====

export interface GeoFeature {
  name: string | null
  locality: string | null
  localadmin: string | null
  county: string | null
  region: string | null
  country: string | null
  label: string | null
}

// Session cache: stable per location, avoids re-querying on re-render / tab switch.
const _revCache = new Map<string, GeoFeature | null>()

export function useReverseGeocode() {
  async function lookup(lat: number, lng: number): Promise<GeoFeature | null> {
    const key = `${lat.toFixed(4)},${lng.toFixed(4)}`
    if (_revCache.has(key)) return _revCache.get(key) ?? null
    try {
      const r = await $fetch<{ feature: GeoFeature | null }>('/api/geocode/reverse', { params: { lat, lon: lng } })
      const f = r?.feature ?? null
      _revCache.set(key, f)
      return f
    } catch {
      return null
    }
  }
  return { lookup }
}

/** Primary place name (freguesia/locality) for the DESIGNATION readout. */
export function placeName(f: GeoFeature | null): string | null {
  if (!f) return null
  return f.locality || f.localadmin || f.name || f.county || f.region || null
}

/** Secondary region line (e.g. "Viana do Castelo · Portugal"). */
export function placeRegion(f: GeoFeature | null): string | null {
  if (!f) return null
  const parts = [f.region, f.country].filter(Boolean)
  return parts.length ? parts.join(' · ') : null
}

/** Navigate to the map focused on a mission. */
export function useMissionActions() {
  const router = useRouter()
  const localePath = useLocalePath()
  function viewOnMap(mission: OpenSkyMission) {
    if (mission.center_lat == null || mission.center_lng == null) return
    router.push({
      path: localePath('/map'),
      query: {
        lat: mission.center_lat.toFixed(6),
        lng: mission.center_lng.toFixed(6),
        zoom: '17',
        opensky_mission: mission.id,
      },
    })
  }
  return { viewOnMap }
}
