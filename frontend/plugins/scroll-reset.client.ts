// The app scrolls inside #main-content (layouts/default.vue), not the window,
// so vue-router's built-in scrollBehavior never touches it: navigating from a
// scrolled page opened the next page already scrolled down. This plugin gives
// the container browser-like scroll semantics:
//  - push/replace to a different path -> scroll to top (or the hash anchor)
//  - back/forward -> restore the position that history entry had
// Query-only navigations (filter/search sync via router.replace) keep scroll.
export default defineNuxtPlugin((nuxtApp) => {
  const router = useRouter()
  const saved = new Map<number, number>() // history entry position -> scrollTop
  let currentPos: number | null = window.history.state?.position ?? null
  let pending: { isPop: boolean; targetPos: number | null; pathChanged: boolean; hash: string } | null = null
  let raf = 0

  const container = () => document.getElementById('main-content')

  // Continuously record the current entry's scroll. Capture phase on document
  // survives layout/container remounts (scroll events don't bubble).
  document.addEventListener(
    'scroll',
    (e) => {
      if ((e.target as HTMLElement)?.id !== 'main-content' || raf) return
      raf = requestAnimationFrame(() => {
        raf = 0
        const el = container()
        if (el && currentPos !== null) saved.set(currentPos, el.scrollTop)
      })
    },
    { capture: true, passive: true },
  )

  router.beforeEach((to, from) => {
    // On back/forward the browser restores history.state before vue-router's
    // guards run, so a history position differing from the entry we are
    // viewing identifies a popstate navigation. (A window 'popstate' listener
    // is unreliable here: microtask checkpoints let router guards run between
    // popstate listeners, so a flag set by our listener would arrive late.)
    const posNow = window.history.state?.position ?? null
    pending = {
      isPop: posNow !== null && currentPos !== null && posNow !== currentPos,
      targetPos: posNow,
      pathChanged: to.path !== from.path,
      hash: to.hash,
    }
  })

  router.afterEach(() => {
    currentPos = window.history.state?.position ?? currentPos
  })

  // page:finish fires after the new page's suspense resolves (KeepAlive
  // activations included), so the target DOM is in place.
  nuxtApp.hook('page:finish', () => {
    const nav = pending
    pending = null
    if (!nav || !nav.pathChanged) return
    const el = container()
    if (!el) return
    if (nav.isPop) {
      const want = (nav.targetPos !== null && saved.get(nav.targetPos)) || 0
      el.scrollTop = want
      // A non-cached page may still be fetching data; retry once the content
      // is tall enough to hold the restored offset.
      if (want > 0 && el.scrollTop < want - 50) {
        setTimeout(() => {
          el.scrollTop = want
        }, 250)
      }
    } else {
      const anchor = nav.hash ? document.querySelector(nav.hash) : null
      if (anchor) anchor.scrollIntoView()
      else el.scrollTop = 0
    }
  })
})
