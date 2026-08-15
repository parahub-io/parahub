/**
 * Live vehicles + per-direction ETAs for ONE transit route.
 *
 * Wraps the `subscribe_route` channel of `ws/v1/transit/`: the daemon pushes
 * every vehicle reporting on the route, the stop ids they snapped to, and the
 * cumulative ETA chain per direction. Shared by the passenger route page and
 * the driver HUD ladder so both render the same live picture.
 *
 * Lifecycle is the caller's: pages are KeepAlive-cached (app.vue forces it on
 * every route), so a page must `disconnect()` in onDeactivated/onUnmounted and
 * `connect()` again in onActivated — otherwise every cached route page keeps a
 * socket streaming behind whatever the user is actually looking at.
 */

import { ref } from 'vue'

export interface RouteLiveOptions {
  /** Fired after each push, before the refs are read by render. */
  onUpdate?: () => void
}

/** `n` = everyone inside their lease, `active` = those whose page is beating now. */
export interface WaitingCell {
  n: number
  active: number
}

function parseByDirection<T>(raw: unknown): Record<number, Record<string, T>> {
  const parsed: Record<number, Record<string, T>> = {}
  for (const [k, v] of Object.entries(raw as Record<string, Record<string, T>>)) {
    parsed[Number(k)] = v
  }
  return parsed
}

export function useTransitRouteLive(options: RouteLiveOptions = {}) {
  const liveVehicles = ref<any[]>([])
  const liveStopIds = ref<string[]>([])
  // {0: {stop_source_id: seconds}, 1: {...}} — keys normalized to numbers
  const allEtas = ref<Record<number, Record<string, number>>>({})
  // Same shape, waiting passengers: {0: {stop_source_id: {n, active}}, 1: {...}}
  const allWaiting = ref<Record<number, Record<string, WaitingCell>>>({})

  let ws: WebSocket | null = null
  let intentionalClose = false
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let dsId = ''
  let routeSourceId = ''

  function connect(newDsId?: string, newRouteSourceId?: string) {
    if (!import.meta.client) return
    if (newDsId && newRouteSourceId) {
      // Re-target: a different route needs a fresh subscription
      if (ws && (newDsId !== dsId || newRouteSourceId !== routeSourceId)) disconnect()
      dsId = newDsId
      routeSourceId = newRouteSourceId
    }
    if (!dsId || !routeSourceId) return
    if (ws) return  // already open/connecting (nulled on close and disconnect)

    intentionalClose = false
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const sock = new WebSocket(`${proto}://${location.host}/ws/v1/transit/`)
    ws = sock

    sock.onopen = () => {
      sock.send(JSON.stringify({
        type: 'subscribe_route', ds_id: dsId, route_source_id: routeSourceId,
      }))
    }

    sock.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        // Markers move on a human tap, not on the daemon tick, so they arrive on
        // their own message carrying only counts — no ETA recomputation per tap.
        if (msg.type === 'waiting_update') {
          if (msg.scope === 'route') allWaiting.value = parseByDirection(msg.waiting || {})
          options.onUpdate?.()
          return
        }
        if (msg.type !== 'route_vehicles' && msg.type !== 'route_live') return
        liveStopIds.value = msg.stop_ids || []
        liveVehicles.value = msg.vehicles || []
        // Convert string keys to numbers: {"0": {...}} → {0: {...}}
        if (msg.etas) allEtas.value = parseByDirection(msg.etas)
        if (msg.waiting) allWaiting.value = parseByDirection(msg.waiting)
        options.onUpdate?.()
      } catch {}
    }

    sock.onclose = () => {
      ws = null
      if (!intentionalClose) scheduleReconnect()
    }
  }

  function scheduleReconnect(delayMs = 3000) {
    if (reconnectTimer) clearTimeout(reconnectTimer)
    if (intentionalClose) return
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      if (!intentionalClose) connect()
    }, delayMs)
  }

  function disconnect() {
    intentionalClose = true
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
    ws?.close()
    ws = null
  }

  /** Call from a `visibilitychange` handler: revive a socket the OS dropped. */
  function reviveIfDropped() {
    if (!ws || ws.readyState === WebSocket.CLOSED || ws.readyState === WebSocket.CLOSING) {
      intentionalClose = false
      scheduleReconnect(0)
    }
  }

  /** Vehicles of `dirId` sitting at `stopSourceId`, newest push wins.
   *
   * A vehicle with a confirmed direction is placed only in its own column. One
   * whose STT direction is still unresolved (`d === null` — dual state at a
   * shared terminus, or freshly appeared with no track yet) has a snapped stop
   * but no direction: place it in whichever rendered column contains that stop.
   * A sid shared by both columns (terminus) shows it in both — the genuine
   * ambiguity while it turns around, never hidden. */
  function vehicleAtStop(stopSourceId: string, dirId: number) {
    return liveVehicles.value.find(
      v => v.sid === stopSourceId && (v.d === dirId || v.d == null)
    ) || null
  }

  const etasFor = (dirId: number) => allEtas.value[dirId] ?? {}
  const waitingFor = (dirId: number) => allWaiting.value[dirId] ?? {}
  const waitingAt = (stopSourceId: string, dirId: number): WaitingCell | null =>
    waitingFor(dirId)[stopSourceId] ?? null

  return {
    liveVehicles, liveStopIds, allEtas, allWaiting,
    connect, disconnect, reviveIfDropped,
    vehicleAtStop, etasFor, waitingFor, waitingAt,
  }
}
