/**
 * Syncs a tab ref with ?tab= query param for bookmarkability.
 * Default tab produces a clean URL (no ?tab= param).
 */
export function useTabSync(validTabs: string[], defaultTab = validTabs[0]) {
  const route = useRoute()
  const router = useRouter()
  const tab = ref(validTabs.includes(String(route.query.tab)) ? String(route.query.tab) : defaultTab)
  watch(tab, (t) => {
    const query = { ...route.query }
    if (t === defaultTab) delete query.tab
    else query.tab = t
    router.replace({ query })
  })
  return tab
}
