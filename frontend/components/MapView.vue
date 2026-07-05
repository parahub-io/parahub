<template>
  <div
    v-show="!loading"
    class="map-view fullscreen"
    :class="{ 'no-animation': !animationEnabled }"
  >
    <!-- Map Container -->
    <div
      ref="miniMapContainer"
      class="mini-map-container"
    >
      <!-- Maplibre mini-map renders here -->
      <div ref="mapRoot" class="mini-map-root" role="application" :aria-label="$t('map.aria_interactive_map')"></div>

      <!-- WebGL unavailable fallback -->
      <MapWebglErrorOverlay v-if="webglError" @retry="reloadPage" />
      <!-- Cached screenshot overlay for instant KeepAlive restore -->
      <img class="map-snapshot-overlay" style="display: none" alt="" aria-hidden="true">

      <!-- Weather HUD: current conditions near the map centre (Open-Meteo).
           Top-right, offset left of the zoom/layer controls strip so it never
           sits under them. -->
      <div
        v-if="weatherHudVisible"
        class="absolute top-[10px] right-16 z-[1000]"
      >
        <MapWeatherWidget :data="weatherData" />
      </div>

      <!-- Back button + browse toggle row (when returnTo) -->
      <div
        v-if="route.query.returnTo && !selectedFeature && activeAvatarPanel === null && !selectedVehicle && !selectedIoTDevice && !selectedCondominium && !selectedEstablishment"
        class="absolute top-[4.5rem] left-4 z-[1001] flex items-center gap-2"
      >
        <button
          v-if="!browseVisible && !routingVisible"
          @click="openBrowsePanel"
          class="p-2.5 bg-white dark:bg-neutral-800 rounded-lg shadow-lg border border-neutral-200 dark:border-neutral-700 hover:shadow-xl transition-all"
          :title="$t('map.browse.toggle_tooltip')"
        >
          <Building2 class="w-5 h-5 text-neutral-700 dark:text-neutral-300" />
        </button>
        <button
          @click.stop="router.push(localePath(route.query.returnTo as string))"
          class="flex items-center gap-2 px-4 py-2.5 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 rounded-lg shadow-lg hover:shadow-xl transition-all border border-neutral-200 dark:border-neutral-700"
        >
          <ArrowLeft class="w-4 h-4" />
          <span class="text-sm font-medium">{{ $t('map.back_to_page') }}</span>
        </button>
      </div>

      <!-- Browse Panel (left sidebar) -->
      <MapBrowsePanel
        v-if="browseVisible"
        :map-instance="mapStore.mapInstance"
        :initial-category-id="browseCategoryId"
        :initial-category-name="browseCategoryName"
        :initial-category-icon="browseCategoryIcon"
        @close="closeBrowsePanel"
        @results="updateBrowseMarkers"
        @select="handleBrowseSelect"
        @category-cleared="handleBrowseCategoryCleared"
      />

      <!-- Routing Panel (left sidebar, same position as browse) -->
      <MapRoutingPanel
        v-if="routingVisible"
        @close="closeRoutingPanel"
        @route-ready="showRouteOnMap"
        @route-cleared="clearRouteFromMap"
      />

      <!-- Unified Search bar with Browse + Directions buttons -->
      <div class="search-with-directions" :class="{ 'panel-open': browseVisible || routingVisible, 'detail-panel-open': !!selectedFeature || activeAvatarPanel !== null || !!selectedVehicle || !!selectedIoTDevice || !!selectedCondominium || !!selectedEstablishment || (urbanActive && !!urbanResult) }">
        <button
          v-if="!route.query.returnTo"
          @click="openBrowsePanel"
          class="browse-fab"
          :class="{ active: browseVisible }"
          :title="$t('map.browse.toggle_tooltip')"
        >
          <Building2 class="w-5 h-5" />
        </button>
        <MapUnifiedSearch
          :panel-open="browseVisible || routingVisible || !!selectedFeature || activeAvatarPanel !== null || !!selectedVehicle"
          @category-selected="handleUnifiedCategorySelect"
          @establishment-selected="handleUnifiedEstablishmentSelect"
          @location-selected="onLocationSelected"
          @search-cleared="onSearchCleared"
          :lang="searchLanguage"
        />
        <button
          @click="toggleRoutingPanel"
          class="directions-fab"
          :class="{ active: routingVisible }"
          :title="$t('map.routing.title')"
        >
          <Route class="w-5 h-5" />
        </button>
      </div>

      <!-- Unified Feature Panel (OSM, avatar controls, profile view, vehicle) -->
      <MapFeaturePanel
        ref="featurePanelRef"
        :feature="selectedFeature"
        :all-features="clickedFeatures"
        :click-coordinates="clickCoordinates"
        :content-type="panelContentTypeWithVehicle"
        :avatar-data="panelAvatarData"
        :vehicle-data="selectedVehicle"
        :iot-device-data="selectedIoTDevice"
        :iot-following="iot.isFollowing.value"
        :condominium-data="selectedCondominium"
        :hub-data="selectedHub"
        :establishment-data="selectedEstablishment"
        :show-back-to-browse="browseWasOpen"
        @close="closeFeaturePanel"
        @back="handleFeaturePanelBack"
        @feature-selected="selectedFeature = $event"
        @search-location="handleSearchLocation"
        @establishment-selected="handleEstablishmentSelected"
        @avatar-type-change="handleAvatarTypeChange"
        @show-trail="handleShowTrail"
        @clear-trail="handleClearTrail"
        @trail-cursor="handleTrailCursor"
        @recenter-iot="handleRecenterIoT"
        @osm-resolved="handleOsmResolved"
      />

      <!-- Urban analysis result — rendered in the standard feature side panel
           (rotating drawn-plot preview on top, framing + edificability below). -->
      <MapFeaturePanel
        content-type="urban"
        :urban-result="urbanResult"
        :urban-polygon="urban.urbanPoints.value"
        :urban-formatted-area="urban.formattedArea.value"
        @close="urban.stopUrban()"
        @urban-redraw="urban.redraw()"
      />

      <!-- Highlighted item marker with blinking animation -->
      <div
        v-if="mapStore.highlightedItem && mapStore.animationsEnabled"
        class="highlight-marker"
        :style="highlightMarkerStyle"
      >
        <div class="highlight-box"></div>
      </div>

      <!-- Map Presence Overlay (MMORPG-style avatars) -->
      <MapPresenceOverlay
        v-if="authStore.isAuthenticated && mapPresenceEnabled"
        :map="mapStore.mapInstance"
        :avatars="nearbyAvatars"
        :own-profile-id="authStore.activeProfile?.id || null"
        :own-avatar-type="currentAvatarType"
        :own-speech-bubble="currentSpeechBubble"
        :own-avatar-state="currentAvatarState"
        :is-keyboard-moving="keyboard.isKeyboardMoving.value"
        :keyboard-direction="keyboard.keyboardDirection.value"
        @avatar-click="handleAvatarClick"
      />

      <!-- Right control strip (layers / tools / IoT popovers, OpenSky group) + mission plan bar -->
      <MapControls
        :top="customControlsTop"
        :open-sky="openSky" :satellite="satellite" :tiles3d="tiles3d" :transit="transit"
        :gov="gov" :church="church" :condo="condo" :hub="hub" :mesh="mesh" :iot="iot"
        :measure="measure" :sun-study="sunStudy" :isochrone="isochrone" :drone-reach="droneReach" :urban="urban"
        @select-tracker="selectAndFlyToTracker"
        @select-property="selectAndFlyToProperty"
      />

      <!-- Bottom-center tool bars (measure / sun study / isochrone / drone reach / urban) -->
      <MapToolbars :measure="measure" :sun-study="sunStudy" :isochrone="isochrone" :drone-reach="droneReach" :urban="urban" />

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onActivated, onDeactivated, onBeforeUnmount, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ArrowLeft, Building2, Route } from 'lucide-vue-next'
import { createGeolocationControl } from '~/composables/useGeolocationControl'
import { useMapKeyboard } from '~/composables/useMapKeyboard'
import { useMapHighlight } from '~/composables/useMapHighlight'
import { useMapIoTLayers } from '~/composables/useMapIoTLayers'
import { useMapOpenSky } from '~/composables/useMapOpenSky'
import { useMapTransitLayers } from '~/composables/useMapTransitLayers'
import { useMapBrowse } from '~/composables/useMapBrowse'
import { useMapRouting } from '~/composables/useMapRouting'
import { useMapAvatarPanel } from '~/composables/useMapAvatarPanel'
import { useMapCondoLayers } from '~/composables/useMapCondoLayers'
import { useMapMeshLayer } from '~/composables/useMapMeshLayer'
import { useMapSatelliteLayer } from '~/composables/useMapSatelliteLayer'
import { useMapGovernmentLayer } from '~/composables/useMapGovernmentLayer'
import { useMapChurchLayer } from '~/composables/useMapChurchLayer'
import { useMapMeasure } from '~/composables/useMapMeasure'
import { useMapSunStudy } from '~/composables/useMapSunStudy'
import { useMapIsochrone } from '~/composables/useMapIsochrone'
import { useMapDroneReach } from '~/composables/useMapDroneReach'
import { useMapUrbanAnalysis } from '~/composables/useMapUrbanAnalysis'

const router = useRouter()
const localePath = useLocalePath()
const route = useRoute()
const mapStore = useMapStore()
const authStore = useAuthStore()

// ======== Theme / Animation ========

const colorMode = useColorMode()
const mapStyle = computed(() => colorMode.value === 'dark' ? 'dark-liberty' : 'osm-liberty')

const animationEnabled = useLocalPref('animation_enabled', true)

// ======== Shared Map State ========

const { mapCenter, mapZoom } = useMapState()
const {
  currentMarker, selectedFeature, clickedFeatures, clickCoordinates,
  setCurrentMarker, setSelectedFeature, setClickedFeatures, setClickCoordinates,
} = useMapState()

// Search language from profile
const searchLanguage = ref('en')
watch(() => authStore.profile?.preferred_language, (newLang) => {
  if (newLang) searchLanguage.value = newLang
}, { immediate: true })

// ======== Composables ========

const highlight = useMapHighlight()

const browse = useMapBrowse({
  setSelectedFeature,
  setClickedFeatures,
  setClickCoordinates,
  animationEnabled,
})
const {
  browseVisible, browseWasOpen,
  browseCategoryId, browseCategoryName, browseCategoryIcon,
} = browse

const routing = useMapRouting({ browseVisible, animationEnabled })
const { routingVisible } = routing

const avatar = useMapAvatarPanel({
  browseVisible,
  browseWasOpen,
  setSelectedFeature,
  setClickedFeatures,
  setClickCoordinates,
})
const {
  mapPresenceEnabled, currentAvatarType, currentSpeechBubble, currentAvatarState,
  activeAvatarPanel, nearbyAvatars, isMapPresenceConnected,
  panelAvatarData,
  wrappedSetState, wrappedSetSpeechBubble,
} = avatar

// Current OpenSky mission filter from URL
const currentOpenSkyMission = computed(() => route.query.opensky_mission as string | undefined)

const openSky = useMapOpenSky(currentOpenSkyMission)

const iot = useMapIoTLayers()

const transit = useMapTransitLayers()

const mesh = useMapMeshLayer()
const satellite = useMapSatelliteLayer()
const condo = useMapCondoLayers()
const hub = useMapHubLayers()
const gov = useMapGovernmentLayer()
const church = useMapChurchLayer()
const tiles3d = useMap3DTiles()

// KeepAlive active state (needed by the panel/weather composables below)
const isActive = ref(true)

// ======== Entity panels (vehicle / IoT / condo / hub / establishment) ========

const panels = useMapEntityPanels({ avatar, routing, browse, iot, openSky, isActive })
const {
  selectedVehicle, selectedIoTDevice, selectedCondominium, selectedHub, selectedEstablishment,
  panelContentTypeWithVehicle, entityPanelOpen,
  clearEntityPanels, closeFeaturePanel, handleFeaturePanelBack,
} = panels

// Wire vehicle click → panel (mutual exclusion via the shared clear)
transit.setVehicleClickHandler((vehicle: any) => {
  clearEntityPanels()
  selectedVehicle.value = vehicle
})

const iotBridge = useMapIoTBridge({ selectedIoTDevice, clearEntityPanels, iot, animationEnabled })
const {
  selectAndFlyToTracker, selectAndFlyToProperty,
  handleShowTrail, handleClearTrail, handleTrailCursor, handleRecenterIoT,
} = iotBridge

const trackerPanelWs = useMapTrackerPanelWs({ selectedIoTDevice, iot })

// ======== Map Tools ========

const measure = useMapMeasure()
const { measureActive } = measure

const sunStudy = useMapSunStudy()
const { sunStudyActive } = sunStudy

const isochrone = useMapIsochrone()
const { isochroneActive } = isochrone

const droneReach = useMapDroneReach()
const { droneReachActive } = droneReach

const urban = useMapUrbanAnalysis()
const { urbanActive } = urban
const urbanResult = urban.result

// Weather HUD — current conditions near the map centre (Open-Meteo, cached).
// Hidden while any panel is open (the HUD sits where panels overlap).
const weatherHud = useMapWeatherHud({
  isActive,
  blocked: computed(() =>
    browseVisible.value || routingVisible.value || !!selectedFeature.value || entityPanelOpen.value
  ),
})
const { weatherData, weatherHudVisible } = weatherHud

const customControlsTop = ref('250px') // updated dynamically after map init

// ======== Layer stack (initial registration + style-reload re-registration) ========

const layerStack = useMapLayerStack({
  highlight, openSky, satellite, iot, mesh, condo, hub, gov, church,
  transit, browse,
  // Draw tools in z-order; one list feeds both registration paths
  drawTools: [measure, sunStudy, isochrone, droneReach, urban],
  routing, currentOpenSkyMission,
})

// ======== Template aliases ========

const toggleRoutingPanel = () => {
  if (!routingVisible.value) {
    // Opening routing → close other panels (mutual exclusion)
    closeFeaturePanel()
    if (browseVisible.value) closeBrowsePanel()
  }
  routing.togglePanel()
}
const closeRoutingPanel = () => routing.closePanel()
const showRouteOnMap = routing.showRouteOnMap
const clearRouteFromMap = routing.clearRouteFromMap
const closeBrowsePanel = () => browse.closePanel()
const updateBrowseMarkers = (results: any[]) => browse.updateMarkers(results)
const handleBrowseSelect = (est: any) => browse.handleSelect(est)
const handleBrowseCategoryCleared = () => browse.handleCategoryCleared()
const handleAvatarClick = avatar.handleAvatarClick
const handleAvatarTypeChange = avatar.handleAvatarTypeChange

const openBrowsePanel = () => {
  if (browseVisible.value) {
    closeBrowsePanel()
    return
  }
  // Mutual exclusion: routing closes fully (route cleared off the map),
  // entity panels clear via the shared reset.
  if (routingVisible.value) routing.closePanel()
  clearEntityPanels()
  browseVisible.value = true
}

// ======== Refs ========

const miniMapContainer = ref<HTMLDivElement | null>(null)
const mapRoot = ref<HTMLDivElement | null>(null)
const featurePanelRef = ref<any>(null)
const loading = ref(true)
const webglError = ref(false)
const reloadPage = () => { if (typeof window !== 'undefined') window.location.reload() }
let miniMap: any = null

// KeepAlive snapshot state (isActive is declared above, before the composables)
let snapshotImgEl: HTMLImageElement | null = null
let cachedCanvasSnapshot: string | null = null

// Highlighted item marker positioning
const highlightMarkerStyle = computed(() => {
  if (!mapStore.highlightedItem || !mapStore.userLocation) return {}
  return { left: '50%', top: '50%', transform: 'translate(-50%, -50%)' }
})

// ======== Keyboard ========

const keyboard = useMapKeyboard({
  getMap: () => miniMap,
  isActive,
  mapPresenceEnabled,
  authStore,
  presenceActions: { setState: wrappedSetState, setSpeechBubble: wrappedSetSpeechBubble },
  currentSpeechBubble,
  currentAvatarState,
  currentAvatarType,
  activeAvatarPanel: avatar.activeAvatarPanel,
  selectedOtherAvatar: avatar.selectedOtherAvatar,
  setSelectedFeature,
  setClickedFeatures,
  setClickCoordinates,
  featurePanelRef,
})

// ======== URL ⇄ map sync (query building, deep-link pendings, position saves) ========

const urlSync = useMapUrlSync({
  getMap: () => miniMap,
  isActive,
  currentOpenSkyMission,
  transit,
  routing,
  browse,
  closeFeaturePanel,
})
const handleOsmResolved = urlSync.handleOsmResolved
const handleEstablishmentSelected = urlSync.handleEstablishmentSelected

// ======== Map click dispatch (priority chain in useMapClickDispatcher) ========

const clickDispatcher = useMapClickDispatcher({
  animationEnabled,
  searchLanguage,
  // Tools that own map clicks while active (sun study is slider-driven)
  interceptWhenActive: [measureActive, isochroneActive, droneReachActive, urbanActive],
  routing,
  browse,
  panels,
  iot,
  avatar,
  highlight,
  updateUrlWithMapState: urlSync.updateUrlWithMapState,
})

// ======== Search handlers ========

const onLocationSelected = async (location: any) => {
  if (!miniMap) return
  const lngLat = [location.lon, location.lat]
  if (currentMarker.value && typeof currentMarker.value.remove === 'function') currentMarker.value.remove()
  // Zoom based on result type: city/region → 13, neighbourhood → 15, default → 17
  const layer = location.raw?.properties?.layer || ''
  const targetZoom = ['locality', 'localadmin', 'region', 'country'].includes(layer) ? 13
    : ['borough', 'neighbourhood', 'macrohood'].includes(layer) ? 15
    : 17
  if (animationEnabled.value) {
    miniMap.flyTo({ center: lngLat, zoom: targetZoom, essential: true, speed: 4.5 })
  } else {
    miniMap.jumpTo({ center: lngLat, zoom: targetZoom })
  }
  try {
    const maplibreModule = await import('maplibre-gl')
    const maplibregl = maplibreModule.default || maplibreModule
    const { createLockOnElement } = await import('~/utils/lockOnMarker')
    const marker = new maplibregl.Marker({ element: createLockOnElement({ noDot: true }), anchor: 'center' }).setLngLat(lngLat).addTo(miniMap)
    setCurrentMarker(marker)
  } catch (err) {
    console.error('[MapView] Failed to add marker:', err)
  }
}

const handleSearchLocation = async (query: string) => {
  try {
    const response = await fetch(`/api/v1/geo/geocode/search?q=${encodeURIComponent(query)}&limit=1&lang=${searchLanguage.value}`)
    const data = await response.json()
    if (data.features && data.features.length > 0) {
      const feature = data.features[0]
      await onLocationSelected({ lat: feature.geometry.coordinates[1], lon: feature.geometry.coordinates[0], name: feature.properties.name || feature.properties.street || query })
    } else {
      useToastStore().warning(`"${query}" not found in geocoder`)
    }
  } catch (error) {
    console.error('Error searching location:', error)
    useToastStore().error('Search failed')
  }
}

const onSearchCleared = () => {
  if (currentMarker.value && typeof currentMarker.value.remove === 'function') {
    currentMarker.value.remove()
    setCurrentMarker(null)
  }
}

// ======== Unified search handlers ========

const handleUnifiedCategorySelect = (cat: any) => {
  browse.handleCategorySelect(cat)
  if (routingVisible.value) { routing.closePanel(); routing.clearRoute() }
}

const handleUnifiedEstablishmentSelect = (est: any) => {
  browse.handleSelect(est)
}

// ======== Escape key — close topmost panel ========

const onEscapeKey = (e: KeyboardEvent) => {
  if (e.key !== 'Escape') return
  // Don't intercept if user is typing in an input/textarea
  const tag = (e.target as HTMLElement)?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA') return

  if (selectedFeature.value || selectedVehicle.value || selectedIoTDevice.value || selectedCondominium.value || selectedHub.value || selectedEstablishment.value) {
    closeFeaturePanel()
  } else if (avatar.activeAvatarPanel.value !== null) {
    avatar.clearAvatarPanel()
  } else if (browseVisible.value) {
    closeBrowsePanel()
  } else if (routingVisible.value) {
    routing.closePanel()
    routing.clearRoute()
  } else if (measureActive.value) {
    measure.stopMeasure()
  } else if (sunStudyActive.value) {
    sunStudy.stopSunStudy()
  } else if (isochroneActive.value) {
    isochrone.stopIsochrone()
  } else if (droneReachActive.value) {
    droneReach.stopDroneReach()
  } else if (urbanActive.value) {
    urban.stopUrban()
  } else {
    return // nothing to close
  }
  e.preventDefault()
}

// ======== Transit vehicle data sync (watcher) ========
transit.syncVehicleData()

// ======== onMounted ========

onMounted(async () => {
  await nextTick()
  document.addEventListener('keydown', onEscapeKey)

  if (!mapRoot.value) { console.error('[MapView] No map root element'); return }

  // Parse query params for initial map position, deep-link pendings
  urlSync.parseInitialQuery()

  try {
    const maplibreModule = await import('maplibre-gl')
    await import('maplibre-gl/dist/maplibre-gl.css')
    const maplibregl = maplibreModule.default || maplibreModule

    const styleMap: Record<string, string> = { 'osm-liberty': '/map-styles/liberty-parahub.json', 'dark-liberty': '/map-styles/dark-liberty-parahub.json' }
    const styleUrl = styleMap[mapStyle.value] || styleMap['osm-liberty']

    miniMap = new maplibregl.Map({
      container: mapRoot.value,
      style: styleUrl,
      center: mapCenter.value,
      zoom: mapZoom.value,
      interactive: true,
      attributionControl: false,
      trackResize: true,
      canvasContextAttributes: { preserveDrawingBuffer: true },
      fadeDuration: animationEnabled.value ? 150 : 0
    })

    miniMap.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
    loading.value = false
    await nextTick()
    miniMap.resize()

    // Controls — nav + geolocation merged into one visual group
    const navControl = new maplibregl.NavigationControl({ showCompass: true })
    miniMap.addControl(navControl, 'top-right')

    const GeolocationControl = createGeolocationControl(mapStore, animationEnabled)
    const geoControl = new GeolocationControl()
    miniMap.addControl(geoControl, 'top-right')

    // Move geolocation button into nav control group (avoids separate visual block)
    const topRight = miniMap.getContainer().querySelector('.maplibregl-ctrl-top-right')
    if (topRight) {
      const groups = topRight.querySelectorAll(':scope > .maplibregl-ctrl-group')
      if (groups.length >= 2) {
        const geoBtn = groups[1].querySelector('button')
        if (geoBtn) { groups[0].appendChild(geoBtn); groups[1].remove() }
      }
      // Position custom controls below nav group
      const navGroup = topRight.querySelector('.maplibregl-ctrl-group')
      if (navGroup) {
        const rect = navGroup.getBoundingClientRect()
        const mapRect = miniMap.getContainer().getBoundingClientRect()
        customControlsTop.value = (rect.bottom - mapRect.top + 10) + 'px'
      }
    }

    const attributionControl = new maplibregl.AttributionControl({
      compact: true,
      customAttribution: 'Weather: <a href="https://open-meteo.com/" target="_blank" rel="noopener">Open-Meteo</a>',
    })
    miniMap.addControl(attributionControl, 'bottom-right')

    const scaleControl = new maplibregl.ScaleControl({ maxWidth: 200 })
    miniMap.addControl(scaleControl, 'bottom-left')

    // Cache canvas snapshot on every idle for KeepAlive
    miniMap.on('idle', () => {
      if (isActive.value && miniMap) {
        try { cachedCanvasSnapshot = miniMap.getCanvas().toDataURL('image/jpeg', 0.8) } catch {}
      }
    })

    // Disable IoT follow mode when user drags the map
    miniMap.on('dragstart', () => { iot.disableFollow() })

    miniMap.on('load', () => {
      // Attribution: remove auto-expand, enable user-toggled expand via attrib-ready marker
      const attribEl = miniMap.getContainer().querySelector('.maplibregl-ctrl-attrib')
      if (attribEl) { attribEl.classList.remove('maplibregl-compact-show'); attribEl.classList.add('attrib-ready') }

      nextTick(() => {
        snapshotImgEl = miniMapContainer.value?.querySelector('.map-snapshot-overlay') as HTMLImageElement | null
      })
      mapStore.setMapInstance(miniMap)
      if (typeof window !== 'undefined') (window as any).mapInstance = miniMap

      // Globe + sky, then the full layer stack (ordering documented in useMapLayerStack)
      layerStack.setupInitial(miniMap)

      // Frame the OpenSky mission tile centered in the viewport (fitBounds + padding),
      // overriding the raw query center/zoom so the whole tile is framed on any screen.
      if (currentOpenSkyMission.value) {
        openSky.fitMissionBounds(miniMap, currentOpenSkyMission.value, { animate: false })
      }

      // Auto-enable transit + marker/route from /transit "Show on map"
      // (fresh mount: parseInitialQuery already centered the map → no recenter)
      urlSync.applyPendingTransitMarker({ recenter: false })

      browse.setupLayers(miniMap)

      // Initialize map presence
      if (authStore.isAuthenticated && mapPresenceEnabled.value) {
        avatar.initializeMapPresence(miniMap)
      }

      // Restore feature panel / open directions from URL
      urlSync.restorePendingFeature()
      urlSync.applyDirectionsFromQuery()

      // Dynamic 2D/3D building switching based on pitch
      miniMap.on('pitch', () => {
        const pitch = miniMap.getPitch()
        if (pitch > 0) {
          miniMap.setLayoutProperty('building', 'visibility', 'none')
          miniMap.setLayoutProperty('building-3d', 'visibility', 'visible')
        } else {
          miniMap.setLayoutProperty('building', 'visibility', 'visible')
          miniMap.setLayoutProperty('building-3d', 'visibility', 'none')
        }
      })
    })

    miniMap.on('error', (e: any) => { console.error('[MapView] Map error:', e) })

    // Watch for theme changes
    watch(mapStyle, async (newStyle) => {
      if (!miniMap) return
      await nextTick()
      const styleMap: Record<string, string> = { 'osm-liberty': '/map-styles/liberty-parahub.json', 'dark-liberty': '/map-styles/dark-liberty-parahub.json' }
      const newStyleUrl = styleMap[newStyle] || styleMap['osm-liberty']
      miniMap.once('style.load', () => {
        layerStack.reapplyAfterStyleChange(miniMap)
      })
      miniMap.setStyle(newStyleUrl)
    }, { flush: 'post' })

    // Watch for OpenSky mission filter changes
    watch(currentOpenSkyMission, async (newMissionId) => {
      if (!miniMap) return
      await openSky.setupLayers(miniMap, newMissionId)
      // Frame the mission tile centered (e.g. navigating from /opensky "Show on map").
      if (newMissionId) {
        const fitted = await openSky.fitMissionBounds(miniMap, newMissionId, { animate: true })
        // Fallback to raw query center/zoom if the tile's bounds are unknown.
        if (!fitted) {
          const lat = parseFloat(route.query.lat as string)
          const lng = parseFloat(route.query.lng as string)
          const zoom = parseFloat(route.query.zoom as string)
          if (!isNaN(lat) && !isNaN(lng)) {
            miniMap.flyTo({ center: [lng, lat], zoom: !isNaN(zoom) ? zoom : 17, speed: 4.5 })
          }
        }
      }
    })

    // Save map position changes to store+URL (debounced) + sync store → map
    urlSync.attachPositionSync(miniMap)

    // Weather HUD: moveend-driven refresh (debounced, cell-deduped) + initial reading.
    weatherHud.attach(miniMap)

    // WASD keyboard
    keyboard.attach()

    // Handle map clicks (priority chain: tools → routing pick → vehicles →
    // marker panels → avatars → OSM feature panel)
    clickDispatcher.attach(miniMap)

    // Watch for marker changes in store
    watch(() => mapStore.markers, () => { highlight.syncMarkers(miniMap, mapStore) }, { deep: true })

  } catch (err: any) {
    console.error('[MapView] Failed to initialize:', err)
    const msg = String(err?.message || err || '')
    if (msg.includes('WebGL') || msg.includes('webglcontextcreationerror')) {
      webglError.value = true
    }
    loading.value = false
  }
})

// ======== KeepAlive lifecycle ========

onActivated(() => {
  isActive.value = true
  if (!snapshotImgEl) {
    snapshotImgEl = miniMapContainer.value?.querySelector('.map-snapshot-overlay') as HTMLImageElement | null
  }
  const showingSnapshot = !!(cachedCanvasSnapshot && snapshotImgEl)
  if (showingSnapshot) {
    snapshotImgEl!.src = cachedCanvasSnapshot!
    snapshotImgEl!.style.display = ''
  }
  nextTick(() => {
    miniMap?.resize()
    if (showingSnapshot && miniMap) {
      miniMap.once('idle', () => {
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            if (snapshotImgEl) snapshotImgEl.style.display = 'none'
          })
        })
      })
      miniMap.triggerRepaint()
    }
    // Handle pending transit marker (set by reapplyQueryNavigation below or
    // left over from a mount whose 'load' never consumed it); the kept-alive
    // map sits wherever the user left it → recenter
    urlSync.applyPendingTransitMarker({ recenter: true })
  })

  iot.resumeRefresh()
  mesh.resumeRefresh()
  sunStudy.resumeSunStudy()
  keyboard.attach()
  document.addEventListener('keydown', onEscapeKey)

  // Re-apply query-driven navigation when re-entering the kept-alive map
  // (onMounted parses the query only on the first mount) — see useMapUrlSync.
  urlSync.reapplyQueryNavigation()

  if (authStore.isAuthenticated && mapPresenceEnabled.value) {
    avatar.initializeMapPresence(miniMap)
  }

  // Refresh weather for wherever the kept-alive map now sits (cell-deduped) and
  // resume the periodic re-poll.
  weatherHud.resume()
})

onDeactivated(() => {
  // Save map position immediately before deactivating —
  // the debounced saveMapPosition would be blocked by isActive=false
  if (miniMap) {
    const center = miniMap.getCenter()
    const { setMapCenter, setMapZoom } = useMapState()
    setMapCenter([center.lng, center.lat])
    setMapZoom(miniMap.getZoom())
  }
  isActive.value = false
  keyboard.detach()
  document.removeEventListener('keydown', onEscapeKey)
  iot.pauseRefresh()
  mesh.pauseRefresh()
  sunStudy.pauseSunStudy()
  if (droneReachActive.value) droneReach.stopDroneReach()
  if (urbanActive.value) urban.stopUrban()
  transit.disconnectWs()
  trackerPanelWs.disconnect()
  avatar.disconnectMapPresence?.()
  weatherHud.stopTimer()
})

// React to avatar toggle changes (from preferences or other pages)
watch(mapPresenceEnabled, (enabled) => {
  if (!miniMap || !authStore.isAuthenticated) return
  if (enabled) {
    avatar.initializeMapPresence(miniMap)
  } else {
    avatar.disconnectMapPresence?.()
  }
})

onBeforeUnmount(() => {
  highlight.cleanupMarkers()
  keyboard.detach()
  document.removeEventListener('keydown', onEscapeKey)
  iot.cleanup()
  mesh.pauseRefresh()
  transit.disconnectWs()
  trackerPanelWs.disconnect()
  tiles3d.dispose()
  if (isMapPresenceConnected.value) avatar.disconnectMapPresence()
  miniMap = null
})
</script>

<style scoped>
/* Base styles */
.map-view {
  position: fixed;
  z-index: 40;
}

/* Smooth transition only when animations enabled */
.map-view:not(.no-animation) {
  transition: all 0.3s ease;
  animation: map-reveal 0.4s cubic-bezier(0.16, 1, 0.3, 1) both;
}
@keyframes map-reveal {
  0% { opacity: 0; }
  40% { opacity: 1; }
  100% { opacity: 1; }
}

/* No animation when disabled - instant changes */
.map-view.no-animation {
  transition: none !important;
}

/* Fullscreen mode */
.map-view.fullscreen {
  top: calc(56px + var(--safe-area-inset-top, env(safe-area-inset-top, 0px))); /* Below navbar + safe area */
  left: 0;
  right: 0;
  bottom: var(--safe-area-inset-bottom, env(safe-area-inset-bottom, 0px));
  width: 100vw;
  height: calc(100vh - 56px - var(--safe-area-inset-top, env(safe-area-inset-top, 0px)) - var(--safe-area-inset-bottom, env(safe-area-inset-bottom, 0px)));
  border-radius: 0;
  border: none;
  background: transparent;
  box-shadow: none;
  z-index: 10; /* Below navbar (50) */
}
@media (min-width: 640px) {
  .map-view.fullscreen {
    top: calc(64px + var(--safe-area-inset-top, env(safe-area-inset-top, 0px)));
    height: calc(100vh - 64px - var(--safe-area-inset-top, env(safe-area-inset-top, 0px)) - var(--safe-area-inset-bottom, env(safe-area-inset-bottom, 0px)));
  }
}
@media (min-width: 768px) {
  .map-view.fullscreen {
    top: calc(80px + var(--safe-area-inset-top, env(safe-area-inset-top, 0px)));
    height: calc(100vh - 80px - var(--safe-area-inset-top, env(safe-area-inset-top, 0px)) - var(--safe-area-inset-bottom, env(safe-area-inset-bottom, 0px)));
  }
}

.mini-map-container {
  position: relative;
  width: 100%;
  height: 100%;
}

.mini-map-root {
  width: 100%;
  height: 100%;
  background: #1a1a3e;
}
:root.dark .mini-map-root {
  background: #0d0d1f;
}

.map-snapshot-overlay {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  z-index: 1;
  pointer-events: none;
}

/* User location marker (MapLibre marker) */
:deep(.user-location-marker) {
  width: 20px;
  height: 20px;
  position: relative;
  pointer-events: none;
}

:deep(.user-location-marker .user-marker-dot) {
  width: 12px;
  height: 12px;
  background: var(--color-secondary);
  border: 2px solid white;
  border-radius: 50%;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 2;
}

:deep(.user-location-marker .user-marker-pulse) {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 20px;
  height: 20px;
  margin: -10px 0 0 -10px;
  background: color-mix(in srgb, var(--color-primary) 40%, transparent);
  border-radius: 50%;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0% {
    transform: scale(0.8);
    opacity: 1;
  }
  100% {
    transform: scale(2.5);
    opacity: 0;
  }
}

/* Highlighted item marker (blinking rectangle) */
.highlight-marker {
  position: absolute;
  pointer-events: none;
  z-index: 9;
}

.highlight-box {
  width: 40px;
  height: 40px;
  border: 3px solid var(--color-error);
  border-radius: 4px;
  animation: blink 1s infinite;
  box-shadow: 0 0 10px color-mix(in srgb, var(--color-error) 60%, transparent);
}

@keyframes blink {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.3;
    transform: scale(1.1);
  }
}

/* Custom geolocation control styles */
:deep(.maplibregl-ctrl-geolocate) {
  background-color: var(--color-surface);
  background-image: none;
  border: 0;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 5px;
  color: var(--color-text);
}

:deep(.maplibregl-ctrl-geolocate:hover) {
  background-color: var(--color-primary-100, #fef9c3);
}

/* Yellow hover for zoom & compass buttons */
:deep(.maplibregl-ctrl-group button:hover) {
  background-color: var(--color-primary-100, #fef9c3);
}
:root.dark :deep(.maplibregl-ctrl-group button:hover) {
  background-color: var(--color-primary-900, #422006);
}
:root.dark :deep(.maplibregl-ctrl-geolocate:hover) {
  background-color: var(--color-primary-900, #422006);
}
/* Dark mode base styles for maplibregl-ctrl-group moved to main.css (global) */

:deep(.maplibregl-ctrl-geolocate-active) {
  color: var(--color-secondary) !important;
  background-color: color-mix(in srgb, var(--color-secondary) 10%, transparent) !important;
}

:deep(.maplibregl-ctrl-geolocate-error) {
  color: var(--color-error) !important;
  background-color: color-mix(in srgb, var(--color-error) 10%, transparent) !important;
}

:deep(.maplibregl-ctrl-geolocate svg) {
  display: block;
}

/* Attribution: collapsed by default, no flash on load */
:deep(.maplibregl-ctrl-attrib.maplibregl-compact) {
  min-height: 20px;
}
:deep(.maplibregl-ctrl-attrib.maplibregl-compact:not(.attrib-ready)) {
  padding: 2px 24px 2px 0;
}
:deep(.maplibregl-ctrl-attrib.maplibregl-compact .maplibregl-ctrl-attrib-inner) {
  display: none;
}
:deep(.maplibregl-ctrl-attrib.maplibregl-compact.attrib-ready.maplibregl-compact-show .maplibregl-ctrl-attrib-inner) {
  display: block;
}

/* Search + Directions FAB wrapper — aligned with feature panel (md:left-0 md:w-96) */
.search-with-directions {
  position: absolute;
  top: 14px;
  left: 20px;
  right: 80px;
  z-index: 1001;
  display: flex;
  align-items: flex-start;
  gap: 10px;
  max-width: 480px;
  pointer-events: none;
}

@media (min-width: 768px) {
  .search-with-directions {
    left: 10px;
    right: auto;
    max-width: calc(24rem - 10px); /* w-96 minus left offset, aligns right edge with panel */
  }
}

.search-with-directions > * {
  pointer-events: auto;
}

.search-with-directions :deep(.map-unified-search) {
  position: static;
  flex: 1;
  min-width: 0;
  max-width: none;
}

.browse-fab,
.directions-fab {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  border: none;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.15);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.2s;
}

.browse-fab,
.directions-fab {
  background: white;
  color: var(--color-text);
}

:root.dark .browse-fab,
:root.dark .directions-fab {
  background: #262626;
}

.browse-fab:hover,
.directions-fab:hover {
  background: var(--color-primary-100, #fef9c3);
}

:root.dark .browse-fab:hover,
:root.dark .directions-fab:hover {
  background: var(--color-primary-900, #422006);
}

.browse-fab.active,
.directions-fab.active {
  background: var(--color-primary);
  color: var(--color-neutral-900, #171717);
}

/* Desktop: hide search bar when detail panel is open (IoT, establishment, vehicle, etc.) */
@media (min-width: 768px) {
  .search-with-directions.detail-panel-open {
    display: none;
  }
}

/* Mobile */
@media (max-width: 640px) {
  .search-with-directions {
    left: 10px;
    right: 60px;
    max-width: none;
  }

  .browse-fab,
  .directions-fab {
    width: 40px;
    height: 40px;
  }
}

</style>
