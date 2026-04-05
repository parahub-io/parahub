// Sync locale from backend profile (client-only, non-blocking)
// Priority: 1) URL prefix (already handled by @nuxtjs/i18n), 2) profile preferred_language, 3) cookie
export default defineNuxtPlugin((nuxtApp) => {
  const i18n = nuxtApp.$i18n
  const authStore = useAuthStore()

  // If the URL already has a locale prefix (e.g. /pt/...), @nuxtjs/i18n sets locale from URL.
  // Only sync from profile if the current locale is the default (en) — meaning no URL prefix.
  // This prevents overriding explicit URL locale choices.
  const urlHasLocale = i18n.locale.value !== i18n.defaultLocale

  authStore.ensureToken().then(() => {
    if (!authStore.token) return

    $fetch('/api/v1/profiles/me/', {
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    }).then((profile: any) => {
      if (profile?.preferred_language && profile.preferred_language !== i18n.locale.value) {
        // Only auto-switch if URL doesn't already specify a locale
        if (!urlHasLocale) {
          i18n.setLocale(profile.preferred_language)
        }
      }
    }).catch(() => {
      // Not authenticated or error — ignore
    })
  }).catch(() => {
    // Token error — ignore
  })
})
