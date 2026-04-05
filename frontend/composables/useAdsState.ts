/**
 * Composable for sharing ads state across nested route pages.
 * Module-level refs persist across page navigations.
 */
import { ref, reactive } from 'vue'

// Feed items cache (used by feed list → detail page)
const feedItems = ref<any[]>([])
const feedViewedIds = reactive(new Set<string>())
const feedEarnedMap = reactive(new Map<string, number>())

// Shared wallet state (used by feed warning + settings)
const walletConfigured = ref(false)
const lnAddress = ref('')
const advertiserWalletConfigured = ref(false)
const walletProvider = ref('')
const profileLoaded = ref(false)
const feedCount = ref(0)

export const useAdsState = () => {
  const authStore = useAuthStore()

  async function loadAdsProfile() {
    try {
      await authStore.ensureToken()
      const profile = await $fetch<any>('/api/v1/ads/profile/', {
        credentials: 'include',
        headers: { 'Authorization': `Bearer ${authStore.token}` }
      })

      if (profile) {
        lnAddress.value = profile.ln_address || ''
        walletConfigured.value = !!profile.ln_address
        advertiserWalletConfigured.value = profile.has_wallet_config || false
        walletProvider.value = profile.wallet_provider || ''
        profileLoaded.value = true
      }
      return profile
    } catch (error) {
      console.error('Failed to load ads profile:', error)
      return null
    }
  }

  async function loadFeedCount() {
    try {
      await authStore.ensureToken()
      const res = await $fetch<{ count: number }>('/api/v1/ads/feed/count/', {
        credentials: 'include',
        headers: { 'Authorization': `Bearer ${authStore.token}` }
      })
      feedCount.value = res.count
    } catch {
      feedCount.value = 0
    }
  }

  async function loadHistory(pageNum = 1, q = '') {
    try {
      await authStore.ensureToken()
      const params: Record<string, any> = { page: pageNum }
      if (q) params.q = q
      const response = await $fetch<any>('/api/v1/ads/feed/history/', {
        credentials: 'include',
        headers: { 'Authorization': `Bearer ${authStore.token}` },
        params,
      })
      return {
        items: response.items || [],
        count: response.count || 0,
      }
    } catch (error) {
      console.error('Failed to load history:', error)
      return { items: [], count: 0 }
    }
  }

  return {
    walletConfigured,
    lnAddress,
    advertiserWalletConfigured,
    walletProvider,
    profileLoaded,
    feedCount,
    feedItems,
    feedViewedIds,
    feedEarnedMap,
    loadAdsProfile,
    loadFeedCount,
    loadHistory,
  }
}
