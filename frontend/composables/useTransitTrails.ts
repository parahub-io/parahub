/**
 * useTransitTrails — animated comet trails behind live transit vehicles.
 *
 * Emission model: each vehicle's trail head is its *displayed* position (fed
 * per-frame by the icon glide animator), always rendered at full brightness;
 * the tail is past head positions pinned once per WS tick, fading by real age
 * in the TripsLayer shader. The comet is therefore emitted continuously by
 * the moving icon instead of jumping tick-to-tick.
 *
 * Route-focus mode: when a single route is focused, trail points snap onto
 * the route geometry and the path between them follows the street polyline
 * (timestamps interpolated by arc length) — a comet crawling along the
 * street rather than a straight chord. Points >SNAP_MAX_M off the shape
 * (detours, bad GPS) fall back to raw chords per segment.
 *
 * Rendering is a single TripsLayer subclass whose fragment shader shapes the
 * comet: the width envelope tapers to a point at the tail, a bright core
 * rides inside a soft glow (replacing the old core+halo layer pair — one
 * attribute upload and draw call instead of two), and the head is lifted
 * toward white so the trail reads as emitted by the icon. It lives in the
 * 'trails' group of the shared overlaid transit canvas
 * (utils/transitDeckOverlay), under the deck vehicle layers, so the
 * per-frame animation never drags MapLibre into a full-scene repaint. The
 * loop is interval-throttled (TICK_MS) and paused on hidden tabs.
 */

import type { TransitDeckOverlay } from '~/utils/transitDeckOverlay'

type LngLat = [number, number]

const TRAIL_GLOBAL_S = 75         // fade window, global view (~2.5 WS ticks)
const TRAIL_FOCUS_S = 90          // fade window, single-route focus (long snake)
const HIST_MAX_AGE_S = TRAIL_FOCUS_S + 30
const MAX_POINTS = 10             // per-vehicle pinned-history cap
const TICK_MS = 125               // 8 fps — fade steps this small are invisible
const SNAP_MAX_M = 80             // beyond this, a point is off-route → raw chord
const METERS_PER_DEG = 111320

interface TrailPoint {
  pos: LngLat
  ts: number                      // seconds, relative to session base (float32-safe)
  _snap?: { ver: number; ok: boolean; s: number; pos: LngLat; seg: number }
}

interface TrailEntry {
  hist: TrailPoint[]              // pinned past head positions, oldest first
  live: LngLat                    // currently displayed (animator) position
  routeId: string
  color: [number, number, number]
}

interface RouteGeom {
  ver: number
  routeId: string
  coords: LngLat[]
  flat: number[]                  // x,y pairs in meters (equirectangular)
  cum: number[]                   // arc length at each vertex, meters
  cosLat: number
}

function hexToRgb(hex: string): [number, number, number] {
  if (!/^[0-9a-fA-F]{6}$/.test(hex)) return [59, 130, 246]
  return [
    parseInt(hex.slice(0, 2), 16),
    parseInt(hex.slice(2, 4), 16),
    parseInt(hex.slice(4, 6), 16),
  ]
}

/** Longest LineString of a GeoJSON geometry (MultiLineString → longest part). */
function extractLine(geometry: any): LngLat[] | null {
  if (!geometry) return null
  if (geometry.type === 'LineString') return geometry.coordinates
  if (geometry.type === 'MultiLineString') {
    let best: LngLat[] | null = null
    for (const part of geometry.coordinates) {
      if (!best || part.length > best.length) best = part
    }
    return best
  }
  return null
}

let geomVer = 0

function buildRouteGeom(routeId: string, geometry: any): RouteGeom | null {
  const coords = extractLine(geometry)
  if (!coords || coords.length < 2) return null
  const cosLat = Math.cos((coords[0][1] * Math.PI) / 180)
  const flat: number[] = new Array(coords.length * 2)
  const cum: number[] = new Array(coords.length)
  let acc = 0
  for (let i = 0; i < coords.length; i++) {
    flat[i * 2] = coords[i][0] * METERS_PER_DEG * cosLat
    flat[i * 2 + 1] = coords[i][1] * METERS_PER_DEG
    if (i > 0) {
      acc += Math.hypot(flat[i * 2] - flat[i * 2 - 2], flat[i * 2 + 1] - flat[i * 2 - 1])
    }
    cum[i] = acc
  }
  return { ver: ++geomVer, routeId, coords, flat, cum, cosLat }
}

/** Nearest point on the route polyline: arc position, snapped coord, segment. */
function snapPoint(g: RouteGeom, p: LngLat) {
  const x = p[0] * METERS_PER_DEG * g.cosLat
  const y = p[1] * METERS_PER_DEG
  let bestD2 = Infinity
  let bestSeg = 0
  let bestT = 0
  for (let i = 0; i < g.coords.length - 1; i++) {
    const ax = g.flat[i * 2]
    const ay = g.flat[i * 2 + 1]
    const dx = g.flat[i * 2 + 2] - ax
    const dy = g.flat[i * 2 + 3] - ay
    const l2 = dx * dx + dy * dy
    let t = l2 ? ((x - ax) * dx + (y - ay) * dy) / l2 : 0
    t = t < 0 ? 0 : t > 1 ? 1 : t
    const ex = x - (ax + t * dx)
    const ey = y - (ay + t * dy)
    const d2 = ex * ex + ey * ey
    if (d2 < bestD2) {
      bestD2 = d2
      bestSeg = i
      bestT = t
    }
  }
  const a = g.coords[bestSeg]
  const b = g.coords[bestSeg + 1]
  return {
    ver: g.ver,
    ok: Math.sqrt(bestD2) <= SNAP_MAX_M,
    s: g.cum[bestSeg] + bestT * (g.cum[bestSeg + 1] - g.cum[bestSeg]),
    pos: [a[0] + bestT * (b[0] - a[0]), a[1] + bestT * (b[1] - a[1])] as LngLat,
    seg: bestSeg,
  }
}

/** Cache snaps on pinned points — they never move; the live head resnaps hot. */
function snapOf(g: RouteGeom, pt: TrailPoint) {
  if (!pt._snap || pt._snap.ver !== g.ver) pt._snap = snapPoint(g, pt.pos)
  return pt._snap
}

/** Expand chord pairs into the street-following polyline with arc-lerped ts. */
function buildSnappedPath(g: RouteGeom, pts: TrailPoint[], outPath: LngLat[], outTs: number[]) {
  let prev = pts[0]
  let prevSnap = snapOf(g, prev)
  outPath.push(prevSnap.ok ? prevSnap.pos : prev.pos)
  outTs.push(prev.ts)
  for (let i = 1; i < pts.length; i++) {
    const cur = pts[i]
    const curSnap = snapOf(g, cur)
    if (prevSnap.ok && curSnap.ok && prevSnap.s !== curSnap.s) {
      const sA = prevSnap.s
      const sB = curSnap.s
      const span = sB - sA
      if (sB > sA) {
        for (let v = prevSnap.seg + 1; v <= curSnap.seg; v++) {
          if (g.cum[v] <= sA || g.cum[v] >= sB) continue
          outPath.push(g.coords[v])
          outTs.push(prev.ts + ((g.cum[v] - sA) / span) * (cur.ts - prev.ts))
        }
      } else {
        for (let v = prevSnap.seg; v >= curSnap.seg + 1; v--) {
          if (g.cum[v] >= sA || g.cum[v] <= sB) continue
          outPath.push(g.coords[v])
          outTs.push(prev.ts + ((g.cum[v] - sA) / span) * (cur.ts - prev.ts))
        }
      }
      outPath.push(curSnap.pos)
      outTs.push(cur.ts)
    } else {
      outPath.push(curSnap.ok ? curSnap.pos : cur.pos)
      outTs.push(cur.ts)
    }
    prev = cur
    prevSnap = curSnap
  }
}

/**
 * Comet cross-section, replacing the stock TripsLayer linear fade (injected
 * over its 'fs:DECKGL_FILTER_COLOR' hook; the time-window discard in
 * 'fs:#main-start' is kept). geometry.uv carries the PathLayer transverse
 * coordinate vPathPosition (x: -1..1 across the strip) — the varying itself
 * is declared in the layer source, which the assembler appends AFTER hook
 * functions, so only the geometry struct is usable here. The whole profile
 * is per-fragment GPU work — no extra geometry or CPU cost:
 *  - envelope width follows the fade → the tail converges to a point
 *  - gaussian core-in-glow profile does in one pass what the old
 *    core+halo layer pair did in two
 *  - the head core is lifted toward white (hot-spark under the icon)
 */
const COMET_PROFILE_FS = `\
float fade = clamp(1.0 - (trips.currentTime - vTime) / trips.trailLength, 0.0, 1.0);
float envelope = mix(0.05, 1.0, pow(fade, 0.6));
float across = abs(geometry.uv.x) / envelope;
if (across > 1.0) discard;
float core = exp(-across * across * 9.0);
float glow = exp(-across * across * 2.5);
float edge = 1.0 - smoothstep(0.75, 1.0, across);
color.a *= pow(fade, 1.4) * min(1.0, 0.85 * core + 0.38 * glow) * edge;
color.rgb = mix(color.rgb, vec3(1.0), 0.4 * core * smoothstep(0.72, 1.0, fade));
`

function makeCometTrailLayer(TripsLayer: any) {
  class CometTrailLayer extends TripsLayer {
    getShaders() {
      const shaders = super.getShaders()
      shaders.inject = { ...shaders.inject, 'fs:DECKGL_FILTER_COLOR': COMET_PROFILE_FS }
      return shaders
    }
  }
  ;(CometTrailLayer as any).layerName = 'CometTrailLayer'
  return CometTrailLayer
}

// Built lazily from @deck.gl/geo-layers (chunk shared with useMap3DTiles via
// Vite dedup — same dynamic import).
let CometLayerCls: any = null

export function useTransitTrails(ov: TransitDeckOverlay) {
  let timer: ReturnType<typeof setInterval> | null = null
  let running = false
  const buffers = new Map<string, TrailEntry>()
  let routeFilter: string | null = null
  let routeGeom: RouteGeom | null = null
  const base = Date.now()
  // Idle gate: seconds-stamp of the last real content change (pin, head move,
  // vehicle drop, filter switch). Everything visible finishes fading within
  // trailLength after it, so past that window the loop stops repainting
  // entirely; the next change wakes it. A parked viewport costs zero frames.
  let lastChangeS = -Infinity

  const nowS = () => (Date.now() - base) / 1000

  function poke() {
    lastChangeS = nowS()
    if (running && timer == null && !document.hidden) startLoop()
  }

  function ensureEntry(id: string, p: any, coord: LngLat): TrailEntry {
    let e = buffers.get(id)
    if (!e) {
      e = { hist: [], live: coord, routeId: p.route_id || '', color: hexToRgb(p.route_color) }
      buffers.set(id, e)
    }
    return e
  }

  /** WS tick (call BEFORE the animator re-aims): pin each vehicle's currently
   * displayed position into history — that is where the comet head has been. */
  function ingest(features: any[]) {
    if (!running) return
    const t = nowS()
    const seen = new Set<string>()
    let changed = false
    for (const f of features) {
      const p = f.properties
      // Feed-namespaced id ({ds}:{vid}) — raw fleet numbers collide across
      // operators, which would stitch two cities' buses into one comet trail.
      const id = p.uid || p.vehicle_id
      seen.add(id)
      const coord = f.geometry.coordinates as LngLat
      const e = ensureEntry(id, p, coord)
      e.routeId = p.route_id || ''
      e.color = hexToRgb(p.route_color)
      const last = e.hist[e.hist.length - 1]
      if (!last || last.pos[0] !== e.live[0] || last.pos[1] !== e.live[1]) {
        e.hist.push({ pos: e.live, ts: t })
        changed = true
      }
      while (e.hist.length > MAX_POINTS || (e.hist.length && e.hist[0].ts < t - HIST_MAX_AGE_S)) {
        e.hist.shift()
      }
    }
    // WS is full-replace per tick — drop vehicles gone from the bbox
    for (const id of buffers.keys()) {
      if (!seen.has(id)) {
        buffers.delete(id)
        changed = true
      }
    }
    if (changed) poke()
  }

  /** Animator frame: move each comet head to the displayed icon position. */
  function updateLive(fc: any) {
    if (!running) return
    let moved = false
    for (const f of fc?.features ?? []) {
      const p = f.properties
      const coord = f.geometry.coordinates as LngLat
      const e = ensureEntry(p.uid || p.vehicle_id, p, coord)
      if (e.live[0] !== coord[0] || e.live[1] !== coord[1]) {
        e.live = coord
        moved = true
      }
    }
    if (moved) poke()
  }

  /** Mirror of activeRouteFilter — hides other routes' trails immediately. */
  function setRouteFilter(routeId: string | null) {
    routeFilter = routeId
    if (!routeId) routeGeom = null
    poke()
  }

  /** Route-focus street snapping. Pass the focused route's GeoJSON geometry;
   * null (or unusable geometry) keeps focus mode on plain chords. */
  function setRouteGeometry(routeId: string | null, geometry: any) {
    routeGeom = routeId && geometry ? buildRouteGeom(routeId, geometry) : null
    poke()
  }

  function renderFrame() {
    if (!ov.ready() || !CometLayerCls) return
    const t = nowS()
    const focused = !!routeFilter
    const g = focused && routeGeom && routeGeom.routeId === routeFilter ? routeGeom : null
    const trails: { path: LngLat[]; ts: number[]; color: [number, number, number] }[] = []
    for (const e of buffers.values()) {
      if (focused && e.routeId !== routeFilter) continue
      if (!e.hist.length) continue
      const pts: TrailPoint[] = [...e.hist, { pos: e.live, ts: t }]
      const path: LngLat[] = []
      const ts: number[] = []
      if (g) {
        buildSnappedPath(g, pts, path, ts)
      } else {
        for (const pt of pts) {
          path.push(pt.pos)
          ts.push(pt.ts)
        }
      }
      trails.push({ path, ts, color: e.color })
    }

    // Binary attribute layout, rebuilt per frame. Per-frame OBJECT data with
    // growing per-path vertex counts hits a deck.gl attribute-manager bug
    // ("RangeError: offset is out of bounds" — row count unchanged, so the
    // tessellator reuses buffers sized for the old vertex total). Explicit
    // typed arrays are sized exactly every frame and skip the tessellator.
    let total = 0
    for (const tr of trails) total += tr.path.length
    const startIndices = new Uint32Array(trails.length + 1)
    const positions = new Float64Array(total * 2)
    const timestamps = new Float32Array(total)
    const colors = new Uint8Array(total * 3)
    let v = 0
    for (let i = 0; i < trails.length; i++) {
      const tr = trails[i]
      startIndices[i + 1] = startIndices[i] + tr.path.length
      for (let j = 0; j < tr.path.length; j++) {
        positions[v * 2] = tr.path[j][0]
        positions[v * 2 + 1] = tr.path[j][1]
        timestamps[v] = tr.ts[j]
        colors[v * 3] = tr.color[0]
        colors[v * 3 + 1] = tr.color[1]
        colors[v * 3 + 2] = tr.color[2]
        v++
      }
    }
    ov.setGroup('trails', [
      new CometLayerCls({
        id: 'transit-trails',
        data: {
          length: trails.length,
          startIndices,
          attributes: {
            getPath: { value: positions, size: 2 },
            getTimestamps: { value: timestamps, size: 1 },
            getColor: { value: colors, size: 3 },
          },
        },
        _pathType: 'open' as const,
        currentTime: t,
        trailLength: focused ? TRAIL_FOCUS_S : TRAIL_GLOBAL_S,
        capRounded: true,
        jointRounded: true,
        widthMinPixels: 13,
      }),
    ])
    // Idle gate: past the fade window since the last change, this frame has
    // already drawn everything fully faded (i.e. blank) — stop repainting.
    // ingest/updateLive/filter changes poke() the loop back awake.
    if (t - lastChangeS > (focused ? TRAIL_FOCUS_S : TRAIL_GLOBAL_S) + 2) {
      stopLoop()
    }
  }

  function startLoop() {
    if (timer != null) return
    timer = setInterval(renderFrame, TICK_MS)
  }

  function stopLoop() {
    if (timer != null) {
      clearInterval(timer)
      timer = null
    }
  }

  function onVisibility() {
    if (document.hidden) stopLoop()
    else if (running) startLoop()
  }

  async function start(map: any) {
    if (running) return
    running = true
    await ov.ensure(map)
    if (!CometLayerCls) {
      const geoLayers = await import('@deck.gl/geo-layers')
      CometLayerCls = makeCometTrailLayer(geoLayers.TripsLayer)
    }
    if (!running) return  // toggled off while the chunk was downloading
    startLoop()
    document.addEventListener('visibilitychange', onVisibility)
    // Debug handle (idle-gate inspection, same pattern as window.__opensky3d)
    if (typeof window !== 'undefined') {
      ;(window as any).__transitTrails = {
        looping: () => timer != null,
        trails: () => buffers.size,
        idleFor: () => Math.round(nowS() - lastChangeS),
      }
    }
  }

  /** Stop animating and forget accumulated positions (same reasoning as
   * disconnectWs: a later re-enable must rebuild from real positions). */
  function stop() {
    running = false
    stopLoop()
    document.removeEventListener('visibilitychange', onVisibility)
    buffers.clear()
    ov.setGroup('trails', [])
  }

  return { start, stop, ingest, updateLive, setRouteFilter, setRouteGeometry }
}
