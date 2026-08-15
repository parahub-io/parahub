<template>
  <!-- Map Layer Controls -->
  <div class="map-layer-controls" :style="{ top }">
    <!-- Layers + Tools + IoT (single group) -->
    <div class="map-ctrl-group">
      <button
        @click.stop="layersPopoverOpen = !layersPopoverOpen; architectPopoverOpen = false; iotPopoverOpen = false; hideIoTPreview()"
        class="opensky-btn"
        :class="{ active: layersPopoverOpen }"
        :title="$t('map.layers.title')"
      >
        <Layers class="w-5 h-5" />
      </button>
      <button
        @click.stop="architectPopoverOpen = !architectPopoverOpen; layersPopoverOpen = false; iotPopoverOpen = false; hideIoTPreview()"
        class="opensky-btn"
        :class="{ active: architectPopoverOpen || measureActive || sunStudyActive || isochroneActive || droneReachActive || urbanActive || tileGridMode }"
        :title="$t('map.architect.title')"
      >
        <Ruler class="w-5 h-5" />
      </button>
      <button
        v-if="authStore.isAuthenticated"
        @click.stop="iotPopoverOpen = !iotPopoverOpen; layersPopoverOpen = false; architectPopoverOpen = false; if (!iotPopoverOpen) hideIoTPreview()"
        class="opensky-btn"
        :class="{ active: iotPopoverOpen }"
        :title="$t('map.controls.devices')"
      >
        <Radar class="w-5 h-5" />
      </button>
    </div>

    <!-- Backdrop for the mobile bottom sheets (hidden on md+) -->
    <Transition name="mc-backdrop">
      <div v-if="anyPopoverOpen" class="mc-backdrop" @click.stop="closeAllPopovers" />
    </Transition>

    <!-- Layers console: popover on desktop, bottom sheet on phones -->
    <Transition name="mc-pop">
      <div v-if="layersPopoverOpen" class="mc-pop" @click.stop>
        <div class="mc-sheet-handle" aria-hidden="true"><span /></div>
        <div class="mc-pop-head">
          <span class="mc-pop-title">{{ $t('map.layers.title') }}</span>
          <span class="mc-pop-badge">{{ $t('map.controls.on_count', { count: activeLayerCount }) }}</span>
        </div>
        <div class="mc-pop-body">
          <UiTileMatrix :groups="layerMatrixGroups" fill="primary" @pick="onLayerPick" />
        </div>
      </div>
    </Transition>

    <!-- Map tools console -->
    <Transition name="mc-pop">
      <div v-if="architectPopoverOpen" class="mc-pop" @click.stop>
        <div class="mc-sheet-handle" aria-hidden="true"><span /></div>
        <div class="mc-pop-head">
          <span class="mc-pop-title">{{ $t('map.architect.title') }}</span>
          <span class="mc-pop-badge">{{ activeToolLabel }}</span>
        </div>
        <div class="mc-pop-body">
          <UiTileMatrix :groups="toolMatrixGroups" fill="primary" @pick="onToolPick" />
        </div>
      </div>
    </Transition>

    <!-- IoT device console -->
    <Transition name="mc-pop">
      <div v-if="iotPopoverOpen" class="mc-pop mc-pop-iot" @click.stop>
        <div class="mc-sheet-handle" aria-hidden="true"><span /></div>
        <div class="mc-pop-head">
          <span class="mc-pop-title">{{ $t('map.controls.devices') }}</span>
          <span class="mc-pop-badge">
            <span class="mc-online-dot" aria-hidden="true" />
            {{ $t('map.controls.online_count', { online: iotStats.online, total: iotStats.total }) }}
          </span>
        </div>
        <div class="mc-pop-body">
          <MapDeviceConsole
            :properties="propertyStore.properties"
            :trackers="trackerPositionsList"
            :routers="meshRouterPositionsList"
            :energy-cells="energyCellsList"
            :env-stations="envStationsList"
            :trackers-enabled="trackersEnabled"
            :routers-enabled="meshEnabled"
            :energy-enabled="energyCellsEnabled"
            :env-enabled="envStationsEnabled"
            @select="onConsoleSelect"
            @toggle-layer="onConsoleToggleLayer"
            @preview="onPreview"
          />
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
/**
 * Right control strip of the map (layers / map tools / IoT consoles).
 *
 * Layers and tools render as a tile matrix (UiTileMatrix), IoT devices as
 * a device console (MapDeviceConsole). On phones (<768px) the popovers become
 * full-bleed bottom sheets so long device lists can never run off screen.
 *
 * Receives the map composable objects from MapView; popover open/close state
 * and the outside-click dismissal live here.
 */
import { computed, ref, watch, onMounted, onActivated, onDeactivated, onBeforeUnmount } from 'vue'
import { Layers, Grid3x3, Radar, Radio, Building, Building2, Bus, Zap, Landmark, MapPin, Package, Wifi, Wind, Satellite, Image as ImageIcon, Cross, Ruler, Sun, Pentagon, Clock, Box } from 'lucide-vue-next'

const props = defineProps<{
  top: string
  openSky: any
  satellite: any
  poi: any
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

const emit = defineEmits<{
  (e: 'select-tracker', tracker: any): void
  (e: 'select-property', property: any): void
}>()

const {
  openSky, satellite, poi, tiles3d, transit, gov, church, condo, hub, mesh, iot,
  measure, sunStudy, isochrone, droneReach, urban,
} = props

const authStore = useAuthStore()
const { t } = useI18n()

// Template aliases (refs auto-unwrap as top-level bindings)
const { openSkyEnabled, missionGenerating, tileGridMode } = openSky
const { satelliteEnabled } = satellite
const { poiEnabled } = poi
const { tiles3dEnabled, tiles3dLoading } = tiles3d
const { transitEnabled } = transit
const { enabled: governmentEnabled } = gov
const { enabled: churchEnabled } = church
const { enabled: condosEnabled } = condo
const { enabled: hubsEnabled } = hub
const { enabled: meshEnabled } = mesh
const {
  trackersEnabled, trackerPositionsList, meshRouterPositionsList,
  energyCellsEnabled, energyCellsList, envStationsEnabled, envStationsList,
  iotPopoverOpen, showIoTPreview, hideIoTPreview,
} = iot
const { measureActive, measureMode } = measure
const { sunStudyActive } = sunStudy
const { isochroneActive } = isochrone
const { droneReachActive } = droneReach
const { urbanActive } = urban

// ======== Popover state ========

const layersPopoverOpen = ref(false)
const architectPopoverOpen = ref(false)

const anyPopoverOpen = computed(() =>
  layersPopoverOpen.value || architectPopoverOpen.value || iotPopoverOpen.value)

const closeAllPopovers = () => {
  layersPopoverOpen.value = false
  architectPopoverOpen.value = false
  iotPopoverOpen.value = false
  hideIoTPreview()
}

// Close popovers on outside click (button/panel clicks use @click.stop)
const onDocumentClick = () => closeAllPopovers()
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

// ======== Layers tile matrix ========

const layerMatrixGroups = computed(() => [
  {
    id: 'imagery',
    label: t('map.controls.imagery'),
    items: [
      { id: 'aerial', icon: Satellite, label: t('map.layers.aerial'), active: openSkyEnabled.value },
      { id: 'satellite', icon: ImageIcon, label: t('map.layers.satellite'), active: satelliteEnabled.value },
      { id: 'tiles3d', icon: Box, label: t('map.layers.aerial_3d'), active: tiles3dEnabled.value, loading: tiles3dLoading.value },
    ],
  },
  {
    id: 'data',
    label: t('map.controls.data_layers'),
    items: [
      { id: 'transit', icon: Bus, label: t('map.layers.transit'), active: transitEnabled.value, dot: !!transit.activeRouteFilter.value },
      { id: 'poi', icon: MapPin, label: t('map.controls.poi_short'), active: poiEnabled.value },
      { id: 'government', icon: Landmark, label: t('map.layers.government'), active: governmentEnabled.value },
      { id: 'churches', icon: Cross, label: t('map.layers.churches'), active: churchEnabled.value },
      { id: 'condos', icon: Building2, label: t('map.layers.condominiums'), active: condosEnabled.value },
      { id: 'hubs', icon: Package, label: t('map.layers.hubs'), active: hubsEnabled.value },
      { id: 'mesh', icon: Wifi, label: t('map.layers.mesh_network'), active: meshEnabled.value },
      { id: 'energy', icon: Zap, label: t('map.layers.energy'), active: energyCellsEnabled.value },
      { id: 'environment', icon: Wind, label: t('map.layers.environment'), active: envStationsEnabled.value },
    ],
  },
])

const activeLayerCount = computed(() =>
  layerMatrixGroups.value.reduce((n, g) => n + g.items.filter((it) => it.active).length, 0))

function onLayerPick(id: string) {
  switch (id) {
    case 'aerial': toggleOpenSkyLayer(); break
    case 'satellite': satellite.toggleLayer(); break
    case 'tiles3d': toggle3DTiles(); break
    case 'transit': transit.toggleLayer(); break
    case 'poi': poi.toggle(); break
    case 'government': gov.toggle(); break
    case 'churches': church.toggle(); break
    case 'condos': condo.toggle(); break
    case 'hubs': hub.toggle(); break
    case 'mesh': mesh.toggle(); break
    case 'energy': iot.toggleEnergyCells(); break
    case 'environment': iot.toggleEnvStations(); break
  }
}

// ======== Map tools: one active at a time ========

type Tool = 'measure-distance' | 'measure-area' | 'sun' | 'isochrone' | 'droneReach' | 'urban' | 'opensky'

const toolMatrixGroups = computed(() => [{
  id: 'tools',
  items: [
    { id: 'measure-distance', icon: Ruler, label: t('map.architect.measure'), active: measureActive.value && measureMode.value === 'distance' },
    { id: 'measure-area', icon: Pentagon, label: t('map.architect.measure_area'), active: measureActive.value && measureMode.value === 'area' },
    { id: 'sun', icon: Sun, label: t('map.architect.sun_study'), active: sunStudyActive.value },
    { id: 'isochrone', icon: Clock, label: t('map.architect.isochrone'), active: isochroneActive.value },
    { id: 'droneReach', icon: Radio, label: t('map.architect.drone_reach'), active: droneReachActive.value },
    { id: 'urban', icon: Building, label: t('map.urban.title'), active: urbanActive.value },
    { id: 'opensky', icon: Grid3x3, label: t('map.opensky.plan_missions'), active: tileGridMode.value, loading: missionGenerating.value },
  ],
}])

const activeToolLabel = computed(() =>
  toolMatrixGroups.value[0].items.find((it) => it.active)?.label ?? t('map.controls.off'))

function startTool(tool: Tool) {
  const keep = tool.startsWith('measure') ? 'measure' : tool
  if (keep !== 'measure' && measureActive.value) measure.stopMeasure()
  if (keep !== 'sun' && sunStudyActive.value) sunStudy.stopSunStudy()
  if (keep !== 'isochrone' && isochroneActive.value) isochrone.stopIsochrone()
  if (keep !== 'droneReach' && droneReachActive.value) droneReach.stopDroneReach()
  if (keep !== 'urban' && urbanActive.value) urban.stopUrban()
  if (keep !== 'opensky' && tileGridMode.value) openSky.toggleTileGrid()
  if (tool === 'measure-distance') measure.toggleMeasure('distance')
  else if (tool === 'measure-area') measure.toggleMeasure('area')
  else if (tool === 'sun') sunStudy.toggleSunStudy()
  else if (tool === 'isochrone') isochrone.toggleIsochrone()
  else if (tool === 'droneReach') droneReach.toggleDroneReach()
  else if (tool === 'opensky') openSky.toggleTileGrid()
  else urban.toggleUrban()
  architectPopoverOpen.value = false
}

function onToolPick(id: string) {
  startTool(id as Tool)
}

// ======== IoT device console ========

const propertyStore = usePropertyStore()
const propertiesLoaded = ref(false)

watch(iotPopoverOpen, async (open) => {
  if (open && !propertiesLoaded.value && authStore.isAuthenticated) {
    await propertyStore.fetchProperties()
    propertiesLoaded.value = true
  }
})

const iotStats = computed(() => {
  const trackers = trackerPositionsList.value || []
  const routers = meshRouterPositionsList.value || []
  const cells = energyCellsList.value || []
  const stations = envStationsList.value || []
  const online = trackers.filter((tr: any) => tr.traccar_status === 'online').length
    + routers.filter((r: any) => r.status === 'online').length
    + cells.filter((c: any) => c.status !== 'OFFLINE').length
    + stations.filter((s: any) => !s.stale).length
  return { online, total: trackers.length + routers.length + cells.length + stations.length }
})

function onConsoleSelect(kind: string, item: any) {
  switch (kind) {
    case 'home': emit('select-property', item); break
    case 'tracker': emit('select-tracker', item); break
    case 'router': iot.flyToMeshRouter(item.latitude, item.longitude, item.name); break
    case 'energy': iot.flyToEnergyCell(item.latitude, item.longitude, item.name); break
    case 'env': iot.flyToEnvStation(item.latitude, item.longitude, item.name); break
  }
}

function onConsoleToggleLayer(kind: string) {
  switch (kind) {
    case 'tracker': iot.toggleTrackers(); break
    case 'router': mesh.toggle(); break
    case 'energy': iot.toggleEnergyCells(); break
    case 'env': iot.toggleEnvStations(); break
  }
}

function onPreview(pos: { lat: number; lon: number } | null) {
  if (pos) showIoTPreview(pos.lat, pos.lon)
  else hideIoTPreview()
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

/* Dark selector repeated after the dark hover rule to win the cascade */
.opensky-btn.active,
:root.dark .opensky-btn.active {
  background: var(--color-primary, #ffe216);
  color: #171717;
}

/* ── Console popovers (desktop) / bottom sheets (phones) ── */

.mc-backdrop {
  display: none;
}

.mc-pop {
  position: absolute;
  right: 54px;
  top: 0;
  z-index: 1003;
  width: 264px;
  max-height: calc(100dvh - 220px - var(--safe-area-inset-top, env(safe-area-inset-top, 0px)) - var(--safe-area-inset-bottom, env(safe-area-inset-bottom, 0px)));
  display: flex;
  flex-direction: column;
  padding: 10px;
  border: 1px solid var(--color-border, #e5e5e5);
  border-radius: 12px;
  background: var(--color-surface, #fff);
  box-shadow: 0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1);
}
/* Floating element in dark mode = solid fill, never tinted alpha */
:root.dark .mc-pop {
  background: #171717;
  border-color: #404040;
}

.mc-pop-iot {
  width: 300px;
}

.mc-sheet-handle { display: none; }

.mc-pop-head {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 2px 2px 10px;
}

.mc-pop-title {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--color-text);
}

.mc-pop-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 10px;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  color: var(--color-text-muted, #737373);
  border: 1px solid var(--color-border, #e5e5e5);
  border-radius: 999px;
  padding: 2px 8px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 60%;
}

.mc-online-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-success, #059669);
  flex-shrink: 0;
}

/* Body scrolls as a fallback (rigid tile matrix on a short viewport); the
   device console manages its own inner list scroll via the flex chain.
   6px padding + negative margin leaves room for the reticle ticks (5px)
   without clipping them against the scroll container edge. */
.mc-pop-body {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  padding: 6px;
  margin: -6px;
}

.mc-pop-enter-active { transition: opacity 0.12s ease-out, transform 0.12s ease-out; }
.mc-pop-leave-active { transition: opacity 0.1s ease-in, transform 0.1s ease-in; }
.mc-pop-enter-from,
.mc-pop-leave-to { opacity: 0; transform: translateX(4px) scale(0.98); }

.mc-backdrop-enter-active,
.mc-backdrop-leave-active { transition: opacity 0.2s; }
.mc-backdrop-enter-from,
.mc-backdrop-leave-to { opacity: 0; }

/* Phones: fused full-bleed bottom sheet — capped height, internal scroll,
   seated on the nav dock (which already carries the gesture-bar safe area). */
@media (max-width: 767px) {
  .mc-backdrop {
    display: block;
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.35);
    z-index: 1002;
  }

  .mc-pop,
  .mc-pop-iot {
    position: fixed;
    left: 0;
    right: 0;
    /* Sits ON the nav bar's top edge — the bar keeps working while a sheet is
       up, so the sheet is a standard (non-modal) one, not a cover. */
    bottom: var(--nav-inset-bottom);
    top: auto;
    width: auto;
    max-height: 76dvh;
    border-radius: 18px 18px 0 0;
    border-left: none;
    border-right: none;
    border-bottom: none;
    padding: 0 12px 10px;
    box-shadow: 0 -8px 24px rgba(0, 0, 0, 0.18);
  }

  .mc-sheet-handle {
    display: flex;
    justify-content: center;
    padding: 8px 0 6px;
    flex-shrink: 0;
  }
  .mc-sheet-handle span {
    width: 36px;
    height: 4px;
    border-radius: 999px;
    background: var(--color-border, #d4d4d4);
  }

  .mc-pop-enter-active { transition: transform 0.22s cubic-bezier(0.2, 0.8, 0.3, 1); }
  .mc-pop-leave-active { transition: transform 0.18s ease-in; }
  .mc-pop-enter-from,
  .mc-pop-leave-to { opacity: 1; transform: translateY(100%); }
}

</style>
