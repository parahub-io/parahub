/**
 * Smooth position tweening for live transit-vehicle GeoJSON sources.
 *
 * GTFS-RT positions arrive in ~30s WS ticks; pushed straight into a MapLibre
 * GeoJSON source they snap the icon to the new spot. This animator glides each
 * vehicle from its last shown position to the new one over `duration` ms (linear
 * — vehicles travel at ~constant speed between samples, so easing would add an
 * unnatural per-tick pulse), calling `apply` with an interpolated
 * FeatureCollection every animation frame.
 *
 * Keyed by a stable per-vehicle id so the same vehicle tweens across ticks:
 *  - new vehicle (no prior position) → appears in place, no slide-in
 *  - vanished vehicle → dropped from the next frame
 *  - a fresh target mid-flight → re-aims from the CURRENT interpolated position
 *
 * Guards: a teleport farther than `maxAnimateMeters` snaps (feed glitch / vehicle
 * re-entering the bbox elsewhere shouldn't fly across the map), and above
 * `maxAnimateFeatures` the whole set snaps (don't run 60fps setData on hundreds
 * of points). All features still render correctly in every case — the guards only
 * drop the eye-candy, never a vehicle.
 */

type LngLat = [number, number]

interface AnimatedFeature {
  key: string
  from: LngLat
  to: LngLat
  feature: any
}

export interface VehicleAnimatorOptions {
  /** Push the interpolated FeatureCollection to the map source. */
  apply: (fc: any) => void
  /** Stable per-vehicle key. Default reads `vehicle_id` then `v`. */
  getKey?: (feature: any) => string
  /** Tween length in ms (default 1000). */
  duration?: number
  /** Beyond this straight-line jump, snap instead of slide (default 5000m). */
  maxAnimateMeters?: number
  /** Above this feature count, snap the whole set (default 350). */
  maxAnimateFeatures?: number
}

function metersBetween(a: LngLat, b: LngLat): number {
  const dLat = (b[1] - a[1]) * 111320
  const dLon = (b[0] - a[0]) * 111320 * Math.cos((a[1] * Math.PI) / 180)
  return Math.hypot(dLat, dLon)
}

export function createVehicleAnimator(opts: VehicleAnimatorOptions) {
  const duration = opts.duration ?? 1000
  const maxAnimateMeters = opts.maxAnimateMeters ?? 5000
  const maxAnimateFeatures = opts.maxAnimateFeatures ?? 350
  const getKey = opts.getKey ?? ((f: any) => f?.properties?.vehicle_id ?? f?.properties?.v)

  // Last position actually shown for each vehicle — the tween's "from" anchor.
  const displayed = new Map<string, LngLat>()
  let segments: AnimatedFeature[] = []
  let startTs = 0
  let raf: number | null = null

  const canRaf = typeof requestAnimationFrame !== 'undefined'

  function render(features: any[]) {
    opts.apply({ type: 'FeatureCollection', features })
  }

  function snap(features: any[]) {
    const out = features.map((f: any) => {
      displayed.set(getKey(f), f.geometry.coordinates as LngLat)
      return f
    })
    render(out)
  }

  function frame(ts: number) {
    if (!startTs) startTs = ts
    const t = Math.min((ts - startTs) / duration, 1)
    const features = segments.map((s) => {
      const lon = s.from[0] + (s.to[0] - s.from[0]) * t
      const lat = s.from[1] + (s.to[1] - s.from[1]) * t
      const pos: LngLat = [lon, lat]
      displayed.set(s.key, pos)
      return { type: 'Feature', geometry: { type: 'Point', coordinates: pos }, properties: s.feature.properties }
    })
    render(features)
    if (t < 1) {
      raf = requestAnimationFrame(frame)
    } else {
      raf = null
      segments = []
    }
  }

  /** Aim every vehicle at its new position and (re)start the tween. */
  function setTarget(fc: any) {
    const features: any[] = fc?.features ?? []

    // Too many points to tween smoothly, or no rAF (SSR) → snap.
    if (!canRaf || features.length > maxAnimateFeatures) {
      if (raf != null) { cancelAnimationFrame(raf); raf = null }
      segments = []
      // prune vanished before snapping so `displayed` doesn't grow unbounded
      const next = new Set(features.map(getKey))
      for (const k of [...displayed.keys()]) if (!next.has(k)) displayed.delete(k)
      snap(features)
      return
    }

    const nextKeys = new Set<string>()
    segments = features.map((f: any) => {
      const key = getKey(f)
      nextKeys.add(key)
      const to = f.geometry.coordinates as LngLat
      // From = current shown position (continuity mid-flight). New vehicle, or a
      // teleport beyond the guard → start at the target (appears in place).
      let from = displayed.get(key) ?? to
      if (from !== to && metersBetween(from, to) > maxAnimateMeters) from = to
      displayed.set(key, from)
      return { key, from, to, feature: f }
    })
    for (const k of [...displayed.keys()]) if (!nextKeys.has(k)) displayed.delete(k)

    startTs = 0
    if (raf == null) raf = requestAnimationFrame(frame)
  }

  /** Halt the tween and forget shown positions (next target appears in place). */
  function stop() {
    if (raf != null) { cancelAnimationFrame(raf); raf = null }
    segments = []
    displayed.clear()
  }

  return { setTarget, stop }
}
