/**
 * Driver Mode composable — GPS broadcasting from driver's browser/tablet.
 *
 * Manages: WebSocket connection, Geolocation API, Wake Lock, TTS announcements.
 * Writes to same Redis transit pipeline as GTFS-RT daemon via WS.
 */

import { ref, onUnmounted } from 'vue'

interface StopInfo {
  id: string
  name: string
}

interface ShiftInfo {
  id: string
  route_id: string
  route_short_name: string
  route_long_name: string
  route_color: string
  route_type: number
  route_source_id: string
  data_source_id: string
  direction_id: number
  vehicle_id: string
  status: string
  place_slug: string
}

export function useDriverMode() {
  const isActive = ref(false)
  const connectionStatus = ref<'disconnected' | 'connecting' | 'connected'>('disconnected')
  const currentStop = ref<StopInfo | null>(null)
  const nextStop = ref<StopInfo | null>(null)
  const speed = ref(0)
  const gpsAccuracy = ref(0)
  const positionCount = ref(0)
  const error = ref<string | null>(null)
  const shiftInfo = ref<ShiftInfo | null>(null)
  const headsign = ref('')
  const stops = ref<StopInfo[]>([])
  const ttsEnabled = ref(true)

  let ws: WebSocket | null = null
  let watchId: number | null = null
  let wakeLock: WakeLockSentinel | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let lastSendTime = 0
  const SEND_INTERVAL = 15_000 // 15 seconds

  async function startShift(routeId: string, directionId: number): Promise<ShiftInfo | null> {
    const authStore = useAuthStore()
    await authStore.ensureToken()
    if (!authStore.token) {
      error.value = 'Not authenticated'
      return null
    }

    try {
      const data = await $fetch<any>('/api/v1/geo/driver/start/', {
        method: 'POST',
        credentials: 'include',
        headers: { Authorization: `Bearer ${authStore.token}` },
        body: { route_id: routeId, direction_id: directionId },
      })

      shiftInfo.value = data
      error.value = null

      // Connect WebSocket
      await connectWs(data.id)
      // Start GPS
      startGps()
      // Acquire Wake Lock
      await acquireWakeLock()

      isActive.value = true
      return data
    } catch (e: any) {
      error.value = e?.data?.detail || e?.message || 'Failed to start shift'
      return null
    }
  }

  async function resumeExistingShift(shift: ShiftInfo) {
    shiftInfo.value = shift
    error.value = null

    // Connect WebSocket
    await connectWs(shift.id)
    // Start GPS
    startGps()
    // Acquire Wake Lock
    await acquireWakeLock()

    isActive.value = true
  }

  async function stopShift() {
    const id = shiftInfo.value?.id
    if (!id) return

    const authStore = useAuthStore()
    await authStore.ensureToken()

    try {
      await $fetch(`/api/v1/geo/driver/stop/${id}/`, {
        method: 'POST',
        credentials: 'include',
        headers: { Authorization: `Bearer ${authStore.token}` },
      })
    } catch (e) {
      // Best effort — WS disconnect will also end shift
    }

    cleanup()
  }

  async function stopShiftById(shiftId: string) {
    const authStore = useAuthStore()
    await authStore.ensureToken()

    try {
      await $fetch(`/api/v1/geo/driver/stop/${shiftId}/`, {
        method: 'POST',
        credentials: 'include',
        headers: { Authorization: `Bearer ${authStore.token}` },
      })
    } catch (e) {
      // Best effort
    }

    cleanup()
  }

  function changeDirection(directionId: number) {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'direction_change', direction_id: directionId }))
    }
  }

  // --- WebSocket ---

  async function connectWs(shiftId: string) {
    if (ws) return
    connectionStatus.value = 'connecting'

    const authStore = useAuthStore()
    await authStore.ensureToken()

    // Set ws_token cookie for WebSocket auth
    document.cookie = `ws_token=${authStore.token}; path=/; SameSite=Strict; Secure`

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    ws = new WebSocket(`${protocol}//${window.location.host}/ws/v1/driver/`)

    ws.onopen = () => {
      connectionStatus.value = 'connected'
      ws?.send(JSON.stringify({ type: 'start', shift_id: shiftId }))
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        // Server may send array [announcement, ack] or single object
        const messages = Array.isArray(data) ? data : [data]
        for (const msg of messages) {
          handleWsMessage(msg)
        }
      } catch {}
    }

    ws.onclose = () => {
      connectionStatus.value = 'disconnected'
      ws = null
      if (isActive.value) {
        // Auto-reconnect
        reconnectTimer = setTimeout(() => {
          if (isActive.value && shiftInfo.value) {
            connectWs(shiftInfo.value.id)
          }
        }, 3000)
      }
    }

    ws.onerror = () => {
      // onclose will fire after onerror
    }
  }

  function handleWsMessage(msg: any) {
    switch (msg.type) {
      case 'shift_confirmed':
        headsign.value = msg.headsign || ''
        if (msg.stops) {
          stops.value = msg.stops
        }
        break

      case 'position_ack':
        positionCount.value = msg.seq || 0
        break

      case 'stop_announcement':
        currentStop.value = { id: msg.stop_id, name: msg.stop_name }
        if (msg.next_stop_id) {
          nextStop.value = { id: msg.next_stop_id, name: msg.next_stop_name }
        }
        if (ttsEnabled.value) {
          announceStop(msg.next_stop_name || msg.stop_name)
        }
        break

      case 'direction_changed':
        headsign.value = msg.headsign || ''
        if (msg.stops) {
          stops.value = msg.stops
        }
        if (shiftInfo.value) {
          shiftInfo.value.direction_id = msg.direction_id
        }
        currentStop.value = null
        nextStop.value = null
        break

      case 'error':
        error.value = msg.message
        break
    }
  }

  // --- GPS ---

  function startGps() {
    if (!navigator.geolocation) {
      error.value = 'GPS not available'
      return
    }

    watchId = navigator.geolocation.watchPosition(
      (pos) => {
        speed.value = pos.coords.speed ? Math.round(pos.coords.speed * 3.6) : 0 // m/s → km/h
        gpsAccuracy.value = Math.round(pos.coords.accuracy)

        const now = Date.now()
        if (now - lastSendTime >= SEND_INTERVAL && ws?.readyState === WebSocket.OPEN) {
          lastSendTime = now
          ws.send(JSON.stringify({
            type: 'position',
            lat: pos.coords.latitude,
            lon: pos.coords.longitude,
            speed: speed.value,
            bearing: pos.coords.heading,
            accuracy: pos.coords.accuracy,
          }))
        }
      },
      (err) => {
        // 1=PERMISSION_DENIED, 2=POSITION_UNAVAILABLE, 3=TIMEOUT
        if (err.code === 1) {
          error.value = 'GPS permission denied'
        } else {
          error.value = 'GPS signal lost'
        }
      },
      {
        enableHighAccuracy: true,
        maximumAge: 10_000,
        timeout: 15_000,
      }
    )
  }

  // --- Wake Lock ---

  async function acquireWakeLock() {
    if (!('wakeLock' in navigator)) return
    try {
      wakeLock = await navigator.wakeLock.request('screen')
      wakeLock.addEventListener('release', () => { wakeLock = null })
    } catch {}
  }

  // --- TTS ---

  function announceStop(name: string) {
    if (!name || typeof window === 'undefined') return
    if (!('speechSynthesis' in window)) return
    const utterance = new SpeechSynthesisUtterance(name)
    utterance.rate = 0.9
    window.speechSynthesis.speak(utterance)
  }

  // --- Cleanup ---

  function cleanup() {
    isActive.value = false
    connectionStatus.value = 'disconnected'

    if (watchId !== null) {
      navigator.geolocation.clearWatch(watchId)
      watchId = null
    }

    if (ws) {
      ws.onclose = null // Prevent reconnect
      ws.close()
      ws = null
    }

    if (wakeLock) {
      wakeLock.release().catch(() => {})
      wakeLock = null
    }

    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }

    // Clear ws_token cookie
    document.cookie = 'ws_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT'

    shiftInfo.value = null
    currentStop.value = null
    nextStop.value = null
    positionCount.value = 0
    speed.value = 0
    gpsAccuracy.value = 0
    error.value = null
  }

  onUnmounted(() => {
    // Don't auto-stop shift on unmount — driver might navigate away briefly
    // Just disconnect WS; shift will timeout via heartbeat TTL
    if (ws) {
      ws.onclose = null
      ws.close()
      ws = null
    }
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
    }
  })

  return {
    // State
    isActive,
    connectionStatus,
    currentStop,
    nextStop,
    speed,
    gpsAccuracy,
    positionCount,
    error,
    shiftInfo,
    headsign,
    stops,
    ttsEnabled,
    // Actions
    startShift,
    stopShift,
    stopShiftById,
    resumeExistingShift,
    changeDirection,
  }
}
