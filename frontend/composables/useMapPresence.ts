/**
 * Map Presence Composable - WebSocket connection for MMORPG-style avatars
 *
 * Usage:
 *   const {
 *     connect,
 *     disconnect,
 *     updatePosition,
 *     setState,
 *     setSpeechBubble,
 *     nearbyAvatars,
 *     isConnected
 *   } = useMapPresence()
 *
 *   await connect()
 *   updatePosition(38.7223, -9.1393, 14)
 */

import { ref, computed, onUnmounted } from 'vue'
import { useWebSocket } from './useWebSocket'

export interface Avatar {
  profile_id: string
  lat: number
  lon: number
  zoom: number
  avatar_type: string
  avatar_state: string
  speech_bubble: string
  profile_hna: string
  profile_name: string
  distance_km?: number
  last_update?: string
}

// LPC animation states
export type AvatarState =
  | 'idle'
  | 'walking'
  | 'jumping'
  | 'sitting'
  | 'emoting'
export type AvatarType = 'p0' | 'p1' | 'p2' | 'p3' | 'p4'

export function useMapPresence() {
  const nearbyAvatars = ref<Map<string, Avatar>>(new Map())

  // Debounce timer for position updates
  let positionUpdateTimer: NodeJS.Timeout | null = null

  // Create WebSocket connection immediately (not in connect())
  const wsConnection = useWebSocket({
    path: '/ws/v1/map/presence/',
    onMessage: handleMessage,
    onOpen: () => {},
    onClose: (event) => {
      nearbyAvatars.value.clear()
    },
    onError: (error) => {
      console.error('[MapPresence] WebSocket error:', error)
    },
    autoReconnect: true,
  })

  /**
   * Connect to map presence WebSocket
   */
  async function connect(): Promise<boolean> {
    try {
      wsConnection.connect()
      return true
    } catch (error) {
      console.error('[MapPresence] Failed to connect:', error)
      return false
    }
  }

  /**
   * Disconnect from WebSocket
   */
  function disconnect() {
    wsConnection.disconnect()
    nearbyAvatars.value.clear()
  }

  /**
   * Handle incoming WebSocket messages
   */
  function handleMessage(data: any) {
    const type = data.type

    if (type === 'nearby_avatars') {
      // Initial list of nearby avatars
      nearbyAvatars.value.clear()
      for (const avatar of data.avatars) {
        nearbyAvatars.value.set(avatar.profile_id, avatar)
      }
    }
    else if (type === 'avatar_update') {
      handleAvatarUpdate(data)
    }
    else if (type === 'pong') {
      // Heartbeat response
    }
    else if (type === 'error') {
      console.error('[MapPresence] Server error:', data.message)
    }
  }

  /**
   * Handle avatar update (position, state, speech bubble)
   */
  function handleAvatarUpdate(data: any) {
    const profileId = data.profile_id
    const updateType = data.update_type

    if (updateType === 'position') {
      // Full position update
      const avatar: Avatar = {
        profile_id: profileId,
        lat: data.lat,
        lon: data.lon,
        zoom: 14, // Default zoom
        avatar_type: data.avatar_type,
        avatar_state: data.avatar_state,
        speech_bubble: '',
        profile_hna: data.profile_hna,
        profile_name: data.profile_name,
      }
      nearbyAvatars.value.set(profileId, avatar)
    }
    else if (updateType === 'state') {
      // State change - create new object to trigger reactivity
      const existingAvatar = nearbyAvatars.value.get(profileId)
      if (existingAvatar) {
        nearbyAvatars.value.set(profileId, {
          ...existingAvatar,
          avatar_state: data.avatar_state
        })
      } else if (data.lat && data.lon) {
        // Avatar not in our map yet, but we have full data - add it
        nearbyAvatars.value.set(profileId, {
          profile_id: profileId,
          lat: data.lat,
          lon: data.lon,
          zoom: 14,
          avatar_type: data.avatar_type || 'p1',
          avatar_state: data.avatar_state,
          speech_bubble: '',
          profile_hna: data.profile_hna || '',
          profile_name: data.profile_name || '',
        })
      }
    }
    else if (updateType === 'speech_bubble') {
      // Speech bubble update - create new object to trigger reactivity
      const existingAvatar = nearbyAvatars.value.get(profileId)
      if (existingAvatar) {
        nearbyAvatars.value.set(profileId, {
          ...existingAvatar,
          speech_bubble: data.speech_bubble
        })
      } else if (data.lat && data.lon) {
        // Avatar not in our map yet, but we have full data - add it
        nearbyAvatars.value.set(profileId, {
          profile_id: profileId,
          lat: data.lat,
          lon: data.lon,
          zoom: 14,
          avatar_type: data.avatar_type || 'p1',
          avatar_state: data.avatar_state || 'idle',
          speech_bubble: data.speech_bubble,
          profile_hna: data.profile_hna || '',
          profile_name: data.profile_name || '',
        })
      }
    }
  }

  /**
   * Update viewport position (debounced 100ms, or immediate if specified)
   */
  function updatePosition(
    lat: number,
    lon: number,
    zoom: number,
    avatarType: AvatarType = 'male-suit',
    avatarState: AvatarState = 'idle',
    immediate: boolean = false
  ) {
    const sendUpdate = () => {
      wsConnection.send({
        type: 'position_update',
        lat,
        lon,
        zoom,
        avatar_type: avatarType,
        avatar_state: avatarState,
      })
    }

    if (immediate) {
      // Send immediately without debounce
      if (positionUpdateTimer) {
        clearTimeout(positionUpdateTimer)
        positionUpdateTimer = null
      }
      sendUpdate()
      return
    }

    // Clear previous timer
    if (positionUpdateTimer) {
      clearTimeout(positionUpdateTimer)
    }

    // Debounce: send update after 100ms of no movement
    positionUpdateTimer = setTimeout(sendUpdate, 100)
  }

  /**
   * Set avatar state (idle, dancing, jumping)
   */
  function setState(state: AvatarState) {
    wsConnection.send({
      type: 'set_state',
      state,
    })
  }

  /**
   * Set speech bubble text
   */
  function setSpeechBubble(text: string) {
    wsConnection.send({
      type: 'set_speech_bubble',
      text: text.slice(0, 200), // Max 200 chars
    })
  }

  /**
   * Send heartbeat ping
   */
  function sendHeartbeat() {
    wsConnection.send({
      type: 'ping',
      timestamp: Date.now(),
    })
  }

  // Auto-disconnect on component unmount
  onUnmounted(() => {
    disconnect()
    if (positionUpdateTimer) {
      clearTimeout(positionUpdateTimer)
    }
  })

  const isConnected = computed(() => wsConnection.isConnected.value)

  return {
    // State
    nearbyAvatars: computed(() => Array.from(nearbyAvatars.value.values())),
    isConnected,

    // Methods
    connect,
    disconnect,
    updatePosition,
    setState,
    setSpeechBubble,
    sendHeartbeat,
  }
}
