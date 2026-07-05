/**
 * Syncs a tab ref with a query param (default ?tab=) for bookmarkability.
 * Default tab produces a clean URL (no param). Pass `paramName` to run a second,
 * independent tab dimension on the same page (e.g. ?status= alongside ?tab=).
 */
export function useTabSync(validTabs: string[], defaultTab = validTabs[0], paramName = 'tab') {
  const route = useRoute()
  const router = useRouter()
  const fromQuery = () => {
    const raw = String(route.query[paramName])
    return validTabs.includes(raw) ? raw : defaultTab
  }
  const tab = ref(fromQuery())
  watch(tab, (t) => {
    const query = { ...route.query }
    if (t === defaultTab) delete query[paramName]
    else query[paramName] = t
    router.replace({ query })
  })
  // Re-sync from the URL on KeepAlive reactivation. All pages are KeepAlive-cached
  // (app.vue), so deep-linking to an already-cached page (e.g. market barter banner →
  // /market/my?tab=barter) reactivates it with a stale tab — setup, and thus the ref()
  // init above, does not re-run. onActivated fires on every re-entry (after the router
  // has updated route.query), so it is the right hook to reconcile tab ← URL.
  onActivated(() => {
    const next = fromQuery()
    if (next !== tab.value) tab.value = next
  })
  return tab
}
