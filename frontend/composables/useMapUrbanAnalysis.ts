/**
 * Urban analysis tool — draw a plot polygon on the map, pick an intended use
 * type, and submit it for an urbanistic assessment.
 *
 * First step / stub: the backend (POST /api/v1/geo/urban/analyze/) just
 * acknowledges the request (returns OK). The deterministic geo/rules/legal
 * pipeline that produces a real urbanistic report is layered on later.
 *
 * Drawing mirrors useMapMeasure's area mode (click vertices, mousemove
 * rubber-band, double-click to finish) but with its own urban-* sources and a
 * `closed` flag: once the ring is closed the use-type picker + Analyze appear.
 */

import { ref, computed } from 'vue'
import turfArea from '@turf/area'
import { polygon as turfPolygon } from '@turf/helpers'
import { createDrawTool, EMPTY_FC } from '~/composables/useMapDrawTool'

// Layer / source IDs (distinct from the measure tool so the two can't collide)
const SRC_POLYGON = 'urban-polygon'
const SRC_POINTS = 'urban-points'
const LYR_POLYGON_FILL = 'urban-polygon-fill'
const LYR_POLYGON_OUTLINE = 'urban-polygon-outline'
const LYR_POINTS = 'urban-points-layer'

// Violet plot — visually distinct from measure (blue) and drone-reach.
const PLOT_COLOR = '#7c3aed'

// Intended building / land-use types — Portuguese PDM "categorias de uso do
// solo" vocabulary (mirror of geo/endpoints/urban.py URBAN_USE_TYPES). Labels
// localized via map.urban.types.<slug>. Informed placeholder, NOT extracted from
// a specific regulamento — real per-município categories come with the rules engine.
export const URBAN_USE_TYPES = [
  'residential',
  'commercial',
  'services',
  'industrial',
  'warehouse',
  'tourism',
  'facility',
  'agricultural',
  'livestock',
  'forestry',
  'mixed',
] as const

export type UrbanUseType = typeof URBAN_USE_TYPES[number]

// Failure modes when importing a plot from an uploaded GeoJSON file.
export type UrbanUploadError = 'invalid_json' | 'no_polygon' | 'not_wgs84' | 'too_few'

// L1 territorial-framing result from POST /geo/urban/analyze/. classe/categoria/
// tipo are authoritative PT source labels (rendered as-is); UI chrome is i18n'd.
// L2 edificability parameters for a qualification (curated rules, artigo-cited).
export interface UrbanRuleHit {
  artigo: string
  indice_utilizacao: number | null
  indice_utilizacao_max: boolean
  indice_impermeabilizacao_pct: number | null
  num_pisos_max: number | null
  cercea_max_m: number | null
  edificavel: boolean
  usos_dominantes: string[] // dominant/permitido use slugs (quadro de usos)
  uso_default_regime: 'condicionado' | 'interdito' | null // curated regime of non-listed uses; null = not curated
  artigo_usos: string // artigo of the usos provision (may differ from edificabilidade artigo)
  notes: string
  area_max_construcao_m2: number | null // índice util × this category's plot share
}
export interface UrbanOrdenamentoHit {
  classe: string
  categoria: string
  subcategoria: string
  coverage_pct: number | null // % of the plot in this category (straddle-aware)
  service_layer: string
  rule: UrbanRuleHit | null // L2 params; null where not yet curated (e.g. rústico)
}
export interface UrbanCondicionanteHit {
  grupo: string
  tipo: string
  kind: 'area' | 'line' | 'point'
  features: number
  service_layer: string
}
// L3 viability synthesis — justified Sim/Condicionado/Não verdict (não constitui parecer).
export interface UrbanViabilityReason {
  code: 'regime_restrito' | 'parte_nao_edificavel' | 'condicionante' | 'edificavel_parametros'
    | 'uso_permitido' | 'uso_condicionado' | 'uso_interdito' | 'uso_nao_adjudicado'
  artigo?: string // regime_restrito / edificavel_parametros / uso_* reasons
  count?: number // condicionante
  use_type?: string // uso_* reasons
}
export interface UrbanViability {
  verdict: 'edificavel' | 'condicionado' | 'nao_edificavel' | 'sem_dados'
  confidence: 'alta' | 'media' | 'baixa'
  reasons: UrbanViabilityReason[]
  use_regime?: 'permitido' | 'condicionado' | 'interdito' | null // chosen use_type vs quadro de usos
}
export interface UrbanResult {
  covered: boolean
  municipio: string | null
  ordenamento: UrbanOrdenamentoHit[]
  condicionantes: UrbanCondicionanteHit[]
  plot_area_m2: number
  uncovered_pct: number
  area_max_construcao_total_m2?: number | null // L2: total buildable area (índice × area)
  area_impermeavel_total_m2?: number | null // L2: total impermeable (sealed) ground area
  diploma?: string | null // L2: legal source of the parameters
  use_type: string
  use_type_checked: boolean // L1 does not yet adjudicate intended use (L2/L3)
  level: string
  viability?: UrbanViability | null // L3 verdict (present when covered)
  source: { portal: string; version: string; ingested_at: string | null } | null
  available_municipios?: string[]
}

export function useMapUrbanAnalysis() {
  const mapStore = useMapStore()
  const authStore = useAuthStore()

  // ======== State ========

  const urbanLoading = ref(false)
  const urbanPoints = ref<[number, number][]>([]) // [lng, lat]
  const cursorPoint = ref<[number, number] | null>(null) // live cursor rubber-band
  const closed = ref(false)                 // ring finalized (double-click)
  const useType = ref<UrbanUseType>('residential')
  const result = ref<UrbanResult | null>(null)

  const area = computed(() => {
    if (urbanPoints.value.length < 3) return 0
    const ring = [...urbanPoints.value, urbanPoints.value[0]]
    try {
      return turfArea(turfPolygon([ring]))
    } catch {
      return 0
    }
  })

  const formattedArea = computed(() => formatArea(area.value))
  const canAnalyze = computed(() => closed.value && urbanPoints.value.length >= 3 && !urbanLoading.value)

  // ======== Helpers ========

  function formatArea(sqMeters: number): string {
    if (sqMeters <= 0) return '0 m²'
    if (sqMeters < 10000) return `${Math.round(sqMeters)} m²`
    if (sqMeters < 1000000) return `${(sqMeters / 10000).toFixed(2)} ha`
    return `${(sqMeters / 1000000).toFixed(2)} km²`
  }

  // ======== GeoJSON Builders ========

  function buildPolygonGeoJSON(): GeoJSON.FeatureCollection {
    const pts = [...urbanPoints.value]
    // While still drawing, follow the cursor for a live rubber-band edge.
    if (!closed.value && cursorPoint.value && pts.length > 0) pts.push(cursorPoint.value)
    if (pts.length < 3) return EMPTY_FC
    const ring = [...pts, pts[0]] // close the ring
    return {
      type: 'FeatureCollection',
      features: [{
        type: 'Feature',
        properties: {},
        geometry: { type: 'Polygon', coordinates: [ring] },
      }],
    }
  }

  function buildPointsGeoJSON(): GeoJSON.FeatureCollection {
    return {
      type: 'FeatureCollection',
      features: urbanPoints.value.map((coord, i) => ({
        type: 'Feature' as const,
        properties: { index: i },
        geometry: { type: 'Point' as const, coordinates: coord },
      })),
    }
  }

  function updateVisualization() {
    const map = mapStore.mapInstance
    if (!map) return
    map.getSource(SRC_POLYGON)?.setData(buildPolygonGeoJSON())
    map.getSource(SRC_POINTS)?.setData(buildPointsGeoJSON())
  }

  // ======== Interaction ========

  function addPoint(coord: [number, number]) {
    if (closed.value) return
    urbanPoints.value = [...urbanPoints.value, coord]
    cursorPoint.value = null
    updateVisualization()
  }

  function undoLastPoint() {
    if (urbanPoints.value.length === 0) return
    // Reopen for editing if we'd previously closed the ring.
    closed.value = false
    result.value = null
    urbanPoints.value = urbanPoints.value.slice(0, -1)
    updateVisualization()
  }

  function finishDrawing() {
    if (urbanPoints.value.length < 3) return
    closed.value = true
    cursorPoint.value = null
    updateVisualization()
  }

  function redraw() {
    closed.value = false
    result.value = null
    urbanPoints.value = []
    cursorPoint.value = null
    tool.clearVisualization()
  }

  // ======== API ========

  async function analyze() {
    if (!canAnalyze.value) return
    const map = mapStore.mapInstance
    if (!map) return

    urbanLoading.value = true
    result.value = null
    try {
      await authStore.ensureToken()
      const resp = await $fetch<UrbanResult>('/api/v1/geo/urban/analyze/', {
        method: 'POST',
        credentials: 'include',
        headers: { Authorization: `Bearer ${authStore.token}` },
        body: { polygon: urbanPoints.value, use_type: useType.value },
      })
      result.value = resp ?? null
    } catch (e: any) {
      console.warn('[Urban] analyze failed:', e)
      useToastStore().error(e?.data?.detail || e?.statusMessage || 'Urban analysis failed')
    } finally {
      urbanLoading.value = false
    }
  }

  // ======== Import a plot from an uploaded GeoJSON ========

  /** First Polygon/MultiPolygon outer ring found in a GeoJSON object, or null. */
  function _firstPolygonRing(gj: any): number[][] | null {
    if (!gj || typeof gj !== 'object') return null
    if (gj.type === 'FeatureCollection' && Array.isArray(gj.features)) {
      for (const f of gj.features) {
        const r = _firstPolygonRing(f)
        if (r) return r
      }
      return null
    }
    if (gj.type === 'Feature') return _firstPolygonRing(gj.geometry)
    if (gj.type === 'Polygon' && Array.isArray(gj.coordinates)) {
      return Array.isArray(gj.coordinates[0]) ? gj.coordinates[0] : null
    }
    if (gj.type === 'MultiPolygon' && Array.isArray(gj.coordinates)) {
      return Array.isArray(gj.coordinates[0]?.[0]) ? gj.coordinates[0][0] : null
    }
    return null
  }

  function _fitToPlot(pts: [number, number][]) {
    const map = mapStore.mapInstance
    if (!map || !pts.length) return
    let minLng = Infinity, minLat = Infinity, maxLng = -Infinity, maxLat = -Infinity
    for (const [lng, lat] of pts) {
      if (lng < minLng) minLng = lng
      if (lng > maxLng) maxLng = lng
      if (lat < minLat) minLat = lat
      if (lat > maxLat) maxLat = lat
    }
    map.fitBounds([[minLng, minLat], [maxLng, maxLat]], { padding: 80, maxZoom: 18, duration: 600 })
  }

  /**
   * Load a plot from GeoJSON text — the "I already have the plot" path for
   * professionals. Uses the first Polygon/MultiPolygon outer ring in a
   * Feature / FeatureCollection / bare Geometry. GeoJSON is WGS84 (lng/lat) by
   * spec (RFC 7946): coordinates out of [-180,180]/[-90,90] are rejected rather
   * than silently misplaced (e.g. an ETRS89/PT-TM06 export). Returns an error
   * code; the caller maps it to a localized toast.
   */
  function loadPlotFromGeoJSON(text: string): { ok: true } | { ok: false; error: UrbanUploadError } {
    let gj: any
    try { gj = JSON.parse(text) } catch { return { ok: false, error: 'invalid_json' } }
    const ring = _firstPolygonRing(gj)
    if (!ring) return { ok: false, error: 'no_polygon' }
    const pts: [number, number][] = []
    for (const c of ring) {
      if (!Array.isArray(c) || typeof c[0] !== 'number' || typeof c[1] !== 'number') {
        return { ok: false, error: 'no_polygon' }
      }
      if (Math.abs(c[0]) > 180 || Math.abs(c[1]) > 90) {
        return { ok: false, error: 'not_wgs84' }
      }
      pts.push([c[0], c[1]])
    }
    // Drop the closing duplicate vertex (we keep the ring open; it's closed on render).
    if (pts.length > 1) {
      const a = pts[0], b = pts[pts.length - 1]
      if (a[0] === b[0] && a[1] === b[1]) pts.pop()
    }
    if (pts.length < 3) return { ok: false, error: 'too_few' }

    const map = mapStore.mapInstance
    if (map) tool.setupLayers(map) // ensure sources exist if the tool was only just opened
    urbanPoints.value = pts
    cursorPoint.value = null
    closed.value = true
    result.value = null
    updateVisualization()
    _fitToPlot(pts)
    return { ok: true }
  }

  // ======== Lifecycle (via createDrawTool) ========

  const tool = createDrawTool({
    tag: 'urban',
    sources: [SRC_POLYGON, SRC_POINTS],
    layers: [
      {
        id: LYR_POLYGON_FILL,
        type: 'fill',
        source: SRC_POLYGON,
        paint: { 'fill-color': PLOT_COLOR, 'fill-opacity': 0.18 },
      },
      {
        id: LYR_POLYGON_OUTLINE,
        type: 'line',
        source: SRC_POLYGON,
        paint: { 'line-color': PLOT_COLOR, 'line-width': 2.5, 'line-opacity': 0.9 },
        layout: { 'line-cap': 'round', 'line-join': 'round' },
      },
      {
        id: LYR_POINTS,
        type: 'circle',
        source: SRC_POINTS,
        paint: {
          'circle-radius': 5,
          'circle-color': '#ffffff',
          'circle-stroke-color': PLOT_COLOR,
          'circle-stroke-width': 2.5,
        },
      },
    ],
    disableDoubleClickZoom: true,
    events: {
      click: (e: any) => {
        addPoint([e.lngLat.lng, e.lngLat.lat])
      },
      dblclick: (e: any) => {
        e.preventDefault()
        // The preceding `click` already added a duplicate vertex — drop it.
        if (urbanPoints.value.length > 1 && !closed.value) {
          urbanPoints.value = urbanPoints.value.slice(0, -1)
        }
        finishDrawing()
      },
      mousemove: (e: any) => {
        if (closed.value || urbanPoints.value.length === 0) return
        cursorPoint.value = [e.lngLat.lng, e.lngLat.lat]
        mapStore.mapInstance?.getSource(SRC_POLYGON)?.setData(buildPolygonGeoJSON())
      },
    },
    onStart: () => {
      closed.value = false
      result.value = null
      urbanPoints.value = []
      cursorPoint.value = null
    },
    onStop: () => {
      closed.value = false
      result.value = null
      cursorPoint.value = null
      urbanPoints.value = []
    },
  })

  return {
    urbanActive: tool.active,
    urbanLoading,
    urbanPoints,
    closed,
    useType,
    result,
    area,
    formattedArea,
    canAnalyze,
    setupLayers: tool.setupLayers,
    undoLastPoint,
    finishDrawing,
    redraw,
    analyze,
    loadPlotFromGeoJSON,
    startUrban: tool.start,
    stopUrban: tool.stop,
    toggleUrban: tool.toggle,
  }
}
