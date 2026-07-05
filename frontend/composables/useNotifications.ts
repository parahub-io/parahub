/**
 * In-app notification feed + unread badge.
 *
 * Module-level refs so the nav bell and the /notifications page share one
 * source of truth across navigations (mirrors useRentalInbox / useMatrixUnread).
 * `unreadCount` drives the bell badge; `items` backs the feed page. Live updates
 * arrive on the realtime `notification.new` event (the backend publishes to the
 * recipient's `user:{id}` channel from notifications.services.emit_notification).
 */
import { ref } from 'vue'
import { Capacitor } from '@capacitor/core'
import { useAuthStore } from '~/stores/auth'

export interface FeedNotification {
  id: string
  object_type?: string  // 'notification' (incoming) | 'activity' (your own action)
  type: string
  category: string
  title: string
  body: string
  url: string
  data: Record<string, any>
  read: boolean
  created_at: string | null
}

export type FeedSource = 'all' | 'incoming' | 'mine'

const unreadCount = ref(0)
const items = ref<FeedNotification[]>([])
// Two orthogonal axes the feed page drives; live events respect them so we
// never prepend an item into a view that wouldn't contain it. `activeSource` =
// which stream(s); `unreadOnly` = keep only unread. Defaults match the nav.
const activeSource = ref<FeedSource>('all')
const unreadOnly = ref(false)

let realtimeHandler: ((data: any) => void) | null = null
let activityHandler: ((data: any) => void) | null = null
let visibilityHandler: (() => void) | null = null

// Native app icon badge (Android/iOS) — same approach as useMatrixUnread.
const updateNativeBadge = async (count: number) => {
  if (!Capacitor.isNativePlatform()) return
  try {
    const { Badge } = await import('@capawesome/capacitor-badge')
    if (count > 0) await Badge.set({ count })
    else await Badge.clear()
  } catch { /* badge unsupported on this device */ }
}

export const useNotifications = () => {
  const authStore = useAuthStore()

  async function authHeaders(): Promise<Record<string, string>> {
    await authStore.ensureToken()
    return { Authorization: `Bearer ${authStore.token}` }
  }

  async function loadUnreadCount() {
    if (!authStore.isAuthenticated) {
      unreadCount.value = 0
      updateNativeBadge(0)
      return
    }
    try {
      const res = await $fetch<{ count: number }>('/api/v1/notifications/unread-count', {
        credentials: 'include',
        headers: await authHeaders(),
      })
      unreadCount.value = res?.count || 0
      updateNativeBadge(unreadCount.value)
    } catch { /* keep previous value on transient failure */ }
  }

  async function loadFeed(opts: { before?: string; category?: string; limit?: number; source?: FeedSource; unread?: boolean } = {}) {
    if (!authStore.isAuthenticated) {
      items.value = []
      return []
    }
    try {
      const q = new URLSearchParams()
      if (opts.limit) q.set('limit', String(opts.limit))
      if (opts.before) q.set('before', opts.before)
      if (opts.category) q.set('category', opts.category)
      if (opts.source) q.set('source', opts.source)
      if (opts.unread) q.set('unread', 'true')
      const res = await $fetch<FeedNotification[]>(`/api/v1/notifications/feed?${q.toString()}`, {
        credentials: 'include',
        headers: await authHeaders(),
      })
      if (opts.before) items.value = [...items.value, ...(res || [])]
      else items.value = res || []
      return res || []
    } catch {
      return []
    }
  }

  async function markRead(ids: string[]) {
    if (!ids.length) return
    // Optimistic: flip local state + badge before the round-trip.
    let dec = 0
    for (const n of items.value) {
      if (ids.includes(n.id) && !n.read) {
        n.read = true
        dec++
      }
    }
    unreadCount.value = Math.max(0, unreadCount.value - dec)
    updateNativeBadge(unreadCount.value)
    try {
      await $fetch('/api/v1/notifications/mark-read', {
        method: 'POST',
        credentials: 'include',
        headers: await authHeaders(),
        body: { ids },
      })
    } catch { /* reconciled on next loadUnreadCount */ }
  }

  async function markAllRead() {
    for (const n of items.value) n.read = true
    unreadCount.value = 0
    updateNativeBadge(0)
    try {
      await $fetch('/api/v1/notifications/mark-all-read', {
        method: 'POST',
        credentials: 'include',
        headers: await authHeaders(),
      })
    } catch { /* reconciled on next loadUnreadCount */ }
  }

  // Register the live handler + visibility refresh, then prime the count.
  // Idempotent: safe to call on every mount / auth change.
  function init() {
    if (!process.client) return
    if (!realtimeHandler) {
      const realtime = useRealtimeStore()
      realtimeHandler = (data: any) => {
        const n: FeedNotification | undefined = data?.notification
        if (!n) return
        // Badge + toast are global (an incoming event always alerts). Only
        // prepend to the visible list if the current view would contain it.
        if (activeSource.value !== 'mine' && !items.value.some(x => x.id === n.id)) {
          items.value = [n, ...items.value]
        }
        unreadCount.value += 1
        updateNativeBadge(unreadCount.value)
        try {
          useToastStore().info(n.body || '', n.title || '')
        } catch { /* toast store not ready */ }
      }
      realtime.on('notification.new', realtimeHandler)
    }
    if (!activityHandler) {
      const realtime = useRealtimeStore()
      activityHandler = (data: any) => {
        const a: FeedNotification | undefined = data?.activity
        if (!a) return
        // Your own action: live so it shows across devices (and surfaces a
        // foreign action you didn't make), but NEVER unread — no badge, no toast.
        // It belongs in the current view only when that view shows your own
        // actions ('all' or 'mine') and isn't filtered to unread-only.
        const unreadFilterOn = activeSource.value !== 'mine' && unreadOnly.value
        if (activeSource.value !== 'incoming' && !unreadFilterOn && !items.value.some(x => x.id === a.id)) {
          items.value = [a, ...items.value]
        }
      }
      realtime.on('activity.new', activityHandler)
    }
    if (!visibilityHandler) {
      visibilityHandler = () => {
        if (document.visibilityState === 'visible') loadUnreadCount()
      }
      document.addEventListener('visibilitychange', visibilityHandler)
    }
    loadUnreadCount()
  }

  function cleanup() {
    unreadCount.value = 0
    items.value = []
    if (realtimeHandler) {
      try { useRealtimeStore().off('notification.new', realtimeHandler) } catch { /* store gone */ }
      realtimeHandler = null
    }
    if (activityHandler) {
      try { useRealtimeStore().off('activity.new', activityHandler) } catch { /* store gone */ }
      activityHandler = null
    }
    if (visibilityHandler) {
      document.removeEventListener('visibilitychange', visibilityHandler)
      visibilityHandler = null
    }
    updateNativeBadge(0)
  }

  return { unreadCount, items, activeSource, unreadOnly, loadUnreadCount, loadFeed, markRead, markAllRead, init, cleanup }
}
