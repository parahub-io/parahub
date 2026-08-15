/**
 * Partners of the ACTIVE profile, cached for the surfaces that need "the people
 * I deal with" in one tap: the site-menu strip and the wallet's send modal.
 *
 * Backed by `GET /api/v1/profiles/search/?only_partners=true` — the platform's
 * one picker backend. It hides synthetic profiles, honours blocks, gates
 * display_name behind name_visible_to, and already carries avatar_url,
 * is_partner and the payment addresses, so no surface has to join anything.
 *
 * Partners are per-profile: switching the active profile changes the answer, so
 * the cache is keyed by profile id and re-fetched when that key stops matching.
 * A partner added or removed elsewhere arrives over WS and only invalidates —
 * the next surface that opens pays for the refetch.
 */
import { useAuthStore } from '~/stores/auth'

export interface QuickPartner {
  id: string
  hna: string
  display_name: string
  avatar_url: string | null
  is_verified_wot: boolean
  is_partner: boolean
  ln_address: string | null
  spark_address: string | null
}

// A list this small is cheap to refetch; the window only collapses the burst of
// opens/closes in one sitting.
const FRESH_MS = 60_000
const PAGE_SIZE = 8

// One WS subscription per client, not one per composable call (each call would
// register a fresh closure and the Set would keep them all)
let wsBound = false

export const usePartnersQuickList = () => {
  const authStore = useAuthStore()

  const items = useState<QuickPartner[]>('partners-quick-items', () => [])
  const count = useState<number>('partners-quick-count', () => 0)
  const loading = useState<boolean>('partners-quick-loading', () => false)
  const loadedForProfileId = useState<string | null>('partners-quick-profile', () => null)
  const loadedAt = useState<number>('partners-quick-at', () => 0)

  const activeProfileId = () => authStore.activeProfile?.id || authStore.user?.profile?.id || null

  function invalidate() {
    loadedAt.value = 0
  }

  if (import.meta.client && !wsBound) {
    wsBound = true
    const realtimeStore = useRealtimeStore()
    realtimeStore.on('partner.added', invalidate)
    realtimeStore.on('partner.removed', invalidate)
  }

  async function fetch() {
    if (!authStore.isAuthenticated || loading.value) return
    const profileId = activeProfileId()
    const fresh = loadedForProfileId.value === profileId && Date.now() - loadedAt.value < FRESH_MS
    if (fresh) return

    loading.value = true
    try {
      await authStore.ensureToken()
      const data = await $fetch<{ items: QuickPartner[]; count: number }>(
        `/api/v1/profiles/search/?only_partners=true&page_size=${PAGE_SIZE}`,
        {
          credentials: 'include',
          headers: { Authorization: `Bearer ${authStore.token}` },
        },
      )
      items.value = data.items || []
      count.value = data.count || 0
      loadedForProfileId.value = profileId
      loadedAt.value = Date.now()
    } catch {
      // Keep the last known list — a stale strip beats an empty one
    } finally {
      loading.value = false
    }
  }

  return { items, count, loading, fetch, invalidate }
}
