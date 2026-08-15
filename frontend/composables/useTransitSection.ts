export type TransitSection = 'transit' | 'rides'

/**
 * Remembers which transit section (public transit vs shared rides) the user
 * opened last, so the top-nav button targets that section directly and swaps
 * its icon/label. Mode choice is sticky — a rides user reaches their tool in
 * one tap while the in-page section strip keeps switching one tap away.
 *
 * Cookie-backed so fresh SSR renders paint the right icon. State hydrates
 * from the payload and reconciles with the live cookie post-mount, because
 * SWR-cached routes serve a cookie-less shell (same pattern as the dev-mode
 * bar in AppNavigation.vue). The cookie is only written client-side — a
 * server-side write on an SWR route could leak Set-Cookie into the shared
 * cache.
 */
export function useTransitSection() {
  const cookie = useCookie<string | undefined>('transit_section', { maxAge: 60 * 60 * 24 * 365 })
  const fromCookie = (): TransitSection => (cookie.value === 'rides' ? 'rides' : 'transit')
  const section = useState<TransitSection>('transit-section', fromCookie)

  onMounted(() => {
    // Route-driven remember() may have already run during setup; it wrote the
    // cookie too, so re-reading the cookie here is always consistent.
    section.value = fromCookie()
  })

  function remember(next: TransitSection) {
    section.value = next
    if (import.meta.client) cookie.value = next
  }

  return { section, remember }
}
