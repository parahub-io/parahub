/**
 * WebSocket composable with cookie-based authentication
 *
 * Provides secure WebSocket connection using cookies instead of query params
 * to prevent token leakage in server logs.
 */

import { ref, onUnmounted } from 'vue'

import { buildWsUrl, clearWsAuthCookie, setWsAuthCookie, shouldRetryWithToken } from '~/utils/wsAuth'

export interface WebSocketOptions {
  /** URL path (e.g., '/ws/v1/items/updates') */
  path: string

  /** Callback for incoming messages */
  onMessage?: (data: any) => void

  /** Callback for connection open */
  onOpen?: () => void

  /** Callback for connection close */
  onClose?: (event: CloseEvent) => void

  /** Callback for errors */
  onError?: (event: Event) => void

  /** Auto-reconnect on disconnect (default: true) */
  autoReconnect?: boolean

  /** Reconnect delay in ms (default: 3000) */
  reconnectDelay?: number

  /** Skip onUnmounted cleanup — use for singleton stores not tied to components */
  skipCleanup?: boolean
}

export const useWebSocket = (options: WebSocketOptions) => {
  const config = useRuntimeConfig()
  const authStore = useAuthStore()

  const ws = ref<WebSocket | null>(null)
  const isConnected = ref(false)
  const reconnectTimeout = ref<NodeJS.Timeout | null>(null)
  let reconnectAttempts = 0
  let tokenInUrl = false

  const {
    path,
    onMessage,
    onOpen,
    onClose,
    onError,
    autoReconnect = true,
    reconnectDelay = 3000,
    skipCleanup = false,
  } = options

  /**
   * Set WebSocket token as cookie before connecting
   * This is the secure method - tokens in cookies are not logged
   */
  const setAuthCookie = () => {
    const token = authStore.token
    if (!token) {
      console.error('Cannot connect WebSocket: No auth token available')
      return false
    }

    // Not HttpOnly — it has to be set from JS. See `utils/wsAuth` for why the
    // cookie is `Lax` and what happens when the WebView drops it anyway.
    setWsAuthCookie(token)
    return true
  }

  /**
   * Remove auth cookie after disconnect
   */
  const clearAuthCookie = () => {
    clearWsAuthCookie()
  }

  /**
   * Connect to WebSocket server
   * Ensures fresh JWT token before each connection attempt
   */
  const connect = async () => {
    // Prevent duplicate connections
    if (ws.value && isConnected.value) {
      return
    }

    if (ws.value) {
      return
    }

    // Ensure fresh token before connecting (handles expired tokens on reconnect)
    await authStore.ensureToken()

    // Set auth cookie before connecting
    if (!setAuthCookie()) {
      return
    }

    try {
      // The token stays out of the URL unless a native client has already been
      // refused once with it in the cookie alone (see `utils/wsAuth`).
      ws.value = new WebSocket(buildWsUrl(path, authStore.token, tokenInUrl))

      // Handle connection open
      ws.value.onopen = () => {
        isConnected.value = true
        reconnectAttempts = 0
        onOpen?.()
      }

      // Handle incoming messages
      ws.value.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          onMessage?.(data)
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error)
        }
      }

      // Handle connection close
      ws.value.onclose = (event) => {
        isConnected.value = false
        ws.value = null

        onClose?.(event)

        // Clear auth cookie
        clearAuthCookie()

        // Refused for want of a token on a native build: the cookie did not
        // reach the handshake, so come back once with it in the query string.
        if (shouldRetryWithToken(event.code, tokenInUrl)) {
          tokenInUrl = true
          reconnectTimeout.value = setTimeout(() => connect(), 200)
          return
        }

        // Auto-reconnect if enabled and not a normal closure
        if (autoReconnect && event.code !== 1000) {
          reconnectAttempts++
          // Exponential backoff: 3s, 6s, 12s, 24s, max 60s
          const delay = Math.min(reconnectDelay * Math.pow(2, reconnectAttempts - 1), 60000)
          reconnectTimeout.value = setTimeout(() => {
            connect()
          }, delay)
        }
      }

      // Handle errors
      ws.value.onerror = (event) => {
        console.error('WebSocket error:', event)
        onError?.(event)
      }

    } catch (error) {
      console.error('Failed to create WebSocket connection:', error)
      clearAuthCookie()
    }
  }

  /**
   * Disconnect from WebSocket server
   */
  const disconnect = () => {
    if (reconnectTimeout.value) {
      clearTimeout(reconnectTimeout.value)
      reconnectTimeout.value = null
    }

    if (ws.value) {
      ws.value.close(1000, 'Client disconnect')
      ws.value = null
      isConnected.value = false
    }

    clearAuthCookie()
  }

  /**
   * Send message to WebSocket server
   */
  const send = (data: any) => {
    if (!ws.value || !isConnected.value) {
      console.error('Cannot send message: WebSocket is not connected')
      return false
    }

    try {
      const message = typeof data === 'string' ? data : JSON.stringify(data)
      ws.value.send(message)
      return true
    } catch (error) {
      console.error('Failed to send WebSocket message:', error)
      return false
    }
  }

  // Cleanup on component unmount (skip for singleton stores)
  if (!skipCleanup) {
    onUnmounted(() => {
      disconnect()
    })
  }

  return {
    ws,
    isConnected,
    connect,
    disconnect,
    send
  }
}
