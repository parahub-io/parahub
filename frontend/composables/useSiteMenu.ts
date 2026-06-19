import { onMounted, onUnmounted, ref, type Ref } from 'vue'

/**
 * Manages the site-menu dropdown in AppNavigation:
 *   - hover-open with 80ms delay (to let touchstart cancel it on hybrid devices)
 *   - hover-close with 200ms delay
 *   - click-outside and ESC to close
 *
 * Pass the container ref so click-outside knows what "outside" means.
 */
export function useSiteMenu(containerRef: Ref<HTMLElement | null>) {
  const isOpen = ref(false)
  let hoverOpenTimer: ReturnType<typeof setTimeout> | null = null
  let hoverCloseTimer: ReturnType<typeof setTimeout> | null = null
  let openedByHover = false

  function cancelHoverOpen() {
    if (hoverOpenTimer) {
      clearTimeout(hoverOpenTimer)
      hoverOpenTimer = null
    }
  }

  function handleHoverEnter(event: PointerEvent) {
    if (event.pointerType !== 'mouse') return
    if (hoverCloseTimer) {
      clearTimeout(hoverCloseTimer)
      hoverCloseTimer = null
    }
    cancelHoverOpen()
    hoverOpenTimer = setTimeout(() => {
      hoverOpenTimer = null
      openedByHover = true
      isOpen.value = true
    }, 80)
  }

  function handleHoverLeave(event: PointerEvent) {
    if (event.pointerType !== 'mouse') return
    cancelHoverOpen()
    if (!openedByHover) return
    if (hoverCloseTimer) clearTimeout(hoverCloseTimer)
    hoverCloseTimer = setTimeout(() => {
      isOpen.value = false
      openedByHover = false
      hoverCloseTimer = null
    }, 200)
  }

  function toggle() {
    isOpen.value = !isOpen.value
    openedByHover = false
  }

  function close() {
    isOpen.value = false
  }

  function handleClickOutside(event: MouseEvent) {
    if (containerRef.value && !containerRef.value.contains(event.target as Node)) {
      isOpen.value = false
    }
  }

  function handleKeyDown(event: KeyboardEvent) {
    if (event.key === 'Escape' && isOpen.value) {
      isOpen.value = false
    }
  }

  // Position (top/right) is computed once at open and is not reactive to layout
  // changes, so close on resize/orientation-change — reopening recomputes it fresh.
  function handleResize() {
    if (isOpen.value) isOpen.value = false
  }

  onMounted(() => {
    if (process.client) {
      document.addEventListener('click', handleClickOutside)
      document.addEventListener('keydown', handleKeyDown)
      window.addEventListener('resize', handleResize)
    }
  })

  onUnmounted(() => {
    if (process.client) {
      document.removeEventListener('click', handleClickOutside)
      document.removeEventListener('keydown', handleKeyDown)
      window.removeEventListener('resize', handleResize)
    }
  })

  return {
    isOpen,
    cancelHoverOpen,
    handleHoverEnter,
    handleHoverLeave,
    toggle,
    close,
  }
}
