import { computed, onMounted, onUnmounted, ref, type Ref } from 'vue'

/**
 * Touch-drag selection for AppNavigation (mobile only):
 *   press on any nav button → drag finger across buttons → release to activate
 *
 * Visual affordances (MUST NOT break):
 *   - button under finger highlights via isDragHovered() (yellow)
 *   - label bar at bottom of screen shows current target's label (yellow)
 *   - on release: a colored dot appears at the target, transitions to a
 *     vertical beam 100vh tall fading to opacity 0 over 300ms
 *   - light theme = red beam, dark theme = yellow
 *
 * Mouse events intentionally do nothing (early return in handleDragStart).
 */
export interface NavDragOptions {
  /** Reactive site-menu open state — drag opens it when starting/hovering menu button, closes it when hovering main-nav buttons */
  isSiteMenuOpen: Ref<boolean>
  /** Called on release when target is a path nav-item (usually: router.push + close menu) */
  onSelectPath: (path: string) => void
  /** Called on release when target is an action button (site-menu / logout / invite) */
  onSelectAction: (action: 'site-menu' | 'logout' | 'invite') => void
  /** Cancel any pending hover-open timer (hybrid device: touchstart fires after pointerenter:mouse) */
  cancelHoverOpen: () => void
  /** Path prefixes that belong to the dropdown grid — hovering these keeps the menu open */
  submenuPathPrefixes: string[]
  /** Resolves the bottom hover-label text from (path, action) — lets caller own i18n + profile-name lookups */
  resolveLabel: (path: string | null, action: string | null) => string | null
}

export function useNavDragSelect(opts: NavDragOptions) {
  const isDragging = ref(false)
  const dragStartTarget = ref<HTMLElement | null>(null)
  const currentHoverTarget = ref<HTMLElement | null>(null)
  const dragMoved = ref(false)
  const releaseAnimation = ref(false)
  const releaseTarget = ref<{ path: string | null; action: string | null; rect: DOMRect | null } | null>(null)
  const beamAnimating = ref(false)

  const beamColor = computed(() => {
    if (process.client) {
      const isDark = document.documentElement.classList.contains('dark')
      return isDark ? '#ffe216' : '#ff0000'
    }
    return '#ffe216'
  })

  const dragHoverLabel = computed(() => {
    if (!isDragging.value || !dragMoved.value || !currentHoverTarget.value) return null
    const path = currentHoverTarget.value.getAttribute('data-nav-path')
    const action = currentHoverTarget.value.getAttribute('data-nav-action')
    return opts.resolveLabel(path, action)
  })

  function getNavButton(element: HTMLElement | null): HTMLElement | null {
    if (!element) return null
    if (element.hasAttribute('data-nav-button')) return element
    return element.closest('[data-nav-button]') as HTMLElement | null
  }

  function handleDragStart(event: MouseEvent | TouchEvent) {
    // Touch only; mouse ignored
    if (event instanceof MouseEvent) return

    // Hybrid device: touchstart fires after pointerenter:mouse → cancel pending hover-open
    opts.cancelHoverOpen()

    const target = event.target as HTMLElement
    const navButton = getNavButton(target)
    if (!navButton) return

    // Don't preventDefault yet — let it behave as a normal tap if drag never happens
    isDragging.value = true
    dragMoved.value = false
    dragStartTarget.value = navButton
    currentHoverTarget.value = navButton
    // No menu open/close here — only when drag actually moves
  }

  function handleDragMove(event: MouseEvent | TouchEvent) {
    if (!isDragging.value) return

    // First move: commit to drag mode
    if (!dragMoved.value) {
      dragMoved.value = true
      event.preventDefault()
      const startAction = dragStartTarget.value?.getAttribute('data-nav-action')
      if (startAction === 'site-menu') {
        opts.isSiteMenuOpen.value = true
      }
    }

    event.preventDefault()

    let clientX: number, clientY: number
    if (event instanceof TouchEvent) {
      const touch = event.touches[0]
      clientX = touch.clientX
      clientY = touch.clientY
    } else {
      clientX = event.clientX
      clientY = event.clientY
    }

    const elementUnder = document.elementFromPoint(clientX, clientY) as HTMLElement
    const navButton = getNavButton(elementUnder)

    // Skip null gaps between buttons to prevent flicker
    if (navButton !== currentHoverTarget.value && navButton !== null) {
      currentHoverTarget.value = navButton

      const action = navButton.getAttribute('data-nav-action')
      const path = navButton.getAttribute('data-nav-path')

      if (action === 'site-menu') {
        opts.isSiteMenuOpen.value = true
      } else if (path) {
        const isSiteSubmenuItem = opts.submenuPathPrefixes.some(p => path.startsWith(p))
        if (!isSiteSubmenuItem) {
          // Main nav button → close dropdown
          opts.isSiteMenuOpen.value = false
        }
      }
    }
  }

  function handleDragEnd(event: MouseEvent | TouchEvent) {
    if (!isDragging.value) return

    if (dragMoved.value) {
      event.preventDefault()

      if (currentHoverTarget.value) {
        const path = currentHoverTarget.value.getAttribute('data-nav-path')
        const action = currentHoverTarget.value.getAttribute('data-nav-action')

        // Save rect BEFORE navigation — element may unmount after
        const rect = currentHoverTarget.value.getBoundingClientRect()
        releaseTarget.value = { path, action, rect }

        releaseAnimation.value = true
        beamAnimating.value = false // initial state: dot

        // Let the initial dot render one frame before starting the beam transition
        setTimeout(() => {
          beamAnimating.value = true
        }, 10)

        // Execute action immediately — don't wait for animation
        if (path) {
          opts.onSelectPath(path)
        } else if (action === 'site-menu' || action === 'logout' || action === 'invite') {
          opts.onSelectAction(action)
        }

        // Clear animation after 300ms
        setTimeout(() => {
          releaseAnimation.value = false
          releaseTarget.value = null
        }, 300)
      }
    }

    isDragging.value = false
    dragStartTarget.value = null
    currentHoverTarget.value = null
    dragMoved.value = false
  }

  function isDragHovered(buttonPath: string | null, buttonAction: string | null): boolean {
    if (!isDragging.value || !currentHoverTarget.value) return false
    const currentPath = currentHoverTarget.value.getAttribute('data-nav-path')
    const currentAction = currentHoverTarget.value.getAttribute('data-nav-action')
    return (!!buttonPath && currentPath === buttonPath) || (!!buttonAction && currentAction === buttonAction)
  }

  // Beam geometry (currently always vertical — kept as function in case horizontal mode returns)
  function getBeamPosition(): string {
    if (!releaseTarget.value?.rect) return 'top: 0; left: 0;'
    const rect = releaseTarget.value.rect
    // Vertical: starts from bottom-center of button, extends down
    return `top: ${rect.bottom + 40}px; left: ${rect.left + rect.width / 2}px;`
  }

  function getBeamStyle(): string {
    return `width: 2px; height: 100vh; opacity: 0; background-color: ${beamColor.value};`
  }

  onMounted(() => {
    if (process.client) {
      document.addEventListener('touchmove', handleDragMove, { passive: false })
      document.addEventListener('touchend', handleDragEnd)
      document.addEventListener('touchcancel', handleDragEnd)
    }
  })

  onUnmounted(() => {
    if (process.client) {
      document.removeEventListener('touchmove', handleDragMove)
      document.removeEventListener('touchend', handleDragEnd)
      document.removeEventListener('touchcancel', handleDragEnd)
    }
  })

  return {
    // state for template bindings
    isDragging,
    dragMoved,
    dragHoverLabel,
    releaseAnimation,
    releaseTarget,
    beamAnimating,
    beamColor,
    // handlers for template
    handleDragStart,
    isDragHovered,
    getBeamPosition,
    getBeamStyle,
  }
}
