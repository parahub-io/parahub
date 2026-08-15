/**
 * Waiting-passenger marker — "I am standing at this pole, for this line".
 *
 * One marker per visitor at a time; placing a new one moves it. The awaited
 * (route, direction) is part of the marker, not just the stop — a person waiting
 * for another line is noise to the driver, and no sensor can tell the two poles
 * of a stop apart (they sit ten metres away, inside GPS error), so the tap is the
 * direction signal.
 *
 * Module-level state: the route page, the stop page and the map all read one
 * marker, and moving it on one surface must un-highlight it on the others.
 *
 * Lifetime mirrors the server's rolling lease. While the page is visible we beat
 * every BEAT_INTERVAL_MS; the server keeps the marker for its full lease after
 * the last beat, so pocketing the phone dims the marker rather than deleting it.
 * Closing the page sends nothing — the lease is what retires an abandoned
 * marker, and firing a delete on unload would wipe the marker of somebody who
 * merely reloaded while still standing at the pole. On mount we ask the server
 * what we already have, so a reload reopens in the right state.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '~/stores/auth'
import { useToastStore } from '~/stores/toast'

export interface WaitingLine {
  route: string
  direction: number
}

interface WaitingMarker {
  ds_id: string
  stop_source_id: string
  lines: WaitingLine[]
  declared_at: number
  beat: number
}

const DEVICE_KEY = 'parahub_waiting_device'
// Comfortably inside the server's ACTIVE_WINDOW (90s) so a visible page never
// flickers into the dimmed state between beats.
const BEAT_INTERVAL_MS = 30_000

const marker = ref<WaitingMarker | null>(null)
const lastError = ref<'throttled' | 'ip_cap' | 'failed' | null>(null)

// The marker follows the tap immediately and the request reconciles it. Standing
// at a pole, the answer to "did it take?" has to be the icon, not a round trip —
// and the state is trivially recoverable, since the server's reply overwrites it
// and a failure puts back exactly what was there before.
//
// No tap is ever blocked — refusing one during a flight would swallow the
// correction tap, the very gesture this surface exists for. Instead every tap is
// accepted at once and two things keep the result honest:
//   * only the newest tap may write the server's answer back (`issued`), so a
//     late reply cannot resurrect a pole the user has already left;
//   * the requests themselves ride a queue, one in flight at a time, because two
//     parallel POSTs can reach different workers and be applied out of order —
//     which would leave the server holding a marker the user cancelled, alive
//     until its lease ran out and counted against a pole nobody stands at.
let issued = 0
let wire: Promise<unknown> = Promise.resolve()

function queued<T>(send: () => Promise<T>): Promise<T> {
  const next = wire.then(send, send)
  wire = next.catch(() => {})
  return next
}

let beatTimer: ReturnType<typeof setInterval> | null = null
let visibilityBound = false
let restored = false

function deviceId(): string {
  if (!import.meta.client) return ''
  let id = localStorage.getItem(DEVICE_KEY)
  if (!id) {
    const bytes = new Uint8Array(16)
    crypto.getRandomValues(bytes)
    id = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
    localStorage.setItem(DEVICE_KEY, id)
  }
  return id
}

export const useWaitingMarker = () => {
  const authStore = useAuthStore()
  const toast = useToastStore()
  const { t } = useI18n()

  function reportError(kind: 'throttled' | 'ip_cap' | 'failed') {
    lastError.value = kind
    toast.error(t(`transit.waiting.error_${kind}`))
  }

  async function authHeaders(): Promise<Record<string, string>> {
    // Anonymous is a first-class case here — most stop-page traffic is signed
    // out, and that is exactly the person standing at the pole.
    if (!authStore.isAuthenticated) return {}
    try {
      await authStore.ensureToken()
      return authStore.token ? { Authorization: `Bearer ${authStore.token}` } : {}
    } catch {
      return {}
    }
  }

  async function call<T>(path: string, body: Record<string, unknown>): Promise<T> {
    return await $fetch<T>(path, {
      method: 'POST',
      credentials: 'include',
      headers: await authHeaders(),
      body: { ...body, device_id: deviceId() },
    })
  }

  /** True when MY marker is at this stop awaiting this line. */
  function isMine(dsId: string, stopSourceId: string, route: string, direction: number): boolean {
    const m = marker.value
    if (!m || m.ds_id !== dsId || m.stop_source_id !== stopSourceId) return false
    return m.lines.some((l) => l.route === route && l.direction === direction)
  }

  /** True when my marker sits at this stop, whatever line it awaits. */
  const myStopKey = computed(() =>
    marker.value ? `${marker.value.ds_id}:${marker.value.stop_source_id}` : '',
  )

  /** Put back what the tap replaced, unless a newer tap already owns the state. */
  function rollback(mine: number, previous: WaitingMarker | null) {
    if (mine !== issued) return
    marker.value = previous
    if (previous) startBeating()
    else stopBeating()
  }

  function reportFailure(e: any) {
    // `detail` is a machine code (ip_cap | rate_limited | invalid), not prose.
    // Any other 429 is the endpoint's rate ceiling — "too fast" is what it means
    // to the person tapping, whichever layer produced it.
    const detail = String(e?.data?.detail || '')
    if (detail === 'ip_cap') return reportError('ip_cap')
    reportError(e?.status === 429 || e?.statusCode === 429 ? 'throttled' : 'failed')
  }

  async function place(dsId: string, stopSourceId: string, lines: WaitingLine[]) {
    if (!lines.length) return false
    const mine = ++issued
    const previous = marker.value
    const now = Date.now() / 1000
    lastError.value = null
    // Mirrors the server: adding a line at the pole I already stand at continues
    // one wait, stepping to another pole starts a new one. The reply overwrites
    // this anyway — but until it lands, the "waiting N min" banner reads from here.
    const samePole = !!previous && previous.ds_id === dsId && previous.stop_source_id === stopSourceId
    marker.value = {
      ds_id: dsId,
      stop_source_id: stopSourceId,
      lines,
      declared_at: samePole ? previous!.declared_at : now,
      beat: now,
    }
    startBeating()
    try {
      const res = await queued(() => call<{ marker: WaitingMarker | null }>(
        '/api/v1/geo/transit/waiting/',
        { ds_id: dsId, stop_source_id: stopSourceId, lines },
      ))
      if (mine === issued) marker.value = res.marker
      return true
    } catch (e: any) {
      rollback(mine, previous)
      reportFailure(e)
      return false
    }
  }

  async function clear() {
    const mine = ++issued
    const previous = marker.value
    marker.value = null
    stopBeating()
    try {
      await queued(() => call('/api/v1/geo/transit/waiting/clear/', {}))
      return true
    } catch (e: any) {
      rollback(mine, previous)
      reportFailure(e)
      return false
    }
  }

  /**
   * The single gesture the UI needs: tapping the line I already await removes my
   * marker, tapping anything else moves it there.
   */
  async function toggle(dsId: string, stopSourceId: string, line: WaitingLine) {
    if (isMine(dsId, stopSourceId, line.route, line.direction)) return await clear()
    return await place(dsId, stopSourceId, [line])
  }

  async function beat() {
    if (!marker.value) return
    try {
      const res = await call<{ alive: boolean }>('/api/v1/geo/transit/waiting/beat/', {})
      if (!res.alive) {
        // Lease ran out, or the awaited bus arrived and the server retired the
        // marker — the honest end of a wait, so drop it locally without asking.
        marker.value = null
        stopBeating()
      }
    } catch {
      // Transient failure: the lease still has room, the next beat will do.
    }
  }

  function onVisibility() {
    if (document.visibilityState === 'visible' && marker.value) beat()
  }

  function startBeating() {
    if (!import.meta.client || beatTimer) return
    beatTimer = setInterval(() => {
      if (document.visibilityState === 'visible') beat()
    }, BEAT_INTERVAL_MS)
    if (!visibilityBound) {
      document.addEventListener('visibilitychange', onVisibility)
      visibilityBound = true
    }
  }

  function stopBeating() {
    if (beatTimer) {
      clearInterval(beatTimer)
      beatTimer = null
    }
  }

  /** Ask the server what marker this visitor already holds (reload, second tab).
   *  POST like every other call here — the device id must not ride a query
   *  string into access logs. */
  async function restore(force = false) {
    if (!import.meta.client || (restored && !force)) return
    restored = true
    try {
      const res = await call<{ marker: WaitingMarker | null }>(
        '/api/v1/geo/transit/waiting/mine/', {},
      )
      marker.value = res.marker
      if (marker.value) startBeating()
    } catch {
      // Nothing restored — the page simply opens with no marker of its own.
    }
  }

  return { marker, lastError, myStopKey, isMine, place, clear, toggle, restore }
}
