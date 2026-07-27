/**
 * Live env-station bridge: one public WS (ws/v1/env/) subscribed to every
 * station the map currently shows — all public stations while the layer is on,
 * plus the open panel's station. Each reading patches the store list, the GL
 * dot and the HUD marker (via iot.updateSingleEnvStation); the open panel
 * object is refreshed when the id matches.
 *
 * Uses a raw WebSocket (not useWebSocket) because the env map feed is public —
 * anonymous viewers must get live updates too, and useWebSocket refuses to
 * connect without an auth token. Mirrors useTransitVehicles.
 *
 * Env readings are infrequent (poll bridge every 3 min, Ecowitt every 60s), so
 * no throttling is needed — unlike the tracker bridge.
 */
import { watch, computed } from 'vue'
import type { Ref } from 'vue'

export function useMapEnvLiveWs(opts: {
  selectedEnvStation: Ref<any>
  iot: {
    envStationsEnabled: Ref<boolean>
    envStationsList: Ref<any[]>
    updateSingleEnvStation: (id: string, latest: any, lastReadingAt: string) => void
  }
}) {
  const { selectedEnvStation, iot } = opts

  let ws: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let reconnectAttempts = 0

  const _wantedIds = (): string[] => {
    const ids = new Set<string>()
    if (iot.envStationsEnabled.value) {
      for (const s of iot.envStationsList.value) if (s?.id) ids.add(s.id)
    }
    if (selectedEnvStation.value?.id) ids.add(selectedEnvStation.value.id)
    return [...ids].sort()
  }
  // String key so the watcher only fires when the actual id set changes
  // (list entries mutate on every reading, the ids themselves rarely do).
  const wantedKey = computed(() => _wantedIds().join(','))

  const isOpen = () => ws?.readyState === WebSocket.OPEN

  const sendSubscription = () => {
    if (isOpen()) ws!.send(JSON.stringify({ type: 'subscribe_stations', station_ids: _wantedIds() }))
  }

  function connect() {
    if (ws || typeof window === 'undefined') return
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    ws = new WebSocket(`${protocol}//${host}/ws/v1/env/`)

    ws.onopen = () => {
      reconnectAttempts = 0
      sendSubscription()
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type !== 'station_update' || !data.station) return
        const s = data.station
        iot.updateSingleEnvStation(s.id, s.latest || {}, s.last_reading_at)
        if (selectedEnvStation.value?.id === s.id) {
          // New object → Vue reactivity refreshes the open panel
          selectedEnvStation.value = {
            ...selectedEnvStation.value,
            latest: s.latest || {},
            last_reading_at: s.last_reading_at || selectedEnvStation.value.last_reading_at,
          }
        }
      } catch { /* ignore malformed frame */ }
    }

    ws.onclose = (event) => {
      ws = null
      // Reconnect only while something still wants updates
      if (event.code !== 1000 && wantedKey.value) {
        const delay = Math.min(3000 * Math.pow(2, reconnectAttempts), 60000)
        reconnectAttempts++
        reconnectTimer = setTimeout(connect, delay)
      }
    }

    ws.onerror = () => {}
  }

  function disconnect() {
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
    if (ws) { ws.close(1000); ws = null }
  }

  watch(wantedKey, (key) => {
    if (!key) { disconnect(); return }
    if (!ws) connect()
    else sendSubscription()
  })

  return { disconnect }
}
