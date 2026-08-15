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

      <!-- Effective camera-center reticle: marks where zoom buttons / flyTo
           center, shifting with panel padding so it always sits in the visual
           center of the unobscured map area -->
      <div v-if="!webglError" class="map-center-reticle" :style="reticleStyle" aria-hidden="true">
        <svg width="9" height="9" viewBox="0 0 9 9" shape-rendering="crispEdges">
          <g stroke="var(--color-primary)" stroke-width="1">
            <line x1="4.5" y1="0" x2="4.5" y2="3" />
            <line x1="4.5" y1="6" x2="4.5" y2="9" />
            <line x1="0" y1="4.5" x2="3" y2="4.5" />
            <line x1="6" y1="4.5" x2="9" y2="4.5" />
          </g>
        </svg>
      </div>

      <!-- Weather HUD: current conditions near the map centre (Open-Meteo).
           Bottom-right, stacked above the attribution ⓘ — the one corner no
           docked panel covers (panels dock left on desktop), so the HUD stays
           up while building/entity panels are open. It yields to the bottom
           tool bars (v-if) and, on phones, to bottom-sheet panels (CSS). -->
      <div
        v-if="weatherHudVisible"
        class="weather-hud-wrap"
        :class="{ 'panel-open': weatherHudPanelOpen }"
      >
        <MapWeatherWidget :data="weatherData" />
      </div>

      <!-- Back button row (when returnTo) + active transit-route chip -->
      <div
        v-if="(route.query.returnTo || transit.activeRouteInfo.value) && !selectedFeature && activeAvatarPanel === null && !selectedVehicle && !selectedIoTDevice && !selectedEnvStation && !selectedCondominium && !selectedHub && !selectedEstablishment"
        class="absolute top-[4.5rem] left-4 z-[1001] flex flex-col items-start gap-2"
      >
        <div v-if="route.query.returnTo" class="flex items-center gap-2">
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

        <!-- Chip: which single route the map is focused on (vehicles are
             filtered to it) — body re-fits the camera, X dismisses -->
        <div
          v-if="transit.activeRouteInfo.value"
          class="flex items-center bg-white dark:bg-neutral-800 rounded-lg shadow-lg border border-neutral-200 dark:border-neutral-700 overflow-hidden"
        >
          <button
            @click.stop="fitActiveTransitRoute"
            class="flex items-center gap-2 pl-2.5 pr-2 py-2 min-w-0 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors"
            :title="$t('map.transit.route_chip_fit')"
          >
            <span
              class="px-1.5 py-0.5 rounded text-xs font-bold flex-shrink-0"
              :style="routeBadgeStyle(transit.activeRouteInfo.value)"
            >{{ transit.activeRouteInfo.value.short_name }}</span>
            <span
              v-if="transit.activeRouteInfo.value.long_name"
              class="text-sm font-medium text-neutral-900 dark:text-neutral-100 truncate max-w-[13rem]"
            >{{ transit.activeRouteInfo.value.long_name }}</span>
          </button>
          <button
            @click.stop="clearActiveTransitRoute"
            class="p-2 flex-shrink-0 text-neutral-500 dark:text-neutral-400 hover:bg-primary-100 dark:hover:bg-primary-900/40 hover:text-neutral-900 dark:hover:text-neutral-100 transition-colors"
            :title="$t('map.transit.route_chip_clear')"
            :aria-label="$t('map.transit.route_chip_clear')"
          >
            <X class="w-4 h-4" />
          </button>
        </div>
      </div>

      <!-- Onboarding quest log (HUD console, top-left under search). Hidden
           while any panel claims the screen; drops below the back-button row
           when that row is present. -->
      <div
        v-if="authStore.isAuthenticated && !weatherHudPanelOpen"
        class="absolute left-4 z-[1000]"
        :class="(route.query.returnTo || transit.activeRouteInfo.value) ? 'top-[8.5rem]' : 'top-[4.5rem]'"
      >
        <MapQuestLog />
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
      <div class="search-with-directions" :class="{ 'panel-open': browseVisible || routingVisible, 'detail-panel-open': !!selectedFeature || activeAvatarPanel !== null || !!selectedVehicle || !!selectedIoTDevice || !!selectedEnvStation || !!selectedCondominium || !!selectedHub || !!selectedEstablishment || (urbanActive && !!urbanResult) || tileGridMode }">
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

      <!-- OpenSky mission planning (tile-grid tool) — standard side panel with
           flight budgets + dashboard link. Rendered before the main instance so
           an entity panel opened from the IoT console paints on top. -->
      <MapFeaturePanel
        content-type="opensky"
        :opensky-active="tileGridMode"
        :opensky-budget="openSky.hoveredTileBudget.value"
        :opensky-generating="openSky.missionGenerating.value"
        @close="openSky.toggleTileGrid()"
      />

      <!-- Unified Feature Panel (OSM, avatar controls, profile view, vehicle) -->
      <MapFeaturePanel
        ref="featurePanelRef"
        :feature="selectedFeature"
        :all-features="clickedFeatures"
        :click-coordinates="clickCoordinates"
        :content-type="panelContentTypeWithVehicle"
        :avatar-data="panelAvatarData"
        :vehicle-data="selectedVehicle"
        :vehicle-following="vehicleFollowing"
        :iot-device-data="selectedIoTDevice"
        :iot-following="iot.isFollowing.value"
        :env-station-data="selectedEnvStation"
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
        @toggle-vehicle-follow="toggleVehicleFollow"
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
        v-model:own-geo-position="ownAvatarGeoPosition"
      />

      <!-- Right control strip (layers / tools / IoT popovers, OpenSky group) + mission plan bar -->
      <MapControls
        :top="customControlsTop"
        :open-sky="openSky" :satellite="satellite" :poi="poi" :tiles3d="tiles3d" :transit="transit"
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
import { ArrowLeft, Building2, Route, X } from 'lucide-vue-next'
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
const { t } = useI18n()
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
  activeAvatarPanel, nearbyAvatars, isMapPresenceConnected, ownAvatarGeoPosition,
  panelAvatarData,
  wrappedSetState, wrappedSetSpeechBubble,
} = avatar

// Current OpenSky mission filter from URL
const currentOpenSkyMission = computed(() => route.query.opensky_mission as string | undefined)

const openSky = useMapOpenSky(currentOpenSkyMission)
const { tileGridMode } = openSky

const iot = useMapIoTLayers()

const transit = useMapTransitLayers()
const { routeBadgeStyle } = useTransitHelpers()

// Active transit-route chip actions (body tap re-fits, X dismisses)
const fitActiveTransitRoute = () => {
  const m = mapStore.mapInstance
  if (m) transit.fitActiveRoute(m)
}
const clearActiveTransitRoute = () => {
  const m = mapStore.mapInstance
  if (m) transit.removeRouteOverlay(m)
}

const mesh = useMapMeshLayer()
const satellite = useMapSatelliteLayer()
const poi = useMapPoiVisibility()
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
  selectedVehicle, selectedIoTDevice, selectedEnvStation,
  selectedCondominium, selectedHub, selectedEstablishment,
  panelContentTypeWithVehicle, entityPanelOpen,
  clearEntityPanels, closeFeaturePanel, handleFeaturePanelBack,
} = panels

// Wire vehicle click → panel (mutual exclusion via the shared clear)
transit.setVehicleClickHandler((vehicle: any) => {
  clearEntityPanels()
  selectedVehicle.value = vehicle
})

// Entering mission planning claims the panel slot — close entity panels
// (the reverse direction is covered by closeFeaturePanel, which exits grid mode)
watch(tileGridMode, (on) => { if (on) clearEntityPanels() })

const iotBridge = useMapIoTBridge({ selectedIoTDevice, clearEntityPanels, iot, animationEnabled })
const {
  selectAndFlyToTracker, selectAndFlyToProperty,
  handleShowTrail, handleClearTrail, handleTrailCursor, handleRecenterIoT,
} = iotBridge

const trackerPanelWs = useMapTrackerPanelWs({ selectedIoTDevice, iot })
const envLiveWs = useMapEnvLiveWs({ selectedEnvStation, iot })

// Selected station carries the lock-on hex — mute its compass bezel meanwhile
watch(() => selectedEnvStation.value?.id || null, (id) => iot.setEnvHudLockDim(id))

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
// Hidden while a bottom tool bar claims its band; docked panels only cover
// the corner on phones (bottom sheets), where CSS hides it via `panel-open`.
const weatherHud = useMapWeatherHud({
  isActive,
  blocked: computed(() =>
    measureActive.value || sunStudyActive.value || isochroneActive.value ||
    droneReachActive.value || urbanActive.value
  ),
})
const { weatherData, weatherHudVisible } = weatherHud
const weatherHudPanelOpen = computed(() =>
  browseVisible.value || routingVisible.value || !!selectedFeature.value ||
  entityPanelOpen.value || tileGridMode.value
)

const customControlsTop = ref('250px') // updated dynamically after map init

// ======== Layer stack (initial registration + style-reload re-registration) ========

const layerStack = useMapLayerStack({
  highlight, openSky, satellite, poi, iot, mesh, condo, hub, gov, church,
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

// ======== Entity-panel deep links (?device=) + vehicle follow ========

const deepLink = useMapDeviceDeepLink({
  getMap: () => miniMap,
  animationEnabled,
  panels: {
    selectedVehicle, selectedIoTDevice, selectedEnvStation,
    selectedCondominium, selectedHub, selectedEstablishment,
    clearEntityPanels,
  },
  iot,
  layers: { mesh, condo, hub, gov, church },
  transit,
})
const { vehicleFollowing, toggleVehicleFollow } = deepLink

// ======== Camera padding for docked panels + center reticle ========

// Any left-docked (desktop) / bottom-sheet (mobile) panel that obscures the map
const anyDockedPanelOpen = computed(() =>
  !!selectedFeature.value || entityPanelOpen.value || browseVisible.value
  || routingVisible.value || (urbanActive.value && !!urbanResult.value)
  || tileGridMode.value
)
const cameraPadding = useMapCameraPadding({
  getMap: () => miniMap,
  panelOpen: anyDockedPanelOpen,
  getPanelPadding: iot.getPanelPadding,
})
const reticleStyle = computed(() => ({
  transform: `translate(calc(-50% + ${cameraPadding.paddingOffset.value.x}px), calc(-50% + ${cameraPadding.paddingOffset.value.y}px))`,
}))

// ======== URL ⇄ map sync (query building, deep-link pendings, position saves) ========

const urlSync = useMapUrlSync({
  getMap: () => miniMap,
  isActive,
  currentOpenSkyMission,
  transit,
  routing,
  browse,
  closeFeaturePanel,
  getDeviceParam: () => deepLink.deviceParam.value,
})
const handleOsmResolved = urlSync.handleOsmResolved
const handleEstablishmentSelected = urlSync.handleEstablishmentSelected

// ======== Map click dispatch (priority chain in useMapClickDispatcher) ========

const clickDispatcher = useMapClickDispatcher({
  animationEnabled,
  searchLanguage,
  // Tools that own map clicks while active (sun study is slider-driven;
  // tile-grid mode handles its own clicks inside useMapOpenSky)
  interceptWhenActive: [measureActive, isochroneActive, droneReachActive, urbanActive, tileGridMode],
  routing,
  browse,
  panels,
  iot,
  avatar,
  highlight,
  updateUrlWithMapState: urlSync.updateUrlWithMapState,
  transitPick: transit.hasVehicleAt,
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
    const marker = new maplibregl.Marker({ element: createLockOnElement(), anchor: 'center' }).setLngLat(lngLat).addTo(miniMap)
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

  if (selectedFeature.value || selectedVehicle.value || selectedIoTDevice.value || selectedEnvStation.value || selectedCondominium.value || selectedHub.value || selectedEstablishment.value) {
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
  } else if (tileGridMode.value) {
    openSky.toggleTileGrid()
  } else if (transit.activeRouteInfo.value) {
    clearActiveTransitRoute()
  } else {
    return // nothing to close
  }
  e.preventDefault()
}

// ======== Transit vehicle data sync (watcher) ========
transit.syncVehicleData()
transit.syncWaitingData()

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

    const GeolocationControl = createGeolocationControl(mapStore, animationEnabled, t)
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

    // Disable IoT / vehicle follow modes when user drags the map
    miniMap.on('dragstart', () => { iot.disableFollow(); deepLink.disableVehicleFollow() })

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

      // Frame all mesh nodes when arriving from /mesh "View on map" (?fit=mesh).
      // The link seeds a Minho-region center so there's no long jump before the
      // async fitBounds resolves.
      if (route.query.fit === 'mesh') {
        mesh.fitBounds(miniMap, { animate: false })
      }

      // Auto-enable transit + marker/route from /transit "Show on map"
      // (fresh mount: parseInitialQuery already centered the map → no recenter)
      urlSync.applyPendingTransitMarker({ recenter: false })

      browse.setupLayers(miniMap)

      // Initialize map presence
      if (authStore.isAuthenticated && mapPresenceEnabled.value) {
        avatar.initializeMapPresence(miniMap)
      }

      // Restore feature panel / entity panel / open directions from URL
      urlSync.restorePendingFeature()
      urlSync.applyDirectionsFromQuery()
      deepLink.restorePendingDevice()

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
  deepLink.restorePendingDevice()

  // Re-frame mesh nodes for a /map?fit=mesh deep-link into the kept-alive map
  // (the 'load' handler above runs only on the first mount).
  if (route.query.fit === 'mesh' && miniMap) {
    mesh.fitBounds(miniMap, { animate: true })
  }

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
  envLiveWs.disconnect()
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
  envLiveWs.disconnect()
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

/* Fullscreen mode — sized by insets, never by vh: mobile Chrome's 100vh
   tracks the LARGEST viewport (URL bar collapsed), and with top+height set
   `bottom` is ignored, so a vh height overhangs the visible edge by the URL
   bar and buries the bottom band (weather / scale / attribution) under the
   browser chrome. A fixed box anchored top+bottom ends at the real edge. */
.map-view.fullscreen {
  top: var(--nav-inset-top);
  left: 0;
  right: 0;
  bottom: var(--nav-inset-bottom);
  border-radius: 0;
  border: none;
  background: transparent;
  box-shadow: none;
  z-index: 10; /* Below navbar (50) */
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

/* Effective camera-center reticle — minimal hollow brand-yellow crosshair
   (3px hairline arms, no halo) marking where zoom buttons / flyTo center.
   transform-only motion (compositor); the transition mirrors the 250ms
   padding ease of useMapCameraPadding. */
.map-center-reticle {
  position: absolute;
  left: 50%;
  top: 50%;
  z-index: 30;
  pointer-events: none;
  transition: transform 250ms ease;
}
.map-center-reticle svg {
  display: block;
}

/* User location marker (MapLibre marker) — avatar-class circle per the map
   marker grammar: course pointer at the rim while moving, honest accuracy
   disc, no decorative pulse */
:deep(.user-location-marker) {
  width: 36px;
  height: 36px;
  position: relative;
  pointer-events: none;
}

:deep(.user-location-marker .user-marker-dot) {
  width: 12px;
  height: 12px;
  background: var(--color-secondary);
  border: 2px solid white;
  border-radius: 50%;
  box-shadow: 0 0 0 1px #1f2937; /* marker-grammar rest stroke */
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 2;
}

:deep(.user-location-marker .user-marker-heading) {
  position: absolute;
  inset: 0;
  opacity: 0;
  transition: opacity 250ms ease;
  z-index: 1;
}

:deep(.user-location-marker.user-marker-moving .user-marker-heading) {
  opacity: 1;
}

:deep(.user-location-marker .user-marker-heading::before) {
  content: '';
  position: absolute;
  top: 2px;
  left: 50%;
  transform: translateX(-50%);
  width: 0;
  height: 0;
  border-left: 5px solid transparent;
  border-right: 5px solid transparent;
  border-bottom: 8px solid var(--color-secondary);
}

:deep(.user-location-marker .user-marker-accuracy) {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  border-radius: 50%;
  background: color-mix(in srgb, var(--color-secondary) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-secondary) 30%, transparent);
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

/* Expanded copyright strip: a real surface card — the MapLibre default is
   half-transparent over the tiles, unreadable on a busy basemap */
:deep(.maplibregl-ctrl-attrib.maplibregl-compact.attrib-ready.maplibregl-compact-show) {
  background: var(--color-surface);
  border: 1px solid var(--color-border, #e5e5e5);
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
}
:root.dark :deep(.maplibregl-ctrl-attrib.maplibregl-compact.attrib-ready.maplibregl-compact-show) {
  background: rgba(30, 30, 30, 0.9);
  border-color: #404040;
  color: #d4d4d4;
}
:root.dark :deep(.maplibregl-ctrl-attrib.maplibregl-compact.attrib-ready.maplibregl-compact-show a) {
  color: #d4d4d4;
}

/* Weather HUD wrapper — bottom-right, one line with the attribution ⓘ
   (left of the button, centered on its height). Panels dock left on
   desktop, so this corner stays clear while they're open; the bottom tool
   bars sit center and the scale bar bottom-left. */
.weather-hud-wrap {
  position: absolute;
  right: 2.75rem;
  bottom: 12px;
  z-index: 1000;
}

/* The expanded copyright strip claims the whole line — the chip yields */
.mini-map-container:has(.maplibregl-ctrl-attrib.maplibregl-compact-show) .weather-hud-wrap {
  display: none;
}

/* Below the desktop breakpoint panels open as bottom sheets over this
   corner — yield while one is up */
@media (max-width: 767px) {
  .weather-hud-wrap.panel-open {
    display: none;
  }
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

<style>
/* Device HUD markers (utils/envHudMarker.ts) — unscoped: the elements are
   created outside Vue and appended by MapLibre. Instrument readout column
   beside each device hexagon (env stations + mesh routers) plus a
   transparent compass bezel around weather hexes; dark mono text with a
   white halo (same legibility scheme as GL map labels). The marker root is a
   0×0 box centered on the rendered (ensemble-offset) point — every part
   hangs off it absolutely. Placement classes come from the ensemble layout
   (useMapDeviceEnsembles.ts); the numeric gaps below must stay in sync with
   its HUD_GAP_* constants. */
.env-hud { pointer-events: none; width: 0; height: 0; }
/* Fade opacity sits on the inner wrapper — MapLibre owns inline styles on
   the marker root element itself. */
.env-hud-inner { opacity: 1; transition: opacity 0.25s; }
.env-hud-stale .env-hud-inner { opacity: 0.45; }
/* Hidden below ENV_HUD_MINZOOM — class toggled on the map container */
.env-hud-below-zoom .env-hud-inner { opacity: 0; }

/* Compass bezel: transparent ring around the hex itself (the map shows
   through); counter-rotates by the map bearing so the red north tick stays
   geo-aligned */
.env-hud-ring {
  position: absolute;
  left: -28px;
  top: -28px;
  width: 56px;
  height: 56px;
  filter: drop-shadow(0 0 1.5px rgba(255, 255, 255, 0.9));
  transform: rotate(var(--map-bearing-neg, 0deg));
  transition: transform 0.3s linear;
}
/* Base-scale (22 px, non-ensemble) hexes wear a proportionally smaller bezel */
.env-hud-base .env-hud-ring { left: -22px; top: -22px; width: 44px; height: 44px; }
/* Selected station wears the lock-on hex right over the bezel — mute the ring
   and ticks so the hex reads clean. The wind pointer stays at full opacity:
   the panel shows direction only as a number, the dart is the live readout. */
.env-hud-ring circle,
.env-hud-ring line { transition: opacity 0.25s; }
.env-hud-lockdim .env-hud-ring circle,
.env-hud-lockdim .env-hud-ring line { opacity: 0.12; }
.env-hud-pointer {
  transform-box: view-box;
  transform-origin: 28px 28px;
  transition: transform 0.9s cubic-bezier(0.22, 1, 0.36, 1);
}

/* Instrument readout column */
.env-hud-col {
  position: absolute;
  top: 0;
  transform: translateY(-50%);
  display: flex;
  flex-direction: column;
  gap: 1px;
  user-select: none;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-variant-numeric: tabular-nums;
  color: #111827;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  white-space: nowrap;
}
.env-hud-side-r .env-hud-col { left: 19px; align-items: flex-start; }
.env-hud-side-l .env-hud-col { right: 19px; align-items: flex-end; }
.env-hud-ringed.env-hud-side-r .env-hud-col { left: 24px; }
.env-hud-ringed.env-hud-side-l .env-hud-col { right: 24px; }
.env-hud-base.env-hud-side-r .env-hud-col { left: 16px; }
.env-hud-base.env-hud-side-l .env-hud-col { right: 16px; }
.env-hud-base.env-hud-ringed.env-hud-side-r .env-hud-col { left: 19px; }
.env-hud-base.env-hud-ringed.env-hud-side-l .env-hud-col { right: 19px; }
/* Diagonal ring slots push their readout outward so stacked columns never kiss */
.env-hud-up .env-hud-col { top: -7px; }
.env-hud-down .env-hud-col { top: 7px; }
/* Pure-top slot: bottom-anchor the column so it grows upward, clear of the
   lower slots' bezel. Left may be overridden inline by the right-rail
   alignment (the column's edge lines up with the columns below). */
.env-hud-topslot .env-hud-col { top: -2px; transform: translateY(-100%); }
.env-hud-topslot.env-hud-side-r .env-hud-col { left: 26px; }
.env-hud-primary {
  font-size: 12.5px;
  font-weight: 700;
  line-height: 1.15;
  text-shadow: 0 0 2px #fff, 0 0 3px #fff, 0 0 4px #fff, 0 1px 2px #fff;
}
.env-hud-rows { display: flex; flex-direction: column; }
.env-hud-row {
  display: flex;
  gap: 4px;
  align-items: baseline;
  line-height: 1.3;
  text-shadow: 0 0 2px #fff, 0 0 3px #fff, 0 0 4px #fff, 0 1px 2px #fff;
}
.env-hud-side-l .env-hud-row { justify-content: flex-end; }
.env-hud-k { font-size: 8px; font-weight: 700; opacity: 0.5; letter-spacing: 0.08em; }
.env-hud-v { font-size: 10px; font-weight: 600; }
@media (prefers-reduced-motion: reduce) {
  .env-hud-inner,
  .env-hud-ring,
  .env-hud-ring circle,
  .env-hud-ring line,
  .env-hud-pointer { transition: none; }
}
</style>
