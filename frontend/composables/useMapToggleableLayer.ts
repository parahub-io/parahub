/**
 * Factory for simple toggleable point-data map layers.
 *
 * Owns the shared lifecycle of the "fetch once → GeoJSON source → icon +
 * label symbol layers → visibility toggle" family (church / government /
 * condo / hub / mesh): lazy first load on enable, setData on repeat setup,
 * idempotent re-add after style reloads (setupLayersOnly), optional periodic
 * refresh with KeepAlive pause/resume, optional hover-hex highlight.
 *
 * Feature CLICKS are not handled here — they stay in MapView's global click
 * handler (queryRenderedFeatures per layer id), which owns panel exclusivity.
 */

import { ref } from 'vue'
import { attachHoverHex } from '~/composables/useMapHighlight'

export interface ToggleableLayerSpec {
  /** Tag for console warnings, e.g. 'ChurchLayer' */
  tag: string
  /** useLocalPref key persisting the toggle */
  prefKey: string
  defaultEnabled?: boolean
  /** GeoJSON source id */
  source: string
  iconLayerId: string
  labelLayerId: string
  /** Fetch the raw item list (thrown errors are caught + warned here) */
  fetchItems: () => Promise<any[]>
  /** Map one item to a GeoJSON Feature; return null to skip it */
  toFeature: (item: any) => any | null
  /** Register canvas icons on the map; painters must be hasImage-guarded */
  ensureIcons: (map: any) => void
  /** icon-image layout value (image name or match/case expression) */
  iconImage: any
  iconMinzoom?: number
  labelMinzoom?: number
  labelTextSize?: number
  /** Re-fetch + setData every N ms while enabled (mesh) */
  refreshMs?: number
  /** Attach hover-hex highlight to the icon layer */
  hoverHex?: boolean
}

/** Shared rounded-square icon background used by the canvas painters. */
export function roundedSquarePath(ctx: CanvasRenderingContext2D, s: number, pad: number, cr = 6) {
  ctx.beginPath()
  ctx.moveTo(pad + cr, pad)
  ctx.lineTo(s - pad - cr, pad)
  ctx.quadraticCurveTo(s - pad, pad, s - pad, pad + cr)
  ctx.lineTo(s - pad, s - pad - cr)
  ctx.quadraticCurveTo(s - pad, s - pad, s - pad - cr, s - pad)
  ctx.lineTo(pad + cr, s - pad)
  ctx.quadraticCurveTo(pad, s - pad, pad, s - pad - cr)
  ctx.lineTo(pad, pad + cr)
  ctx.quadraticCurveTo(pad, pad, pad + cr, pad)
  ctx.closePath()
}

export function createToggleableDataLayer(spec: ToggleableLayerSpec) {
  const mapStore = useMapStore()

  const enabled = useLocalPref(spec.prefKey, spec.defaultEnabled ?? false)
  const list = ref<any[]>([])
  let loaded = false
  let refreshTimer: ReturnType<typeof setInterval> | null = null

  const load = async (): Promise<any[]> => {
    try {
      const data = await spec.fetchItems()
      list.value = data || []
      return list.value
    } catch (e) {
      console.warn(`[${spec.tag}] Failed to fetch:`, e)
      return []
    }
  }

  const buildGeoJSON = (items: any[]) => ({
    type: 'FeatureCollection' as const,
    features: items.map(spec.toFeature).filter(Boolean),
  })

  const iconLayerDef = (vis: string) => ({
    id: spec.iconLayerId,
    type: 'symbol',
    source: spec.source,
    ...(spec.iconMinzoom != null ? { minzoom: spec.iconMinzoom } : {}),
    layout: {
      'icon-image': spec.iconImage,
      'icon-allow-overlap': true,
      visibility: vis,
    },
  })

  const labelLayerDef = (vis: string) => ({
    id: spec.labelLayerId,
    type: 'symbol',
    source: spec.source,
    ...(spec.labelMinzoom != null ? { minzoom: spec.labelMinzoom } : {}),
    layout: {
      'text-field': ['get', 'name'],
      'text-size': spec.labelTextSize ?? 11,
      'text-offset': [0, 1.5],
      'text-anchor': 'top',
      'text-optional': true,
      visibility: vis,
    },
    paint: {
      'text-color': '#374151',
      'text-halo-color': '#ffffff',
      'text-halo-width': 1.5,
    },
  })

  const addLayers = async (map: any) => {
    const items = await load()
    loaded = true

    const geojson = buildGeoJSON(items)
    if (map.getSource(spec.source)) {
      ;(map.getSource(spec.source) as any).setData(geojson)
      return
    }

    spec.ensureIcons(map)
    map.addSource(spec.source, { type: 'geojson', data: geojson })

    const vis = enabled.value ? 'visible' : 'none'
    map.addLayer(iconLayerDef(vis))
    map.addLayer(labelLayerDef(vis))
    if (spec.hoverHex) attachHoverHex(map, spec.iconLayerId)
  }

  const refresh = async () => {
    const map = mapStore.mapInstance
    if (!map || !map.getSource(spec.source)) return
    const items = await load()
    ;(map.getSource(spec.source) as any).setData(buildGeoJSON(items))
  }

  const startRefresh = () => {
    if (!spec.refreshMs || refreshTimer) return
    refreshTimer = setInterval(refresh, spec.refreshMs)
  }

  const stopRefresh = () => {
    if (refreshTimer) {
      clearInterval(refreshTimer)
      refreshTimer = null
    }
  }

  /** Initial setup on map load. onReady fires after the async first load. */
  const setupLayers = (map: any, onReady?: () => void) => {
    if (enabled.value) {
      addLayers(map).then(() => onReady?.())
      startRefresh()
    }
  }

  /** Re-add source/layers after a style reload (no data refetch). */
  const setupLayersOnly = (map: any) => {
    if (!loaded || list.value.length === 0) return
    const geojson = buildGeoJSON(list.value)

    spec.ensureIcons(map)
    if (!map.getSource(spec.source)) {
      map.addSource(spec.source, { type: 'geojson', data: geojson })
    }

    const vis = enabled.value ? 'visible' : 'none'
    if (!map.getLayer(spec.iconLayerId)) map.addLayer(iconLayerDef(vis))
    if (!map.getLayer(spec.labelLayerId)) map.addLayer(labelLayerDef(vis))
    if (spec.hoverHex) attachHoverHex(map, spec.iconLayerId)
  }

  const toggle = () => {
    enabled.value = !enabled.value
    const map = mapStore.mapInstance
    if (!map) return

    if (enabled.value && !loaded) {
      addLayers(map)
      startRefresh()
      return
    }

    const vis = enabled.value ? 'visible' : 'none'
    for (const id of [spec.iconLayerId, spec.labelLayerId]) {
      if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', vis)
    }

    if (enabled.value) startRefresh()
    else stopRefresh()
  }

  /** KeepAlive deactivate hook — stop polling while the map page is cached. */
  const pauseRefresh = () => {
    stopRefresh()
  }

  /** KeepAlive activate hook — resume polling + refresh immediately. */
  const resumeRefresh = () => {
    if (spec.refreshMs && enabled.value && !refreshTimer) {
      startRefresh()
      refresh()
    }
  }

  return {
    enabled,
    list,
    setupLayers,
    setupLayersOnly,
    toggle,
    pauseRefresh,
    resumeRefresh,
  }
}
