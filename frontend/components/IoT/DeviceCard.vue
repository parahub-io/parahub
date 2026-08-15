<template>
  <div class="device-card group" :class="{ 'realtime-flash': justUpdated }">
    <!-- Zone A0: Map viewport — any device with a known position (tracker fix / mesh set location).
         Status lives on the map as a HUD overlay so the header below stays a single dense row. -->
    <div v-if="hasMap" class="relative shrink-0 m-1 mb-0 aspect-[1.618/1] rounded overflow-hidden bg-neutral-200 dark:bg-neutral-700">
      <img v-if="snapshotUrl" :src="snapshotUrl" :alt="device.name" class="w-full h-full object-cover" loading="lazy" />
      <div v-else class="w-full h-full animate-pulse" />
      <IoTSnapshotMarker :fill="markerFill" :glyph="markerGlyph" />
      <!-- Top scrim keeps the HUD legible over map tiles -->
      <div class="absolute inset-x-0 top-0 h-9 bg-gradient-to-b from-black/55 to-transparent pointer-events-none" />
      <span class="absolute top-2 left-3 font-mono text-[10px] uppercase tracking-wider text-white/75">
        {{ getDeviceTypeLabel(device.device_type) }}
      </span>
      <span class="absolute top-2 right-3 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wider text-white/90"
            role="status" aria-live="polite">
        <span class="w-1.5 h-1.5 rounded-full" :class="getStatusColor(device)" />
        {{ getDeviceStatus(device).text }}
      </span>
    </div>

    <div class="p-4 flex-1 flex flex-col" :class="{ 'pt-2.5': hasMap }">
    <!-- Zone A: Header -->
    <div class="flex justify-between items-start mb-2">
      <div class="flex-1 min-w-0">
        <h3 class="text-base font-semibold text-neutral-900 dark:text-neutral-100 truncate">
          {{ device.name }}
        </h3>
        <!-- Subtitle: hardware · uptime + badges -->
        <div v-if="device.device_type === 'MESH_ROUTER'" class="flex items-center gap-1.5 flex-wrap mt-0.5">
          <span class="text-xs text-neutral-500 dark:text-neutral-400">
            <template v-if="device.connection_info?.hardware_profile && device.connection_info.hardware_profile !== 'unknown'">
              {{ getHardwareName(device.connection_info.hardware_profile) }}
            </template>
            <template v-if="device.connection_info?.hardware_profile && device.connection_info.hardware_profile !== 'unknown' && device.connection_info?.uptime"> · </template>
            <template v-if="device.connection_info?.uptime">
              {{ formatUptime(device.connection_info.uptime) }}
            </template>
          </span>
          <!-- Role badge -->
          <span v-if="firmwareRole && firmwareRole !== 'unknown'"
                class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium"
                :class="firmwareRole === 'bumblebee'
                  ? 'bg-amber-100 text-amber-800 dark:bg-amber-800 dark:text-amber-200'
                  : 'bg-sky-100 text-sky-800 dark:bg-sky-800 dark:text-sky-200'">
            {{ firmwareRole === 'bumblebee' ? 'Bumblebee' : 'Bee' }}
          </span>
          <!-- VPN pill -->
          <span v-if="vpnPill" class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium" :class="vpnPill.cls">
            {{ vpnPill.label }}
          </span>
          <!-- Ygg inbound wedged: node heartbeats but its management path is dead -->
          <span v-if="device.ygg_inbound_ok === false"
                class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300"
                :title="$t('iot.ssh_unreachable_hint')">
            {{ $t('iot.ssh_unreachable') }}
          </span>
          <!-- Property chip -->
          <NuxtLink v-if="propertyId && propertyName" :to="localePath(`/iot/${propertyId}`)" class="property-chip">
            <Home class="w-3 h-3" aria-hidden="true" /> {{ propertyName }}
          </NuxtLink>
          <!-- Shared-by chip -->
          <span v-if="isShared" class="property-chip" :title="device.owner_hna || undefined">
            <Users class="w-3 h-3" aria-hidden="true" /> {{ $t('iot.shared_by', { name: device.owner_name }) }}
          </span>
          <!-- Hosting reciprocity: this node is what keeps the owner's pass alive -->
          <NuxtLink v-if="keepsHostPass" :to="localePath('/free')" class="property-chip" :title="$t('iot.host_pass_hint')">
            <Gauge class="w-3 h-3" aria-hidden="true" /> {{ $t('iot.host_pass') }}
          </NuxtLink>
        </div>
        <!-- Non-mesh type badge -->
        <div v-else class="flex items-center gap-1.5 flex-wrap mt-0.5">
          <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium"
                :class="getDeviceTypeClass(device.device_type)">
            {{ getDeviceTypeLabel(device.device_type) }}
          </span>
          <!-- Property chip -->
          <NuxtLink v-if="propertyId && propertyName" :to="localePath(`/iot/${propertyId}`)" class="property-chip">
            <Home class="w-3 h-3" aria-hidden="true" /> {{ propertyName }}
          </NuxtLink>
          <!-- Shared-by chip -->
          <span v-if="isShared" class="property-chip" :title="device.owner_hna || undefined">
            <Users class="w-3 h-3" aria-hidden="true" /> {{ $t('iot.shared_by', { name: device.owner_name }) }}
          </span>
        </div>
      </div>

      <!-- Status (in the header only when there is no map HUD carrying it) -->
      <div v-if="!hasMap" class="flex items-center gap-1.5 shrink-0 ml-2" role="status" aria-live="polite">
        <div class="w-2.5 h-2.5 rounded-full"
             :class="getStatusColor(device)"
             :aria-label="`Status: ${getDeviceStatus(device).text}`"></div>
        <span class="text-sm text-neutral-500 dark:text-neutral-400">
          {{ getDeviceStatus(device).text }}
        </span>
      </div>
    </div>

    <!-- Zone B: Firmware Update Banner (mesh only, conditional) -->
    <UiAlert v-if="hasFirmwareUpdate" variant="warning" :icon="ArrowUpCircle" class="mb-3">
      {{ $t('iot.firmware') }}: {{ $t('iot.firmware_update_banner', { current: device.connection_info?.firmware_version, latest: device.latest_firmware_version }) }}
    </UiAlert>

    <!-- Zone C: Key metrics. Everything deeper (addresses, telemetry, settings)
         lives on the device page — the card stays scannable in a grid. -->
    <div v-if="device.device_type === 'MESH_ROUTER'" class="space-y-1 mb-2.5">
      <div v-if="device.connection_info?.firmware_version" class="flex justify-between text-sm">
        <span class="text-neutral-500 dark:text-neutral-400">{{ $t('iot.firmware') }}:</span>
        <span class="text-neutral-900 dark:text-neutral-100">{{ device.connection_info.firmware_version }}</span>
      </div>

      <div v-if="device.last_seen" class="flex justify-between text-sm">
        <span class="text-neutral-500 dark:text-neutral-400">{{ $t('iot.last_heartbeat') }}:</span>
        <span class="text-neutral-900 dark:text-neutral-100" :title="formatDate(device.last_seen)">{{ formatRelativeTime(device.last_seen) }}</span>
      </div>
    </div>

    <!-- Generic Device Info (non-mesh, non-tracker) -->
    <div v-else-if="device.device_type !== 'TRACKER'" class="space-y-1 mb-2.5">
      <div v-if="device.imei" class="flex justify-between text-sm">
        <span class="text-neutral-500 dark:text-neutral-400">IMEI:</span>
        <span class="font-mono text-neutral-900 dark:text-neutral-100">{{ device.imei }}</span>
      </div>

      <div v-if="device.last_seen" class="flex justify-between text-sm">
        <span class="text-neutral-500 dark:text-neutral-400">{{ $t('iot.last_activity') }}:</span>
        <span class="text-neutral-900 dark:text-neutral-100">{{ formatDate(device.last_seen) }}</span>
      </div>
    </div>

    <!-- Tracker info (map lives in the top viewport) -->
    <div v-if="device.device_type === 'TRACKER'" class="mb-2.5">
      <div v-if="!hasMap" class="flex items-center text-neutral-500 dark:text-neutral-400 mb-2">
        <MapPin class="w-4 h-4 mr-2" aria-hidden="true" />
        <span class="text-sm">{{ $t('iot.no_location') }}</span>
      </div>

      <div class="space-y-1">
        <div v-if="device.last_seen" class="flex justify-between text-sm">
          <span class="text-neutral-500 dark:text-neutral-400">{{ $t('iot.last_activity') }}:</span>
          <span class="text-neutral-900 dark:text-neutral-100" :title="formatDate(device.last_seen)">{{ formatRelativeTime(device.last_seen) }}</span>
        </div>

        <div v-if="device.speed != null" class="flex justify-between text-sm">
          <span class="text-neutral-500 dark:text-neutral-400">{{ $t('iot.speed') }}:</span>
          <span class="text-neutral-900 dark:text-neutral-100">{{ getSpeedInfo(device.speed) }}</span>
        </div>

        <div v-if="device.battery_level != null" class="flex justify-between text-sm">
          <span class="text-neutral-500 dark:text-neutral-400 flex items-center">
            <BatteryFull class="w-3 h-3 mr-1" aria-hidden="true" />{{ $t('iot.battery') }}:
          </span>
          <span :class="getBatteryColor(device.battery_level)">{{ getBatteryInfo(device.battery_level).level }}</span>
        </div>
      </div>
    </div>

    <!-- Zone D: Actions. Two, deliberately: the one thing people do at the door
         (hand over the WiFi password) and the door to everything else. -->
    <div class="flex items-center gap-2 mt-auto pt-2.5 border-t border-neutral-200 dark:border-neutral-700">
      <UiButton
        v-if="device.device_type === 'MESH_ROUTER' && canManage"
        variant="outline" size="sm" :icon="Wifi" :loading="wifiLoading"
        :title="$t('iot.show_wifi_password')" @click="handleShowWifiPassword"
      >
        WiFi
      </UiButton>

      <UiButton
        variant="secondary" size="sm" :icon="SlidersHorizontal" class="ml-auto"
        :to="localePath(`/iot/device/${device.id}`)"
      >
        {{ $t('iot.manage') }}
      </UiButton>
    </div>

    <div v-if="wifiError" class="mt-2 text-sm text-error dark:text-error-400">
      {{ wifiError }}
    </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  Wifi, MapPin, BatteryFull, ArrowUpCircle, Home, Users, Gauge, SlidersHorizontal,
} from 'lucide-vue-next'
import { NAVIGATION_GLYPH } from '~/composables/useMapToggleableLayer'
import type { IoTDevice } from '~/stores/iot'

interface Props {
  device: IoTDevice
  // Shown as a chip linking to the property page (device-inventory views)
  propertyId?: string | null
  propertyName?: string | null
}

const props = defineProps<Props>()

const toastStore = useToastStore()
const localePath = useLocalePath()
const { deviceErrorText } = useIoT()
const { justUpdated } = useRealtimeObject(computed(() => props.device.id))

// Shorthand for firmware role
const firmwareRole = computed(() => props.device.connection_info?.firmware_role)

// Access role (universal ObjectAccess grants): OWNER when absent (legacy paths)
const accessRole = computed(() => props.device.access_role || 'OWNER')
const canManage = computed(() => accessRole.value !== 'VIEWER')
const isShared = computed(() => !!props.device.owner_name)

// Only while the node actually reports — reciprocity runs off the heartbeat,
// and a chip on a dead node would promise coverage nothing is renewing.
const keepsHostPass = computed(() =>
  !!props.device.keeps_host_pass && getDeviceStatus(props.device).status === 'online')

// Mesh router coordinates from connection_info or device-level lat/lon
const meshRouterLat = computed(() => props.device.latitude ?? props.device.connection_info?.latitude ?? null)
const meshRouterLng = computed(() => props.device.longitude ?? props.device.connection_info?.longitude ?? null)

// Map viewport (shared single MapLibre instance) — trackers (live fix) and
// mesh routers (owner-set location) both render the top map snapshot
const { capture, invalidate } = useMapSnapshots()
const snapshotUrl = ref<string | null>(null)

const mapLat = computed(() => props.device.device_type === 'MESH_ROUTER' ? meshRouterLat.value : props.device.latitude ?? null)
const mapLng = computed(() => props.device.device_type === 'MESH_ROUTER' ? meshRouterLng.value : props.device.longitude ?? null)
const hasMap = computed(() => mapLat.value != null && mapLng.value != null)

// Marker grammar (PK/design-system.md § Map Markers): device hexagon, fill =
// status — online secondary, stale/unknown grey, offline red. Glyph = device
// type, same as /map: WiFi arcs for mesh routers, navigation arrow for trackers.
const MARKER_STATUS_FILLS: Record<string, string> = {
  online: '#4E4EC8', recent: '#a3a3a3', never: '#a3a3a3', offline: '#ef4444',
}
const markerFill = computed(() => MARKER_STATUS_FILLS[getDeviceStatus(props.device).status] || '#a3a3a3')
const markerGlyph = computed(() => {
  if (props.device.device_type === 'MESH_ROUTER') return 'wifi' as const
  if (props.device.device_type === 'TRACKER') return NAVIGATION_GLYPH
  return null
})

async function loadSnapshot() {
  if (mapLat.value == null || mapLng.value == null) return
  snapshotUrl.value = await capture(mapLat.value, mapLng.value)
}

// Reload snapshot when the position changes (tracker moves / mesh location set)
watch(
  [mapLat, mapLng],
  ([lat, lon], [oldLat, oldLon]) => {
    if (lat == null || lon == null) return
    if (lat === oldLat && lon === oldLon) return
    if (oldLat != null && oldLon != null) invalidate(oldLat, oldLon)
    loadSnapshot()
  },
)

onMounted(loadSnapshot)

// VPN pill for bumblebee routers
const vpnPill = computed(() => {
  if (props.device.device_type !== 'MESH_ROUTER') return null
  if (firmwareRole.value !== 'bumblebee') return null
  const mode = props.device.connection_info?.vpn_mode
  if (!mode || mode === 'unknown') return null
  if (mode === 'vps') return { label: 'VPS', cls: 'bg-secondary-100 text-secondary-800 dark:bg-secondary-800 dark:text-secondary-200' }
  if (mode === 'mullvad') return { label: 'Mullvad', cls: 'bg-green-100 text-green-800 dark:bg-green-800 dark:text-green-200' }
  if (mode === 'none') return { label: 'No VPN', cls: 'bg-red-100 text-red-800 dark:bg-red-800 dark:text-red-200' }
  return null
})

// Firmware update indicator
const hasFirmwareUpdate = computed(() => {
  if (props.device.device_type !== 'MESH_ROUTER') return false
  const current = props.device.connection_info?.firmware_version
  const latest = props.device.latest_firmware_version
  if (!current || !latest) return false
  return current !== latest
})

const store = useIoTStore()
const {
  getDeviceTypeLabel,
  getDeviceStatus,
  formatDate,
  formatRelativeTime,
  formatUptime,
  getBatteryInfo,
  getSpeedInfo,
  getHardwareName,
} = useIoT()

// WiFi password: the one action that happens standing next to the router, so it
// stays on the card. Toast + clipboard, no navigation.
const wifiLoading = ref(false)
const wifiError = ref<string | null>(null)

const handleShowWifiPassword = async () => {
  if (wifiLoading.value) return
  wifiLoading.value = true
  wifiError.value = null

  try {
    const data = await store.getWifiPassword(props.device.id)
    try {
      await navigator.clipboard.writeText(data.wifi_password)
    } catch { /* clipboard may fail */ }
    toastStore.success(`SSID: ${data.ssid}\nPassword: ${data.wifi_password}`, undefined, 30000)
  } catch (err: any) {
    wifiError.value = deviceErrorText(err)
  } finally {
    wifiLoading.value = false
  }
}

// Device type styling (non-mesh only now)
const getDeviceTypeClass = (type: string) => {
  const classes: Record<string, string> = {
    'TRACKER': 'bg-purple-100 text-purple-800 dark:bg-purple-800 dark:text-purple-200',
    'SENSOR': 'bg-secondary-100 text-secondary-800 dark:bg-secondary-800 dark:text-secondary-200',
    'ACTUATOR': 'bg-green-100 text-green-800 dark:bg-green-800 dark:text-green-200',
    'GATEWAY': 'bg-orange-100 text-orange-800 dark:bg-orange-800 dark:text-orange-200',
  }
  return classes[type] || 'bg-neutral-100 text-neutral-800 dark:bg-neutral-800 dark:text-neutral-200'
}

// Status color
const getStatusColor = (device: IoTDevice) => {
  const status = getDeviceStatus(device).status
  const colors: Record<string, string> = {
    'online': 'bg-green-500',
    'recent': 'bg-yellow-500',
    'offline': 'bg-red-500',
    'never': 'bg-neutral-400'
  }
  return colors[status] || 'bg-neutral-400'
}

// Battery color based on level
const getBatteryColor = (batteryLevel: number) => {
  if (batteryLevel > 50) return 'text-green-600 dark:text-green-400'
  if (batteryLevel > 20) return 'text-yellow-600 dark:text-yellow-400'
  return 'text-red-600 dark:text-red-400'
}
</script>

<style scoped>
.device-card {
  @apply flex flex-col bg-neutral-100 dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700;
  @apply hover:border-primary transition-colors;
}

.realtime-flash {
  @apply ring-2 ring-yellow-400;
}

.property-chip {
  @apply inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium;
  @apply bg-neutral-200 text-neutral-600 dark:bg-neutral-700 dark:text-neutral-300;
  @apply hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors;
}
</style>
