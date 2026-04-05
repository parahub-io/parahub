/**
 * WebSocket composable with cookie-based authentication
 *
 * Provides secure WebSocket connection using cookies instead of query params
 * to prevent token leakage in server logs.
 */

import { ref, onUnmounted } from 'vue'

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

    // Set ws_token cookie
    // Note: We don't use HttpOnly here because we need to set it from JS
    // The token itself is already validated on the backend
    document.cookie = `ws_token=${token}; path=/; SameSite=Strict; Secure`
    return true
  }

  /**
   * Remove auth cookie after disconnect
   */
  const clearAuthCookie = () => {
    document.cookie = 'ws_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT'
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
      // Determine protocol (ws or wss)
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const host = window.location.host

      // Build WebSocket URL WITHOUT token in query params (security fix)
      const wsUrl = `${protocol}//${host}${path}`

      ws.value = new WebSocket(wsUrl)

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
