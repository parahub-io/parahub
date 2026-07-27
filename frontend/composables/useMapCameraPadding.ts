/**
 * Camera padding for MapView's docked panels.
 *
 * A left-docked panel (feature/entity/browse/routing/urban) overlays the map,
 * so the camera's true center sits behind or right next to it — zoom buttons
 * and flyTo targets read as skewed to the user. This watcher keeps MapLibre's
 * viewport padding in sync with panel state (left 384px on desktop, bottom
 * 50vh for the mobile sheet — iot.getPanelPadding()), making every camera
 * operation center on the UNOBSCURED area.
 *
 * flush: 'sync' so the padding applies within the same click-dispatcher tick,
 * BEFORE the dispatcher's own flyTo runs (that fly also carries the padding
 * explicitly and simply cancels our ease mid-flight — same target).
 *
 * `paddingOffset` feeds the center reticle in MapView's template: the screen
 * offset of the effective (padded) camera center from the container center.
 */
import { computed, ref, watch } from 'vue'
import type { ComputedRef, Ref } from 'vue'

const ZERO_PADDING = { top: 0, bottom: 0, left: 0, right: 0 }

export function useMapCameraPadding(opts: {
  getMap: () => any
  panelOpen: ComputedRef<boolean> | Ref<boolean>
  getPanelPadding: () => any
}) {
  const { getMap, panelOpen, getPanelPadding } = opts

  const currentPadding = ref<{ top: number; bottom: number; left: number; right: number }>({ ...ZERO_PADDING })

  const apply = (open: boolean) => {
    const map = getMap()
    const target = (open ? getPanelPadding() : undefined) || { ...ZERO_PADDING }
    const prev = currentPadding.value
    if (target.top === prev.top && target.bottom === prev.bottom
      && target.left === prev.left && target.right === prev.right) return
    currentPadding.value = target
    if (!map) return
    map.easeTo({ padding: target, duration: 250 })
  }

  watch(panelOpen, (open) => apply(open), { flush: 'sync' })

  /** Screen offset (px) of the padded camera center from the container center. */
  const paddingOffset = computed(() => ({
    x: (currentPadding.value.left - currentPadding.value.right) / 2,
    y: (currentPadding.value.top - currentPadding.value.bottom) / 2,
  }))

  return { currentPadding, paddingOffset }
}
