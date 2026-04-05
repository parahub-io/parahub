/**
 * Sun study tool for the map.
 * Shows sun direction + shadow direction based on date/time.
 * Uses suncalc for astronomical calculations.
 */

import { ref, computed, watch } from 'vue'
import SunCalc from 'suncalc'

const EMPTY_FC: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] }

// Layer / source IDs — single source for sun elements (1 worker round-trip instead of 3)
const SRC_SUN = 'sun-study'
const LYR_SUN_DIR = 'sun-direction-line'
const LYR_SHADOW_DIR = 'sun-shadow-line'
const LYR_SUN_MARKER = 'sun-marker-layer'
const SRC_TERMINATOR = 'sun-terminator'
const LYR_TERM_OUTER = 'sun-term-outer'  // pre-twilight band (-6° to 0°)
const LYR_TERM_MID = 'sun-term-mid'      // civil twilight (0° to +6°)
const LYR_TERM_INNER = 'sun-term-inner'  // full night (beyond +6°)
const LYR_TERMINATOR_LINE = 'sun-terminator-line'

// Module-level handler for cleanup
let _moveEndHandler: (() => void) | null = null
let _realtimeInterval: ReturnType<typeof setInterval> | null = null
let _rafId: number | null = null

export function useMapSunStudy() {
  const mapStore = useMapStore()
  const colorMode = useColorMode()

  // ======== State ========

  const sunStudyActive = ref(false)
  const sunTimeMinutes = ref(_nowMinutes())
  const sunDateISO = ref(_todayISO()) // "YYYY-MM-DD"
  const realtimeMode = ref(true) // true = clock ticks in real-time
  const mapCenter = ref({ lat: 38.7223, lng: -9.1393 }) // reactive, updated on moveend

  // ======== Computed ========

  const formattedTime = computed(() => {
    const h = Math.floor(sunTimeMinutes.value / 60)
    const m = sunTimeMinutes.value % 60
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
  })

  const selectedDateTime = computed(() => {
    const [y, mo, d] = sunDateISO.value.split('-').map(Number)
    const h = Math.floor(sunTimeMinutes.value / 60)
    const m = sunTimeMinutes.value % 60
    return new Date(y, mo - 1, d, h, m)
  })

  function _syncMapCenter() {
    const map = mapStore.mapInstance
    if (!map) return
    const c = map.getCenter()
    mapCenter.value = { lat: c.lat, lng: c.lng }
  }

  const sunPosition = computed(() => {
    const pos = SunCalc.getPosition(selectedDateTime.value, mapCenter.value.lat, mapCenter.value.lng)
    return {
      // suncalc azimuth: 0 = south, π = north, positive = west. Convert to geographic bearing (0 = north, clockwise)
      azimuthDeg: ((pos.azimuth * 180 / Math.PI) + 180) % 360,
      altitudeDeg: pos.altitude * 180 / Math.PI,
    }
  })

  const sunTimes = computed(() => {
    const times = SunCalc.getTimes(selectedDateTime.value, mapCenter.value.lat, mapCenter.value.lng)
    return {
      sunrise: _formatTime(times.sunrise),
      sunset: _formatTime(times.sunset),
      goldenHourStart: times.goldenHour, // evening golden hour start
      goldenHourEnd: times.sunset,
      goldenHourMorningStart: times.sunrise,
      goldenHourMorningEnd: times.goldenHourEnd, // morning golden hour end
      blueHourStart: times.blueHourDawn || null,
      blueHourEnd: times.blueHourDawnEnd || null,
      blueHourEveningStart: times.blueHourDusk || null,
      blueHourEveningEnd: times.blueHourDuskEnd || null,
    }
  })

  const isGoldenHour = computed(() => {
    const t = selectedDateTime.value.getTime()
    const times = SunCalc.getTimes(selectedDateTime.value, mapCenter.value.lat, mapCenter.value.lng)
    // Evening golden hour
    if (t >= times.goldenHour.getTime() && t <= times.sunset.getTime()) return true
    // Morning golden hour
    if (t >= times.sunrise.getTime() && t <= times.goldenHourEnd.getTime()) return true
    return false
  })

  const isNight = computed(() => sunPosition.value.altitudeDeg < 0)

  // ======== Helpers ========

  function _todayISO(): string {
    const d = new Date()
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  }

  function _nowMinutes(): number {
    const d = new Date()
    return d.getHours() * 60 + d.getMinutes()
  }

  function _formatTime(d: Date): string {
    if (!d || isNaN(d.getTime())) return '--:--'
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  }

  /** Offset a point by distance (meters) and bearing (degrees, 0=north, clockwise) */
  function _offsetPoint(lng: number, lat: number, distanceM: number, bearingDeg: number): [number, number] {
    const R = 6371000
    const brng = bearingDeg * Math.PI / 180
    const lat1 = lat * Math.PI / 180
    const lng1 = lng * Math.PI / 180
    const d = distanceM / R

    const lat2 = Math.asin(Math.sin(lat1) * Math.cos(d) + Math.cos(lat1) * Math.sin(d) * Math.cos(brng))
    const lng2 = lng1 + Math.atan2(Math.sin(brng) * Math.sin(d) * Math.cos(lat1), Math.cos(d) - Math.sin(lat1) * Math.sin(lat2))

    return [lng2 * 180 / Math.PI, lat2 * 180 / Math.PI]
  }

  // ======== Subsolar point (astronomical) ========

  /** Subsolar point: where the sun is directly overhead at a given instant (UTC) */
  function _getSubsolarPoint(date: Date): { lat: number; lng: number } {
    const J2000 = Date.UTC(2000, 0, 1, 12)
    const d = (date.getTime() - J2000) / 86400000
    const M = (357.5291 + 0.98560028 * d) % 360
    const Mrad = M * Math.PI / 180
    const C = 1.9148 * Math.sin(Mrad) + 0.02 * Math.sin(2 * Mrad) + 0.0003 * Math.sin(3 * Mrad)
    const L = (M + C + 180 + 102.9372) % 360
    const Lrad = L * Math.PI / 180
    const obliquity = 23.4393 * Math.PI / 180
    const dec = Math.asin(Math.sin(Lrad) * Math.sin(obliquity))
    const RA = Math.atan2(Math.sin(Lrad) * Math.cos(obliquity), Math.cos(Lrad))
    const GMST = (280.16 + 360.9856235 * d) % 360
    return {
      lat: dec * 180 / Math.PI,
      lng: ((RA * 180 / Math.PI - GMST + 540) % 360) - 180,
    }
  }

  // ======== GeoJSON ========

  /** Line length in meters that looks ~15% of viewport width at current zoom */
  function _viewportLineLen(): number {
    const map = mapStore.mapInstance
    if (!map) return 400
    // meters per pixel at current zoom & latitude
    const zoom = map.getZoom()
    const lat = mapCenter.value.lat
    const mpp = 156543.03 * Math.cos(lat * Math.PI / 180) / Math.pow(2, zoom)
    // ~15% of viewport width
    const canvas = map.getCanvas()
    const px = canvas ? canvas.width * 0.15 / (window.devicePixelRatio || 1) : 200
    return Math.max(100, mpp * px)
  }

  function _buildSunLineGeoJSON(): GeoJSON.FeatureCollection {
    if (!sunStudyActive.value) return EMPTY_FC
    const { lat, lng } = mapCenter.value
    const az = sunPosition.value.azimuthDeg
    const alt = sunPosition.value.altitudeDeg
    if (alt < -6) return EMPTY_FC // deep night, no meaningful direction

    const lineLen = _viewportLineLen()
    const endPoint = _offsetPoint(lng, lat, lineLen, az)

    return {
      type: 'FeatureCollection',
      features: [{
        type: 'Feature',
        properties: {},
        geometry: { type: 'LineString', coordinates: [[lng, lat], endPoint] },
      }],
    }
  }

  function _buildShadowLineGeoJSON(): GeoJSON.FeatureCollection {
    if (!sunStudyActive.value) return EMPTY_FC
    const { lat, lng } = mapCenter.value
    const az = sunPosition.value.azimuthDeg
    const alt = sunPosition.value.altitudeDeg
    if (alt <= 0) return EMPTY_FC // no shadow when sun is below horizon

    // Shadow length proportional to viewport but scaled by sun altitude
    const baseLen = _viewportLineLen()
    const altRad = Math.max(alt * Math.PI / 180, 0.05)
    const shadowLen = Math.min(baseLen * 1.5, baseLen * 0.25 / Math.tan(altRad))
    const shadowBearing = (az + 180) % 360
    const endPoint = _offsetPoint(lng, lat, shadowLen, shadowBearing)

    return {
      type: 'FeatureCollection',
      features: [{
        type: 'Feature',
        properties: {},
        geometry: { type: 'LineString', coordinates: [[lng, lat], endPoint] },
      }],
    }
  }

  function _buildSunMarkerGeoJSON(): GeoJSON.FeatureCollection {
    if (!sunStudyActive.value) return EMPTY_FC
    const { lat, lng } = mapCenter.value
    const az = sunPosition.value.azimuthDeg
    const alt = sunPosition.value.altitudeDeg
    if (alt < -6) return EMPTY_FC

    const endPoint = _offsetPoint(lng, lat, _viewportLineLen(), az)
    return {
      type: 'FeatureCollection',
      features: [{
        type: 'Feature',
        properties: {},
        geometry: { type: 'Point', coordinates: endPoint },
      }],
    }
  }

  /**
   * Night gradient: 3 overlapping polygons at different solar altitude thresholds.
   * Stacking creates a smooth twilight gradient:
   *   -6° to 0° (pre-sunset glow), 0° to +6° (civil twilight), beyond +6° (full night).
   * Uses generalized equation: sin(h) = sin(δ)sin(φ) + cos(δ)cos(Δλ)cos(φ)
   */
  let _prevSubLat = NaN
  let _prevSubLng = NaN
  let _cachedNightFC: GeoJSON.FeatureCollection = EMPTY_FC
  let _nightDirty = false

  /** Compute terminator-like curve for a given sun altitude threshold */
  function _twilightLine(subLat: number, subLng: number, altDeg: number): [number, number][] {
    const decRad = subLat * Math.PI / 180
    const sinDec = Math.sin(decRad)
    const cosDec = Math.cos(decRad)
    const sinAlt = Math.sin(altDeg * Math.PI / 180)
    const line: [number, number][] = []
    for (let lng = -180; lng <= 180; lng += 2) {
      const dLngRad = (lng - subLng) * Math.PI / 180
      const a = sinDec
      const b = cosDec * Math.cos(dLngRad)
      const R = Math.sqrt(a * a + b * b)
      let phi: number
      if (R < 1e-10) {
        phi = 0
      } else {
        const cR = -sinAlt / R
        if (cR > 1) { phi = -90; } // permanent day at this longitude
        else if (cR < -1) { phi = 90; } // permanent night
        else { phi = (Math.atan2(a, b) - Math.acos(cR)) * 180 / Math.PI }
      }
      line.push([lng, Math.max(-90, Math.min(90, phi))])
    }
    return line
  }

  /** Close a twilight line into a night polygon (CCW ring) */
  function _closeNightRing(line: [number, number][], nightPoleUp: boolean): [number, number][] {
    const ring: [number, number][] = []
    if (!nightPoleUp) {
      // Night extends south: south pole east, then terminator west
      ring.push([-180, -90], [180, -90])
      for (let i = line.length - 1; i >= 0; i--) ring.push(line[i])
      ring.push([-180, -90])
    } else {
      // Night extends north: terminator east, then north pole west
      ring.push(...line)
      ring.push([180, 90], [-180, 90])
      ring.push(line[0])
    }
    return ring
  }

  function _buildNightGeoJSON(): GeoJSON.FeatureCollection {
    if (!sunStudyActive.value) { _nightDirty = false; return EMPTY_FC }
    const sub = _getSubsolarPoint(selectedDateTime.value)
    if (Math.abs(sub.lat - _prevSubLat) < 0.5 && Math.abs(sub.lng - _prevSubLng) < 0.5) {
      _nightDirty = false
      return _cachedNightFC
    }
    _nightDirty = true
    _prevSubLat = sub.lat
    _prevSubLng = sub.lng
    const poleUp = sub.lat < 0

    // 3 bands: outer (-6°), mid (0°/terminator), inner (+6°)
    const bands = [-6, 0, 6]
    const features: GeoJSON.Feature[] = bands.map(alt => ({
      type: 'Feature' as const,
      properties: { band: alt },
      geometry: {
        type: 'Polygon' as const,
        coordinates: [_closeNightRing(_twilightLine(sub.lat, sub.lng, alt), poleUp)],
      },
    }))

    _cachedNightFC = { type: 'FeatureCollection', features }
    return _cachedNightFC
  }

  // ======== Layer Management ========

  function setupLayers(map: any) {
    if (map.getSource(SRC_SUN)) return

    // Single source for sun/shadow/marker — 1 worker round-trip instead of 3
    map.addSource(SRC_SUN, { type: 'geojson', data: EMPTY_FC })
    map.addSource(SRC_TERMINATOR, { type: 'geojson', data: EMPTY_FC })

    // Night gradient — 3 overlapping fill layers, opacities stack for smooth twilight
    map.addLayer({
      id: LYR_TERM_OUTER, type: 'fill', source: SRC_TERMINATOR,
      filter: ['==', ['get', 'band'], -6],
      paint: { 'fill-color': '#000020', 'fill-opacity': 0.08 },
    })
    map.addLayer({
      id: LYR_TERM_MID, type: 'fill', source: SRC_TERMINATOR,
      filter: ['==', ['get', 'band'], 0],
      paint: { 'fill-color': '#000020', 'fill-opacity': 0.10 },
    })
    map.addLayer({
      id: LYR_TERM_INNER, type: 'fill', source: SRC_TERMINATOR,
      filter: ['==', ['get', 'band'], 6],
      paint: { 'fill-color': '#000020', 'fill-opacity': 0.12 },
    })

    // Thin terminator line at actual sunset boundary
    map.addLayer({
      id: LYR_TERMINATOR_LINE, type: 'line', source: SRC_TERMINATOR,
      filter: ['==', ['get', 'band'], 0],
      paint: { 'line-color': '#f59e0b', 'line-width': 1, 'line-opacity': 0.3 },
    })

    // Shadow line (gray, dashed) — filtered from combined source
    map.addLayer({
      id: LYR_SHADOW_DIR,
      type: 'line',
      source: SRC_SUN,
      filter: ['==', ['get', 'role'], 'shadow'],
      paint: { 'line-color': '#4b5563', 'line-width': 4, 'line-dasharray': [3, 2], 'line-opacity': 0.6 },
      layout: { 'line-cap': 'round' },
    })

    // Sun direction line (orange)
    map.addLayer({
      id: LYR_SUN_DIR,
      type: 'line',
      source: SRC_SUN,
      filter: ['==', ['get', 'role'], 'sun'],
      paint: { 'line-color': '#f59e0b', 'line-width': 4, 'line-opacity': 0.85 },
      layout: { 'line-cap': 'round' },
    })

    // Sun marker (circle at end of direction line)
    map.addLayer({
      id: LYR_SUN_MARKER,
      type: 'circle',
      source: SRC_SUN,
      filter: ['==', ['get', 'role'], 'marker'],
      paint: { 'circle-radius': 10, 'circle-color': '#f59e0b', 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 2, 'circle-opacity': 0.9 },
    })
  }

  let _lastLightTime = 0
  let _pendingLightTimer: ReturnType<typeof setTimeout> | null = null

  function _updateLight(map: any) {
    // setLight triggers a full map re-render (~18ms). Throttle to max 10Hz.
    const now = performance.now()
    if (now - _lastLightTime < 100) {
      // Schedule a trailing update so final position is always applied
      if (!_pendingLightTimer) {
        _pendingLightTimer = setTimeout(() => {
          _pendingLightTimer = null
          _applyLight(map)
        }, 100)
      }
      return
    }
    _applyLight(map)
  }

  function _applyLight(map: any) {
    _lastLightTime = performance.now()
    const az = sunPosition.value.azimuthDeg
    const alt = sunPosition.value.altitudeDeg
    const polar = Math.max(0, Math.min(90, 90 - alt))
    const intensity = alt > 0 ? 0.4 + 0.2 * Math.min(alt / 45, 1) : 0.15
    let color = '#ffffff'
    if (alt <= 0) color = '#8090b0'
    else if (alt < 10) color = '#ffcc66'
    else if (alt < 25) color = '#ffe0a0'
    map.setLight({ anchor: 'map', position: [1.5, az, polar], color, intensity })
  }

  function _resetLight(map: any) {
    map.setLight({ anchor: 'viewport', position: [1.15, 210, 30], color: '#ffffff', intensity: 0.5 })
  }

  function _applyTerminatorTheme(map: any) {
    const dark = colorMode.value === 'dark'
    const c = dark ? '#000000' : '#000020'
    // Stacked opacities: outer 0.08/0.12, mid 0.10/0.18, inner 0.12/0.20
    // Total at full night: dark 0.50, light 0.30
    map.setPaintProperty(LYR_TERM_OUTER, 'fill-color', c)
    map.setPaintProperty(LYR_TERM_OUTER, 'fill-opacity', dark ? 0.12 : 0.08)
    map.setPaintProperty(LYR_TERM_MID, 'fill-color', c)
    map.setPaintProperty(LYR_TERM_MID, 'fill-opacity', dark ? 0.18 : 0.10)
    map.setPaintProperty(LYR_TERM_INNER, 'fill-color', c)
    map.setPaintProperty(LYR_TERM_INNER, 'fill-opacity', dark ? 0.20 : 0.12)
  }

  let _lastSourceUpdate = 0
  let _pendingSourceTimer: ReturnType<typeof setTimeout> | null = null

  function _pushSources(map: any) {
    _lastSourceUpdate = performance.now()
    const features: GeoJSON.Feature[] = []
    for (const f of _buildSunLineGeoJSON().features) features.push({ ...f, properties: { role: 'sun' } })
    for (const f of _buildShadowLineGeoJSON().features) features.push({ ...f, properties: { role: 'shadow' } })
    for (const f of _buildSunMarkerGeoJSON().features) features.push({ ...f, properties: { role: 'marker' } })
    const sunSrc = map.getSource(SRC_SUN)
    if (sunSrc) sunSrc.setData({ type: 'FeatureCollection', features })
    const nightData = _buildNightGeoJSON()
    if (_nightDirty) {
      const termSrc = map.getSource(SRC_TERMINATOR)
      if (termSrc) termSrc.setData(nightData)
    }
  }

  function updateVisualization() {
    const map = mapStore.mapInstance
    if (!map) return
    // Throttle MapLibre source updates to ~15Hz — each setData triggers a full re-render
    const now = performance.now()
    if (now - _lastSourceUpdate < 66) {
      // Schedule trailing update so final slider position is always rendered
      if (!_pendingSourceTimer) {
        _pendingSourceTimer = setTimeout(() => {
          _pendingSourceTimer = null
          _pushSources(map)
          _updateLight(map)
        }, 66)
      }
      return
    }
    // Cancel trailing timer — we're updating now
    if (_pendingSourceTimer) { clearTimeout(_pendingSourceTimer); _pendingSourceTimer = null }
    _pushSources(map)
    _updateLight(map)
  }

  function clearVisualization() {
    const map = mapStore.mapInstance
    if (!map) return
    const sunSrc = map.getSource(SRC_SUN)
    const termSrc = map.getSource(SRC_TERMINATOR)
    if (sunSrc) sunSrc.setData(EMPTY_FC)
    if (termSrc) termSrc.setData(EMPTY_FC)
    _prevSubLat = NaN
    _prevSubLng = NaN
    _cachedNightFC = EMPTY_FC
    _lastLightTime = 0
    _lastSourceUpdate = 0
    if (_pendingLightTimer) { clearTimeout(_pendingLightTimer); _pendingLightTimer = null }
    if (_pendingSourceTimer) { clearTimeout(_pendingSourceTimer); _pendingSourceTimer = null }
  }

  // ======== Interaction ========

  function _startRealtimeClock() {
    _stopRealtimeClock()
    _realtimeInterval = setInterval(() => {
      if (!realtimeMode.value || !sunStudyActive.value) return
      sunTimeMinutes.value = _nowMinutes()
      // Also keep date in sync (handles midnight rollover)
      sunDateISO.value = _todayISO()
    }, 60_000) // update every minute
  }

  function _stopRealtimeClock() {
    if (_realtimeInterval) {
      clearInterval(_realtimeInterval)
      _realtimeInterval = null
    }
  }

  function startSunStudy() {
    const map = mapStore.mapInstance
    if (!map) return
    // Reset to current real time
    realtimeMode.value = true
    sunDateISO.value = _todayISO()
    sunTimeMinutes.value = _nowMinutes()
    _syncMapCenter()

    if (!sunStudyActive.value) {
      sunStudyActive.value = true
      _moveEndHandler = () => { _syncMapCenter(); updateVisualization() }
      map.on('moveend', _moveEndHandler)
    }

    _applyTerminatorTheme(map)
    updateVisualization()
    _startRealtimeClock()
  }

  function stopSunStudy() {
    const map = mapStore.mapInstance
    sunStudyActive.value = false
    clearVisualization()
    _stopRealtimeClock()
    if (_rafId) { cancelAnimationFrame(_rafId); _rafId = null }
    if (map) {
      _resetLight(map)
      if (_moveEndHandler) {
        map.off('moveend', _moveEndHandler)
        _moveEndHandler = null
      }
    }
  }

  function toggleSunStudy() {
    if (sunStudyActive.value) stopSunStudy()
    else startSunStudy()
  }

  // Watch time/date changes to update visualization (RAF-throttled to avoid jank on slider drag)
  function _scheduleUpdate() {
    if (_rafId) return
    _rafId = requestAnimationFrame(() => {
      _rafId = null
      if (sunStudyActive.value) updateVisualization()
    })
  }

  watch([sunTimeMinutes, sunDateISO], _scheduleUpdate)

  // Break out of real-time mode when user manually changes date away from today
  watch(sunDateISO, (val) => {
    if (val !== _todayISO()) {
      realtimeMode.value = false
    }
  })

  return {
    sunStudyActive,
    sunTimeMinutes,
    sunDateISO,
    realtimeMode,
    sunPosition,
    sunTimes,
    formattedTime,
    isGoldenHour,
    isNight,
    setupLayers,
    startSunStudy,
    stopSunStudy,
    toggleSunStudy,
    updateVisualization,
  }
}
