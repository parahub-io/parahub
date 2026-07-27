/**
 * Co-located IoT device ensembles — shared screen-space layout across the
 * static device map layers (env stations + mesh routers + energy cells;
 * trackers move and stay out).
 *
 * Members within GROUP_RADIUS_M of each other merge into one ensemble that
 * renders as a hexagonal lattice: 2 = horizontal pair, 3 = compact triangle,
 * 4+ = center + lattice ring(s). Offsets are screen px applied via
 * data-driven `icon-offset`, so coordinates stay truthful ("on one object"
 * is expressed by giving devices the same point) and the pattern is constant
 * across zooms. Ensemble hexes render at ENSEMBLE_ICON_SCALE (28 px vs the
 * 22 px base) — hover, lock-on and click follow the rendered position via
 * `renderedPointCoords` (useMapHighlight.ts).
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
   * Members of one group sharing this key show only ONE readout column (the
   * first in deterministic order) — e.g. co-located mesh routers broadcast
   * the same shared-wifi SSID, so one column represents the spot. Demoted
   * members get `hudSuppressed` and fall back to their name label.
   */
  hudDedupeKey?: string
  /** Compass bezel around the hex (widens the readout rail gap) */
  wind?: boolean
}

export interface EnsemblePlacement {
  /**
   * Render anchor [lng, lat]: the group centroid. Members may sit up to
   * GROUP_RADIUS_M apart — anchoring the whole lattice on one point keeps
   * the pattern intact at high zoom (per-member anchors would distort it by
   * the geo spread, which scales with zoom while the px offsets do not).
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
  /** hud member demoted by hudDedupeKey — skip its readout, keep its label */
  hudSuppressed: boolean
}

/** Ensemble members render at 28 px (base device hexes are DEVICE_HEX_SIZE=22). */
export const ENSEMBLE_ICON_SCALE = 28 / 22

/** Lattice spacing: px between adjacent member centers (fits the 31 px bezel). */
const S = 34

/** Members at most this many meters apart merge into one ensemble. */
const GROUP_RADIUS_M = 5

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
  return slots.slice(0, n)
}

interface MemberFlat extends EnsembleMemberInput {
  key: string
}

// ── Module state (shared by every layer on the single map) ──

const segments = new Map<string, EnsembleMemberInput[]>()
const placementByKey = new Map<string, EnsemblePlacement>()
const listeners = new Map<string, () => void>()

/** ~meters² between two members (small-distance equirectangular). */
function _near(a: MemberFlat, b: MemberFlat): boolean {
  const dLat = (a.lat - b.lat) * 111320
  const dLon = (a.lon - b.lon) * 111320 * Math.cos(a.lat * Math.PI / 180)
  return dLat * dLat + dLon * dLon <= GROUP_RADIUS_M * GROUP_RADIUS_M
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
    placementByKey.set(m.key, {
      anchor: [m.lon, m.lat], offset: [0, 0], glOffset: [0, 0], groupSize: 1,
      side: 'right', topSlot: false, nudge: null, hudLeft: null,
      labelPos: m.hud ? null : 'below', hudSuppressed: false,
    })
    return
  }

  const anchor: [number, number] = [
    members.reduce((a, m) => a + m.lon, 0) / n,
    members.reduce((a, m) => a + m.lat, 0) / n,
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

  for (const [m, s] of chosen) {
    const [x, y] = s
    const center = Math.abs(x) < 0.5 && Math.abs(y) < 0.5
    const topSlot = Math.abs(x) < 0.5 && y < -12
    const hud = hudOf.get(m)!
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
      labelPos: hud || center ? null : y < -0.5 ? 'above' : 'below',
      hudSuppressed: !!m.hud && !hud,
    })
  }
}

function _recompute() {
  placementByKey.clear()
  const all: MemberFlat[] = []
  for (const [seg, members] of segments) {
    for (const m of members) all.push({ ...m, key: `${seg}:${m.id}` })
  }
  // Deterministic regardless of publish order
  all.sort((a, b) => (a.key < b.key ? -1 : 1))

  // Union-find over pairwise distance — fleets are small (tens of devices),
  // O(n²) is fine here
  const parent = all.map((_, i) => i)
  const find = (i: number): number => {
    while (parent[i] !== i) { parent[i] = parent[parent[i]]; i = parent[i] }
    return i
  }
  for (let i = 0; i < all.length; i++) {
    for (let j = i + 1; j < all.length; j++) {
      if (_near(all[i], all[j])) parent[find(i)] = find(j)
    }
  }
  const groups = new Map<number, MemberFlat[]>()
  all.forEach((m, i) => {
    const root = find(i)
    const g = groups.get(root)
    if (g) g.push(m); else groups.set(root, [m])
  })
  for (const g of groups.values()) _placeGroup(g)
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
