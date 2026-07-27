/**
 * Webmail INBOX unseen counter for the nav menu badge.
 *
 * Module-level ref so the menu tile badge and the menu-button bubble share one
 * source of truth (mirrors useNotifications). No realtime channel: the backend
 * itself only learns the count by polling IMAP (no push from Dovecot), so we
 * refresh lazily — on nav mount and each time the site menu opens; the server
 * caches the count for 60s per account.
 */
import { ref } from 'vue'
import { useAuthStore } from '~/stores/auth'

const unseenCount = ref(0)
// Flips false on the first "no mailbox" response so we stop asking for the session
let hasMailbox = true
let inflight = false

export const useMailUnread = () => {
  const authStore = useAuthStore()

  async function refresh() {
    if (!authStore.isAuthenticated || !hasMailbox || inflight) return
    inflight = true
    try {
      await authStore.ensureToken()
      const data = await $fetch<{ has_mailbox: boolean, unseen: number | null }>(
        '/api/v1/profiles/me/mail-unread/',
        {
          credentials: 'include',
          headers: { Authorization: `Bearer ${authStore.token}` },
        },
      )
      if (!data.has_mailbox) {
        hasMailbox = false
        unseenCount.value = 0
      } else if (typeof data.unseen === 'number') {
        unseenCount.value = data.unseen
      }
      // unseen === null with a mailbox → transient IMAP hiccup, keep last known value
    } catch {
      // Network/auth hiccup — keep last known value
    } finally {
      inflight = false
    }
  }

  function reset() {
    unseenCount.value = 0
    hasMailbox = true
  }

  return { unseenCount, refresh, reset }
}
