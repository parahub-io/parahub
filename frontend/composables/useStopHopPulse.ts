import { ref, onScopeDispose } from 'vue'

/**
 * Per-item "just happened here" pulse for live transit lists.
 *
 * Diffs each push of a keyed collection against the previous one and flags an
 * item as pulsing (for `durationMs`) when it changed in a way the caller cares
 * about. Source-agnostic — feed it from a WS push or a poll, it only sees
 * `reconcile(items)`. Pair with the global `.stop-pulse-ring` / `.stop-pulse-pop`
 * CSS (assets/css/main.css) on the rendered icon.
 *
 *   Route page (hop to a new stop):  { key: v => v.v, changed: (a,b) => a.sid !== b.sid }
 *   Stop page  (vehicle arrives):    { key: v => v.vehicle_id, pulseOnAppear: true }
 *
 * The first reconcile only seeds the baseline (never pulses) — so a page load
 * doesn't flash every item. Timers are cleared on scope dispose; no manual
 * onUnmounted needed.
 */
interface PulseOpts<T> {
  /** Stable identity per item; items with no key are ignored. */
  key: (item: T) => string | undefined
  /** Pulse when a still-present item changed (e.g. its snapped stop). */
  changed?: (prev: T, next: T) => boolean
  /** Pulse when an item appears that wasn't in the previous push. */
  pulseOnAppear?: boolean
  /** Pulse lifetime; must match the CSS animation total (default 1200ms). */
  durationMs?: number
}

export function useStopHopPulse<T>(opts: PulseOpts<T>) {
  const { key, changed, pulseOnAppear = false, durationMs = 1200 } = opts

  const pulsing = ref<Record<string, boolean>>({})
  const prev = new Map<string, T>()
  const timers = new Map<string, ReturnType<typeof setTimeout>>()
  let initialized = false

  const isPulsing = (k?: string): boolean => !!k && !!pulsing.value[k]

  function start(k: string) {
    const existing = timers.get(k)
    if (existing) clearTimeout(existing)
    pulsing.value = { ...pulsing.value, [k]: true }
    timers.set(k, setTimeout(() => {
      timers.delete(k)
      const m = { ...pulsing.value }; delete m[k]; pulsing.value = m
    }, durationMs))
  }

  function clear(k: string) {
    const existing = timers.get(k)
    if (existing) { clearTimeout(existing); timers.delete(k) }
    if (pulsing.value[k]) { const m = { ...pulsing.value }; delete m[k]; pulsing.value = m }
  }

  function reconcile(items: T[]) {
    const seen = new Set<string>()
    for (const it of items) {
      const k = key(it)
      if (!k) continue
      seen.add(k)
      const p = prev.get(k)
      if (initialized) {
        if (p === undefined) {
          if (pulseOnAppear) start(k)
        } else if (changed && changed(p, it)) {
          start(k)
        }
      }
      prev.set(k, it)
    }
    for (const k of [...prev.keys()]) {
      if (!seen.has(k)) { prev.delete(k); clear(k) }
    }
    initialized = true
  }

  onScopeDispose(() => {
    for (const t of timers.values()) clearTimeout(t)
    timers.clear()
  })

  return { isPulsing, reconcile }
}
