/**
 * Factory for interactive map draw tools (measure / isochrone / droneReach /
 * urban / sunStudy).
 *
 * Owns the shared lifecycle of the "activate → cursor + map event handlers →
 * draw into own GeoJSON sources → deactivate cleans everything" family:
 * idempotent source+layer registration (style-reload safe), handler
 * attach/detach with module-level slots (cleanup survives composable
 * re-instantiation, matching the old per-tool module-level handler refs),
 * cursor + doubleClickZoom management, empty-all-sources clearVisualization.
 *
 * Tool-specific drawing state, GeoJSON builders and API calls stay in each
 * tool's composable; the factory only runs the lifecycle around them.
 *
 * stop() deactivates even when the map is already gone (map-touching steps
 * are skipped) — the old sunStudy semantics; the other tools used to silently
 * ignore stop() without a map, leaving a stale active=true.
 */

import { ref } from 'vue'

export const EMPTY_FC: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] }

export interface DrawToolSpec {
  /** Unique tag keying the module-level handler slot, e.g. 'measure' */
  tag: string
  /** GeoJSON source ids; created empty by setupLayers, emptied by clearVisualization */
  sources: string[]
  /** Layer definitions added in order after the sources (z-order = array order) */
  layers: any[]
  /** Map cursor while active; null = leave the cursor alone (sunStudy) */
  cursor?: string | null
  /** Disable double-click zoom while active (dblclick-to-finish tools) */
  disableDoubleClickZoom?: boolean
  /** Skip clearVisualization on start — for re-entrant tools that restyle a
   *  live visualization instead of restarting a drawing (sunStudy) */
  clearOnStart?: boolean
  /** Map events attached on start, detached on stop */
  events?: Record<string, (e: any) => void>
  /** Reset tool state / kick off side effects; runs after the start clear */
  onStart?: (map: any) => void
  /** Extra teardown on stop; runs last (map may be null) */
  onStop?: (map: any | null) => void
  /** Extra state reset whenever the visuals are cleared */
  onClear?: () => void
}

// Attached handler sets keyed by tool tag. Module-level so a re-instantiated
// composable (KeepAlive eviction + remount) can still detach the previous
// instance's handlers from the map they were attached to.
const _attached = new Map<string, { map: any; events: Record<string, (e: any) => void> }>()

function _detachTag(tag: string) {
  const rec = _attached.get(tag)
  if (!rec) return
  for (const [event, handler] of Object.entries(rec.events)) rec.map.off(event, handler)
  _attached.delete(tag)
}

export function createDrawTool(spec: DrawToolSpec) {
  const mapStore = useMapStore()

  const active = ref(false)

  /** Idempotent source+layer registration — called on map load AND after
   *  every style reload (setStyle wipes all sources/layers). */
  function setupLayers(map: any) {
    if (map.getSource(spec.sources[0])) return
    for (const source of spec.sources) {
      map.addSource(source, { type: 'geojson', data: EMPTY_FC })
    }
    for (const layer of spec.layers) map.addLayer(layer)
  }

  function clearVisualization() {
    const map = mapStore.mapInstance
    if (!map) return
    for (const source of spec.sources) {
      map.getSource(source)?.setData(EMPTY_FC)
    }
    spec.onClear?.()
  }

  function _attach(map: any) {
    if (!spec.events) return
    _detachTag(spec.tag) // idempotent: a re-entrant start re-attaches cleanly
    for (const [event, handler] of Object.entries(spec.events)) map.on(event, handler)
    _attached.set(spec.tag, { map, events: spec.events })
  }

  function start() {
    const map = mapStore.mapInstance
    if (!map) return
    active.value = true
    if (spec.clearOnStart !== false) clearVisualization()
    spec.onStart?.(map)
    if (spec.cursor !== null) map.getCanvas().style.cursor = spec.cursor ?? 'crosshair'
    if (spec.disableDoubleClickZoom) map.doubleClickZoom.disable()
    _attach(map)
  }

  function stop() {
    const map = mapStore.mapInstance
    active.value = false
    if (map) {
      if (spec.cursor !== null) map.getCanvas().style.cursor = ''
      if (spec.disableDoubleClickZoom) map.doubleClickZoom.enable()
    }
    _detachTag(spec.tag)
    clearVisualization()
    spec.onStop?.(map)
  }

  function toggle() {
    if (active.value) stop()
    else start()
  }

  return { active, setupLayers, clearVisualization, start, stop, toggle }
}
