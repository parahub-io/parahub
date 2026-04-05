/**
 * Syncs UI preferences between localStorage (fast, reactive) and backend profile.
 *
 * Server-synced keys: preferred_currency, animation_enabled, map_style
 * Client-only keys: opensky_mode, map_presence_enabled, opensky_enabled, transit_enabled, etc.
 *
 * On login/page load: server values overwrite localStorage.
 * On change: localStorage updates instantly, PATCH debounced to backend.
 */

const SYNCED_KEYS = ['preferred_currency', 'animation_enabled', 'map_style'] as const
type SyncedKey = typeof SYNCED_KEYS[number]

let patchTimer: ReturnType<typeof setTimeout> | null = null
let pendingPatch: Partial<Record<SyncedKey, any>> = {}

/**
 * Called after fetchUser() — writes server preferences into localStorage.
 */
export function syncPreferencesFromProfile(profile: Record<string, any>) {
  if (!import.meta.client) return

  for (const key of SYNCED_KEYS) {
    if (key in profile && profile[key] !== undefined) {
      localStorage.setItem(key, JSON.stringify(profile[key]))
    }
  }
}

/**
 * Called when a synced preference changes — debounced PATCH to backend.
 */
export function savePrefToBackend(key: SyncedKey, value: any) {
  if (!import.meta.client) return

  pendingPatch[key] = value

  if (patchTimer) clearTimeout(patchTimer)
  patchTimer = setTimeout(async () => {
    const body = { ...pendingPatch }
    pendingPatch = {}

    try {
      const { useAuthStore } = await import('~/stores/auth')
      const authStore = useAuthStore()
      if (!authStore.isAuthenticated) return

      await authStore.ensureToken()
      if (!authStore.token) return

      await $fetch('/api/v1/profiles/me/preferences/', {
        method: 'PATCH',
        credentials: 'include',
        headers: {
          'Authorization': `Bearer ${authStore.token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(body)
      })
    } catch (e) {
      console.warn('[prefs-sync] Failed to save preferences to backend:', e)
    }
  }, 1000)
}
