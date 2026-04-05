/**
 * Composable for real-time poll updates via unified WebSocket.
 *
 * Uses realtimeStore.joinRoom('poll', id) instead of a dedicated WS connection.
 * Same return interface as before — zero changes needed in consuming components.
 */
import { ref, onMounted, onUnmounted } from 'vue'

export interface PollWebSocketMessage {
  type: 'poll.initial_state' | 'poll.vote_cast' | 'poll.delegation_created' | 'poll.delegation_revoked' | 'poll.status_changed' | 'poll.results_updated'
  [key: string]: any
}

export function usePollWebSocket(pollId: string) {
  const realtimeStore = useRealtimeStore()
  const authStore = useAuthStore()

  const connected = ref(false)
  const error = ref<string | null>(null)
  const lastMessage = ref<PollWebSocketMessage | null>(null)

  // Event callbacks
  const onVoteCast = ref<((data: any) => void) | null>(null)
  const onDelegationCreated = ref<((data: any) => void) | null>(null)
  const onDelegationRevoked = ref<((data: any) => void) | null>(null)
  const onStatusChanged = ref<((data: any) => void) | null>(null)
  const onResultsUpdated = ref<((data: any) => void) | null>(null)

  // Handlers registered on the realtime store (need refs for cleanup)
  const _handlers: Array<{ event: string; fn: (data: any) => void }> = []

  function _registerHandler(event: string, fn: (data: any) => void) {
    realtimeStore.on(event, fn)
    _handlers.push({ event, fn })
  }

  function _setup() {
    _registerHandler('poll.vote_cast', (data) => {
      lastMessage.value = data
      onVoteCast.value?.(data)
    })

    _registerHandler('poll.delegation_created', (data) => {
      lastMessage.value = data
      onDelegationCreated.value?.(data)
    })

    _registerHandler('poll.delegation_revoked', (data) => {
      lastMessage.value = data
      onDelegationRevoked.value?.(data)
    })

    _registerHandler('poll.status_changed', (data) => {
      lastMessage.value = data
      onStatusChanged.value?.(data)
    })

    _registerHandler('poll.results_updated', (data) => {
      lastMessage.value = data
      onResultsUpdated.value?.(data)
    })

    _registerHandler('poll.initial_state', (data) => {
      lastMessage.value = data
    })

    // Track connection state
    _registerHandler('room.joined', (data) => {
      if (data.room === 'poll' && data.id === pollId) {
        connected.value = true
      }
    })

    _registerHandler('room.left', (data) => {
      if (data.room === 'poll' && data.id === pollId) {
        connected.value = false
      }
    })
  }

  function connect() {
    if (!authStore.isAuthenticated) {
      // Anonymous users get REST-only (no live updates)
      return
    }
    realtimeStore.connect()
    realtimeStore.joinRoom('poll', pollId)
    connected.value = realtimeStore.connected
  }

  function disconnect() {
    realtimeStore.leaveRoom('poll', pollId)
    connected.value = false

    // Unregister all handlers
    for (const { event, fn } of _handlers) {
      realtimeStore.off(event, fn)
    }
    _handlers.length = 0
  }

  // Setup handlers immediately (before mount, so callers can set onVoteCast etc.)
  _setup()

  onMounted(() => {
    connect()
  })

  onUnmounted(() => {
    disconnect()
  })

  return {
    connected,
    error,
    lastMessage,
    connect,
    disconnect,
    onVoteCast,
    onDelegationCreated,
    onDelegationRevoked,
    onStatusChanged,
    onResultsUpdated,
  }
}
