export default defineNuxtRouteMiddleware(async (to, from) => {
  // Skip middleware during server-side rendering
  if (process.server) return

  const authStore = useAuthStore()
  const localePath = useLocalePath()

  // Check if user is authenticated
  if (!authStore.isAuthenticated) {
    // Reconcile from session (no storage)
    await authStore.ensureSession()

    // If still not authenticated after session check, redirect to about page
    if (!authStore.isAuthenticated) {
      const homePath = localePath('/')
      // Use external redirect to avoid layout overflow issues
      if (process.client) {
        window.location.replace(homePath)
        return abortNavigation()
      }
      return navigateTo(homePath, { replace: true })
    }
  }
})
