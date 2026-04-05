export const useDocNav = () => {
  const route = useRoute()
  const router = useRouter()
  const localePath = useLocalePath()

  const pages = [
    { path: '/docs/getting-started', titleKey: 'about.gettingStarted.title' },
    { path: '/docs/mission', titleKey: 'about.toc.mission' },
    { path: '/docs/features', titleKey: 'about.features.title' },
    { path: '/docs/wot', titleKey: 'about.wotSystem.title' },
    { path: '/docs/crypto', titleKey: 'about.cryptoProofs.title' },
    { path: '/docs/barter', titleKey: 'about.barterSystem.title' },
    { path: '/docs/governance', titleKey: 'about.governanceSystem.title' },
    { path: '/docs/ads', titleKey: 'about.adsSystem.title' },
    { path: '/docs/mesh', titleKey: 'about.meshSystem.title' },
    { path: '/docs/energy', titleKey: 'about.energySystem.title' },
    { path: '/docs/federation', titleKey: 'about.federationSystem.title' },
    { path: '/docs/transparency', titleKey: 'about.transparency.title' },
    { path: '/docs/condo', titleKey: 'about.condoSystem.title' },
    { path: '/docs/phub', titleKey: 'about.phubSystem.title' },
    { path: '/docs/tickets', titleKey: 'about.ticketsSystem.title' },
    { path: '/docs/transit-ops', titleKey: 'about.transitOps.title' },
    { path: '/docs/driver', titleKey: 'about.driverMode.title' },
    { path: '/docs/voice', titleKey: 'about.voiceChat.title' },
    { path: '/docs/conduct', titleKey: 'footer.code_of_conduct' },
    { path: '/docs/arbitration', titleKey: 'about.arbitration.title' },
    { path: '/docs/tech', titleKey: 'about.techStack.title' },
  ]

  // Match by route name (strips locale suffix automatically)
  const currentIndex = computed(() => {
    const routeName = route.name?.toString().replace(/___[a-z]{2}$/, '') || ''
    return pages.findIndex(p => {
      const expectedName = p.path.replace(/^\//, '').replace(/\//g, '-')
      return routeName === expectedName
    })
  })

  const prev = computed(() => currentIndex.value > 0 ? pages[currentIndex.value - 1] : null)
  const next = computed(() => currentIndex.value < pages.length - 1 ? pages[currentIndex.value + 1] : null)

  // Arrow left/right keyboard navigation for doc content pages
  if (import.meta.client) {
    const onKeydown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      if (e.key === 'ArrowLeft' && prev.value) {
        e.preventDefault()
        router.push(localePath(prev.value.path))
      } else if (e.key === 'ArrowRight' && next.value) {
        e.preventDefault()
        router.push(localePath(next.value.path))
      }
    }
    onMounted(() => window.addEventListener('keydown', onKeydown))
    onUnmounted(() => window.removeEventListener('keydown', onKeydown))
  }

  return { prev, next, pages, localePath }
}
