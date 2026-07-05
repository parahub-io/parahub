// Sync locale from backend profile (client-only, non-blocking)
// Priority: 1) URL prefix (already handled by @nuxtjs/i18n), 2) profile preferred_language, 3) cookie
export default defineNuxtPlugin((nuxtApp) => {
  const i18n = nuxtApp.$i18n
  const authStore = useAuthStore()

  // If the URL already has a locale prefix (e.g. /pt/...), @nuxtjs/i18n sets locale from URL.
  // Only sync from profile if the current locale is the default (en) — meaning no URL prefix.
  // This prevents overriding explicit URL locale choices.
  const urlHasLocale = i18n.locale.value !== i18n.defaultLocale
  if (urlHasLocale) return

  // Strictly after hydration: ensureSession() sets authStore.user the moment
  // the response lands, and setLocale() rewrites rendered text. Fired at
  // plugin scope, either can land mid-hydration. On SWR-cached routes the
  // served shell is the anonymous cached render, so an early authed flip is a
  // guaranteed hydration mismatch (Vue's recovery has thrown insertBefore
  // errors on /about). ensureSession is single-flight and also fired by
  // init.client's app:mounted hook — this await shares that request.
  // preferred_language rides in the session payload, so no JWT mint or
  // /profiles/me/ round-trip is needed here.
  nuxtApp.hook('app:mounted', () => {
    authStore.ensureSession().then(() => {
      const lang = (authStore.user?.profile as any)?.preferred_language
      if (lang && lang !== i18n.locale.value) {
        i18n.setLocale(lang)
      }
    }).catch(() => {
      // Not authenticated or error — ignore
    })
  })
})
