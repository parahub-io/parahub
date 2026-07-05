/**
 * Single map 'click' handler for MapView, routing a click through the
 * priority chain:
 *   1. draw-tool intercept — active tools own their clicks via their own
 *      map handlers (sun study is slider-driven, so it does not intercept)
 *   2. routing waypoint pick (reverse-geocoded origin/destination)
 *   3. transit vehicle — delegated to the vehicle layer's own click handler
 *   4. marker panels: IoT devices / condominiums / hubs / government+church
 *      (spec table; first hit wins, order = visual priority)
 *   5. avatars — own avatar by center radius, others by position radius
 *   6. OSM feature panel open, or close-everything fallback on empty ground
 *
 * clearEntityPanels (shared, useMapEntityPanels) wipes ALL sibling entity
 * panels — the panel component renders by priority, so a stale sibling left
 * set would "resurface" when the top panel closes.
 */
import type { Ref, ComputedRef } from 'vue'

export function useMapClickDispatcher(opts: {
  animationEnabled: Ref<boolean>
  searchLanguage: Ref<string>
  /** Active-state refs of tools that fully own map clicks while active */
  interceptWhenActive: Array<Ref<boolean>>
  routing: {
    routingVisible: Ref<boolean>
    awaitingMapClick: Ref<'origin' | 'dest' | null>
    routingOrigin: Ref<any>
    routingDest: Ref<any>
  }
  browse: { browseVisible: Ref<boolean>; browseWasOpen: Ref<boolean> }
  panels: {
    selectedVehicle: Ref<any>
    selectedIoTDevice: Ref<any>
    selectedCondominium: Ref<any>
    selectedHub: Ref<any>
    selectedEstablishment: Ref<any>
    entityPanelOpen: ComputedRef<boolean>
    clearEntityPanels: () => void
    closeFeaturePanel: () => void
  }
  iot: {
    showIoTLockOn: (lat: number, lon: number) => void
    trackerPositionsList: Ref<any[]>
  }
  avatar: {
    mapPresenceEnabled: Ref<boolean>
    currentAvatarType: Ref<string>
    nearbyAvatars: Ref<any[]>
    handleAvatarClick: (avatar: any, isOwn?: boolean) => void
  }
  highlight: {
    clearActiveFeature: (map: any) => void
    setActiveFeature: (map: any, feature: any) => void
  }
  updateUrlWithMapState: (lat: number, lng: number, feature?: any) => void
}) {
  const {
    animationEnabled, searchLanguage, interceptWhenActive,
    routing, browse, panels, iot, avatar, highlight, updateUrlWithMapState,
  } = opts
  const { routingVisible, awaitingMapClick, routingOrigin, routingDest } = routing
  const { browseVisible, browseWasOpen } = browse
  const {
    selectedVehicle, selectedIoTDevice, selectedCondominium, selectedHub, selectedEstablishment,
    entityPanelOpen, clearEntityPanels, closeFeaturePanel,
  } = panels
  const { trackerPositionsList } = iot
  const { mapPresenceEnabled, currentAvatarType, nearbyAvatars, handleAvatarClick } = avatar

  const { t } = useI18n()
  const authStore = useAuthStore()
  const { setSelectedFeature, setClickedFeatures, setClickCoordinates } = useMapState()

  const attach = (map: any) => {
    map.on('click', (event: any) => {
      // Intercept click for architect tools (handled by composable's own handlers)
      if (interceptWhenActive.some(active => active.value)) return

      // Intercept click for routing waypoints
      if (awaitingMapClick.value) {
        const which = awaitingMapClick.value
        const lngLat = event.lngLat
        $fetch<any>(`/api/v1/geo/geocode/search?q=${lngLat.lat.toFixed(6)},${lngLat.lng.toFixed(6)}&limit=1&lang=${searchLanguage.value}`)
          .then((data: any) => {
            const label = data?.features?.[0]?.properties?.label || `${lngLat.lat.toFixed(5)}, ${lngLat.lng.toFixed(5)}`
            const point = { lat: lngLat.lat, lon: lngLat.lng, name: label }
            if (which === 'origin') routingOrigin.value = point
            else routingDest.value = point
          })
          .catch(() => {
            const point = { lat: lngLat.lat, lon: lngLat.lng, name: `${lngLat.lat.toFixed(5)}, ${lngLat.lng.toFixed(5)}` }
            if (which === 'origin') routingOrigin.value = point
            else routingDest.value = point
          })
        awaitingMapClick.value = null
        return
      }

      // If clicked on a transit vehicle, let the vehicle handler handle it (skip OSM panel)
      const vehicleHit = map.queryRenderedFeatures(event.point, { layers: ['transit-vehicles-circle', 'transit-vehicles-icon', 'transit-vehicles-heading', 'transit-vehicles-bar'].filter(id => map.getLayer(id)) })
      if (vehicleHit?.length > 0) return

      // Marker-panel dispatch: first hit wins, order = visual priority.
      const flyToMarker = (coords: any, targetZoom: number) => {
        const zoom = Math.max(map.getZoom(), targetZoom)
        if (animationEnabled.value !== false) {
          map.flyTo({ center: coords, zoom, essential: true, speed: 4.5 })
        } else {
          map.jumpTo({ center: coords, zoom })
        }
      }
      const lngLatOf = (coords: any) => coords ? { lng: coords[0], lat: coords[1] } : null
      const markerPanels: Array<{ layers: string[]; zoom: number; open: (f: any, coords: any) => void }> = [
        {
          // IoT devices (before avatars — IoT uses exact pixel hit, avatars use radius)
          layers: ['trackers-circle', 'mesh-routers-circle', 'energy-cells-circle'],
          zoom: 17,
          open: (f, coords) => {
            const layerId = f.layer?.id || ''
            const deviceType = layerId.startsWith('trackers') ? 'tracker' : layerId.startsWith('mesh-routers') ? 'mesh_router' : 'energy_cell'
            const trackerEntry = deviceType === 'tracker'
              ? trackerPositionsList.value.find((tp: any) => tp.device_id === f.properties?.device_id)
              : null
            selectedIoTDevice.value = {
              deviceType,
              device_id: f.properties?.device_id || '',
              name: f.properties?.name || '',
              status: f.properties?.status || 'unknown',
              speed: f.properties?.speed || '',
              firmware_role: f.properties?.firmware_role || '',
              hardware_profile: f.properties?.hardware_profile || '',
              price: f.properties?.price || '',
              lngLat: lngLatOf(coords),
              last_update: trackerEntry?.last_update || null,
            }
            if (coords) iot.showIoTLockOn(coords[1], coords[0])
          },
        },
        {
          layers: ['condos-circle'],
          zoom: 17,
          open: (f, coords) => {
            selectedCondominium.value = {
              id: f.properties?.id || '',
              name: f.properties?.name || '',
              slug: f.properties?.slug || '',
              full_address: f.properties?.full_address || '',
              fraction_count: f.properties?.fraction_count || 0,
              member_count: f.properties?.member_count || 0,
              lngLat: lngLatOf(coords),
            }
          },
        },
        {
          layers: ['hubs-circle'],
          zoom: 17,
          open: (f, coords) => {
            selectedHub.value = {
              id: f.properties?.id || '',
              name: f.properties?.name || '',
              slug: f.properties?.slug || '',
              hub_capacity: f.properties?.hub_capacity || 0,
              hub_accepted_sizes: f.properties?.hub_accepted_sizes || '',
              hub_storage_fee_daily: f.properties?.hub_storage_fee_daily || '0',
              opening_hours: f.properties?.opening_hours || '',
              phone: f.properties?.phone || '',
              lngLat: lngLatOf(coords),
            }
          },
        },
        {
          layers: ['government-icon', 'churches-icon'],
          zoom: 16,
          open: (f, coords) => {
            const layerId = f.layer?.id || ''
            selectedEstablishment.value = {
              id: f.properties?.id || '',
              name: f.properties?.name || '',
              slug: f.properties?.slug || '',
              category_label: layerId === 'churches-icon' ? t('map.layers.churches') : t('map.layers.government'),
              municipality: f.properties?.municipality || '',
              lngLat: lngLatOf(coords),
            }
          },
        },
      ]
      for (const spec of markerPanels) {
        const layers = spec.layers.filter(id => map.getLayer(id))
        if (!layers.length) continue
        const hit = map.queryRenderedFeatures(event.point, { layers })
        if (!hit?.length) continue
        const f = hit[0]
        const coords = (f.geometry as any)?.coordinates
        clearEntityPanels()
        spec.open(f, coords)
        if (coords) flyToMarker(coords, spec.zoom)
        return
      }

      // Check if click was on avatar (after IoT — IoT uses exact pixel hit, avatars use radius)
      const clickRadius = 32
      const ownClickRadius = 48
      if (authStore.activeProfile?.id && mapPresenceEnabled.value) {
        const center = map.getCenter()
        const centerPoint = map.project([center.lng, center.lat])
        const dx = event.point.x - centerPoint.x
        const dy = event.point.y - centerPoint.y
        if (Math.sqrt(dx * dx + dy * dy) <= ownClickRadius) {
          handleAvatarClick({
            profile_id: authStore.activeProfile.id, lat: center.lat, lon: center.lng,
            zoom: 14, avatar_type: currentAvatarType.value, avatar_state: 'idle',
            speech_bubble: '', profile_hna: '', profile_name: 'You'
          }, true)
          return
        }
      }

      for (const av of nearbyAvatars.value) {
        if (!av.lat || !av.lon) continue
        if (av.profile_id === authStore.activeProfile?.id) continue
        const avatarPoint = map.project([av.lon, av.lat])
        const dx = event.point.x - avatarPoint.x
        const dy = event.point.y - avatarPoint.y
        if (Math.sqrt(dx * dx + dy * dy) <= clickRadius) {
          handleAvatarClick(av, false)
          return
        }
      }

      // Query all features at click point
      const allFeatures = map.queryRenderedFeatures(event.point)
      highlight.clearActiveFeature(map)

      let features = allFeatures?.filter((f: any) => {
        const layerId = f.layer?.id || ''
        if (layerId.endsWith('-hover') || layerId.endsWith('-active')) return false
        if (layerId.includes('_casing')) return false
        if (layerId === 'map-presence-layer' || layerId === 'map-presence-bubbles') return false
        if (layerId === 'poi-hover-hex-layer') return false
        if (layerId.startsWith('transit-vehicles')) return false
        if (layerId.startsWith('trackers-') || layerId.startsWith('mesh-routers-') || layerId.startsWith('energy-cells-') || layerId.startsWith('condos-')) return false
        return true
      }) || []

      const seen = new Set()
      features = features.filter((f: any) => {
        const key = `${f.sourceLayer || 'unknown'}_${f.id || Math.random()}`
        if (seen.has(key)) return false
        seen.add(key)
        return true
      })

      // Mobile: a deliberately-selected entity panel (IoT / vehicle / avatar / condo / hub /
      // establishment) must be DISMISSED by tapping the map, not hijacked by an OSM feature
      // underneath it (e.g. tapping near a tracker at z17 lands on a forest landcover polygon).
      // The bottom sheet slides away as expected. OSM→OSM swap (selectedFeature open) is preserved.
      if (entityPanelOpen.value && typeof window !== 'undefined' && window.innerWidth < 768) {
        closeFeaturePanel()
        return
      }

      if (features.length > 0) {
        let feature = features[0]
        if (feature.sourceLayer === 'housenumber') {
          const buildingFeature = features.find((f: any) => f.sourceLayer === 'building')
          if (buildingFeature) feature = buildingFeature
        }
        selectedVehicle.value = null
        selectedIoTDevice.value = null
        selectedCondominium.value = null
        selectedHub.value = null
        selectedEstablishment.value = null
        highlight.setActiveFeature(map, feature)
        if (routingVisible.value) routingVisible.value = false
        if (browseVisible.value) { browseWasOpen.value = true; browseVisible.value = false }
        setClickedFeatures(features)
        setSelectedFeature(feature)
        setClickCoordinates({ lat: event.lngLat.lat, lng: event.lngLat.lng })
        updateUrlWithMapState(event.lngLat.lat, event.lngLat.lng, feature)
      } else {
        closeFeaturePanel()
      }
    })
  }

  return { attach }
}
