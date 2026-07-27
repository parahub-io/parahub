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
import { renderedPointCoords, renderedPointOffset } from '~/composables/useMapHighlight'

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
    selectedEnvStation: Ref<any>
    selectedCondominium: Ref<any>
    selectedHub: Ref<any>
    selectedEstablishment: Ref<any>
    entityPanelOpen: ComputedRef<boolean>
    clearEntityPanels: () => void
    closeFeaturePanel: () => void
  }
  iot: {
    showIoTLockOn: (lat: number, lon: number, offsetPx?: [number, number] | null) => void
    trackerPositionsList: Ref<any[]>
    getPanelPadding: () => any
  }
  avatar: {
    mapPresenceEnabled: Ref<boolean>
    currentAvatarType: Ref<string>
    nearbyAvatars: Ref<any[]>
    ownAvatarGeoPosition: Ref<{ lat: number; lon: number } | null>
    handleAvatarClick: (avatar: any, isOwn?: boolean) => void
  }
  highlight: {
    clearActiveFeature: (map: any) => void
    setActiveFeature: (map: any, feature: any) => void
  }
  updateUrlWithMapState: (lat: number, lng: number, feature?: any) => void
  /** True when a live transit vehicle sits under the point (deck.gl overlay
   * pick — vehicles are not MapLibre layers, queryRenderedFeatures is blind
   * to them). The overlay's own click handler opens the vehicle panel. */
  transitPick?: (point: { x: number; y: number }) => boolean
}) {
  const {
    animationEnabled, searchLanguage, interceptWhenActive,
    routing, browse, panels, iot, avatar, highlight, updateUrlWithMapState,
  } = opts
  const { routingVisible, awaitingMapClick, routingOrigin, routingDest } = routing
  const { browseVisible, browseWasOpen } = browse
  const {
    selectedVehicle, selectedIoTDevice, selectedEnvStation,
    selectedCondominium, selectedHub, selectedEstablishment,
    entityPanelOpen, clearEntityPanels, closeFeaturePanel,
  } = panels
  const { trackerPositionsList } = iot
  const { mapPresenceEnabled, currentAvatarType, nearbyAvatars, ownAvatarGeoPosition, handleAvatarClick } = avatar

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

      // If clicked on a transit vehicle, let the deck overlay's own click
      // handler handle it (skip OSM panel)
      if (opts.transitPick?.(event.point)) return

      // Marker-panel dispatch: first hit wins, order = visual priority.
      // The panel is open by the time the camera moves, so the fly carries the
      // panel padding — the marker lands in the center of the UNOBSCURED area.
      const flyToMarker = (coords: any, targetZoom: number) => {
        const zoom = Math.max(map.getZoom(), targetZoom)
        const padding = iot.getPanelPadding()
        if (animationEnabled.value !== false) {
          map.flyTo({ center: coords, zoom, essential: true, speed: 4.5, padding })
        } else {
          map.jumpTo({ center: coords, zoom, padding })
        }
      }
      const lngLatOf = (coords: any) => coords ? { lng: coords[0], lat: coords[1] } : null
      // open() receives the true geometry anchor + the constant screen-px
      // fan-out offset of ensemble members (renderedPointOffset). Lock-on
      // markers anchor on the geo point and carry the offset in px so they
      // track the icon across zooms; the camera flies to the merged
      // (zoom-baked) rendered position instead.
      const markerPanels: Array<{ layers: string[]; zoom: number; open: (f: any, anchor: any, lockOnOffset: [number, number] | null) => void }> = [
        {
          // IoT devices (before avatars — IoT uses exact pixel hit, avatars use radius)
          layers: ['trackers-circle', 'mesh-routers-circle', 'mesh-public-icon', 'energy-cells-circle'],
          zoom: 17,
          open: (f, anchor, lockOnOffset) => {
            const layerId = f.layer?.id || ''
            const deviceType = layerId.startsWith('trackers') ? 'tracker' : layerId.startsWith('mesh-') ? 'mesh_router' : 'energy_cell'
            const trackerEntry = deviceType === 'tracker'
              ? trackerPositionsList.value.find((tp: any) => tp.device_id === f.properties?.device_id)
              : null
            selectedIoTDevice.value = {
              deviceType,
              // Energy-cell features carry `id` (EnergyCell ULID), not device_id
              device_id: f.properties?.device_id || f.properties?.id || '',
              name: f.properties?.name || '',
              status: f.properties?.status || 'unknown',
              speed: f.properties?.speed || '',
              firmware_role: f.properties?.firmware_role || '',
              hardware_profile: f.properties?.hardware_profile || '',
              price: f.properties?.price || '',
              owner_name: f.properties?.owner_name || '',
              owner_cri: f.properties?.owner_cri || '',
              lngLat: lngLatOf(anchor),
              lockOnOffset,
              last_update: trackerEntry?.last_update || null,
            }
            if (anchor) iot.showIoTLockOn(anchor[1], anchor[0], lockOnOffset)
          },
        },
        {
          // Environmental stations (weather + air quality) — open the standard panel
          layers: ['env-stations-icon'],
          zoom: 15,
          open: (f, anchor, lockOnOffset) => {
            let latest: any = {}
            try { latest = JSON.parse(f.properties?.latestJson || '{}') } catch { latest = {} }
            selectedEnvStation.value = {
              id: f.properties?.id || '',
              name: f.properties?.name || '',
              source: f.properties?.source || '',
              latest,
              last_reading_at: f.properties?.lastReadingAt || null,
              public_url: f.properties?.publicUrl || '',
              owner_name: f.properties?.ownerName || '',
              owner_cri: f.properties?.ownerCri || '',
              lngLat: lngLatOf(anchor),
              lockOnOffset,
            }
            if (anchor) iot.showIoTLockOn(anchor[1], anchor[0], lockOnOffset)
          },
        },
        {
          layers: ['condos-circle'],
          zoom: 17,
          open: (f, anchor) => {
            selectedCondominium.value = {
              id: f.properties?.id || '',
              name: f.properties?.name || '',
              slug: f.properties?.slug || '',
              full_address: f.properties?.full_address || '',
              fraction_count: f.properties?.fraction_count || 0,
              member_count: f.properties?.member_count || 0,
              lngLat: lngLatOf(anchor),
            }
          },
        },
        {
          layers: ['hubs-circle'],
          zoom: 17,
          open: (f, anchor) => {
            selectedHub.value = {
              id: f.properties?.id || '',
              name: f.properties?.name || '',
              slug: f.properties?.slug || '',
              hub_capacity: f.properties?.hub_capacity || 0,
              hub_accepted_sizes: f.properties?.hub_accepted_sizes || '',
              hub_storage_fee_daily: f.properties?.hub_storage_fee_daily || '0',
              opening_hours: f.properties?.opening_hours || '',
              phone: f.properties?.phone || '',
              lngLat: lngLatOf(anchor),
            }
          },
        },
        {
          layers: ['government-icon', 'churches-icon'],
          zoom: 16,
          open: (f, anchor) => {
            const layerId = f.layer?.id || ''
            selectedEstablishment.value = {
              id: f.properties?.id || '',
              name: f.properties?.name || '',
              slug: f.properties?.slug || '',
              // kind feeds the ?device= deep-link (category_label is localized)
              kind: layerId === 'churches-icon' ? 'church' : 'gov',
              category_label: layerId === 'churches-icon' ? t('map.layers.churches') : t('map.layers.government'),
              municipality: f.properties?.municipality || '',
              lngLat: lngLatOf(anchor),
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
        const anchor = (f.geometry as any)?.coordinates ?? null
        const lockOnOffset = renderedPointOffset(f)
        // Camera target: rendered position (honors fanned-out co-located icons)
        const coords = renderedPointCoords(map, f) ?? anchor
        clearEntityPanels()
        spec.open(f, anchor, lockOnOffset)
        if (coords) flyToMarker(coords, spec.zoom)
        return
      }

      // Check if click was on avatar (after IoT — IoT uses exact pixel hit, avatars use radius)
      const clickRadius = 32
      const ownClickRadius = 48
      if (authStore.activeProfile?.id && mapPresenceEnabled.value) {
        // Own avatar renders at its animated position, which lags map center
        // during pan and the run-to-center animation
        const ownPos = ownAvatarGeoPosition.value
          ?? (() => { const c = map.getCenter(); return { lat: c.lat, lon: c.lng } })()
        const ownPoint = map.project([ownPos.lon, ownPos.lat])
        const dx = event.point.x - ownPoint.x
        const dy = event.point.y - ownPoint.y
        if (Math.sqrt(dx * dx + dy * dy) <= ownClickRadius) {
          handleAvatarClick({
            profile_id: authStore.activeProfile.id, lat: ownPos.lat, lon: ownPos.lon,
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
        if (layerId.startsWith('trackers-') || layerId.startsWith('mesh-routers-') || layerId.startsWith('mesh-public-') || layerId.startsWith('energy-cells-') || layerId.startsWith('env-stations-') || layerId.startsWith('condos-')) return false
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
        selectedEnvStation.value = null
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
