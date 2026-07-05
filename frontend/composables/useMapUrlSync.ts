/**
 * URL ⇄ map synchronisation for MapView: one module for everything that reads
 * or writes the /map query string.
 *
 * map → URL: buildMapQuery serialises position + selected feature (+ sticky
 * params like opensky_mission / returnTo), written back on debounced
 * moveend/zoomend and on targeted panel events (osmId resolution,
 * establishment selection).
 *
 * URL → map: parseInitialQuery seeds the map position before the map exists
 * and stashes deep-link pendings on window (_pendingFeatureRestore /
 * _pendingTransitMarker); applyPendingTransitMarker / restorePendingFeature /
 * applyDirectionsFromQuery consume them once the map is ready; and
 * reapplyQueryNavigation re-runs query-driven navigation when re-entering the
 * kept-alive map (onMounted parses the query only on the first mount).
 *
 * attachPositionSync also mirrors external mapCenter/mapZoom store writes
 * onto the map, guarded against echo loops with the user-movement saves.
 */
import { watch } from 'vue'
import type { Ref } from 'vue'
import { debounce } from '~/utils/debounce'

export function useMapUrlSync(opts: {
  getMap: () => any
  isActive: Ref<boolean>
  currentOpenSkyMission: Ref<string | undefined>
  transit: {
    transitEnabled: Ref<boolean>
    enableLayerVisibility: (map: any) => void
    connectWs: () => void
    showRouteOnMap: (map: any, routeCity: string, routeSlug: string) => void
    removeRouteOverlay: (map: any) => void
    resetDataLoaded: () => void
  }
  routing: {
    routingVisible: Ref<boolean>
    routingOrigin: Ref<any>
    routingDest: Ref<any>
  }
  browse: { browseVisible: Ref<boolean>; closePanel: () => void }
  closeFeaturePanel: () => void
}) {
  const { getMap, isActive, currentOpenSkyMission, transit, routing, browse, closeFeaturePanel } = opts

  const router = useRouter()
  const route = useRoute()
  const localePath = useLocalePath()
  const { t } = useI18n()
  const mapStore = useMapStore()
  const {
    mapCenter, mapZoom, selectedFeature,
    setMapCenter, setMapZoom,
    setSelectedFeature, setClickedFeatures, setClickCoordinates,
  } = useMapState()

  // Dismissable bus-stop marker dropped by a transit deep-link
  let transitStopMarker: any = null

  // ======== map → URL ========

  const buildMapQuery = (lat: number, lng: number, zoom: number, feature?: any) => {
    const query: any = { lat: lat.toFixed(6), lng: lng.toFixed(6), zoom: zoom.toFixed(2) }
    if (feature?.sourceLayer) query.layer = feature.sourceLayer
    if (feature?.id) query.featureId = feature.id
    // Preserve osmId: from feature props, or keep existing URL value (set by handleOsmResolved)
    const osmId = feature?.properties?.osm_id || (feature ? route.query.osmId : undefined)
    if (osmId) query.osmId = String(osmId)
    // Preserve establishmentId while panel is open
    if (feature && route.query.establishmentId) query.establishmentId = route.query.establishmentId
    if (currentOpenSkyMission.value) query.opensky_mission = currentOpenSkyMission.value
    if (route.query.returnTo) query.returnTo = route.query.returnTo
    return query
  }

  const updateUrlWithMapState = (lat: number, lng: number, feature: any = null) => {
    const map = getMap()
    if (!map || !isActive.value) return
    router.replace({ path: localePath('/map'), query: buildMapQuery(lat, lng, map.getZoom(), feature) })
  }

  const handleOsmResolved = ({ osmId }: { osmId: number }) => {
    if (!getMap() || !isActive.value || !osmId) return
    const query = { ...route.query, osmId: String(osmId) }
    router.replace({ path: localePath('/map'), query })
  }

  const handleEstablishmentSelected = (establishmentId: string | null) => {
    const map = getMap()
    if (!map || !isActive.value) return
    const center = map.getCenter()
    const query = buildMapQuery(center.lat, center.lng, map.getZoom(), selectedFeature.value)
    if (establishmentId) query.establishmentId = establishmentId
    else delete query.establishmentId
    router.replace({ path: localePath('/map'), query })
  }

  // Echo-loop guards between the store→map watchers and the map→URL saves
  let isUpdatingFromUser = false
  let isUpdatingFromCode = false

  // Debounced user-movement → store + URL saves, plus store → map watchers.
  // Attached once the map exists (same lifetime as the map's own listeners).
  const attachPositionSync = (map: any) => {
    const saveMapPosition = debounce(() => {
      if (!getMap() || isUpdatingFromCode || !isActive.value) return
      isUpdatingFromUser = true
      const center = map.getCenter()
      const currentZoom = map.getZoom()
      setMapCenter([center.lng, center.lat])
      setMapZoom(currentZoom)
      const query = buildMapQuery(center.lat, center.lng, currentZoom, selectedFeature.value)
      router.replace({ path: localePath('/map'), query })
      setTimeout(() => { isUpdatingFromUser = false }, 100)
    }, 500)

    map.on('moveend', saveMapPosition)
    map.on('zoomend', saveMapPosition)

    watch(mapCenter, (center) => {
      const m = getMap()
      if (m && center && !isUpdatingFromUser) {
        isUpdatingFromCode = true
        m.setCenter(center)
        setTimeout(() => { isUpdatingFromCode = false }, 100)
      }
    })
    watch(mapZoom, (zoom) => {
      const m = getMap()
      if (m && zoom != null && !isUpdatingFromUser) {
        const currentZoom = m.getZoom()
        if (Math.abs(currentZoom - zoom) > 0.01) {
          isUpdatingFromCode = true
          m.setZoom(zoom)
          setTimeout(() => { isUpdatingFromCode = false }, 100)
        }
      }
    })
  }

  // ======== URL → map ========

  // Seed map position from the query before the map is created, and stash
  // deep-link pendings (?transit=1 marker/route, feature restore params).
  const parseInitialQuery = () => {
    if (!route.query) return
    const lat = parseFloat(route.query.lat as string)
    const lng = parseFloat(route.query.lng as string)
    const zoom = parseFloat(route.query.zoom as string)
    if (!isNaN(lat) && !isNaN(lng)) {
      setMapCenter([lng, lat])
      if (!isNaN(zoom)) setMapZoom(zoom)
      if (route.query.transit === '1') {
        transit.transitEnabled.value = true
        ;(window as any)._pendingTransitMarker = { lat, lng, routeCity: route.query.routeCity as string, routeSlug: route.query.routeSlug as string }
      }
      if (route.query.layer || route.query.featureId || route.query.osmId || route.query.establishmentId) {
        ;(window as any)._pendingFeatureRestore = { lat, lng, layer: route.query.layer, featureId: route.query.featureId, osmId: route.query.osmId, establishmentId: route.query.establishmentId }
      }
    } else {
      // Directions deep-link (?dest_lat/dest_lng): start centered on the
      // destination so there's no flash of the default location before
      // applyDirectionsFromQuery (called on map load) opens the panel.
      const dlat = parseFloat(route.query.dest_lat as string)
      const dlng = parseFloat(route.query.dest_lng as string)
      if (!isNaN(dlat) && !isNaN(dlng)) {
        setMapCenter([dlng, dlat])
        if (!isNaN(zoom)) setMapZoom(zoom)
      }
    }
  }

  // Restore the feature panel for a coordinate carried in the URL
  // (?establishmentId / layer / featureId / osmId). Shared by the first map
  // load and by onActivated, so it works whether the map is freshly mounted or
  // a kept-alive instance being re-entered.
  const restorePendingFeature = () => {
    if (!getMap() || !(window as any)._pendingFeatureRestore) return
    const pending = (window as any)._pendingFeatureRestore
    setTimeout(() => {
      const map = getMap()
      if (!map) return
      const point = map.project([pending.lng, pending.lat])
      const features = map.queryRenderedFeatures(point)
      if (features && features.length > 0) {
        let targetFeature = features[0]
        if (pending.layer) targetFeature = features.find((f: any) => f.sourceLayer === pending.layer) || features[0]
        if (pending.featureId) targetFeature = features.find((f: any) => f.id == pending.featureId) || targetFeature
        setClickedFeatures(features)
        setSelectedFeature(targetFeature)
        setClickCoordinates({ lat: pending.lat, lng: pending.lng })
        if (pending.establishmentId) (window as any)._pendingEstablishmentId = pending.establishmentId
      }
      delete (window as any)._pendingFeatureRestore
    }, 500)
  }

  // Open the directions panel with a destination carried in the URL
  // (?dest_lat / dest_lng / dest_name) — e.g. an org's "get directions" button.
  // Prefills origin from the user's known location so the route computes
  // immediately; otherwise the panel prompts for a starting point. Returns true
  // when the query carried a destination.
  const applyDirectionsFromQuery = () => {
    const dlat = parseFloat(route.query.dest_lat as string)
    const dlng = parseFloat(route.query.dest_lng as string)
    if (isNaN(dlat) || isNaN(dlng)) return false
    const name = (route.query.dest_name as string) || `${dlat.toFixed(5)}, ${dlng.toFixed(5)}`
    // Open the routing panel (mutual exclusion with the other left panels)
    closeFeaturePanel()
    if (browse.browseVisible.value) browse.closePanel()
    routing.routingVisible.value = true
    routing.routingDest.value = { lat: dlat, lon: dlng, name }
    // Prefill origin from the user's location when we already have it → route
    // computes right away via the useRouting watcher.
    if (!routing.routingOrigin.value && mapStore.userLocation) {
      const [olng, olat] = mapStore.userLocation
      routing.routingOrigin.value = { lat: olat, lon: olng, name: t('map.routing.use_my_location') }
    }
    const map = getMap()
    if (map) {
      const zoom = parseFloat(route.query.zoom as string)
      map.jumpTo({ center: [dlng, dlat], zoom: !isNaN(zoom) ? zoom : 15 })
    }
    return true
  }

  // Consume a pending transit deep-link (/transit "Show on map"): connect the
  // realtime WS, then draw the route overlay or drop a dismissable stop marker
  // with a crosshair flash. `recenter` additionally re-enables transit layer
  // visibility and jumps to the target — needed when re-entering the kept-alive
  // map, which sits wherever the user left it (a freshly mounted map already
  // starts at the query center via parseInitialQuery).
  const applyPendingTransitMarker = ({ recenter }: { recenter: boolean }) => {
    const map = getMap()
    if (!map || !(window as any)._pendingTransitMarker) return
    const { lat, lng, zoom, routeCity, routeSlug } = (window as any)._pendingTransitMarker
    delete (window as any)._pendingTransitMarker
    if (transitStopMarker) { transitStopMarker.remove(); transitStopMarker = null }
    if (recenter) {
      transit.enableLayerVisibility(map)
      map.jumpTo({ center: [lng, lat], zoom: !isNaN(zoom) ? zoom : 16 })
    }
    transit.connectWs()
    if (routeCity && routeSlug) {
      transit.showRouteOnMap(map, routeCity, routeSlug)
    } else {
      Promise.all([import('~/utils/lockOnMarker'), import('maplibre-gl')]).then(([{ createLockOnElement, flashCrosshair }, mod]) => {
        const maplibregl = mod.default || mod
        const el = createLockOnElement({ iconUrl: '/img/bus-stop.png', clickable: true })
        el.addEventListener('click', () => { marker.remove(); transitStopMarker = null })
        const marker = new maplibregl.Marker({ element: el, anchor: 'center' }).setLngLat([lng, lat]).addTo(map)
        transitStopMarker = marker
        setTimeout(() => {
          if (!transitStopMarker) return
          const pt = map.project([lng, lat])
          flashCrosshair(map.getContainer(), Math.round(pt.x), Math.round(pt.y))
        }, 450)
      })
    }
  }

  // Re-apply query-driven navigation when re-entering the kept-alive map.
  // onMounted (which parses lat/lng/zoom/establishmentId/layer) runs only on the
  // first mount, so without this a navigation like /map?lat=..&establishmentId=..
  // (e.g. clicking an org's map/address) would leave the kept-alive map sitting
  // at its previous position instead of recentering on the target. A transit
  // deep-link (?transit=1) instead re-stashes the pending marker, consumed by
  // applyPendingTransitMarker once the caller's nextTick runs.
  const reapplyQueryNavigation = () => {
    const map = getMap()
    if (map && route.query.transit !== '1' && !applyDirectionsFromQuery()) {
      const lat = parseFloat(route.query.lat as string)
      const lng = parseFloat(route.query.lng as string)
      const zoom = parseFloat(route.query.zoom as string)
      if (!isNaN(lat) && !isNaN(lng)) {
        const wantsFeature = !!(route.query.layer || route.query.featureId || route.query.osmId || route.query.establishmentId)
        const c = map.getCenter()
        const moved = Math.abs(c.lat - lat) > 1e-5 || Math.abs(c.lng - lng) > 1e-5
        if (moved || wantsFeature) {
          map.jumpTo({ center: [lng, lat], zoom: !isNaN(zoom) ? zoom : map.getZoom() })
        }
        if (wantsFeature) {
          ;(window as any)._pendingFeatureRestore = {
            lat, lng,
            layer: route.query.layer, featureId: route.query.featureId,
            osmId: route.query.osmId, establishmentId: route.query.establishmentId,
          }
          restorePendingFeature()
        }
      }
    }

    if (route.query.transit === '1') {
      const lat = parseFloat(route.query.lat as string)
      const lng = parseFloat(route.query.lng as string)
      if (!isNaN(lat) && !isNaN(lng)) {
        transit.transitEnabled.value = true
        if (map) transit.removeRouteOverlay(map)
        ;(window as any)._pendingTransitMarker = { lat, lng, zoom: parseFloat(route.query.zoom as string), routeCity: route.query.routeCity as string, routeSlug: route.query.routeSlug as string }
        transit.resetDataLoaded()
      }
    } else if (transit.transitEnabled.value && map) {
      transit.connectWs()
    }
  }

  return {
    updateUrlWithMapState,
    handleOsmResolved,
    handleEstablishmentSelected,
    attachPositionSync,
    parseInitialQuery,
    restorePendingFeature,
    applyDirectionsFromQuery,
    applyPendingTransitMarker,
    reapplyQueryNavigation,
  }
}
