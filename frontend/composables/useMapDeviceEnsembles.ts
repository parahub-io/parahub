/**
 * Co-located IoT device ensembles — shared screen-space layout across the
 * device map layers (env stations + mesh routers + energy cells + parked
 * trackers; a moving tracker leaves the lattice).
 *
 * Members closer than one lattice cell ON SCREEN merge into one ensemble that
 * renders as a hexagonal lattice: 2 = horizontal pair, 3 = compact triangle,
 * 4+ = center + lattice ring(s). Offsets are screen px applied via
 * data-driven `icon-offset` — the pattern is the same at every zoom, only the
 * membership follows the scale. Ensemble hexes render at ENSEMBLE_ICON_SCALE
 * (28 px vs the 22 px base) — hover, lock-on and click follow the rendered
 * position via `renderedPointCoords` (useMapHighlight.ts).
 *
 * The merge threshold lives in screen space because the lattice does. A fixed
 * metric radius agrees with the 34 px pitch at exactly one zoom: below it,
 * neighbours a few metres apart stay separate ensembles whose lattices then
 * interpenetrate (the pile this rule exists to prevent); above it, devices
 * that already have room on screen get pulled together and drawn compressed.
 * So the radius is S px converted to metres at the current map scale
 * (setEnsembleScale), and ensembles dissolve back onto true points as the
 * user zooms in.
 *
 * Slot assignment is deterministic and collision-free: readout stations take
 * horizontally outward slots (their instrument column needs clear space) —
 * weather resolves ties to the right (bezel + readout), air to the left;
 * wifi/infra go topmost; the rest fill from the center. The center slot never
 * hosts a readout station. The top slot's column bottom-anchors and aligns
 * its left edge with the rightmost right-side column below (the "rail"), so
 * stacked readouts share one edge instead of forming a staircase.
 *
 * Each layer publishes its member list via setEnsembleSegment() whenever its
 * data or visibility changes, reads placements back via ensemblePlacement(),
 * and re-renders on onEnsembleChange(). Contract: change listeners only
 * re-render (setData / HUD sync) — they must never publish synchronously.
 */

export type EnsembleRole = 'weather' | 'air' | 'infra' | 'other'

export interface EnsembleMemberInput {
  /** Stable per-layer id (station/device ULID) */
  id: string
  lat: number
  lon: number
  role: EnsembleRole
  /** Instrument readout column present — it replaces the GL name label */
  hud?: boolean
  /**
   * Members sharing this key show only ONE readout column (the first in
   * deterministic order) within a group AND within a column's width on screen
   * — e.g. every router on one mesh broadcasts the same shared-wifi SSID, so
   * one column represents the spot instead of stacking identical readouts.
   * Demoted members get `hudSuppressed` and fall back to their name label.
   */
  hudDedupeKey?: string
  /** Compass bezel around the hex (widens the readout rail gap) */
  wind?: boolean
  /**
   * The point drifts (a parked tracker's GPS). Mobile members join a lattice
   * but never anchor it — the ensemble would jitter with every position tick.
   */
  mobile?: boolean
}

export interface EnsemblePlacement {
  /**
   * Render anchor [lng, lat]: the centroid of the group's immobile members.
   * Members sit within a lattice cell of each other on screen — anchoring the
   * whole lattice on one point keeps the pattern intact at high zoom
   * (per-member anchors would distort it by the geo spread, which scales with
   * zoom while the px offsets do not).
   */
  anchor: [number, number]
  /** Screen-px offset from the anchor (y down) */
  offset: [number, number]
  /**
   * The same offset in GL `icon-offset` units: MapLibre multiplies
   * icon-offset by icon-size, so ensemble members (icon-size =
   * ENSEMBLE_ICON_SCALE) get it pre-divided to land exactly on `offset` px.
   * Use for the symbol layout; use `offset` for DOM markers and JS math.
   */
  glOffset: [number, number]
  groupSize: number
  /** Side the readout column extends to */
  side: 'left' | 'right'
  /** Pure-top ring slot — the column bottom-anchors and grows upward */
  topSlot: boolean
  /** Diagonal ring slots push their column vertically outward */
  nudge: 'up' | 'down' | null
  /** Right-rail override: absolute left px for the top slot's column */
  hudLeft: number | null
  /** Name-label flip for label-only members (null = label suppressed) */
  labelPos: 'above' | 'below' | null
  /**
   * `text-offset` in ems for the name label, carrying the member's own slot
   * offset — GL applies `icon-offset` to the icon only, so without this every
   * member's label would pile onto the group anchor instead of sitting under
   * its own hexagon. Null for lone devices (the layer's own default applies).
   */
  labelOffset: [number, number] | null
  labelAnchor: 'top' | 'bottom' | null
  /** hud member demoted by hudDedupeKey — skip its readout, keep its label */
  hudSuppressed: boolean
}

/** Ensemble members render at 28 px (base device hexes are DEVICE_HEX_SIZE=22). */
export const ENSEMBLE_ICON_SCALE = 28 / 22

/** Lattice spacing: px between adjacent member centers (fits the 31 px bezel). */
const S = 34

/** Radius used until the map reports its scale (≈ S px around zoom 18). */
const FALLBACK_RADIUS_M = 5

/**
 * One readout per dedupe key per this radius in px — a column is ~120 px of
 * text hanging off a 34 px cell, so anything nearer is either the same column
 * twice or a column lying across its neighbours' hexes.
 */
const HUD_DEDUPE_PX = 220

/** Space a readout column claims beside its hex: [reach, half-height] px. */
const HUD_COL_PX: [number, number] = [140, 40]

/** Clearance a name label needs from the next cell: [horizontal, vertical] px. */
const LABEL_CLEAR_PX: [number, number] = [40, 10]

/** Device name labels are 11 px; `text-offset` is in ems of that. */
const LABEL_TEXT_PX = 11
/** Gap between a 28 px ensemble hex and its label, in ems. */
const LABEL_GAP_EM = 1.6

/** Map scale in meters per screen px, quantized; 0 until the map reports it. */
let metersPerPixel = 0

/** Merge threshold: one lattice cell, measured on screen. */
const _groupRadiusM = () => (metersPerPixel > 0 ? S * metersPerPixel : FALLBACK_RADIUS_M)

// Readout column gaps from the member center — MUST match the .env-hud-col
// left/right values in MapView.vue CSS.
const HUD_GAP_PLAIN = 19
const HUD_GAP_RINGED = 24

const _at = (deg: number, dist: number): [number, number] => [
  Math.round(dist * Math.cos(deg * Math.PI / 180) * 100) / 100,
  Math.round(dist * Math.sin(deg * Math.PI / 180) * 100) / 100,
]

// Hex-lattice ring directions (screen degrees, y down): up, lower-right,
// lower-left, upper-right, down, upper-left — fills alternate sides first.
const RING1 = [270, 30, 150, 330, 90, 210]
// Second shell: edge midpoints (√3·S) first, corners (2·S) after
const RING2_MID = [300, 60, 180, 0, 120, 240]

// Axial lattice basis matching RING1 (neighbours at 30°, 90° … 330°) and its
// six unit steps — used to keep growing the honeycomb past the second shell.
const AX_U: [number, number] = [S * Math.cos(Math.PI / 6), S * Math.sin(Math.PI / 6)]
const AX_V: [number, number] = [0, S]
const AX_DIRS: [number, number][] = [[1, 0], [0, 1], [-1, 1], [-1, 0], [0, -1], [1, -1]]

/** Lattice ring k (6k cells) in screen px, walked clockwise from the top. */
function _ringSlots(k: number): [number, number][] {
  const out: [number, number][] = []
  let [a, b] = [AX_DIRS[4][0] * k, AX_DIRS[4][1] * k] // start straight up
  for (const [da, db] of AX_DIRS) {
    for (let i = 0; i < k; i++) {
      out.push([
        Math.round((a * AX_U[0] + b * AX_V[0]) * 100) / 100,
        Math.round((a * AX_U[1] + b * AX_V[1]) * 100) / 100,
      ])
      a += da
      b += db
    }
  }
  return out
}

/** Canonical slot offsets (screen px, y down) for an n-member ensemble. */
function ensembleSlots(n: number): [number, number][] {
  if (n <= 1) return [[0, 0]]
  if (n === 2) return [[-S / 2, 0], [S / 2, 0]]
  // Compact triangle: pairwise distance S, slots up / lower-right / lower-left
  if (n === 3) return [_at(270, S / Math.sqrt(3)), _at(30, S / Math.sqrt(3)), _at(150, S / Math.sqrt(3))]
  // 4+: center + lattice ring, growing a second shell for crowds
  const slots: [number, number][] = [[0, 0], ...RING1.map((a) => _at(a, S))]
  for (const a of RING2_MID) slots.push(_at(a, S * Math.sqrt(3)))
  for (const a of RING1) slots.push(_at(a, 2 * S))
  // Whole neighbourhoods merge at low zoom — keep laying cells rather than
  // stacking the overflow on the center slot
  for (let k = 3; slots.length < n; k++) slots.push(..._ringSlots(k))
  return slots.slice(0, n)
}

interface MemberFlat extends EnsembleMemberInput {
  key: string
}

// ── Module state (shared by every layer on the single map) ──

const segments = new Map<string, EnsembleMemberInput[]>()
const placementByKey = new Map<string, EnsemblePlacement>()
/** Slot a member's name label would take if it showed one (see _placeGroup). */
const labelSlotByKey = new Map<string, 'above' | 'below' | null>()
const listeners = new Map<string, () => void>()

/** Meters between two coordinates (small-distance equirectangular). */
function _metersBetween(
  aLat: number, aLon: number, bLat: number, bLon: number,
): [number, number] {
  return [
    (aLon - bLon) * 111320 * Math.cos(aLat * Math.PI / 180),
    (aLat - bLat) * 111320,
  ]
}

function _near(a: MemberFlat, b: MemberFlat, radiusM: number): boolean {
  const [east, north] = _metersBetween(a.lat, a.lon, b.lat, b.lon)
  return east * east + north * north <= radiusM * radiusM
}

function _placeGroup(members: MemberFlat[]) {
  const n = members.length

  // hudDedupeKey: one readout per key within the group (deterministic — the
  // members arrive pre-sorted); demoted members act as label-only
  const seenDedupe = new Set<string>()
  const hudOf = new Map<MemberFlat, boolean>()
  for (const m of members) {
    let hud = !!m.hud
    if (hud && m.hudDedupeKey) {
      if (seenDedupe.has(m.hudDedupeKey)) hud = false
      else seenDedupe.add(m.hudDedupeKey)
    }
    hudOf.set(m, hud)
  }

  if (n === 1) {
    const m = members[0]
    labelSlotByKey.set(m.key, 'below')
    placementByKey.set(m.key, {
      anchor: [m.lon, m.lat], offset: [0, 0], glOffset: [0, 0], groupSize: 1,
      side: 'right', topSlot: false, nudge: null, hudLeft: null,
      labelPos: m.hud ? null : 'below', labelOffset: null, labelAnchor: null,
      hudSuppressed: false,
    })
    return
  }

  // Immobile members define the anchor: a parked tracker's GPS wanders a few
  // metres between ticks, and a centroid that includes it drags the whole
  // lattice along with it
  const anchorOn = members.filter((m) => !m.mobile)
  const src = anchorOn.length ? anchorOn : members
  const anchor: [number, number] = [
    src.reduce((a, m) => a + m.lon, 0) / src.length,
    src.reduce((a, m) => a + m.lat, 0) / src.length,
  ]

  const free = ensembleSlots(n).slice()
  const takeBest = (score: (s: [number, number]) => number): [number, number] => {
    if (free.length === 0) return [0, 0]
    let best = 0
    for (let j = 1; j < free.length; j++) if (score(free[j]) > score(free[best])) best = j
    return free.splice(best, 1)[0]
  }
  // Readout stations never sit on the center slot (their column would clash
  // with the bottom slot); label-only members are welcome there.
  const centerPen = (m: MemberFlat, s: [number, number]) =>
    (hudOf.get(m) && Math.abs(s[0]) < 0.5 && Math.abs(s[1]) < 0.5 ? -1000 : 0)
  const chosen = new Map<MemberFlat, [number, number]>()
  for (const m of members) if (m.role === 'weather') chosen.set(m, takeBest((s) => Math.abs(s[0]) * 10 + s[0] + centerPen(m, s)))
  for (const m of members) if (m.role === 'air') chosen.set(m, takeBest((s) => Math.abs(s[0]) * 10 - s[0] + centerPen(m, s)))
  for (const m of members) if (m.role === 'infra') chosen.set(m, takeBest((s) => -s[1] + centerPen(m, s)))
  for (const m of members) if (!chosen.has(m)) chosen.set(m, takeBest((s) => centerPen(m, s)))

  // Right rail: the top slot's column aligns its left edge with the rightmost
  // right-side column below, so stacked blocks share one edge (no staircase)
  let rail = 0
  for (const [m, s] of chosen) {
    const topSlot = Math.abs(s[0]) < 0.5 && s[1] < -12
    if (hudOf.get(m) && s[0] > -0.5 && !topSlot) rail = Math.max(rail, s[0] + (m.wind ? HUD_GAP_RINGED : HUD_GAP_PLAIN))
  }

  // A name label is a wide block hanging under (or over) its hex, so it only
  // fits where the lattice leaves that side open — otherwise it lands on a
  // neighbour's hexagon, which GL collision cannot prevent (device icons are
  // allow-overlap). Outer cells keep their name, inner ones answer on click.
  const taken = [...chosen.values()]
  const labelBlocked = (s: [number, number], dir: 'above' | 'below') =>
    taken.some((t) => t !== s && Math.abs(t[0] - s[0]) < LABEL_CLEAR_PX[0]
      && (dir === 'below' ? t[1] - s[1] > LABEL_CLEAR_PX[1] : t[1] - s[1] < -LABEL_CLEAR_PX[1]))

  for (const [m, s] of chosen) {
    const [x, y] = s
    const center = Math.abs(x) < 0.5 && Math.abs(y) < 0.5
    const topSlot = Math.abs(x) < 0.5 && y < -12
    const hud = hudOf.get(m)!
    // Kept for every member (not just label-only ones): a readout that loses
    // the cross-group dedupe falls back to its name in this very slot
    const labelSlot = center
      ? null
      : !labelBlocked(s, 'below') ? 'below' : !labelBlocked(s, 'above') ? 'above' : null
    labelSlotByKey.set(m.key, labelSlot)
    placementByKey.set(m.key, {
      anchor,
      offset: [x, y],
      glOffset: [
        Math.round((x / ENSEMBLE_ICON_SCALE) * 100) / 100,
        Math.round((y / ENSEMBLE_ICON_SCALE) * 100) / 100,
      ],
      groupSize: n,
      side: x < -0.5 ? 'left' : 'right',
      topSlot,
      nudge: topSlot ? null : y < -12 ? 'up' : y > 12 ? 'down' : null,
      hudLeft: hud && topSlot && rail > 0 ? Math.round((rail - x) * 10) / 10 : null,
      // A readout column replaces the name label; the center slot suppresses
      // it too (anything below overlaps the bottom slot's hex)
      labelPos: hud ? null : labelSlot,
      labelOffset: [
        Math.round((x / LABEL_TEXT_PX) * 100) / 100,
        Math.round((y / LABEL_TEXT_PX + (labelSlot === 'above' ? -LABEL_GAP_EM : LABEL_GAP_EM)) * 100) / 100,
      ],
      labelAnchor: labelSlot === 'above' ? 'bottom' : 'top',
      hudSuppressed: !!m.hud && !hud,
    })
  }
}

/**
 * Second pass, in screen space across ALL groups — a readout column is far
 * wider than the lattice cell that grouping works on, so it needs its own
 * arbitration:
 *  1. one column per dedupe key per HUD_DEDUPE_PX (every router on one mesh
 *     broadcasts the same SSID; repeating it stacks identical blocks over
 *     each other and over the neighbours' hexes). Losers fall back to their
 *     name label, exactly like the in-group dedupe;
 *  2. the surviving column opens towards the emptier side, so it reaches into
 *     free map instead of across the devices next door — the in-group `side`
 *     only knows its own lattice.
 */
function _placeHudColumns(all: MemberFlat[]) {
  if (metersPerPixel <= 0 || all.length === 0) return
  const [oLat, oLon] = [all[0].lat, all[0].lon] // local origin keeps the px math small
  const px = new Map<string, [number, number]>()
  for (const m of all) {
    const pl = placementByKey.get(m.key)
    if (!pl) continue
    const [east, north] = _metersBetween(pl.anchor[1], pl.anchor[0], oLat, oLon)
    px.set(m.key, [east / metersPerPixel + pl.offset[0], -north / metersPerPixel + pl.offset[1]])
  }

  /** Devices (any group) the column would cover if it opened this way. */
  const crowd = (key: string, dir: 1 | -1) => {
    const p = px.get(key)!
    let n = 0
    for (const [k, q] of px) {
      if (k === key) continue
      const dx = (q[0] - p[0]) * dir
      // The band covers a neighbour's hex AND the name label under it
      if (dx > 0 && dx < HUD_COL_PX[0] && Math.abs(q[1] - p[1]) < HUD_COL_PX[1]) n++
    }
    return n
  }

  const openColumn = (m: MemberFlat) => {
    const pl = placementByKey.get(m.key)!
    const right = crowd(m.key, 1)
    const left = crowd(m.key, -1)
    const side = right < left ? 'right' : left < right ? 'left' : pl.side
    if (side !== pl.side) {
      pl.side = side
      pl.hudLeft = null // the right-rail alignment only holds on its own side
    }
  }

  const suppress = (m: MemberFlat) => {
    const pl = placementByKey.get(m.key)!
    pl.hudSuppressed = true
    pl.labelPos = labelSlotByKey.get(m.key) ?? null
  }

  // Only members that actually render a column take part — an offline router
  // carries the dedupe key but has no readout
  const live = all.filter((m) => m.hud && !placementByKey.get(m.key)?.hudSuppressed && px.has(m.key))
  const byKey = new Map<string, MemberFlat[]>()
  for (const m of live) {
    if (!m.hudDedupeKey) { openColumn(m); continue }
    const g = byKey.get(m.hudDedupeKey)
    if (g) g.push(m); else byKey.set(m.hudDedupeKey, [m])
  }

  for (const candidates of byKey.values()) {
    let pending = candidates
    while (pending.length) {
      const seed = px.get(pending[0].key)!
      const near = pending.filter((c) => {
        const q = px.get(c.key)!
        return Math.hypot(q[0] - seed[0], q[1] - seed[1]) < HUD_DEDUPE_PX
      })
      // The neighbourhood's one column goes to whichever member can open it
      // into free map — the outermost device, in practice
      let best = near[0]
      let bestCrowd = Math.min(crowd(best.key, 1), crowd(best.key, -1))
      for (const c of near.slice(1)) {
        const score = Math.min(crowd(c.key, 1), crowd(c.key, -1))
        if (score < bestCrowd) { best = c; bestCrowd = score }
      }
      openColumn(best)
      for (const c of near) if (c !== best) suppress(c)
      pending = pending.filter((c) => !near.includes(c))
    }
  }
}

function _recompute() {
  placementByKey.clear()
  labelSlotByKey.clear()
  const all: MemberFlat[] = []
  for (const [seg, members] of segments) {
    for (const m of members) all.push({ ...m, key: `${seg}:${m.id}` })
  }
  // Deterministic regardless of publish order
  all.sort((a, b) => (a.key < b.key ? -1 : 1))

  // Union-find over pairwise distance — fleets are small (tens of devices),
  // O(n²) is fine here
  const radiusM = _groupRadiusM()
  const parent = all.map((_, i) => i)
  const find = (i: number): number => {
    while (parent[i] !== i) { parent[i] = parent[parent[i]]; i = parent[i] }
    return i
  }
  for (let i = 0; i < all.length; i++) {
    for (let j = i + 1; j < all.length; j++) {
      if (_near(all[i], all[j], radiusM)) parent[find(i)] = find(j)
    }
  }
  const groups = new Map<number, MemberFlat[]>()
  all.forEach((m, i) => {
    const root = find(i)
    const g = groups.get(root)
    if (g) g.push(m); else groups.set(root, [m])
  })
  for (const g of groups.values()) _placeGroup(g)
  _placeHudColumns(all)
}

/**
 * Publish a layer's current member list (empty array when the layer is
 * toggled off or has no data). Triggers a recompute + change notification.
 */
export function setEnsembleSegment(segment: string, members: EnsembleMemberInput[]) {
  segments.set(segment, members)
  _recompute()
  for (const cb of listeners.values()) cb()
}

/**
 * Publish the map scale (meters per screen px at the viewport center) — the
 * merge threshold and the HUD dedupe window are both screen-space, so they
 * regroup as the user zooms. Quantized to 1/8 zoom steps: a `zoom` event
 * fires per animation frame, and every recompute re-setData's each device
 * layer, while the threshold itself only flips occasionally.
 */
export function setEnsembleScale(mpp: number) {
  if (!(mpp > 0)) return
  const q = 2 ** (Math.round(Math.log2(mpp) * 8) / 8)
  if (q === metersPerPixel) return
  metersPerPixel = q
  _recompute()
  for (const cb of listeners.values()) cb()
}

/**
 * Re-render hook, keyed so a re-created composable replaces (not stacks) its
 * subscription. Pass null to unsubscribe.
 */
export function onEnsembleChange(key: string, cb: (() => void) | null) {
  if (cb) listeners.set(key, cb)
  else listeners.delete(key)
}

export function ensemblePlacement(segment: string, id: string): EnsemblePlacement | undefined {
  return placementByKey.get(`${segment}:${id}`)
}
