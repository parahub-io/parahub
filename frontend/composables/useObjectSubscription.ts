/**
 * Composables for auto-subscribing to real-time object updates via WebSocket.
 *
 * useObjectSubscription(data)     — single object, merges changes into ref
 * useObjectListSubscription(list) — list of objects, merges changes by id
 */
import { watch, onMounted, onUnmounted, type Ref } from 'vue'

interface HasId {
  id: string
  [key: string]: any
}

/**
 * Subscribe to real-time updates for a single object.
 * Automatically merges incoming field changes into the reactive ref.
 *
 * @param data - Ref to the object (must have .id)
 */
export function useObjectSubscription<T extends HasId>(data: Ref<T | null>) {
  const realtimeStore = useRealtimeStore()
  const authStore = useAuthStore()

  let currentId: string | null = null

  function handler(event: any) {
    if (!data.value || event.id !== data.value.id) return
    // Merge only the fields present in changes
    Object.assign(data.value, event.changes)
  }

  function sub(id: string) {
    if (!id || id === currentId) return
    if (currentId) {
      realtimeStore.unsubscribe([currentId])
    }
    realtimeStore.subscribe([id])
    currentId = id
  }

  function unsub() {
    if (currentId) {
      realtimeStore.unsubscribe([currentId])
      currentId = null
    }
  }

  // Watch for id changes (e.g. navigating between items)
  watch(
    () => data.value?.id,
    (newId, oldId) => {
      if (newId && newId !== oldId) {
        sub(newId)
      } else if (!newId && oldId) {
        unsub()
      }
    },
  )

  onMounted(() => {
    if (!authStore.isAuthenticated) return
    realtimeStore.connect()
    realtimeStore.on('object.updated', handler)
    if (data.value?.id) {
      sub(data.value.id)
    }
  })

  onUnmounted(() => {
    realtimeStore.off('object.updated', handler)
    unsub()
  })
}

/**
 * Subscribe to real-time updates for a list of objects.
 * Automatically diffs ids on list changes (add new, remove gone).
 *
 * @param list - Ref to the array of objects (each must have .id)
 */
export function useObjectListSubscription<T extends HasId>(list: Ref<T[]>) {
  const realtimeStore = useRealtimeStore()
  const authStore = useAuthStore()

  let subscribedIds = new Set<string>()

  function handler(event: any) {
    const items = list.value
    if (!items) return
    const idx = items.findIndex((item) => item.id === event.id)
    if (idx !== -1) {
      Object.assign(items[idx], event.changes)
    }
  }

  function syncSubscriptions(newIds: Set<string>) {
    const toAdd = [...newIds].filter((id) => !subscribedIds.has(id))
    const toRemove = [...subscribedIds].filter((id) => !newIds.has(id))

    if (toRemove.length) realtimeStore.unsubscribe(toRemove)
    if (toAdd.length) realtimeStore.subscribe(toAdd)

    subscribedIds = new Set(newIds)
  }

  // Watch for list changes (items added/removed)
  watch(
    () => list.value.map((item) => item.id).join(','),
    () => {
      const ids = new Set(list.value.map((item) => item.id))
      syncSubscriptions(ids)
    },
  )

  onMounted(() => {
    if (!authStore.isAuthenticated) return
    realtimeStore.connect()
    realtimeStore.on('object.updated', handler)
    if (list.value.length) {
      const ids = new Set(list.value.map((item) => item.id))
      syncSubscriptions(ids)
    }
  })

  onUnmounted(() => {
    realtimeStore.off('object.updated', handler)
    if (subscribedIds.size) {
      realtimeStore.unsubscribe([...subscribedIds])
      subscribedIds.clear()
    }
  })
}
