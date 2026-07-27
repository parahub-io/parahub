/**
 * useTransitVehiclesDeck — live transit vehicles as deck.gl layers on the
 * shared overlaid transit canvas (utils/transitDeckOverlay).
 *
 * Why deck and not MapLibre circle/symbol layers: the glide animator feeds new
 * positions ~22 fps while vehicles move, and a MapLibre GeoJSON setData marks
 * the whole source dirty → full repaint of the entire vector scene per frame
 * (the idle-CPU bug). On the deck canvas each update touches only these small
 * layers; MapLibre repaints solely on real camera/data changes.
 *
 * Visual parity with the former MapLibre layers:
 *  - z10–13: small route-colored dots (gray for stationary "zombie" vehicles)
 *  - z13+ (any zoom in single-route focus): upright type icon, bearing chevron
 *    orbiting above it (map-aligned rotation), route-color bar underneath
 *  - hover: pointer cursor + the shared brand hover hex (poi-hover-hex-src)
 *  - click: dispatched to the vehicle panel callback
 */

import type { TransitDeckOverlay } from '~/utils/transitDeckOverlay'

// Map GTFS route_type → icon name (exact matches; ranges in resolveIconName)
const ROUTE_TYPE_ICON: Record<number, string> = {
  0: 'tram', 1: 'metro', 2: 'train', 3: 'bus', 4: 'ferry',
  7: 'train', 11: 'trolleybus', 200: '2bus', 1100: 'airplane', 1501: 'bus-taxi',
}
const ICON_NAMES = ['bus', 'tram', 'metro', 'train', 'ferry', 'trolleybus', 'bus-taxi', '2bus', 'airplane']

function resolveIconName(routeType: number): string {
  if (ROUTE_TYPE_ICON[routeType]) return ROUTE_TYPE_ICON[routeType]
  if (routeType >= 200 && routeType <= 299) return '2bus'
  if (routeType >= 900 && routeType <= 999) return 'tram'
  if (routeType >= 100 && routeType <= 199) return 'train'
  if (routeType >= 400 && routeType <= 499) return 'metro'
  if (routeType >= 700 && routeType <= 799) return 'bus'
  if (routeType >= 1500 && routeType <= 1599) return 'bus-taxi'
  return 'bus'
}

function hexToRgb(hex: string): [number, number, number] {
  if (!/^[0-9a-fA-F]{6}$/.test(hex)) return [59, 130, 246]
  return [
    parseInt(hex.slice(0, 2), 16),
    parseInt(hex.slice(2, 4), 16),
    parseInt(hex.slice(4, 6), 16),
  ]
}

/** Piecewise-linear replica of the former MapLibre interpolate expressions. */
function lerpStops(z: number, stops: Array<[number, number]>): number {
  if (z <= stops[0][0]) return stops[0][1]
  for (let i = 1; i < stops.length; i++) {
    if (z <= stops[i][0]) {
      const [z0, v0] = stops[i - 1]
      const [z1, v1] = stops[i]
      return v0 + ((z - z0) / (z1 - z0)) * (v1 - v0)
    }
  }
  return stops[stops.length - 1][1]
}
const symbolScale = (z: number) => lerpStops(z, [[13, 0.45], [16, 0.65], [18, 0.85]])
const dotRadius = (z: number) => lerpStops(z, [[10, 3], [13, 5]])

const VEHICLE_ICON_MIN_ZOOM = 13   // global view; single-route focus shows icons at every zoom
const DOT_MIN_ZOOM = 10
const ZOMBIE_ALPHA = 153           // 0.6, matches the former icon/circle opacity

// Atlas cell: 96px raster for a 48px logical icon (2x, crisp on hidpi).
const CELL = 96
const BAR_W = 88   // route-color bar, 2x raster of logical 44x6
const BAR_H = 12

/**
 * Build the icon atlas: colored + grayscale type icons, the bearing chevron,
 * and a white bar (mask, tinted per route via getColor).
 *
 * Chevron cell: drawn near the top with the anchor on the bottom edge — the
 * anchor sits on the vehicle point and getAngle rotates around it, so the
 * chevron orbits the icon at 34 logical px (same as the former icon-offset).
 */
async function buildAtlas(): Promise<{ canvas: HTMLCanvasElement; mapping: Record<string, any> }> {
  const canvas = document.createElement('canvas')
  canvas.width = CELL * (ICON_NAMES.length * 2 + 1) + BAR_W
  canvas.height = CELL
  const ctx = canvas.getContext('2d')!
  const mapping: Record<string, any> = {}

  const loadImg = (url: string) => new Promise<HTMLImageElement | null>((resolve) => {
    const img = new Image(CELL, CELL)
    img.crossOrigin = 'anonymous'
    img.onload = () => resolve(img)
    img.onerror = () => resolve(null)  // blank cell — vehicle still has dot/bar
    img.src = url
  })
  const imgs = await Promise.all(ICON_NAMES.map((n) => loadImg(`/img/transit/${n}.svg`)))
  imgs.forEach((img, i) => {
    const cx = i * CELL
    const gx = (ICON_NAMES.length + i) * CELL
    if (img) {
      ctx.drawImage(img, cx, 0, CELL, CELL)
      ctx.filter = 'grayscale(100%) brightness(0.8)'
      ctx.drawImage(img, gx, 0, CELL, CELL)
      ctx.filter = 'none'
    }
    mapping[ICON_NAMES[i]] = { x: cx, y: 0, width: CELL, height: CELL }
    mapping[`${ICON_NAMES[i]}-gray`] = { x: gx, y: 0, width: CELL, height: CELL }
  })

  // Chevron — two sides of the brand flat-top hexagon (120° apex, arms at 30°),
  // block center 68 raster px (34 logical) above the bottom-edge anchor.
  const hx = ICON_NAMES.length * 2 * CELL
  ctx.strokeStyle = '#f4c110'
  ctx.lineWidth = 8
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'
  ctx.beginPath()
  ctx.moveTo(hx + 6, 38)
  ctx.lineTo(hx + 48, 14)
  ctx.lineTo(hx + 90, 38)
  ctx.stroke()
  mapping.heading = { x: hx, y: 0, width: CELL, height: CELL, anchorX: CELL / 2, anchorY: CELL }

  const bx = hx + CELL
  ctx.fillStyle = '#ffffff'
  ctx.fillRect(bx, 0, BAR_W, BAR_H)
  mapping.bar = { x: bx, y: 0, width: BAR_W, height: BAR_H, mask: true }

  return { canvas, mapping }
}

export function useTransitVehiclesDeck(ov: TransitDeckOverlay) {
  let map: any = null
  let IconLayerCls: any = null
  let ScatterplotLayerCls: any = null
  let atlas: { canvas: HTMLCanvasElement; mapping: Record<string, any> } | null = null
  let features: any[] = []
  let routeFocus = false
  let running = false
  let starting: Promise<void> | null = null
  let dispatchClick: ((vehicle: any) => void) | null = null
  let hoveredKey: string | null = null
  let lastLayerIds: string[] = []

  function onHover(info: any) {
    if (!map) return
    const f = info?.object
    const key = f ? (f.properties.uid || f.properties.vehicle_id) : null
    if (key === hoveredKey) return
    hoveredKey = key
    map.getCanvas().style.cursor = f ? 'pointer' : ''
    // Same brand hover hex the MapLibre layers used (attachHoverHex, size 1.9)
    const src = map.getSource('poi-hover-hex-src')
    if (!src) return
    if (f) {
      if (map.getLayer('poi-hover-hex-layer')) map.setLayoutProperty('poi-hover-hex-layer', 'icon-size', 1.9)
      src.setData({ type: 'FeatureCollection', features: [{ type: 'Feature', properties: {}, geometry: f.geometry }] })
    } else {
      src.setData({ type: 'FeatureCollection', features: [] })
    }
  }

  function onClick(info: any) {
    const f = info?.object
    if (!f || !dispatchClick) return
    dispatchClick({
      ...f.properties,
      lngLat: {
        lng: info.coordinate?.[0] ?? f.geometry.coordinates[0],
        lat: info.coordinate?.[1] ?? f.geometry.coordinates[1],
      },
    })
  }

  function render() {
    if (!running || !ov.ready() || !ScatterplotLayerCls) return
    const z = map?.getZoom?.() ?? 0
    const layers: any[] = []

    // The basemap runs MapLibre's globe projection, so the deck overlay uses
    // GlobeView, whose default GPU parameters cull back-facing triangles (far
    // side of the globe). IconLayer quads are wound back-facing after the
    // shader's y-flip and get culled to nothing — override per layer. Vehicles
    // are viewport-bbox-scoped, so losing far-side culling costs nothing.
    const noCull = { parameters: { cullMode: 'none' as const } }

    if (features.length && z >= DOT_MIN_ZOOM && z < VEHICLE_ICON_MIN_ZOOM) {
      layers.push(new ScatterplotLayerCls({
        ...noCull,
        id: 'transit-vehicles-circle',
        data: features,
        pickable: true,
        radiusUnits: 'pixels',
        getRadius: dotRadius(z),
        stroked: true,
        lineWidthUnits: 'pixels',
        getLineWidth: 1.5,
        getPosition: (f: any) => f.geometry.coordinates,
        getFillColor: (f: any) => f.properties.zombie === 1
          ? [136, 136, 136, ZOMBIE_ALPHA]
          : [...hexToRgb(f.properties.route_color), 255],
        getLineColor: (f: any) => f.properties.zombie === 1 ? [102, 102, 102, 255] : [255, 255, 255, 255],
      }))
    }

    if (features.length && atlas && (routeFocus || z >= VEHICLE_ICON_MIN_ZOOM)) {
      const s = symbolScale(z)
      const common = {
        ...noCull,
        data: features,
        pickable: true,
        iconAtlas: atlas.canvas,
        iconMapping: atlas.mapping,
        getPosition: (f: any) => f.geometry.coordinates,
      }
      // Same stack order as the former MapLibre layers: chevron, bar, icon on top.
      layers.push(new IconLayerCls({
        ...common,
        id: 'transit-vehicles-heading',
        // Skip stationary (zombie) vehicles AND any without a real GTFS-RT
        // heading — a missing bearing would render a spurious north chevron.
        data: features.filter((f: any) => f.properties.zombie !== 1 && f.properties.has_bearing === 1),
        billboard: false,  // map-aligned, like icon-rotation-alignment: map
        getIcon: () => 'heading',
        getSize: 48 * s,
        getAngle: (f: any) => -(f.properties.bearing || 0),  // deck angles are CCW, bearings CW
      }))
      layers.push(new IconLayerCls({
        ...common,
        id: 'transit-vehicles-bar',
        // Route identity under the icon — only when the feed defines route_color
        data: features.filter((f: any) => f.properties.route_color_set === 1),
        getIcon: () => 'bar',
        getSize: 6 * s,
        getPixelOffset: [0, 32 * s],
        getColor: (f: any) => [...hexToRgb(f.properties.route_color), f.properties.zombie === 1 ? ZOMBIE_ALPHA : 255],
      }))
      layers.push(new IconLayerCls({
        ...common,
        id: 'transit-vehicles-icon',
        getIcon: (f: any) => resolveIconName(f.properties.route_type) + (f.properties.zombie === 1 ? '-gray' : ''),
        getSize: 48 * s,
        // Non-mask icons use only the alpha component of getColor (zombie dim)
        getColor: (f: any) => [0, 0, 0, f.properties.zombie === 1 ? ZOMBIE_ALPHA : 255],
      }))
    }

    lastLayerIds = layers.map((l) => l.id)
    ov.setGroup('vehicles', layers)
  }

  /** Attach overlay + load deck layer chunk + build atlas, then render (idempotent). */
  async function start(m: any, onVehicleClick: (vehicle: any) => void) {
    dispatchClick = onVehicleClick
    map = m
    running = true
    if (!starting) {
      starting = (async () => {
        await ov.ensure(m)
        if (!IconLayerCls) {
          const mod = await import('@deck.gl/layers')
          IconLayerCls = (mod as any).IconLayer
          ScatterplotLayerCls = (mod as any).ScatterplotLayer
        }
        if (!atlas) atlas = await buildAtlas()
        ov.setDeckProps({ onHover, onClick })
      })().catch((e) => {
        starting = null  // allow a retry on the next start
        throw e
      })
    }
    await starting
    if (!running) return  // stopped while the chunk/atlas was loading
    // Symbol scale and the dot/icon zoom split depend on zoom (named handler,
    // off-before-on: start() re-runs on style reloads / toggle cycles)
    map.off('zoom', render)
    map.on('zoom', render)
    render()
    // Debug handle (same pattern as window.__transitTrails)
    if (typeof window !== 'undefined') {
      ;(window as any).__transitVehicles = {
        running: () => running,
        features: () => features.length,
        layers: () => lastLayerIds.slice(),
        zoom: () => map?.getZoom?.(),
        atlas: () => !!atlas,
      }
    }
  }

  /** Called by the glide animator with interpolated positions (and on WS snap). */
  function update(fc: any) {
    features = fc?.features ?? []
    render()
  }

  /** Single-route focus renders icons at every zoom (matches route mini-map). */
  function setRouteFocus(on: boolean) {
    if (routeFocus === on) return
    routeFocus = on
    render()
  }

  /** True when a vehicle sits under the screen point (map click dispatcher
   * uses this to leave the click to the overlay's own handler). Trails are
   * not pickable, so any pick on the shared overlay is a vehicle. */
  function hasVehicleAt(point: { x: number; y: number }): boolean {
    if (!running) return false
    return !!ov.pick({ x: point.x, y: point.y, radius: 1 })?.object
  }

  /** Clear rendered vehicles (transit toggled off / WS disconnected). */
  function stop() {
    running = false
    features = []
    hoveredKey = null
    if (map) {
      map.off('zoom', render)
      try { map.getCanvas().style.cursor = '' } catch { /* map torn down */ }
    }
    ov.setGroup('vehicles', [])
  }

  return { start, stop, update, setRouteFocus, hasVehicleAt }
}
