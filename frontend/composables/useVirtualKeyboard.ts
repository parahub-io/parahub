import { onMounted, onUnmounted } from 'vue'

/**
 * Flags an open virtual keyboard as a `kb-open` class on <html>, so CSS can
 * collapse the bottom navigation dock while the user types (see main.css
 * § Navigation dock insets).
 *
 * Measured off visualViewport rather than focus events on purpose: the chat
 * page types inside a cross-origin iframe, where the parent document sees no
 * focus at all, but the visual viewport shrinks either way.
 *
 * Browsers differ in what a keyboard does to the viewport (`resizes-visual`
 * vs `resizes-content`), and the URL bar collapsing shrinks it too — hence a
 * threshold well above URL-bar height and below any real keyboard. Comparing
 * against innerHeight (the layout viewport) rather than a remembered maximum
 * keeps it correct across orientation changes and split-screen resizes.
 */
const KEYBOARD_MIN_PX = 160

export function useVirtualKeyboard() {
  if (!import.meta.client) return

  let raf = 0

  function measure() {
    const vv = window.visualViewport
    if (!vv) return
    // Ignore pinch-zoom: it shrinks the visual viewport without a keyboard
    if (vv.scale > 1.05) return
    const hidden = window.innerHeight - vv.height - vv.offsetTop
    document.documentElement.classList.toggle('kb-open', hidden > KEYBOARD_MIN_PX)
  }

  function schedule() {
    if (raf) return
    raf = requestAnimationFrame(() => {
      raf = 0
      measure()
    })
  }

  onMounted(() => {
    const vv = window.visualViewport
    if (!vv) return
    vv.addEventListener('resize', schedule)
    vv.addEventListener('scroll', schedule)
    measure()
  })

  onUnmounted(() => {
    const vv = window.visualViewport
    if (vv) {
      vv.removeEventListener('resize', schedule)
      vv.removeEventListener('scroll', schedule)
    }
    if (raf) cancelAnimationFrame(raf)
    document.documentElement.classList.remove('kb-open')
  })
}
