import { ref, computed, type Ref } from 'vue'

export type SnapPoint = 'peek' | 'half' | 'full'

const SNAP_HEIGHTS: Record<SnapPoint, number> = {
  peek: 25,
  half: 50,
  full: 85
}

const VELOCITY_THRESHOLD = 0.5 // px/ms — fast swipe threshold
const DISMISS_THRESHOLD = 15 // vh — below this, dismiss

interface UseBottomSheetOptions {
  initialSnap?: SnapPoint
  onDismiss?: () => void
}

export function useBottomSheet(options: UseBottomSheetOptions = {}) {
  const snapPoint = ref<SnapPoint>(options.initialSnap || 'half')
  const isDragging = ref(false)
  const currentHeight = ref(SNAP_HEIGHTS[snapPoint.value])

  let startY = 0
  let startHeight = 0
  let startTime = 0
  let lastY = 0

  const sheetStyle = computed(() => ({
    height: `${currentHeight.value}vh`,
    maxHeight: '90vh',
    transition: isDragging.value ? 'none' : 'height 0.3s ease'
  }))

  function snapTo(point: SnapPoint) {
    snapPoint.value = point
    currentHeight.value = SNAP_HEIGHTS[point]
  }

  function onTouchStart(e: TouchEvent) {
    isDragging.value = true
    startY = e.touches[0].clientY
    lastY = startY
    startHeight = currentHeight.value
    startTime = Date.now()
  }

  function onTouchMove(e: TouchEvent) {
    if (!isDragging.value) return
    const currentY = e.touches[0].clientY
    const deltaY = startY - currentY // positive = drag up
    const deltaVh = (deltaY / window.innerHeight) * 100
    const newHeight = Math.max(5, Math.min(90, startHeight + deltaVh))
    currentHeight.value = newHeight
    lastY = currentY
  }

  function onTouchEnd(e: TouchEvent) {
    if (!isDragging.value) return
    isDragging.value = false

    const endY = e.changedTouches[0].clientY
    const elapsed = Date.now() - startTime
    const velocity = (startY - endY) / Math.max(elapsed, 1) // px/ms, positive = upward

    // Fast swipe detection
    if (Math.abs(velocity) > VELOCITY_THRESHOLD) {
      if (velocity > 0) {
        // Fast swipe up → full
        snapTo('full')
      } else {
        // Fast swipe down → dismiss or peek
        if (currentHeight.value < SNAP_HEIGHTS.half) {
          options.onDismiss?.()
        } else {
          snapTo('peek')
        }
      }
      return
    }

    // Slow drag — snap to nearest
    if (currentHeight.value < DISMISS_THRESHOLD) {
      options.onDismiss?.()
      return
    }

    const midPeekHalf = (SNAP_HEIGHTS.peek + SNAP_HEIGHTS.half) / 2
    const midHalfFull = (SNAP_HEIGHTS.half + SNAP_HEIGHTS.full) / 2

    if (currentHeight.value < midPeekHalf) {
      snapTo('peek')
    } else if (currentHeight.value < midHalfFull) {
      snapTo('half')
    } else {
      snapTo('full')
    }
  }

  const dragHandleAttrs = {
    onTouchstart: onTouchStart,
    onTouchmove: onTouchMove,
    onTouchend: onTouchEnd
  }

  return {
    sheetStyle,
    dragHandleAttrs,
    snapTo,
    snapPoint,
    isDragging
  }
}
