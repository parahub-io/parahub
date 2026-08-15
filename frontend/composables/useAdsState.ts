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
// Claimable reward total behind the nav badge (sats across unviewed ads)
const feedRewardSats = ref(0)
// Bumped when a live (WS-driven) refetch raises the claimable total — the nav
// badge listens to this to play its one-shot ping. Initial page-load fetches
// don't bump it, so the badge only pings on genuinely new rewards.
const feedRewardPulse = ref(0)
const totalEarned = ref(0)

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
        totalEarned.value = profile.total_earned_sats || 0
        profileLoaded.value = true
      }
      return profile
    } catch (error) {
      console.error('Failed to load ads profile:', error)
      return null
    }
  }

  async function loadFeedCount(opts: { live?: boolean } = {}) {
    try {
      await authStore.ensureToken()
      const res = await $fetch<{ count: number; total_reward_sats: number }>('/api/v1/ads/feed/count/', {
        credentials: 'include',
        headers: { 'Authorization': `Bearer ${authStore.token}` }
      })
      const prevSats = feedRewardSats.value
      feedCount.value = res.count
      feedRewardSats.value = res.total_reward_sats || 0
      if (opts.live && feedRewardSats.value > prevSats) feedRewardPulse.value++
    } catch {
      feedCount.value = 0
      feedRewardSats.value = 0
    }
  }

  async function loadHistory(pageNum = 1, q = '') {
    try {
      await authStore.ensureToken()
      const { $i18n } = useNuxtApp() as any
      const params: Record<string, any> = { page: pageNum }
      if (q) params.q = q
      if ($i18n?.locale?.value) params.translate_to = $i18n.locale.value
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
    feedRewardSats,
    feedRewardPulse,
    totalEarned,
    feedItems,
    feedViewedIds,
    feedEarnedMap,
    loadAdsProfile,
    loadFeedCount,
    loadHistory,
  }
}
