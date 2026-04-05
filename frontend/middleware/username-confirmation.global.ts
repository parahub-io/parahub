/**
 * Global middleware to enforce username confirmation for new OAuth users.
 *
 * New users who sign in via Google OAuth must confirm/choose their username
 * before accessing any other part of the site.
 */
export default defineNuxtRouteMiddleware(async (to, from) => {
  // Skip during SSR
  if (process.server) return

  // Allow access to these routes without username confirmation
  // Use route name matching (locale suffix is stripped) to handle locale prefixes
  const allowedRouteNames = [
    'choose-username',
    'login',
    'logout',
    'about',
    'auth-callback',
    'legal-terms',
    'legal-privacy',
  ]

  const routeName = to.name?.toString().replace(/___[a-z]{2}$/, '') || ''
  if (allowedRouteNames.some(name => routeName === name || routeName.startsWith(name + '-'))) {
    return
  }

  const authStore = useAuthStore()

  // Only check for authenticated users
  if (!authStore.isAuthenticated) {
    return
  }

  // Check if user needs username confirmation
  if (authStore.needsUsernameConfirmation) {
    const localePath = useLocalePath()
    return navigateTo(localePath('/choose-username'), { replace: true })
  }
})
