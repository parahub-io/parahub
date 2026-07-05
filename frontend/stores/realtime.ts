import { defineStore } from 'pinia'

export interface ObjectUpdate {
  id: string
  object_type: string
  changes: Record<string, any>
  timestamp: number
}

type EventHandler = (data: any) => void

export const useRealtimeStore = defineStore('realtime', {
  state: () => ({
    subscriptions: new Set<string>(),
    latestUpdates: new Map<string, ObjectUpdate>(),
    connected: false,
    _pendingSubscriptions: new Set<string>(),
    joinedRooms: new Map<string, Set<string>>(),
    _pendingJoins: [] as Array<{ room: string; id: string }>,
  }),

  actions: {
    connect() {
      // Idempotent — only create WS once
      if (_ws || _connecting) return
      _doConnect(this)
    },

    subscribe(ids: string[]) {
      if (!ids.length) return

      for (const id of ids) {
        this.subscriptions.add(id)
      }

      if (_ws && this.connected) {
        _sendSubscribe(ids)
      } else {
        for (const id of ids) {
          this._pendingSubscriptions.add(id)
        }
      }
    },

    unsubscribe(ids: string[]) {
      if (!ids.length) return

      for (const id of ids) {
        this.subscriptions.delete(id)
        this._pendingSubscriptions.delete(id)
        this.latestUpdates.delete(id)
      }

      if (_ws && this.connected) {
        _sendUnsubscribe(ids)
      }
    },

    joinRoom(room: string, id: string) {
      // Track locally
      if (!this.joinedRooms.has(room)) {
        this.joinedRooms.set(room, new Set())
      }
      this.joinedRooms.get(room)!.add(id)

      if (_ws && this.connected) {
        _sendJson({ type: 'join', room, id })
      } else {
        this._pendingJoins.push({ room, id })
      }
    },

    leaveRoom(room: string, id: string) {
      // Remove from tracking
      const roomSet = this.joinedRooms.get(room)
      if (roomSet) {
        roomSet.delete(id)
        if (roomSet.size === 0) {
          this.joinedRooms.delete(room)
        }
      }

      // Remove from pending
      this._pendingJoins = this._pendingJoins.filter(
        (p) => !(p.room === room && p.id === id)
      )

      if (_ws && this.connected) {
        _sendJson({ type: 'leave', room, id })
      }
    },

    on(eventType: string, handler: EventHandler) {
      if (!_eventHandlers.has(eventType)) {
        _eventHandlers.set(eventType, new Set())
      }
      _eventHandlers.get(eventType)!.add(handler)
    },

    off(eventType: string, handler: EventHandler) {
      const handlers = _eventHandlers.get(eventType)
      if (handlers) {
        handlers.delete(handler)
        if (handlers.size === 0) {
          _eventHandlers.delete(eventType)
        }
      }
    },

    disconnect() {
      _cleanup()
      this.connected = false
    },

    _handleMessage(data: any) {
      const type = data.type as string

      if (type === 'object.updated') {
        this._handleObjectUpdated(data)
      } else if (type === 'ads.feed_updated') {
        const { loadFeedCount } = useAdsState()
        loadFeedCount()
      }
      // subscribed/unsubscribed/room.joined/room.left — silently acknowledged

      // Dispatch to registered event handlers
      const handlers = _eventHandlers.get(type)
      if (handlers) {
        for (const handler of handlers) {
          try {
            handler(data)
          } catch (e) {
            console.error(`[realtime] Error in handler for ${type}:`, e)
          }
        }
      }
    },

    _handleObjectUpdated(data: { id: string; object_type: string; changes: Record<string, any> }) {
      const update: ObjectUpdate = {
        id: data.id,
        object_type: data.object_type,
        changes: data.changes,
        timestamp: Date.now(),
      }

      this.latestUpdates.set(data.id, update)

      // Evict oldest entries to prevent unbounded growth
      if (this.latestUpdates.size > 500) {
        const oldest = this.latestUpdates.keys().next().value
        if (oldest !== undefined) this.latestUpdates.delete(oldest)
      }

      // Domain dispatch
      if (data.object_type === 'iot_device') {
        const iotStore = useIoTStore()
        const c = data.changes
        if (c.latitude != null && c.longitude != null) {
          iotStore.updateDeviceLocation(data.id, {
            lat: c.latitude,
            lon: c.longitude,
            speed: c.speed,
            battery_level: c.battery_level,
            device_timestamp: c.device_timestamp,
          })
        }
      }
    },

    _onOpen() {
      this.connected = true
      _startHeartbeat()

      // Re-subscribe all active subscriptions on reconnect
      const all = new Set([...this.subscriptions, ...this._pendingSubscriptions])
      this._pendingSubscriptions.clear()

      if (all.size > 0) {
        _sendSubscribe([...all])
      }

      // Re-join rooms on reconnect
      for (const { room, id } of this._pendingJoins) {
        _sendJson({ type: 'join', room, id })
      }
      this._pendingJoins = []

      // Re-join tracked rooms (on reconnect after disconnect)
      for (const [room, ids] of this.joinedRooms) {
        for (const id of ids) {
          _sendJson({ type: 'join', room, id })
        }
      }
    },

    _onClose() {
      this.connected = false
      _stopHeartbeat()
    },
  },
})

// --- Module-level WS state (not reactive, singleton) ---

let _ws: WebSocket | null = null
let _connecting = false
let _reconnectTimeout: ReturnType<typeof setTimeout> | null = null
let _reconnectAttempts = 0
let _heartbeat: ReturnType<typeof setInterval> | null = null
const _eventHandlers = new Map<string, Set<EventHandler>>()

// Heartbeat keeps the connection counted as "online" (server presence window is
// 60s) and alive through proxy idle timeouts. 30s → tolerates one missed beat.
const HEARTBEAT_INTERVAL = 30000

function _startHeartbeat() {
  _stopHeartbeat()
  _heartbeat = setInterval(() => {
    _sendJson({ type: 'heartbeat', timestamp: Date.now() })
  }, HEARTBEAT_INTERVAL)
}

function _stopHeartbeat() {
  if (_heartbeat) {
    clearInterval(_heartbeat)
    _heartbeat = null
  }
}

function _sendJson(data: any) {
  if (_ws?.readyState === WebSocket.OPEN) {
    _ws.send(JSON.stringify(data))
  }
}

function _sendSubscribe(ids: string[]) {
  _sendJson({ type: 'subscribe', ids })
}

function _sendUnsubscribe(ids: string[]) {
  _sendJson({ type: 'unsubscribe', ids })
}

function _cleanup() {
  _stopHeartbeat()
  if (_reconnectTimeout) {
    clearTimeout(_reconnectTimeout)
    _reconnectTimeout = null
  }
  if (_ws) {
    _ws.close(1000, 'Client disconnect')
    _ws = null
  }
  _connecting = false
  _reconnectAttempts = 0
}

async function _doConnect(store: ReturnType<typeof useRealtimeStore>) {
  _connecting = true

  const authStore = useAuthStore()
  await authStore.ensureToken()

  const token = authStore.token
  if (!token) {
    console.error('[realtime] No auth token for WS')
    _connecting = false
    return
  }

  // Set ws_token cookie (same pattern as useWebSocket)
  document.cookie = `ws_token=${token}; path=/; SameSite=Strict; Secure`

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host

  _ws = new WebSocket(`${protocol}//${host}/ws/v1/realtime/`)

  _ws.onopen = () => {
    _connecting = false
    _reconnectAttempts = 0
    store._onOpen()
  }

  _ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      store._handleMessage(data)
    } catch (e) {
      console.error('[realtime] Failed to parse WS message:', e)
    }
  }

  _ws.onclose = (event) => {
    _ws = null
    _connecting = false
    store._onClose()

    // Clear auth cookie
    document.cookie = 'ws_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT'

    // Auto-reconnect (not on clean close)
    if (event.code !== 1000) {
      _reconnectAttempts++
      const delay = Math.min(3000 * Math.pow(2, _reconnectAttempts - 1), 60000)
      _reconnectTimeout = setTimeout(() => {
        _doConnect(store)
      }, delay)
    }
  }

  _ws.onerror = (event) => {
    console.error('[realtime] WS error:', event)
  }
}
