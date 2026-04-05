import { ref, computed, watch } from 'vue'
import { Capacitor } from '@capacitor/core'
import { useAuthStore } from '~/stores/auth'

// Update native app icon badge (Android/iOS)
const updateNativeBadge = async (count: number) => {
  if (!Capacitor.isNativePlatform()) return
  try {
    const { Badge } = await import('@capawesome/capacitor-badge')
    if (count > 0) {
      await Badge.set({ count })
    } else {
      await Badge.clear()
    }
  } catch { /* badge not supported on this device */ }
}

// Global state for unread count (shared across all instances)
// Use reactive ref at module level to ensure single source of truth
const totalUnreadCount = ref(0)
const rooms = ref<Array<{ room_id: string; unread_count: number }>>([])
const isInitialized = ref(false)
const isFirstSyncCompleted = ref(false) // Prevent showing stale count before fully_read markers load
let syncInterval: ReturnType<typeof setInterval> | null = null
let matrixAccessToken: string | null = null
let matrixSyncToken: string | null = null
let isSyncing = false
let handleVisibilityChange: (() => void) | null = null
let syncRetryCount = 0
const MAX_SYNC_RETRIES = 5

export const useMatrixUnread = () => {
  const authStore = useAuthStore()

  // Get Matrix user ID for the current user
  const getMatrixUserId = () => {
    if (!authStore.user?.id) return null
    const matrixUser = authStore.user.id.toLowerCase().replace(/-/g, '_')
    return `@${matrixUser}:parahub.io`
  }

  // Store latest event IDs and fully_read markers per room
  const roomReadMarkers = new Map<string, { latestEventId: string | null, fullyReadEventId: string | null }>()

  // Calculate unread count - hybrid approach using notification_count + fully_read override
  const calculateRoomUnread = (roomId: string, roomData: any, isIncrementalSync: boolean) => {
    const matrixUserId = getMatrixUserId()
    if (!matrixUserId) return 0

    // Get notification_count from server (per-device, but updates faster)
    const notificationCount = roomData.unread_notifications?.notification_count || 0

    // Get or initialize room read markers
    let markers = roomReadMarkers.get(roomId)
    if (!markers) {
      markers = { latestEventId: null, fullyReadEventId: null }
      roomReadMarkers.set(roomId, markers)
    }

    // Update latest event ID if timeline present
    const timelineEvents = roomData.timeline?.events || []
    if (timelineEvents.length > 0) {
      const latestEvent = timelineEvents[timelineEvents.length - 1]
      if (latestEvent?.event_id) {
        markers.latestEventId = latestEvent.event_id
      }
    }

    // Update fully_read marker ONLY if explicitly present in this sync
    const accountDataEvents = roomData.account_data?.events || []
    const fullyReadEvent = accountDataEvents.find((e: any) => e.type === 'm.fully_read')
    if (fullyReadEvent?.content?.event_id) {
      const newMarker = fullyReadEvent.content.event_id
      if (markers.fullyReadEventId !== newMarker) {
        markers.fullyReadEventId = newMarker
      }
    }

    // Strategy: Use notification_count BUT override to 0 if fully_read == latest
    // This handles cross-device sync: when you read in Element, fully_read updates
    if (markers.latestEventId && markers.fullyReadEventId &&
        markers.latestEventId === markers.fullyReadEventId) {
      return 0
    }

    return notificationCount
  }

  // Fetch unread counts from Matrix sync API using read receipts
  const fetchUnreadCounts = async () => {
    if (!authStore.isAuthenticated) {
      return
    }

    try {
      // Get Matrix credentials if not already initialized
      if (!matrixAccessToken) {
        try {
          const response = await $fetch('/api/v1/matrix/widget-token', {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${authStore.token}`
            }
          })

          if (response.success) {
            matrixAccessToken = response.access_token
          } else {
            console.warn('[useMatrixUnread] Failed to get Matrix token, disabling sync')
            return
          }
        } catch (e: any) {
          // 401/403 from widget-token — don't retry, auth is broken
          console.warn('[useMatrixUnread] Matrix token request failed, disabling sync')
          return
        }
      }

      // Fetch sync data - get notification_count, latest event, and fully_read markers
      const filter = {
        room: {
          include_leave: false,
          state: { lazy_load_members: true },
          timeline: { limit: 1 }, // Only need latest event for comparison
          ephemeral: { types: ['m.receipt'] }, // Include read receipts to trigger sync when user reads messages
          account_data: { types: ['m.fully_read'] } // Get fully_read markers for cross-device sync
        },
        presence: { types: [] }
      }

      const params = new URLSearchParams({
        timeout: '0', // Don't long-poll, just get current state
        filter: JSON.stringify(filter),
        // Add timestamp to prevent caching
        _t: Date.now().toString()
      })

      const syncResponse = await fetch(`https://parahub.io/_matrix/client/r0/sync?${params}`, {
        headers: {
          'Authorization': `Bearer ${matrixAccessToken}`,
          'Cache-Control': 'no-cache'
        }
      })

      if (!syncResponse.ok) {
        if (syncResponse.status === 401 || syncResponse.status === 403) {
          console.warn('[useMatrixUnread] Matrix token expired, clearing')
          matrixAccessToken = null
        }
        return
      }

      const syncData = await syncResponse.json()

      // Update rooms with unread counts
      const roomsMap = new Map(rooms.value.map(r => [r.room_id, r]))

      // Process joined rooms (add/update)
      if (syncData.rooms?.join) {
        const updatedRooms = Object.entries(syncData.rooms.join).map(([roomId, roomData]: [string, any]) => {
          const unreadCount = calculateRoomUnread(roomId, roomData, false)

          return {
            room_id: roomId,
            unread_count: unreadCount
          }
        })

        updatedRooms.forEach(room => {
          roomsMap.set(room.room_id, room)
        })
      }

      // Process left rooms (remove from cache)
      if (syncData.rooms?.leave) {
        Object.keys(syncData.rooms.leave).forEach(roomId => {
          roomsMap.delete(roomId)
        })
      }

      rooms.value = Array.from(roomsMap.values())

      // Update total unread count
      const totalCount = rooms.value.reduce((sum, r) => sum + r.unread_count, 0)
      const previousCount = totalUnreadCount.value
      totalUnreadCount.value = totalCount
      updateNativeBadge(totalCount)

      // Send WebSocket notification if count changed (to sync across tabs)
      if (totalCount !== previousCount) {
        try {
          await $fetch('/api/v1/matrix/notify-unread', {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${authStore.token}`
            },
            body: { count: totalCount }
          })
        } catch (err) {
          console.error('Failed to send WebSocket notification:', err)
        }
      }
    } catch (err) {
      console.error('Failed to fetch Matrix unread counts:', err)
    }
  }

  // Start Matrix sync loop with long-polling (instant updates)
  const startMatrixSync = async () => {
    if (isSyncing) return
    isSyncing = true

    const doSync = async () => {
      if (!isSyncing || !authStore.isAuthenticated) return

      try {
        // Filter to get notification_count, latest event, and fully_read markers
        const filter = {
          room: {
            include_leave: false,
            state: { lazy_load_members: true },
            timeline: { limit: 1 }, // Only need latest event for comparison
            ephemeral: { types: ['m.receipt'] }, // Include read receipts to trigger sync when user reads messages
            account_data: { types: ['m.fully_read'] } // Get fully_read markers for cross-device sync
          },
          presence: { types: [] }
        }

        const params = new URLSearchParams({
          timeout: '10000', // 10s long poll for faster updates
          filter: JSON.stringify(filter),
          ...(matrixSyncToken && { since: matrixSyncToken })
        })

        const response = await fetch(`https://parahub.io/_matrix/client/r0/sync?${params}`, {
          headers: {
            'Authorization': `Bearer ${matrixAccessToken}`
          }
        })

        if (!response.ok) {
          if (response.status === 401 || response.status === 403) {
            // Auth failed — token invalid/expired, stop syncing entirely
            console.warn('[useMatrixUnread] Matrix auth failed, stopping sync')
            isSyncing = false
            matrixAccessToken = null
            return
          }
          // Transient error — retry with exponential backoff
          syncRetryCount++
          if (syncRetryCount > MAX_SYNC_RETRIES) {
            console.warn('[useMatrixUnread] Max retries reached, stopping sync')
            isSyncing = false
            return
          }
          const delay = Math.min(5000 * Math.pow(2, syncRetryCount - 1), 60000)
          setTimeout(doSync, delay)
          return
        }

        const data = await response.json()
        syncRetryCount = 0 // Reset on success
        const isIncrementalSync = !!matrixSyncToken
        matrixSyncToken = data.next_batch

        // Mark first sync as completed (now we have fully_read markers)
        if (isIncrementalSync) {
          isFirstSyncCompleted.value = true
        }

        // Process unread counts from sync
        const roomsMap = new Map(rooms.value.map(r => [r.room_id, r]))

        // Process joined rooms (add/update)
        if (data.rooms?.join) {
          const updatedRooms = Object.entries(data.rooms.join).map(([roomId, roomData]: [string, any]) => ({
            room_id: roomId,
            unread_count: calculateRoomUnread(roomId, roomData, isIncrementalSync)
          }))

          updatedRooms.forEach(room => {
            roomsMap.set(room.room_id, room)
          })
        }

        // Process left rooms (remove from cache)
        if (data.rooms?.leave) {
          Object.keys(data.rooms.leave).forEach(roomId => {
            roomsMap.delete(roomId)
          })
        }

        rooms.value = Array.from(roomsMap.values())

        const totalCount = rooms.value.reduce((sum, r) => sum + r.unread_count, 0)
        const previousCount = totalUnreadCount.value
        totalUnreadCount.value = totalCount
        if (totalCount !== previousCount) updateNativeBadge(totalCount)

        // Send WebSocket notification if count changed (to sync across tabs)
        if (totalCount !== previousCount) {
          try {
            await $fetch('/api/v1/matrix/notify-unread', {
              method: 'POST',
              headers: {
                'Authorization': `Bearer ${authStore.token}`
              },
              body: { count: totalCount }
            })
          } catch (err) {
            console.error('[useMatrixUnread] Failed to send WebSocket notification:', err)
          }
        }

        // Continue syncing
        if (isSyncing) {
          setTimeout(doSync, 0)
        }
      } catch (err) {
        console.error('[useMatrixUnread] Matrix sync error:', err)
        syncRetryCount++
        if (isSyncing && syncRetryCount <= MAX_SYNC_RETRIES) {
          const delay = Math.min(5000 * Math.pow(2, syncRetryCount - 1), 60000)
          setTimeout(doSync, delay)
        } else if (syncRetryCount > MAX_SYNC_RETRIES) {
          console.warn('[useMatrixUnread] Max retries reached, stopping sync')
          isSyncing = false
        }
      }
    }

    doSync()
  }

  // Initialize the service
  const initialize = async () => {
    if (isInitialized.value) {
      return
    }

    if (!authStore.isAuthenticated) {
      return
    }

    isInitialized.value = true

    // Ensure JWT token is available before making Matrix API calls
    // (onMounted fires before init.client.ts app:mounted where ensureToken runs)
    await authStore.ensureToken()

    // Initial fetch to get Matrix token
    await fetchUnreadCounts()

    // If token acquisition failed, don't start sync loop
    if (!matrixAccessToken) {
      isInitialized.value = false
      return
    }

    // Register handler for matrix.unread_update events from global WebSocket
    // Global notifications handler will call this function
    if (typeof window !== 'undefined') {
      (window as any).__matrixUnreadHandler = (data: any) => {
        if (data.type === 'matrix.unread_update') {
          totalUnreadCount.value = data.count
          updateNativeBadge(data.count)
        }
      }
    }

    // Add visibility change listener for instant updates when tab becomes visible
    handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        fetchUnreadCounts()
      }
    }
    document.addEventListener('visibilitychange', handleVisibilityChange)

    // Start Matrix sync loop for instant updates (replaces polling)
    startMatrixSync()
  }

  // Cleanup
  const cleanup = () => {
    isSyncing = false
    if (syncInterval) {
      clearInterval(syncInterval)
      syncInterval = null
    }

    // Unregister global handler
    if (typeof window !== 'undefined') {
      delete (window as any).__matrixUnreadHandler
    }

    // Remove visibility change listener
    if (handleVisibilityChange) {
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      handleVisibilityChange = null
    }
    isInitialized.value = false
    isFirstSyncCompleted.value = false
    updateNativeBadge(0)
    matrixAccessToken = null
    matrixSyncToken = null
    syncRetryCount = 0
  }

  return {
    totalUnreadCount,
    isFirstSyncCompleted,
    initialize,
    cleanup,
    fetchUnreadCounts
  }
}
