<template>
  <!-- Map Layer Controls -->
  <div class="map-layer-controls" :style="{ top }">
    <!-- Layers + Tools + IoT (single group) -->
    <div class="map-ctrl-group">
      <!-- Layers button (Aerial + Transit + Condo + Gov + Hubs + Mesh + Energy) -->
      <div class="layers-control">
        <button
          @click.stop="layersPopoverOpen = !layersPopoverOpen; architectPopoverOpen = false; iotPopoverOpen = false; hideIoTPreview()"
          class="opensky-btn"
          :title="$t('map.layers.title')"
        >
          <Layers class="w-5 h-5" />
        </button>
        <div v-if="layersPopoverOpen" class="layers-popover" @click.stop>
          <button
            class="layers-popover-item"
            :class="{ active: openSkyEnabled }"
            :aria-pressed="openSkyEnabled"
            @click="toggleOpenSkyLayer"
          >
            <Satellite class="w-4 h-4 flex-shrink-0" aria-hidden="true" />
            <span class="layers-popover-label">{{ $t('map.layers.aerial') }}</span>
            <Eye v-if="openSkyEnabled" class="w-3.5 h-3.5 flex-shrink-0 opacity-70" aria-hidden="true" />
            <EyeOff v-else class="w-3.5 h-3.5 flex-shrink-0 opacity-30" aria-hidden="true" />
          </button>
          <button
            class="layers-popover-item"
            :class="{ active: satelliteEnabled }"
            :aria-pressed="satelliteEnabled"
            @click="satellite.toggleLayer()"
          >
            <ImageIcon class="w-4 h-4 flex-shrink-0" aria-hidden="true" />
            <span class="layers-popover-label">{{ $t('map.layers.satellite') }}</span>
            <Eye v-if="satelliteEnabled" class="w-3.5 h-3.5 flex-shrink-0 opacity-70" aria-hidden="true" />
            <EyeOff v-else class="w-3.5 h-3.5 flex-shrink-0 opacity-30" aria-hidden="true" />
          </button>
          <button
            class="layers-popover-item"
            :class="{ active: tiles3dEnabled }"
            :aria-pressed="tiles3dEnabled"
            @click="toggle3DTiles"
          >
            <Box class="w-4 h-4 flex-shrink-0" aria-hidden="true" />
            <span class="layers-popover-label">{{ $t('map.layers.aerial_3d') }}</span>
            <Loader2 v-if="tiles3dLoading" class="w-3.5 h-3.5 flex-shrink-0 opacity-70 animate-spin" aria-hidden="true" />
            <Eye v-else-if="tiles3dEnabled" class="w-3.5 h-3.5 flex-shrink-0 opacity-70" aria-hidden="true" />
            <EyeOff v-else class="w-3.5 h-3.5 flex-shrink-0 opacity-30" aria-hidden="true" />
          </button>
          <button
            class="layers-popover-item"
            :class="{ active: transitEnabled }"
            :aria-pressed="transitEnabled"
            @click="transit.toggleLayer()"
          >
            <Bus class="w-4 h-4 flex-shrink-0" aria-hidden="true" />
            <span class="layers-popover-label">{{ $t('map.layers.transit') }}</span>
            <span v-if="transit.activeRouteFilter.value" class="w-2 h-2 bg-secondary-600 rounded-full flex-shrink-0" aria-hidden="true"></span>
            <Eye v-if="transitEnabled" class="w-3.5 h-3.5 flex-shrink-0 opacity-70" aria-hidden="true" />
            <EyeOff v-else class="w-3.5 h-3.5 flex-shrink-0 opacity-30" aria-hidden="true" />
          </button>
          <button
            class="layers-popover-item"
            :class="{ active: governmentEnabled }"
            :aria-pressed="governmentEnabled"
            @click="gov.toggle()"
          >
            <Landmark class="w-4 h-4 flex-shrink-0" aria-hidden="true" />
            <span class="layers-popover-label">{{ $t('map.layers.government') }}</span>
            <Eye v-if="governmentEnabled" class="w-3.5 h-3.5 flex-shrink-0 opacity-70" aria-hidden="true" />
            <EyeOff v-else class="w-3.5 h-3.5 flex-shrink-0 opacity-30" aria-hidden="true" />
          </button>
          <button
            class="layers-popover-item"
            :class="{ active: churchEnabled }"
            :aria-pressed="churchEnabled"
            @click="church.toggle()"
          >
            <Cross class="w-4 h-4 flex-shrink-0" aria-hidden="true" />
            <span class="layers-popover-label">{{ $t('map.layers.churches') }}</span>
            <Eye v-if="churchEnabled" class="w-3.5 h-3.5 flex-shrink-0 opacity-70" aria-hidden="true" />
            <EyeOff v-else class="w-3.5 h-3.5 flex-shrink-0 opacity-30" aria-hidden="true" />
          </button>
          <button
            class="layers-popover-item"
            :class="{ active: condosEnabled }"
            :aria-pressed="condosEnabled"
            @click="condo.toggle()"
          >
            <Building2 class="w-4 h-4 flex-shrink-0" aria-hidden="true" />
            <span class="layers-popover-label">{{ $t('map.layers.condominiums') }}</span>
            <Eye v-if="condosEnabled" class="w-3.5 h-3.5 flex-shrink-0 opacity-70" aria-hidden="true" />
            <EyeOff v-else class="w-3.5 h-3.5 flex-shrink-0 opacity-30" aria-hidden="true" />
          </button>
          <button
            class="layers-popover-item"
            :class="{ active: hubsEnabled }"
            :aria-pressed="hubsEnabled"
            @click="hub.toggle()"
          >
            <Package class="w-4 h-4 flex-shrink-0" aria-hidden="true" />
            <span class="layers-popover-label">{{ $t('map.layers.hubs') }}</span>
            <Eye v-if="hubsEnabled" class="w-3.5 h-3.5 flex-shrink-0 opacity-70" aria-hidden="true" />
            <EyeOff v-else class="w-3.5 h-3.5 flex-shrink-0 opacity-30" aria-hidden="true" />
          </button>
          <button
            class="layers-popover-item"
            :class="{ active: meshEnabled }"
            :aria-pressed="meshEnabled"
            @click="mesh.toggle()"
          >
            <Wifi class="w-4 h-4 flex-shrink-0" aria-hidden="true" />
            <span class="layers-popover-label">{{ $t('map.layers.mesh_network') }}</span>
            <Eye v-if="meshEnabled" class="w-3.5 h-3.5 flex-shrink-0 opacity-70" aria-hidden="true" />
            <EyeOff v-else class="w-3.5 h-3.5 flex-shrink-0 opacity-30" aria-hidden="true" />
          </button>
          <button
            class="layers-popover-item"
            :class="{ active: energyCellsEnabled }"
            :aria-pressed="energyCellsEnabled"
            @click="iot.toggleEnergyCells()"
          >
            <Zap class="w-4 h-4 flex-shrink-0" aria-hidden="true" />
            <span class="layers-popover-label">{{ $t('map.layers.energy') }}</span>
            <Eye v-if="energyCellsEnabled" class="w-3.5 h-3.5 flex-shrink-0 opacity-70" aria-hidden="true" />
            <EyeOff v-else class="w-3.5 h-3.5 flex-shrink-0 opacity-30" aria-hidden="true" />
          </button>
        </div>
      </div>
      <!-- Map Tools -->
      <div class="architect-control">
        <button
          @click.stop="architectPopoverOpen = !architectPopoverOpen; layersPopoverOpen = false; iotPopoverOpen = false; hideIoTPreview()"
          class="opensky-btn"
          :class="{ active: measureActive || sunStudyActive || isochroneActive || droneReachActive || urbanActive }"
          :title="$t('map.architect.title')"
        >
          <Ruler class="w-5 h-5" />
        </button>
        <div v-if="architectPopoverOpen" class="layers-popover" @click.stop>
          <button
            class="layers-popover-item"
            :class="{ active: measureActive && measureMode === 'distance' }"
            @click="startTool('measure-distance')"
          >
            <Ruler class="w-4 h-4 flex-shrink-0" aria-hidden="true" />
            <span class="layers-popover-label">{{ $t('map.architect.measure') }}</span>
          </button>
          <button
            class="layers-popover-item"
            :class="{ active: measureActive && measureMode === 'area' }"
            @click="startTool('measure-area')"
          >
            <Pentagon class="w-4 h-4 flex-shrink-0" aria-hidden="true" />
            <span class="layers-popover-label">{{ $t('map.architect.measure_area') }}</span>
          </button>
          <button
            class="layers-popover-item"
            :class="{ active: sunStudyActive }"
            @click="startTool('sun')"
          >
            <Sun class="w-4 h-4 flex-shrink-0" aria-hidden="true" />
            <span class="layers-popover-label">{{ $t('map.architect.sun_study') }}</span>
          </button>
          <button
            class="layers-popover-item"
            :class="{ active: isochroneActive }"
            @click="startTool('isochrone')"
          >
            <Clock class="w-4 h-4 flex-shrink-0" aria-hidden="true" />
            <span class="layers-popover-label">{{ $t('map.architect.isochrone') }}</span>
          </button>
          <button
            class="layers-popover-item"
            :class="{ active: droneReachActive }"
            @click="startTool('droneReach')"
          >
            <Radio class="w-4 h-4 flex-shrink-0" aria-hidden="true" />
            <span class="layers-popover-label">{{ $t('map.architect.drone_reach') }}</span>
          </button>
          <button
            class="layers-popover-item"
            :class="{ active: urbanActive }"
            @click="startTool('urban')"
          >
            <Building class="w-4 h-4 flex-shrink-0" aria-hidden="true" />
            <span class="layers-popover-label">{{ $t('map.urban.title') }}</span>
          </button>
        </div>
      </div>
      <!-- IoT Devices popover (Routers + Trackers) -->
      <div v-if="authStore.isAuthenticated" class="tracker-control">
        <button
          @click.stop="iotPopoverOpen = !iotPopoverOpen; layersPopoverOpen = false; architectPopoverOpen = false; if (!iotPopoverOpen) hideIoTPreview()"
          class="opensky-btn"
          title="IoT Devices"
        >
          <Radar class="w-5 h-5" />
        </button>
        <div v-if="iotPopoverOpen" class="tracker-popover" @click.stop>
          <!-- My Homes section -->
          <div v-if="propertyStore.properties.length > 0" class="tracker-popover-header" @click="iotHomesExpanded = !iotHomesExpanded" @keydown.enter="iotHomesExpanded = !iotHomesExpanded" @keydown.space.prevent="iotHomesExpanded = !iotHomesExpanded" role="button" tabindex="0" style="cursor: pointer;">
            <div class="iot-section-toggle">
              <ChevronRight class="w-3 h-3 iot-chevron" :class="{ expanded: iotHomesExpanded }" />
              <Home class="w-3.5 h-3.5" />
              <span class="tracker-popover-title">{{ $t('property.my_homes') }}</span>
            </div>
          </div>
          <template v-if="iotHomesExpanded && propertyStore.properties.length > 0">
            <button
              v-for="p in propertyStore.properties"
              :key="p.id"
              class="tracker-popover-item"
              :disabled="!p.latitude"
              @click="p.latitude && $emit('select-property', p)"
              @mouseenter="p.latitude && showIoTPreview(p.latitude, p.longitude)"
              @mouseleave="hideIoTPreview()"
            >
              <component :is="propertyTypeIcon(p.property_type)" class="w-3 h-3 opacity-60" />
              <span class="tracker-item-name">{{ p.name }}</span>
              <span v-if="p.device_count" class="tracker-item-speed">{{ p.device_count }} IoT</span>
            </button>
          </template>
          <!-- GPS Trackers section -->
          <div class="tracker-popover-header" @click="iotTrackersExpanded = !iotTrackersExpanded" @keydown.enter="iotTrackersExpanded = !iotTrackersExpanded" @keydown.space.prevent="iotTrackersExpanded = !iotTrackersExpanded" role="button" tabindex="0" style="cursor: pointer;">
            <div class="iot-section-toggle">
              <ChevronRight class="w-3 h-3 iot-chevron" :class="{ expanded: iotTrackersExpanded }" />
              <Radar class="w-3.5 h-3.5" />
              <span class="tracker-popover-title">GPS Trackers</span>
            </div>
            <button @click.stop="iot.toggleTrackers()" class="tracker-eye-btn" :aria-label="trackersEnabled ? $t('map.toggle_hide_layer', { layer: 'GPS Trackers' }) : $t('map.toggle_show_layer', { layer: 'GPS Trackers' })">
              <Eye v-if="trackersEnabled" class="w-3.5 h-3.5" />
              <EyeOff v-else class="w-3.5 h-3.5 opacity-50" />
            </button>
          </div>
          <template v-if="iotTrackersExpanded">
            <div v-if="trackerPositionsList.length === 0" class="tracker-popover-empty">
              No trackers
            </div>
            <button
              v-for="t in trackerPositionsList"
              :key="t.device_id"
              class="tracker-popover-item"
              @click="$emit('select-tracker', t)"
              @mouseenter="showIoTPreview(t.latitude, t.longitude)"
              @mouseleave="hideIoTPreview()"
            >
              <span class="tracker-status-dot" :class="t.traccar_status === 'online' ? 'online' : t.traccar_status === 'offline' ? 'offline' : 'unknown'"></span>
              <span class="tracker-item-name">{{ t.name }}</span>
              <span v-if="trackerSignalAge(t) >= 5" class="tracker-item-signal-lost" :title="t.last_update">{{ trackerSignalAgeText(t) }}</span>
              <span v-else-if="t.speed && t.speed > 1" class="tracker-item-speed">{{ Math.round(t.speed) }} km/h</span>
            </button>
          </template>
        </div>
      </div>
    </div>
    <!-- OpenSky pilot tools (only when aerial mode active) -->
    <div v-if="openSkyMode" class="map-ctrl-group">
      <NuxtLink
        :to="localePath('/opensky')"
        class="opensky-btn"
        title="OpenSky Dashboard"
      >
        <Plane class="w-5 h-5" />
      </NuxtLink>
      <button
        v-if="authStore.isAuthenticated"
        @click="openSky.toggleMissionArea()"
        class="opensky-btn"
        :class="{ active: tileGridMode || missionGenerating }"
        :disabled="missionGenerating"
        :title="tileGridMode ? $t('map.opensky.exit_planning') : $t('map.opensky.plan_missions')"
      >
        <Grid3x3 class="w-5 h-5" :class="{ 'animate-pulse': missionGenerating }" />
      </button>
    </div>
  </div>

  <!-- OpenSky mission planning hint (top center, in grid mode) -->
  <div v-if="tileGridMode" class="opensky-plan-bar">
    <template v-if="hoveredTileBudget">
      <span class="opensky-plan-tile">Z17/{{ hoveredTileBudget.x }}/{{ hoveredTileBudget.y }}</span>
      <span class="opensky-plan-sep">·</span>
      <span class="opensky-plan-budget">
        <span class="opensky-plan-level">{{ $t('map.opensky.battery_level', { level: 1, min: hoveredTileBudget.battery1 }) }}</span>
        <span class="opensky-plan-desc">{{ $t('map.opensky.ortho') }}</span>
      </span>
      <span class="opensky-plan-sep">·</span>
      <span class="opensky-plan-budget">
        <span class="opensky-plan-level">{{ $t('map.opensky.battery_level', { level: 3, min: hoveredTileBudget.battery3 }) }}</span>
        <span class="opensky-plan-desc">{{ $t('map.opensky.baseline_3d') }}</span>
      </span>
      <span class="opensky-plan-sep">·</span>
      <span class="opensky-plan-budget">
        <span class="opensky-plan-level">{{ $t('map.opensky.battery_level', { level: 5, min: hoveredTileBudget.battery5 }) }}</span>
        <span class="opensky-plan-desc">{{ $t('map.opensky.ultra_3d') }}</span>
      </span>
      <span class="opensky-plan-hint">{{ $t('map.opensky.click_to_download') }}</span>
    </template>
    <template v-else>
      <span class="opensky-plan-hint">{{ $t('map.opensky.hover_hint') }}</span>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * Right control strip of the map (layers / map tools / IoT popovers, OpenSky
 * pilot group) plus the top-center OpenSky mission-planning hint bar.
 *
 * Receives the map composable objects from MapView; popover open/close state
 * and the outside-click dismissal live here.
 */
import { ref, watch, onMounted, onActivated, onDeactivated, onBeforeUnmount } from 'vue'
import { Layers, Grid3x3, Plane, Radar, Radio, Eye, EyeOff, Building, Building2, ChevronRight, Bus, Zap, Home, Warehouse, LandPlot, Landmark, Package, Wifi, Satellite, Image as ImageIcon, Cross, Ruler, Sun, Pentagon, Clock, Box, Loader2 } from 'lucide-vue-next'

const props = defineProps<{
  top: string
  openSky: any
  satellite: any
  tiles3d: any
  transit: any
  gov: any
  church: any
  condo: any
  hub: any
  mesh: any
  iot: any
  measure: any
  sunStudy: any
  isochrone: any
  droneReach: any
  urban: any
}>()

defineEmits<{
  (e: 'select-tracker', tracker: any): void
  (e: 'select-property', property: any): void
}>()

const {
  openSky, satellite, tiles3d, transit, gov, church, condo, hub, mesh, iot,
  measure, sunStudy, isochrone, droneReach, urban,
} = props

const authStore = useAuthStore()
const localePath = useLocalePath()

// Template aliases (refs auto-unwrap as top-level bindings)
const { openSkyEnabled, openSkyMode, missionGenerating, tileGridMode, hoveredTileBudget } = openSky
const { satelliteEnabled } = satellite
const { tiles3dEnabled, tiles3dLoading } = tiles3d
const { transitEnabled } = transit
const { enabled: governmentEnabled } = gov
const { enabled: churchEnabled } = church
const { enabled: condosEnabled } = condo
const { enabled: hubsEnabled } = hub
const { enabled: meshEnabled } = mesh
const {
  trackersEnabled, trackerPositionsList, energyCellsEnabled,
  iotPopoverOpen, iotTrackersExpanded, showIoTPreview, hideIoTPreview,
} = iot
const { measureActive, measureMode } = measure
const { sunStudyActive } = sunStudy
const { isochroneActive } = isochrone
const { droneReachActive } = droneReach
const { urbanActive } = urban

// ======== Popover state ========

const layersPopoverOpen = ref(false)
const architectPopoverOpen = ref(false)

// Close popovers on outside click (button/panel clicks use @click.stop)
const onDocumentClick = () => {
  iotPopoverOpen.value = false
  hideIoTPreview()
  layersPopoverOpen.value = false
  architectPopoverOpen.value = false
}
onMounted(() => document.addEventListener('click', onDocumentClick))
onActivated(() => document.addEventListener('click', onDocumentClick))
onDeactivated(() => document.removeEventListener('click', onDocumentClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocumentClick))

// ======== Layer toggles with mutual exclusion ========

const toggleOpenSkyLayer = () => {
  // Mutual exclusion: disable 3D tiles when enabling 2D aerial
  if (!openSky.openSkyEnabled.value && tiles3d.tiles3dEnabled.value) {
    tiles3d.toggle()
  }
  openSky.toggleLayer()
}
const toggle3DTiles = () => {
  // Mutual exclusion: disable 2D aerial when enabling 3D tiles
  if (!tiles3d.tiles3dEnabled.value && openSky.openSkyEnabled.value) {
    openSky.toggleLayer()
  }
  tiles3d.toggle()
}

// ======== Map tools: one active at a time ========

type Tool = 'measure-distance' | 'measure-area' | 'sun' | 'isochrone' | 'droneReach' | 'urban'

function startTool(tool: Tool) {
  const keep = tool.startsWith('measure') ? 'measure' : tool
  if (keep !== 'measure' && measureActive.value) measure.stopMeasure()
  if (keep !== 'sun' && sunStudyActive.value) sunStudy.stopSunStudy()
  if (keep !== 'isochrone' && isochroneActive.value) isochrone.stopIsochrone()
  if (keep !== 'droneReach' && droneReachActive.value) droneReach.stopDroneReach()
  if (keep !== 'urban' && urbanActive.value) urban.stopUrban()
  if (tool === 'measure-distance') measure.toggleMeasure('distance')
  else if (tool === 'measure-area') measure.toggleMeasure('area')
  else if (tool === 'sun') sunStudy.toggleSunStudy()
  else if (tool === 'isochrone') isochrone.toggleIsochrone()
  else if (tool === 'droneReach') droneReach.toggleDroneReach()
  else urban.toggleUrban()
  architectPopoverOpen.value = false
}

// ======== My Homes (properties) in the IoT popover ========

const propertyStore = usePropertyStore()
const iotHomesExpanded = ref(true)
const propertiesLoaded = ref(false)

watch(iotPopoverOpen, async (open) => {
  if (open && !propertiesLoaded.value && authStore.isAuthenticated) {
    await propertyStore.fetchProperties()
    propertiesLoaded.value = true
  }
})

const propertyTypeIcon = (type: string) => {
  switch (type) {
    case 'apartment': return Building2
    case 'garage': return Warehouse
    case 'land': return LandPlot
    default: return Home
  }
}

/** Returns age in minutes since last tracker update, or 0 if fresh/unavailable. */
const trackerSignalAge = (t: any): number => {
  if (!t.last_update) return 0
  return Math.floor((Date.now() - new Date(t.last_update).getTime()) / 60_000)
}

const trackerSignalAgeText = (t: any): string => {
  const min = trackerSignalAge(t)
  if (min < 60) return `${min}m`
  const h = Math.floor(min / 60)
  const rem = min % 60
  return rem > 0 ? `${h}h${rem}m` : `${h}h`
}
</script>

<style scoped>
/* Layer Controls — stacked groups like maplibregl-ctrl */
.map-layer-controls {
  position: absolute;
  right: 10px;
  z-index: 1000;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.map-ctrl-group {
  display: flex;
  flex-direction: column;
  border-radius: 4px;
  box-shadow: 0 0 0 2px rgba(0, 0, 0, 0.1);
  background: var(--color-surface);
}
:root.dark .map-ctrl-group {
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.08);
  background: rgba(30, 30, 30, 0.75);
  backdrop-filter: blur(8px);
}

.map-ctrl-group > * + * {
  border-top: 1px solid rgba(0, 0, 0, 0.12);
}
:root.dark .map-ctrl-group > * + * {
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}

.opensky-btn {
  width: 44px;
  height: 44px;
  background: transparent;
  border: none;
  border-radius: 0;
  box-shadow: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text);
  transition: background 0.2s, color 0.2s;
}

/* Round corners on first/last elements in the group */
.map-ctrl-group > :first-child,
.map-ctrl-group > :first-child > .opensky-btn {
  border-top-left-radius: 4px;
  border-top-right-radius: 4px;
}

.map-ctrl-group > :last-child,
.map-ctrl-group > :last-child > .opensky-btn {
  border-bottom-left-radius: 4px;
  border-bottom-right-radius: 4px;
}

.opensky-btn:hover {
  background: var(--color-primary-100, #fef9c3);
}
:root.dark .opensky-btn:hover {
  background: var(--color-primary-900, #422006);
}

.opensky-btn.active {
  background: var(--color-secondary);
  color: white;
}

/* Layers popover */
.layers-control {
  position: relative;
}

.layers-popover {
  position: absolute;
  right: 48px;
  top: 0;
  width: 190px;
  background: var(--color-surface);
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  overflow: hidden;
  z-index: 1001;
}

.layers-popover-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 9px 10px;
  border: none;
  background: none;
  cursor: pointer;
  text-align: left;
  font-size: 13px;
  color: var(--color-text);
  transition: background 0.15s;
}

.layers-popover-item + .layers-popover-item {
  border-top: 1px solid var(--color-border);
}

.layers-popover-item:hover {
  background: var(--color-primary-100, #fef9c3);
}
:root.dark .layers-popover-item:hover {
  background: var(--color-primary-900, #422006);
}

.layers-popover-item.active {
  background: var(--color-secondary-50, #eff6ff);
}
:root.dark .layers-popover-item.active {
  background: rgba(59, 130, 246, 0.15);
}

.layers-popover-label {
  flex: 1;
  white-space: nowrap;
}

/* Map Tools */
.architect-control {
  position: relative;
}

/* Tracker popover */
.tracker-control {
  position: relative;
}

.iot-section-toggle {
  display: flex;
  align-items: center;
  gap: 5px;
}

.iot-chevron {
  transition: transform 0.15s;
  flex-shrink: 0;
}

.iot-chevron.expanded {
  transform: rotate(90deg);
}

.tracker-popover {
  position: absolute;
  right: 48px;
  top: 0;
  width: 210px;
  /* dvh + safe-area so the list tail does not slide under the Android nav bar */
  max-height: calc(100dvh - 300px - var(--safe-area-inset-top, env(safe-area-inset-top, 0px)) - var(--safe-area-inset-bottom, env(safe-area-inset-bottom, 0px)));
  overflow-y: auto;
  background: var(--color-surface);
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  z-index: 1001;
}

.tracker-popover-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  border-bottom: 1px solid var(--color-border);
}

.tracker-popover-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text);
}

.tracker-eye-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px;
  color: var(--color-text-muted);
  display: flex;
  align-items: center;
}

.tracker-eye-btn:hover {
  color: var(--color-secondary);
}

.tracker-popover-empty {
  padding: 12px 10px;
  text-align: center;
  color: var(--color-text-muted);
  font-size: 12px;
}

.tracker-popover-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 10px;
  border: none;
  background: none;
  cursor: pointer;
  text-align: left;
  font-size: 12px;
  color: var(--color-text);
  transition: background 0.15s;
}

.tracker-popover-item:hover {
  background: var(--color-primary-100, #fef9c3);
}
:root.dark .tracker-popover-item:hover {
  background: var(--color-primary-900, #422006);
}

.tracker-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.tracker-status-dot.online { background: var(--color-success); }
.tracker-status-dot.offline { background: var(--color-error); }
.tracker-status-dot.unknown { background: var(--color-text-muted); }

.tracker-item-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tracker-item-speed {
  color: var(--color-text-muted);
  font-size: 11px;
  flex-shrink: 0;
}

.tracker-item-signal-lost {
  color: var(--color-error);
  font-size: 10px;
  flex-shrink: 0;
  opacity: 0.8;
}

/* OpenSky mission-planning hint bar */
.opensky-plan-bar {
  position: absolute;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1001;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 16px;
  background: var(--color-surface);
  border-radius: 24px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.18);
  white-space: nowrap;
  pointer-events: none;
  font-size: 13px;
}
:root.dark .opensky-plan-bar {
  background: rgba(30, 30, 30, 0.9);
  backdrop-filter: blur(8px);
}
.opensky-plan-tile {
  font-weight: 700;
  color: #3b82f6;
  font-variant-numeric: tabular-nums;
}
.opensky-plan-sep {
  color: var(--color-text-muted);
  opacity: 0.5;
}
.opensky-plan-budget {
  display: inline-flex;
  align-items: baseline;
  gap: 4px;
}
.opensky-plan-level {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.opensky-plan-desc {
  font-size: 11px;
  color: var(--color-text-muted);
}
.opensky-plan-hint {
  font-size: 12px;
  color: var(--color-text-muted);
  font-style: italic;
}

@media (max-width: 640px) {
  .opensky-plan-bar {
    left: 10px;
    right: 10px;
    transform: none;
    justify-content: center;
    flex-wrap: wrap;
    font-size: 11px;
    padding: 6px 10px;
  }
}
</style>
