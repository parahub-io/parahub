/**
 * Entity-panel state for MapView: which map entity (vehicle / IoT device /
 * condominium / hub / establishment) has its side panel open, plus the shared
 * clear/close flows.
 *
 * Single source of truth for panel mutual exclusion: every "open X" flow must
 * go through clearEntityPanels() — MapFeaturePanel renders by priority, so a
 * stale sibling left set would "resurface" when the top panel closes (the old
 * per-site hand-maintained clear lists had drifted apart).
 */
import { ref, computed } from 'vue'
import type { Ref } from 'vue'

export function useMapEntityPanels(opts: {
  avatar: {
    clearAvatarPanel: () => void
    activeAvatarPanel: Ref<any>
    panelContentType: { value: any }
  }
  routing: { routingVisible: Ref<boolean> }
  browse: { browseVisible: Ref<boolean>; browseWasOpen: Ref<boolean> }
  iot: {
    hideIoTLockOn: () => void
    disableFollow: () => void
    clearTrail: (map: any) => void
  }
  openSky: { tileGridMode: Ref<boolean>; toggleMissionArea: () => void }
  isActive: Ref<boolean>
}) {
  const { avatar, routing, browse, iot, openSky, isActive } = opts
  const mapStore = useMapStore()
  const router = useRouter()
  const route = useRoute()
  const localePath = useLocalePath()
  const {
    currentMarker, setCurrentMarker,
    setSelectedFeature, setClickedFeatures, setClickCoordinates,
  } = useMapState()

  const selectedVehicle = ref<any>(null)
  const selectedIoTDevice = ref<any>(null)
  const selectedCondominium = ref<any>(null)
  const selectedHub = ref<any>(null)
  const selectedEstablishment = ref<any>(null)

  // Priority order mirrors MapFeaturePanel's rendering priority
  const panelContentTypeWithVehicle = computed(() => {
    if (selectedVehicle.value) return 'vehicle'
    if (selectedIoTDevice.value) return 'iot_device'
    if (selectedCondominium.value) return 'condominium'
    if (selectedHub.value) return 'hub'
    if (selectedEstablishment.value) return 'establishment'
    return avatar.panelContentType.value
  })

  const entityPanelOpen = computed(() =>
    !!selectedVehicle.value || !!selectedIoTDevice.value
    || !!selectedCondominium.value || !!selectedHub.value || !!selectedEstablishment.value
    || avatar.activeAvatarPanel.value !== null
  )

  const resetSelections = () => {
    setSelectedFeature(null)
    setClickedFeatures([])
    setClickCoordinates(null)
    avatar.clearAvatarPanel()
    selectedVehicle.value = null
    selectedIoTDevice.value = null
    selectedCondominium.value = null
    selectedHub.value = null
    selectedEstablishment.value = null
  }

  // "Open another panel" semantics: hide the routing panel but keep the drawn
  // route on the map; remember an open browse panel so "back" can restore it.
  const clearEntityPanels = () => {
    resetSelections()
    if (routing.routingVisible.value) routing.routingVisible.value = false
    if (browse.browseVisible.value) {
      browse.browseWasOpen.value = true
      browse.browseVisible.value = false
    }
  }

  const closeFeaturePanel = () => {
    resetSelections()
    // Remove search marker
    if (currentMarker.value && typeof currentMarker.value.remove === 'function') {
      currentMarker.value.remove()
      setCurrentMarker(null)
    }
    iot.hideIoTLockOn()
    iot.disableFollow()
    if (mapStore.mapInstance) iot.clearTrail(mapStore.mapInstance)
    browse.browseWasOpen.value = false
    if (openSky.tileGridMode.value) openSky.toggleMissionArea()
    if (isActive.value) {
      const center = mapStore.mapInstance?.getCenter()
      if (center) {
        const query: any = { lat: center.lat.toFixed(6), lng: center.lng.toFixed(6), zoom: mapStore.mapInstance?.getZoom().toFixed(2) }
        if (route.query.returnTo) query.returnTo = route.query.returnTo
        router.replace({ path: localePath('/map'), query })
      }
    }
  }

  const handleFeaturePanelBack = () => {
    resetSelections()
    iot.hideIoTLockOn()
    browse.browseVisible.value = true
    browse.browseWasOpen.value = false
  }

  return {
    selectedVehicle,
    selectedIoTDevice,
    selectedCondominium,
    selectedHub,
    selectedEstablishment,
    panelContentTypeWithVehicle,
    entityPanelOpen,
    clearEntityPanels,
    closeFeaturePanel,
    handleFeaturePanelBack,
  }
}
