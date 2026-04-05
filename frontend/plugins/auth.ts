export default defineNuxtPlugin(async (nuxtApp) => {
  const authStore = useAuthStore()

  // Skip if user already loaded
  if (authStore.user) return

  try {
    if (process.server) {
      // On server, forward the cookies from the incoming request
      const headers = useRequestHeaders(['cookie'])

      // Only proceed if we have cookies
      if (headers.cookie) {
        const sessionData = await $fetch('/api/v1/auth/session/', {
          headers,
          credentials: 'include',
          baseURL: 'http://127.0.0.1:8000' // Internal server URL
        })

        if (sessionData.authenticated && sessionData.user) {
          authStore.user = sessionData.user

          // Set activeProfile from session data (backend returns active profile from session)
          if (sessionData.user.profile) {
            authStore.activeProfile = {
              id: sessionData.user.profile.id,
              hna: sessionData.user.profile.hna,
              display_name: sessionData.user.profile.display_name,
              profile_type: sessionData.user.profile.profile_type,
              is_primary: sessionData.user.profile.is_primary,
              reputation_score: sessionData.user.profile.reputation_score || 0,
              is_verified_wot: sessionData.user.profile.is_verified_wot || false,
              can_manage: true
            }
          }
        }
        // If not authenticated, that's fine - no error
      }
    }
    // NOTE: Do not modify auth state on client here.
    // Client-side reconciliation is deferred to app:mounted in a client-only plugin.
  } catch (error) {
    // Log only unexpected errors
    console.error('Auth plugin error:', error)
  }
})