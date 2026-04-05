/**
 * Global gamepad defaults — scroll, focus, nav, back.
 * Registered at lowest priority; page components override via useGamepad().
 */
export default defineNuxtPlugin((nuxtApp) => {
  nuxtApp.hook('app:mounted', () => {
    const { onButton, onAxis, _manager } = useGamepad()
    const router = useRouter()

    const B = {
      A: 0, B: 1, LB: 4, RB: 5, LT: 6, RT: 7,
      START: 9,
      DPAD_UP: 12, DPAD_DOWN: 13, DPAD_LEFT: 14, DPAD_RIGHT: 15,
    }

    // ── Input mode detection ──
    _manager.onAnyInput = () => {
      document.body.setAttribute('data-gamepad-active', '')
    }

    function clearGamepadMode() {
      document.body.removeAttribute('data-gamepad-active')
    }
    window.addEventListener('mousemove', clearGamepadMode, { passive: true })
    window.addEventListener('mousedown', clearGamepadMode, { passive: true })
    window.addEventListener('keydown', clearGamepadMode, { passive: true })

    // ── Helpers ──

    function getScrollContainer(): HTMLElement {
      return document.getElementById('main-content') || document.documentElement
    }

    function scrollBy(px: number) {
      getScrollContainer().scrollBy({ top: px, behavior: 'smooth' })
    }

    function moveFocus(direction: number) {
      const focusable = Array.from(document.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
      )).filter(el => {
        if (el.offsetParent === null && el.style.position !== 'fixed') return false
        return el.getBoundingClientRect().width > 0
      })

      if (focusable.length === 0) return

      const active = document.activeElement as HTMLElement
      const idx = focusable.indexOf(active)
      let next: number

      if (idx === -1) {
        next = direction > 0 ? 0 : focusable.length - 1
      } else {
        next = (idx + direction + focusable.length) % focusable.length
      }

      focusable[next].focus()
      focusable[next].scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    }

    function cycleNavButton(direction: number) {
      const buttons = Array.from(document.querySelectorAll<HTMLElement>('[data-nav-button]'))
      if (buttons.length === 0) return

      const active = document.activeElement as HTMLElement
      const idx = buttons.indexOf(active)
      let next: number

      if (idx === -1) {
        // Find currently active nav button
        const current = buttons.findIndex(b => b.classList.contains('active') || b.getAttribute('aria-current') === 'page')
        next = current === -1 ? 0 : (current + direction + buttons.length) % buttons.length
      } else {
        next = (idx + direction + buttons.length) % buttons.length
      }

      buttons[next].focus()
      buttons[next].click()
    }

    // ── Default button bindings ──

    // D-pad Up/Down — stepped scroll
    onButton(B.DPAD_UP, () => { scrollBy(-80) })
    onButton(B.DPAD_DOWN, () => { scrollBy(80) })

    // D-pad Left/Right — linear focus movement
    onButton(B.DPAD_LEFT, () => { moveFocus(-1) })
    onButton(B.DPAD_RIGHT, () => { moveFocus(1) })

    // A — click active element
    onButton(B.A, () => {
      const el = document.activeElement as HTMLElement
      if (el && el !== document.body) {
        el.click()
      }
    })

    // B — back
    onButton(B.B, () => { router.back() })

    // LB/RB — cycle nav buttons
    onButton(B.LB, () => { cycleNavButton(-1) })
    onButton(B.RB, () => { cycleNavButton(1) })

    // LT/RT — page up/down (80% viewport)
    onButton(B.LT, () => { scrollBy(-window.innerHeight * 0.8) })
    onButton(B.RT, () => { scrollBy(window.innerHeight * 0.8) })

    // Start — home
    const localePath = useLocalePath()
    onButton(B.START, () => { router.push(localePath('/')) })

    // ── Left stick Y axis (axis 1) — smooth scroll ──
    onAxis(1, (value: number) => {
      getScrollContainer().scrollBy({ top: Math.round(value * 12) })
    })
  })
})
