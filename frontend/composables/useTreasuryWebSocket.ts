/**
 * Composable for real-time treasury budget updates via unified WebSocket.
 * Uses realtimeStore.joinRoom('treasury', establishmentId).
 */
import { ref, watch, onMounted, onUnmounted, type Ref } from 'vue'

export interface TreasuryMedianData {
  category_id: string
  slug: string
  name: string
  icon: string
  median_percent: number
  voter_count: number
}

export function useTreasuryWebSocket(establishmentId: Ref<string>) {
  const realtimeStore = useRealtimeStore()
  const authStore = useAuthStore()

  const connected = ref(false)
  const onMediansUpdated = ref<((data: any) => void) | null>(null)

  const _handlers: Array<{ event: string; fn: (data: any) => void }> = []
  let _currentRoomId: string | null = null

  function _registerHandler(event: string, fn: (data: any) => void) {
    realtimeStore.on(event, fn)
    _handlers.push({ event, fn })
  }

  function _setup() {
    _registerHandler('treasury.medians_updated', (data) => {
      // Only handle updates for our establishment
      if (data.id === establishmentId.value) {
        onMediansUpdated.value?.(data)
      }
    })

    _registerHandler('room.joined', (data) => {
      if (data.room === 'treasury' && data.id === establishmentId.value) {
        connected.value = true
      }
    })

    _registerHandler('room.left', (data) => {
      if (data.room === 'treasury' && data.id === establishmentId.value) {
        connected.value = false
      }
    })
  }

  function connect() {
    if (!authStore.isAuthenticated) return
    const id = establishmentId.value
    if (!id) return
    realtimeStore.connect()
    realtimeStore.joinRoom('treasury', id)
    _currentRoomId = id
    connected.value = realtimeStore.connected
  }

  function disconnect() {
    if (_currentRoomId) {
      realtimeStore.leaveRoom('treasury', _currentRoomId)
      _currentRoomId = null
    }
    connected.value = false
    for (const { event, fn } of _handlers) {
      realtimeStore.off(event, fn)
    }
    _handlers.length = 0
  }

  _setup()

  // Watch for establishmentId changes (e.g. after fetch resolves)
  watch(establishmentId, (newId, oldId) => {
    if (oldId && oldId !== newId) {
      realtimeStore.leaveRoom('treasury', oldId)
    }
    if (newId && authStore.isAuthenticated) {
      realtimeStore.connect()
      realtimeStore.joinRoom('treasury', newId)
      _currentRoomId = newId
      connected.value = realtimeStore.connected
    }
  })

  onMounted(() => {
    connect()
  })

  onUnmounted(() => {
    disconnect()
  })

  return {
    connected,
    onMediansUpdated,
    connect,
    disconnect,
  }
}
