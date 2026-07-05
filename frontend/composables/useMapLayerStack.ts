/**
 * Layer-stack orchestration for MapView: one module owns BOTH the initial
 * on('load') layer registration and the style-reload re-registration, so the
 * two sequences cannot drift apart. (The hand-maintained reload copy had lost
 * isochrone/droneReach: after a theme flip their sources stayed wiped and the
 * tools silently rendered nothing until a page remount.)
 *
 * Order matters twice over:
 *  - MapLibre z-order = add order (e.g. satellite below the OpenSky raster,
 *    transit route overlay below browse markers);
 *  - highlight.setupInteractiveFeatures must run after all synchronously
 *    added layers; async layers (gov/church fetch) re-register via callback.
 *
 * browse.setupLayers is intentionally NOT part of setupInitial: on first load
 * MapView registers it after the transit deep-link block, so a deep-linked
 * route overlay lands below the browse markers — same relative order as in
 * reapplyAfterStyleChange.
 */
import type { Ref } from 'vue'

export function useMapLayerStack(opts: {
  highlight: {
    setupLayers: (map: any) => void
    setupInteractiveFeatures: (map: any) => void
    syncMarkers: (map: any, store: any) => void
  }
  openSky: {
    setupLayers: (map: any, missionId?: string) => any
    tileGridMode: Ref<boolean>
    toggleTileGrid: () => void
  }
  satellite: { setupLayer: (map: any) => void }
  iot: { setupLayers: (map: any) => void; setupLayersOnly: (map: any) => void }
  mesh: { setupLayers: (map: any) => void; setupLayersOnly: (map: any) => void }
  condo: { setupLayers: (map: any) => void; setupLayersOnly: (map: any) => void }
  hub: { setupLayers: (map: any) => void; setupLayersOnly: (map: any) => void }
  gov: { setupLayers: (map: any, onReady?: () => void) => void; setupLayersOnly: (map: any) => void }
  church: { setupLayers: (map: any, onReady?: () => void) => void; setupLayersOnly: (map: any) => void }
  transit: {
    setupLayers: (map: any) => void
    resetDataLoaded: () => void
    redrawActiveRoute: (map: any) => void
  }
  browse: { setupLayers: (map: any) => void }
  /** createDrawTool instances (measure/sunStudy/isochrone/droneReach/urban),
   *  in z-order. One list feeds BOTH registration paths — a tool listed here
   *  cannot be lost on style reload. */
  drawTools: Array<{ setupLayers: (map: any) => void }>
  routing: {
    routingVisible: Ref<boolean>
    routeGeoJSON: Ref<any>
    routeBounds: Ref<any>
    showRouteOnMap: (geojson: any, bounds: any) => void
  }
  currentOpenSkyMission: { value: string | undefined }
}) {
  const {
    highlight, openSky, satellite, iot, mesh, condo, hub, gov, church,
    transit, browse, drawTools, routing,
  } = opts
  const mapStore = useMapStore()
  const colorMode = useColorMode()

  /** Globe projection + sky/atmosphere config adapted to the current theme. */
  function applyGlobeAndSky(map: any) {
    map.setProjection({ type: 'globe' })
    const dark = colorMode.value === 'dark'
    map.setSky({
      'sky-color': dark ? '#0a0a1a' : '#88c0ec',
      'fog-color': dark ? '#0a0a1a' : '#88c0ec',
      'sky-horizon-blend': 0.4,
      'horizon-fog-blend': 0,
      'fog-ground-blend': 0,
      'atmosphere-blend': 0,
    })
  }

  /** First map load: full layer registration (data fetches included). */
  function setupInitial(map: any) {
    applyGlobeAndSky(map)
    // Layer order: highlight → markers → OpenSky → IoT → gov/church → transit → interactive (last, needs all layers)
    highlight.setupLayers(map)
    highlight.syncMarkers(map, mapStore)
    openSky.setupLayers(map, opts.currentOpenSkyMission.value)
    satellite.setupLayer(map) // below OpenSky raster (OpenSky wins on top)
    iot.setupLayers(map)
    mesh.setupLayers(map)
    condo.setupLayers(map)
    hub.setupLayers(map)
    const reRegister = () => highlight.setupInteractiveFeatures(map)
    gov.setupLayers(map, reRegister)
    church.setupLayers(map, reRegister)
    transit.setupLayers(map)
    for (const tool of drawTools) tool.setupLayers(map)
    highlight.setupInteractiveFeatures(map) // after all sync layers exist; async layers re-register via callback
  }

  /** After setStyle wiped all sources/layers: re-register without refetching. */
  function reapplyAfterStyleChange(map: any) {
    applyGlobeAndSky(map)
    highlight.setupLayers(map)
    openSky.setupLayers(map, opts.currentOpenSkyMission.value)
    satellite.setupLayer(map) // below OpenSky raster (OpenSky wins on top)
    // Re-enable tile grid if it was active before style change
    if (openSky.tileGridMode.value) {
      openSky.tileGridMode.value = false
      openSky.toggleTileGrid()
    }
    iot.setupLayersOnly(map)
    mesh.setupLayersOnly(map)
    condo.setupLayersOnly(map)
    hub.setupLayersOnly(map)
    gov.setupLayersOnly(map)
    church.setupLayersOnly(map)
    transit.resetDataLoaded()
    transit.setupLayers(map)
    transit.redrawActiveRoute(map) // setStyle wiped the single-route overlay
    browse.setupLayers(map)
    for (const tool of drawTools) tool.setupLayers(map)
    highlight.setupInteractiveFeatures(map) // after all layers
    highlight.syncMarkers(map, mapStore)
    // Restore the directions route overlay
    if (routing.routingVisible.value && routing.routeGeoJSON.value && routing.routeBounds.value) {
      routing.showRouteOnMap(routing.routeGeoJSON.value, routing.routeBounds.value)
    }
  }

  return { applyGlobeAndSky, setupInitial, reapplyAfterStyleChange }
}
