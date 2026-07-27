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
import {
  setEnsembleSegment, ensemblePlacement, onEnsembleChange, ENSEMBLE_ICON_SCALE,
  type EnsembleMemberInput, type EnsemblePlacement,
} from '~/composables/useMapDeviceEnsembles'
import type { DeviceHudView } from '~/utils/envHudMarker'

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
  /**
   * Join the co-located device ensemble layout (useMapDeviceEnsembles.ts):
   * members publish on every data/visibility change, features gain
   * iconOffset / ensemble-scale / label-flip properties, and hudView items
   * get an instrument-readout DOM marker (which replaces the GL name label).
   */
  ensemble?: {
    segment: string
    /** Map one item to an ensemble member; null = not a member */
    toMember: (item: any) => EnsembleMemberInput | null
    /** Readout content for an item; null = no HUD (name label stays) */
    hudView?: (item: any, placement: EnsemblePlacement | undefined) =>
      Pick<DeviceHudView, 'primary' | 'rows' | 'windDir' | 'stale'> | null
  }
}

// ── Marker grammar tokens (PK/design-system.md § Map Markers) ──
// Shape = entity class: flat-top hexagon → live device, rounded square → static
// place. Fill = status/data. Glyph = device type (auto-contrast). One 1px dark
// rest stroke on every marker (legibility on satellite/dark basemaps).
export const MARKER_STROKE_COLOR = '#1f2937'
export const MARKER_STROKE_WIDTH = 1 // px at 1x
export const DEVICE_HEX_SIZE = 22 // px at 1x
export const PLACE_SQUARE_SIZE = 20 // px at 1x

// Device-type glyphs — lucide 24×24 path data (keep in sync with the
// lucide-vue-next icons of the same name), drawn via drawLucideGlyph.
export const ZAP_GLYPH = ['M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z']
export const LEAF_GLYPH = ['M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z', 'M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12']
export const WIND_GLYPH = ['M12.8 19.6A2 2 0 1 0 14 16H2', 'M17.5 8a2.5 2.5 0 1 1 2 4H2', 'M9.8 4.4A2 2 0 1 1 11 8H2']
export const NAVIGATION_GLYPH = ['M3 11L22 2L13 21L11 13Z']
// Static device layers (env stations, mesh routers, energy cells) appear from
// this zoom — device hexes are noise at regional/country scale. Labels follow
// at DEVICE_LABEL_MINZOOM; HUD readout columns later still (ENV_HUD_MINZOOM=12).
export const DEVICE_MINZOOM = 9
export const DEVICE_LABEL_MINZOOM = 11

/** Flat-top hexagon path inscribed in an s×s canvas (inset keeps stroke inside). */
export function hexagonPath(ctx: CanvasRenderingContext2D, s: number, inset = 3) {
  const r = s / 2
  ctx.beginPath()
  for (let i = 0; i < 6; i++) {
    const angle = (Math.PI / 3) * i
    const x = r + (r - inset) * Math.cos(angle)
    const y = r + (r - inset) * Math.sin(angle)
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
  }
  ctx.closePath()
}

/** Stroke the current path with the unified marker outline (canvases are 2x). */
export function strokeMarkerOutline(ctx: CanvasRenderingContext2D) {
  ctx.lineWidth = MARKER_STROKE_WIDTH * 2
  ctx.strokeStyle = MARKER_STROKE_COLOR
  ctx.stroke()
}

/** Dark glyph on light fills, white on dark — relative-luminance cut at 0.55. */
export function glyphColorFor(fill: string): string {
  const h = fill.replace('#', '')
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255)
  return (0.2126 * r + 0.7152 * g + 0.0722 * b) > 0.55 ? MARKER_STROKE_COLOR : '#ffffff'
}

/** Draw lucide 24×24 stroke paths centered on an s×s canvas, scaled to glyphBox px. */
export function drawLucideGlyph(
  ctx: CanvasRenderingContext2D, s: number, paths: string[], glyphBox: number, color: string,
) {
  ctx.save()
  const scale = glyphBox / 24
  ctx.translate((s - glyphBox) / 2, (s - glyphBox) / 2)
  ctx.scale(scale, scale)
  ctx.strokeStyle = color
  ctx.lineWidth = 2.4
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'
  for (const d of paths) ctx.stroke(new Path2D(d))
  ctx.restore()
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

  /** Publish this layer's ensemble members (empty when toggled off). */
  const publishMembers = () => {
    if (!spec.ensemble) return
    const members = enabled.value
      ? list.value.map(spec.ensemble.toMember).filter(Boolean) as EnsembleMemberInput[]
      : []
    setEnsembleSegment(spec.ensemble.segment, members)
  }

  const load = async (): Promise<any[]> => {
    try {
      const data = await spec.fetchItems()
      list.value = data || []
      publishMembers()
      return list.value
    } catch (e) {
      console.warn(`[${spec.tag}] Failed to fetch:`, e)
      return []
    }
  }

  const buildGeoJSON = (items: any[]) => ({
    type: 'FeatureCollection' as const,
    features: items.map((item: any) => {
      const f = spec.toFeature(item)
      if (!f || !spec.ensemble) return f
      const m = spec.ensemble.toMember(item)
      const pl = m ? ensemblePlacement(spec.ensemble.segment, m.id) : undefined
      const inEnsemble = (pl?.groupSize || 1) > 1
      // Group members render from the shared centroid anchor + screen-space
      // slot offset; hover/lock-on/click follow it via renderedPointCoords
      // (useMapHighlight.ts). The GL layout uses the icon-size-corrected
      // glOffset variant.
      if (pl && f.geometry?.type === 'Point') f.geometry.coordinates = pl.anchor
      f.properties.iconOffset = pl?.offset || [0, 0]
      f.properties.glIconOffset = pl?.glOffset || [0, 0]
      f.properties.ensemble = inEnsemble
      // labelPos null = a readout column (or the center slot) replaces the label
      f.properties.labelHidden = pl ? pl.labelPos === null : false
      if (pl?.labelPos === 'above') {
        f.properties.labelOffset = [0, -1.6]
        f.properties.labelAnchor = 'bottom'
      } else if (inEnsemble && pl?.labelPos === 'below') {
        // 28 px ensemble hexes need a touch more clearance than the 22 px base
        f.properties.labelOffset = [0, 1.6]
      }
      return f
    }).filter(Boolean),
  })

  const iconLayerDef = (vis: string) => ({
    id: spec.iconLayerId,
    type: 'symbol',
    source: spec.source,
    ...(spec.iconMinzoom != null ? { minzoom: spec.iconMinzoom } : {}),
    layout: {
      'icon-image': spec.iconImage,
      'icon-allow-overlap': true,
      ...(spec.ensemble
        ? {
            'icon-offset': ['get', 'glIconOffset'],
            'icon-size': ['case', ['get', 'ensemble'], ENSEMBLE_ICON_SCALE, 1],
          }
        : {}),
      visibility: vis,
    },
  })

  const labelLayerDef = (vis: string) => ({
    id: spec.labelLayerId,
    type: 'symbol',
    source: spec.source,
    ...(spec.labelMinzoom != null ? { minzoom: spec.labelMinzoom } : {}),
    layout: {
      'text-field': spec.ensemble
        ? ['case', ['get', 'labelHidden'], '', ['get', 'name']]
        : ['get', 'name'],
      'text-size': spec.labelTextSize ?? 11,
      'text-offset': spec.ensemble
        ? ['coalesce', ['get', 'labelOffset'], ['literal', [0, 1.5]]]
        : [0, 1.5],
      'text-anchor': spec.ensemble
        ? ['coalesce', ['get', 'labelAnchor'], 'top']
        : 'top',
      'text-optional': true,
      visibility: vis,
    },
    paint: {
      'text-color': '#374151',
      'text-halo-color': '#ffffff',
      'text-halo-width': 1.5,
    },
  })

  // ---- Instrument-readout HUD markers (utils/envHudMarker.ts) ----
  const hudMarkers = new Map<string, { marker: any; update: (v: DeviceHudView) => void }>()

  const removeHud = () => {
    for (const rec of hudMarkers.values()) rec.marker.remove()
    hudMarkers.clear()
  }

  const syncHud = async (map: any) => {
    const ens = spec.ensemble
    if (!ens?.hudView || typeof window === 'undefined') return
    if (!enabled.value) { removeHud(); return }
    const maplibregl = ((await import('maplibre-gl')) as any).default || (await import('maplibre-gl'))
    const { createDeviceHudElement } = await import('~/utils/envHudMarker')
    // Re-check: the layer may have been toggled off while the imports resolved
    if (!enabled.value) { removeHud(); return }
    const seen = new Set<string>()
    for (const item of list.value) {
      const m = ens.toMember(item)
      if (!m) continue
      const pl = ensemblePlacement(ens.segment, m.id)
      if (pl?.hudSuppressed) continue // deduped — the name label shows instead
      const content = ens.hudView(item, pl)
      if (!content) continue
      seen.add(m.id)
      const lngLat = pl?.anchor || [m.lon, m.lat]
      let rec = hudMarkers.get(m.id)
      if (!rec) {
        const { el, update } = createDeviceHudElement()
        const marker = new maplibregl.Marker({ element: el, anchor: 'center', offset: pl?.offset || [0, 0] })
          .setLngLat(lngLat)
          .addTo(map)
        rec = { marker, update }
        hudMarkers.set(m.id, rec)
      } else {
        rec.marker.setLngLat(lngLat)
        rec.marker.setOffset(pl?.offset || [0, 0])
      }
      rec.update({
        ...content,
        ensemble: (pl?.groupSize || 1) > 1,
        side: pl?.side || 'right',
        topSlot: pl?.topSlot || false,
        nudge: pl?.nudge || null,
        hudLeft: pl?.hudLeft ?? null,
      })
    }
    for (const [id, rec] of hudMarkers) {
      if (!seen.has(id)) { rec.marker.remove(); hudMarkers.delete(id) }
    }
  }

  // Other layers' publishes regroup our members — re-render from cache.
  // (Listeners must never publish; see useMapDeviceEnsembles.ts.)
  if (spec.ensemble) {
    onEnsembleChange(`layer:${spec.tag}`, () => {
      const map = mapStore.mapInstance
      if (!map || !map.getSource(spec.source)) return
      ;(map.getSource(spec.source) as any).setData(buildGeoJSON(list.value))
      void syncHud(map)
    })
  }

  const addLayers = async (map: any) => {
    const items = await load()
    loaded = true

    const geojson = buildGeoJSON(items)
    if (map.getSource(spec.source)) {
      ;(map.getSource(spec.source) as any).setData(geojson)
      void syncHud(map)
      return
    }

    spec.ensureIcons(map)
    map.addSource(spec.source, { type: 'geojson', data: geojson })

    const vis = enabled.value ? 'visible' : 'none'
    map.addLayer(iconLayerDef(vis))
    map.addLayer(labelLayerDef(vis))
    if (spec.hoverHex) attachHoverHex(map, spec.iconLayerId)
    void syncHud(map)
  }

  const refresh = async () => {
    const map = mapStore.mapInstance
    if (!map || !map.getSource(spec.source)) return
    const items = await load()
    ;(map.getSource(spec.source) as any).setData(buildGeoJSON(items))
    void syncHud(map)
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
    void syncHud(map)
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

    // Regroup the shared ensemble: members leave on hide, rejoin on show
    // (the change listener re-renders this and every co-located layer)
    publishMembers()
    void syncHud(map)

    if (enabled.value) startRefresh()
    else stopRefresh()
  }

  /**
   * Force the layer visible with its data loaded — for deep-links whose intent
   * is "show me this on the map" even if the user had toggled the pref off.
   * Returns the item list.
   */
  const ensureLoaded = async (map: any): Promise<any[]> => {
    if (!map) return []
    if (!enabled.value) {
      enabled.value = true
      if (!loaded) { await addLayers(map); startRefresh() }
      else { publishMembers(); void syncHud(map) }
      for (const id of [spec.iconLayerId, spec.labelLayerId]) {
        if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', 'visible')
      }
    } else if (!loaded) {
      await addLayers(map)
      startRefresh()
    }
    return list.value
  }

  /**
   * Frame all of this layer's points in the viewport — for deep-links whose
   * intent is "show me these on the map" (e.g. /mesh → /map?fit=mesh). Forces
   * the layer visible first (fetching its data if not yet loaded), then
   * fitBounds over every point. Returns false when there's nothing to frame.
   */
  const fitBounds = async (
    map: any,
    opts: { animate?: boolean; padding?: number; maxZoom?: number } = {},
  ): Promise<boolean> => {
    if (!map) return false
    await ensureLoaded(map)
    const items = loaded ? list.value : await load()
    const coords = items
      .map(spec.toFeature)
      .filter(Boolean)
      .map((f: any) => f.geometry?.coordinates)
      .filter((c: any) => Array.isArray(c) && c.length === 2)
    if (coords.length === 0) return false

    let [minLng, minLat] = coords[0]
    let [maxLng, maxLat] = coords[0]
    for (const [lng, lat] of coords) {
      if (lng < minLng) minLng = lng
      if (lng > maxLng) maxLng = lng
      if (lat < minLat) minLat = lat
      if (lat > maxLat) maxLat = lat
    }

    map.fitBounds([[minLng, minLat], [maxLng, maxLat]], {
      padding: opts.padding ?? 80,
      maxZoom: opts.maxZoom ?? 14,
      animate: opts.animate ?? true,
      duration: 800,
    })
    return true
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
    ensureLoaded,
    fitBounds,
    pauseRefresh,
    resumeRefresh,
  }
}
