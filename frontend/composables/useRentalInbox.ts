/**
 * Shared state for the rental owner inbox.
 * Module-level ref so the Requests-tab badge on /market/my stays in sync
 * across navigations. `pendingCount` = REQUESTED bookings awaiting owner action.
 */
import { ref } from 'vue'
import { useAuthStore } from '~/stores/auth'

const pendingCount = ref(0)

export const useRentalInbox = () => {
  const authStore = useAuthStore()

  async function loadPendingCount() {
    if (!authStore.isAuthenticated) {
      pendingCount.value = 0
      return
    }
    try {
      await authStore.ensureToken()
      const res = await $fetch<{ count: number }>('/api/v1/rental/bookings/pending-count', {
        credentials: 'include',
        headers: { Authorization: `Bearer ${authStore.token}` },
      })
      pendingCount.value = res?.count || 0
    } catch {
      pendingCount.value = 0
    }
  }

  return { pendingCount, loadPendingCount }
}
