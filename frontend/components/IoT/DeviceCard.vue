<template>
  <div class="device-card group" :class="{ 'realtime-flash': justUpdated }">
    <!-- Zone A: Header -->
    <div class="flex justify-between items-start mb-3">
      <div class="flex-1 min-w-0">
        <!-- Inline rename -->
        <div v-if="renaming" class="flex items-center gap-1.5 mb-1">
          <input
            ref="renameInput"
            v-model="renameValue"
            class="text-lg font-semibold bg-transparent border-b-2 border-primary outline-none text-neutral-900 dark:text-neutral-100 flex-1 min-w-0"
            maxlength="100"
            @keydown.enter="saveRename"
            @keydown.escape="cancelRename"
          />
          <button @click="saveRename" class="p-1 rounded hover:bg-green-100 dark:hover:bg-green-900/30 text-green-600 dark:text-green-400 transition-colors" :aria-label="'Save'">
            <Check class="w-4 h-4" />
          </button>
          <button @click="cancelRename" class="p-1 rounded hover:bg-neutral-200 dark:hover:bg-neutral-700 text-neutral-500 transition-colors" :aria-label="'Cancel'">
            <X class="w-4 h-4" />
          </button>
        </div>
        <h3 v-else class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 truncate">
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
        </div>
        <!-- Non-mesh type badge -->
        <div v-else class="flex items-center gap-1.5 flex-wrap mt-0.5">
          <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium"
                :class="getDeviceTypeClass(device.device_type)">
            {{ getDeviceTypeLabel(device.device_type) }}
          </span>
        </div>
      </div>

      <!-- Status -->
      <div class="flex items-center gap-1.5 shrink-0 ml-2" role="status" aria-live="polite">
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

    <!-- Zone C: Key Metrics (mesh routers) -->
    <div v-if="device.device_type === 'MESH_ROUTER'" class="space-y-1.5 mb-3">
      <div v-if="device.connection_info?.firmware_version" class="flex justify-between text-sm">
        <span class="text-neutral-500 dark:text-neutral-400">{{ $t('iot.firmware') }}:</span>
        <span class="text-neutral-900 dark:text-neutral-100">{{ device.connection_info.firmware_version }}</span>
      </div>

      <div v-if="device.last_seen" class="flex justify-between text-sm">
        <span class="text-neutral-500 dark:text-neutral-400">{{ $t('iot.last_heartbeat') }}:</span>
        <span class="text-neutral-900 dark:text-neutral-100" :title="formatDate(device.last_seen)">{{ formatRelativeTime(device.last_seen) }}</span>
      </div>

      <!-- Zone D: Collapsible network details with copy buttons -->
      <details v-if="device.device_id || hasYggdrasil || hasMeshIp" class="border border-neutral-200 dark:border-neutral-700 rounded-lg mt-2">
        <summary class="cursor-pointer px-3 py-2 text-sm font-medium text-neutral-500 dark:text-neutral-400 hover:bg-neutral-50 dark:hover:bg-neutral-700/50 rounded-lg transition-colors select-none">
          {{ $t('iot.network_details') }}
        </summary>
        <div class="px-3 pb-3 pt-1 space-y-2">
          <div v-if="device.device_id" class="flex justify-between items-center text-sm gap-2">
            <span class="text-neutral-500 dark:text-neutral-400 shrink-0">MAC:</span>
            <div class="flex items-center gap-1 min-w-0">
              <span class="font-mono text-neutral-900 dark:text-neutral-100 truncate">{{ device.device_id }}</span>
              <button @click="copyWithToast(device.device_id!, $t('iot.copied_address'))" class="copy-btn" :aria-label="$t('iot.copy')">
                <Copy class="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          <div v-if="hasYggdrasil" class="flex justify-between items-center text-sm gap-2">
            <span class="text-neutral-500 dark:text-neutral-400 shrink-0">Yggdrasil:</span>
            <div class="flex items-center gap-1 min-w-0">
              <span class="font-mono text-xs text-neutral-900 dark:text-neutral-100 break-all">
                {{ device.connection_info!.yggdrasil_address }}
              </span>
              <button @click="copyWithToast(device.connection_info!.yggdrasil_address!, $t('iot.copied_address'))" class="copy-btn shrink-0" :aria-label="$t('iot.copy')">
                <Copy class="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          <div v-if="hasMeshIp" class="flex justify-between items-center text-sm gap-2">
            <span class="text-neutral-500 dark:text-neutral-400 shrink-0">Mesh IP:</span>
            <div class="flex items-center gap-1 min-w-0">
              <span class="font-mono text-neutral-900 dark:text-neutral-100">{{ device.connection_info!.mesh_ip }}</span>
              <button @click="copyWithToast(device.connection_info!.mesh_ip!, $t('iot.copied_address'))" class="copy-btn" :aria-label="$t('iot.copy')">
                <Copy class="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      </details>
    </div>

    <!-- Generic Device Info (non-mesh, non-tracker) -->
    <div v-else-if="device.device_type !== 'TRACKER'" class="space-y-2 mb-4">
      <div v-if="device.imei" class="flex justify-between text-sm">
        <span class="text-neutral-500 dark:text-neutral-400">IMEI:</span>
        <span class="font-mono text-neutral-900 dark:text-neutral-100">{{ device.imei }}</span>
      </div>

      <div v-if="device.last_seen" class="flex justify-between text-sm">
        <span class="text-neutral-500 dark:text-neutral-400">{{ $t('iot.last_activity') }}:</span>
        <span class="text-neutral-900 dark:text-neutral-100">{{ formatDate(device.last_seen) }}</span>
      </div>
    </div>

    <!-- Location data for trackers -->
    <div v-if="device.device_type === 'TRACKER'" class="mb-4">
      <!-- Map snapshot (shared MapLibre instance) -->
      <div v-if="hasLocationData(device)" class="mb-3 relative aspect-[1.618/1] rounded-lg overflow-hidden bg-neutral-200 dark:bg-neutral-700">
        <img v-if="snapshotUrl" :src="snapshotUrl" :alt="device.name" class="w-full h-full object-cover" loading="lazy" />
        <div v-else class="w-full h-full animate-pulse" />
        <div class="snapshot-marker">
          <div class="snapshot-marker-pulse" />
          <div class="snapshot-marker-dot" />
        </div>
      </div>
      <div v-else class="flex items-center text-neutral-500 dark:text-neutral-400 mb-3">
        <MapPin class="w-4 h-4 mr-2" aria-hidden="true" />
        <span class="text-sm">{{ $t('iot.no_location') }}</span>
      </div>

      <!-- Tracker info -->
      <div class="space-y-2">
        <div v-if="device.last_seen" class="flex justify-between text-sm">
          <span class="text-neutral-500 dark:text-neutral-400">{{ $t('iot.last_activity') }}:</span>
          <span class="text-neutral-900 dark:text-neutral-100">{{ formatDate(device.last_seen) }}</span>
        </div>

        <div v-if="device.speed !== undefined" class="flex justify-between text-sm">
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

    <!-- Zone F: Actions -->
    <div class="flex items-start gap-2 pt-3 border-t border-neutral-200 dark:border-neutral-700">
      <div class="flex flex-wrap items-center gap-2 flex-1">
        <!-- Traccar link for registered trackers -->
        <a v-if="device.device_type === 'TRACKER' && device.traccar_device_id && traccarUrl"
           :href="traccarUrl"
           target="_blank"
           :aria-label="'Open Traccar for device ' + device.name + ' (opens in new tab)'"
           class="btn-primary text-sm">
          <LucideMap class="w-4 h-4 mr-1" aria-hidden="true" />
          <span>Traccar</span>
        </a>

        <!-- WiFi password quick button (mesh only) -->
        <button v-if="device.device_type === 'MESH_ROUTER'"
                @click="handleShowWifiPassword"
                :disabled="wifiLoading"
                :title="$t('iot.show_wifi_password')"
                class="btn-secondary text-sm">
          <Loader2 v-if="wifiLoading" class="w-4 h-4 mr-1 animate-spin" aria-hidden="true" />
          <Wifi v-else class="w-4 h-4 mr-1" aria-hidden="true" />
          <span>WiFi</span>
        </button>

        <!-- VPN (bumblebee only) -->
        <button v-if="device.device_type === 'MESH_ROUTER' && firmwareRole === 'bumblebee'"
                @click="showVpnSettings = true"
                :title="vpnMenuLabel"
                class="btn-secondary text-sm">
          <Shield class="w-4 h-4 mr-1" aria-hidden="true" />
          <span>{{ vpnMenuLabel }}</span>
        </button>
      </div>

      <!-- Kebab menu -->
      <div class="relative shrink-0" ref="kebabRef">
        <button @click="showKebabMenu = !showKebabMenu"
                class="p-1.5 rounded-md text-neutral-500 dark:text-neutral-400 hover:bg-neutral-200 dark:hover:bg-neutral-700 transition-colors"
                :aria-label="$t('iot.more_actions')">
          <EllipsisVertical class="w-5 h-5" aria-hidden="true" />
        </button>

        <!-- Dropdown (opens upward) -->
        <Transition
          enter-active-class="transition ease-out duration-100"
          enter-from-class="transform opacity-0 scale-95"
          enter-to-class="transform opacity-100 scale-100"
          leave-active-class="transition ease-in duration-75"
          leave-from-class="transform opacity-100 scale-100"
          leave-to-class="transform opacity-0 scale-95"
        >
          <div v-if="showKebabMenu"
               class="absolute right-0 bottom-full mb-1 w-48 rounded-md shadow-lg bg-white dark:bg-neutral-800 ring-1 ring-black/5 dark:ring-white/10 z-20">
            <div class="py-1">
              <!-- WiFi Settings (bumblebee only) -->
              <button v-if="device.device_type === 'MESH_ROUTER' && firmwareRole !== 'bee'"
                      @click="showWifiConfig = true; showKebabMenu = false"
                      class="kebab-item">
                <Settings class="w-4 h-4 mr-2" aria-hidden="true" />
                {{ $t('mesh.wifi_settings') }}
              </button>

              <!-- Network Settings (bumblebee only — includes speed limit, LAN VPN, wired mesh) -->
              <button v-if="device.device_type === 'MESH_ROUTER' && firmwareRole === 'bumblebee'"
                      @click="showNetworkSettings = true; showKebabMenu = false"
                      class="kebab-item">
                <Network class="w-4 h-4 mr-2" aria-hidden="true" />
                {{ $t('mesh.network_settings') }}
              </button>

              <!-- Wired Mesh (bee only — bumblebee has it inside Network Settings) -->
              <button v-if="device.device_type === 'MESH_ROUTER' && firmwareRole === 'bee'"
                      @click="showWiredMesh = true; showKebabMenu = false"
                      class="kebab-item">
                <Network class="w-4 h-4 mr-2" aria-hidden="true" />
                {{ $t('mesh.wired_mesh') }}
              </button>

              <!-- Yggdrasil Access (bumblebee only) -->
              <button v-if="device.device_type === 'MESH_ROUTER' && firmwareRole === 'bumblebee'"
                      @click="showYggAccess = true; showKebabMenu = false"
                      class="kebab-item">
                <Globe class="w-4 h-4 mr-2" aria-hidden="true" />
                {{ $t('mesh.ygg_access') }}
              </button>

              <!-- Set Location (mesh routers) -->
              <button v-if="device.device_type === 'MESH_ROUTER'"
                      @click="showLocationPicker = true; showKebabMenu = false"
                      class="kebab-item">
                <MapPinned class="w-4 h-4 mr-2" aria-hidden="true" />
                {{ $t('mesh.set_location') }}
              </button>

              <!-- Root Password (mesh routers) -->
              <button v-if="device.device_type === 'MESH_ROUTER'"
                      @click="handleShowRootPassword(); showKebabMenu = false"
                      :disabled="rootLoading"
                      class="kebab-item">
                <Lock class="w-4 h-4 mr-2" aria-hidden="true" />
                {{ $t('iot.show_root_password') }}
              </button>

              <!-- Diagnostics (mesh routers) -->
              <button v-if="device.device_type === 'MESH_ROUTER'"
                      @click="showDiagnostics = true; showKebabMenu = false"
                      class="kebab-item">
                <Activity class="w-4 h-4 mr-2" aria-hidden="true" />
                {{ $t('mesh.diagnostics') }}
              </button>

              <!-- Divider -->
              <div class="border-t border-neutral-200 dark:border-neutral-700 my-1"></div>

              <!-- Rename -->
              <button @click="startRename(); showKebabMenu = false"
                      class="kebab-item">
                <Pencil class="w-4 h-4 mr-2" aria-hidden="true" />
                {{ $t('iot.rename') }}
              </button>

              <!-- Divider -->
              <div class="border-t border-neutral-200 dark:border-neutral-700 my-1"></div>

              <!-- Delete -->
              <button @click="showDeleteModal = true; showKebabMenu = false"
                      class="kebab-item !text-red-600 dark:!text-red-400 hover:!bg-red-50 dark:hover:!bg-red-900/20">
                <Trash2 class="w-4 h-4 mr-2" aria-hidden="true" />
                {{ $t('iot.delete') }}
              </button>
            </div>
          </div>
        </Transition>
      </div>
    </div>

    <!-- Errors -->
    <div v-if="wifiError" class="mt-2 text-sm text-red-600 dark:text-red-400">
      {{ wifiError }}
    </div>
    <div v-if="rootError" class="mt-2 text-sm text-red-600 dark:text-red-400">
      {{ rootError }}
    </div>

    <!-- Zone G: Delete Confirmation Modal -->
    <Modal v-model="showDeleteModal" :title="$t('iot.confirm_delete_title')" :icon="Trash2" icon-class="text-red-500" size="sm">
      <p class="text-sm text-neutral-600 dark:text-neutral-400">
        {{ $t('iot.confirm_delete_body', { name: device.name }) }}
      </p>
      <template #footer>
        <button @click="showDeleteModal = false" class="btn-secondary text-sm">
          {{ $t('iot.cancel') }}
        </button>
        <button @click="confirmDelete" class="btn-error text-sm">
          {{ $t('iot.delete') }}
        </button>
      </template>
    </Modal>

    <!-- WiFi Config Modal -->
    <IoTWifiConfigModal
      v-if="showWifiConfig"
      :device-id="device.id"
      :current-ssid="device.connection_info?.private_ssid"
      @close="showWifiConfig = false"
      @updated="$emit('refresh')"
    />

    <!-- Location Picker Modal -->
    <IoTLocationPickerModal
      v-if="showLocationPicker"
      :device-id="device.id"
      :initial-lat="meshRouterLat ?? undefined"
      :initial-lng="meshRouterLng ?? undefined"
      @close="showLocationPicker = false"
      @saved="handleLocationSaved"
    />

    <!-- VPN Settings Modal -->
    <IoTVpnSettingsModal
      v-if="showVpnSettings"
      :device-id="device.id"
      @close="showVpnSettings = false"
    />

    <!-- Network Settings Modal -->
    <IoTNetworkSettingsModal
      v-if="showNetworkSettings"
      :device-id="device.id"
      @close="showNetworkSettings = false"
    />

    <!-- Yggdrasil Access Modal -->
    <IoTYggAccessModal
      v-if="showYggAccess"
      :device-id="device.id"
      @close="showYggAccess = false"
    />

    <!-- Wired Mesh Modal (bee only — simple single-toggle modal) -->
    <IoTWiredMeshModal
      v-if="showWiredMesh"
      :device-id="device.id"
      @close="showWiredMesh = false"
    />

    <!-- Diagnostics Modal -->
    <IoTDiagnosticsModal
      v-if="showDiagnostics"
      :device-id="device.id"
      :firmware-role="firmwareRole || 'bee'"
      @close="showDiagnostics = false"
    />
  </div>
</template>

<script setup lang="ts">
import { Map as LucideMap, Trash2, Wifi, Lock, MapPin, BatteryFull, Settings, MapPinned, Shield, EllipsisVertical, Network, Activity, Pencil, Copy, ArrowUpCircle, Check, X, Loader2, Globe } from 'lucide-vue-next'
import type { IoTDevice } from '~/stores/iot'

interface Props {
  device: IoTDevice
}

interface Emits {
  (e: 'delete', deviceId: string): void
  (e: 'refresh'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const toastStore = useToastStore()
const { justUpdated } = useRealtimeObject(computed(() => props.device.id))

// Map snapshot for tracker cards (shared single MapLibre instance)
const { capture, invalidate } = useMapSnapshots()
const snapshotUrl = ref<string | null>(null)

async function loadSnapshot() {
  if (props.device.device_type !== 'TRACKER') return
  if (props.device.latitude == null || props.device.longitude == null) return
  snapshotUrl.value = await capture(props.device.latitude, props.device.longitude)
}

// Reload snapshot when tracker moves
watch(
  () => [props.device.latitude, props.device.longitude],
  ([lat, lon], [oldLat, oldLon]) => {
    if (lat == null || lon == null) return
    if (lat === oldLat && lon === oldLon) return
    if (oldLat != null && oldLon != null) invalidate(oldLat, oldLon)
    loadSnapshot()
  },
)

onMounted(loadSnapshot)

// Shorthand for firmware role
const firmwareRole = computed(() => props.device.connection_info?.firmware_role)

// Mesh router coordinates from connection_info or device-level lat/lon
const meshRouterLat = computed(() => props.device.latitude ?? props.device.connection_info?.latitude ?? null)
const meshRouterLng = computed(() => props.device.longitude ?? props.device.connection_info?.longitude ?? null)

// Computed helpers for network details conditionals
const hasYggdrasil = computed(() =>
  props.device.connection_info?.yggdrasil_address &&
  props.device.connection_info.yggdrasil_address !== 'unknown' &&
  props.device.connection_info.yggdrasil_address !== 'none'
)
const hasMeshIp = computed(() =>
  props.device.connection_info?.mesh_ip &&
  props.device.connection_info.mesh_ip !== 'unknown'
)

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

// VPN menu label — dynamic from vpn_mode
const vpnMenuLabel = computed(() => {
  const mode = props.device.connection_info?.vpn_mode
  if (mode === 'mullvad') return 'VPN: Mullvad'
  if (mode === 'vps') return 'VPN: VPS'
  return 'VPN'
})

// Firmware update indicator
const hasFirmwareUpdate = computed(() => {
  if (props.device.device_type !== 'MESH_ROUTER') return false
  const current = props.device.connection_info?.firmware_version
  const latest = props.device.latest_firmware_version
  if (!current || !latest) return false
  return current !== latest
})

const handleLocationSaved = (_lat: number, _lng: number) => {
  emit('refresh')
}

const store = useIoTStore()
const {
  getDeviceTypeLabel,
  getDeviceStatus,
  formatDate,
  formatRelativeTime,
  formatUptime,
  getTraccarDeviceUrl,
  hasLocationData,
  getBatteryInfo,
  getSpeedInfo,
  getHardwareName
} = useIoT()

// Computed property for Traccar URL
const traccarUrl = computed(() => {
  const url = getTraccarDeviceUrl(props.device)
  return url && url !== '#' ? url : null
})

// Modal state
const showWifiConfig = ref(false)
const showLocationPicker = ref(false)
const showVpnSettings = ref(false)
const showNetworkSettings = ref(false)
const showYggAccess = ref(false)
const showWiredMesh = ref(false)
const showDiagnostics = ref(false)
const showDeleteModal = ref(false)

// Kebab menu state
const showKebabMenu = ref(false)
const kebabRef = ref<HTMLElement | null>(null)

// Rename state
const renaming = ref(false)
const renameValue = ref('')
const renameInput = ref<HTMLInputElement | null>(null)

const startRename = () => {
  renameValue.value = props.device.name
  renaming.value = true
  nextTick(() => {
    renameInput.value?.focus()
    renameInput.value?.select()
  })
}

const saveRename = async () => {
  const name = renameValue.value.trim()
  if (name.length < 2 || name.length > 100) return
  if (name === props.device.name) {
    renaming.value = false
    return
  }
  try {
    await store.renameDevice(props.device.id, name)
  } catch { /* keep old name visible */ }
  renaming.value = false
}

const cancelRename = () => {
  renaming.value = false
}

// Copy to clipboard with toast feedback
const copyWithToast = async (text: string, message: string) => {
  try {
    await navigator.clipboard.writeText(text)
    toastStore.success(message)
  } catch {
    // Fallback: silently fail
  }
}

// WiFi password state
const wifiLoading = ref(false)
const wifiError = ref<string | null>(null)

// Root password state
const rootLoading = ref(false)
const rootError = ref<string | null>(null)

const handleShowWifiPassword = async () => {
  if (wifiLoading.value) return
  wifiLoading.value = true
  wifiError.value = null

  try {
    const data = await store.getWifiPassword(props.device.id)
    // Copy to clipboard + show toast
    const text = data.wifi_password
    try {
      await navigator.clipboard.writeText(text)
    } catch { /* clipboard may fail */ }
    toastStore.success(`SSID: ${data.ssid}\nPassword: ${text}`, undefined, 30000)
  } catch (err: any) {
    wifiError.value = err.message || 'Failed to get WiFi password'
  } finally {
    wifiLoading.value = false
  }
}

const handleShowRootPassword = async () => {
  if (rootLoading.value) return
  rootLoading.value = true
  rootError.value = null

  try {
    const data = await store.getRootPassword(props.device.id)
    // Copy to clipboard + show toast
    const text = data.root_password
    try {
      await navigator.clipboard.writeText(text)
    } catch { /* clipboard may fail */ }
    toastStore.success(`root@${data.hostname}\nPassword: ${text}`, undefined, 30000)
  } catch (err: any) {
    rootError.value = err.message || 'Failed to get root password'
  } finally {
    rootLoading.value = false
  }
}

// Delete confirmation
const confirmDelete = () => {
  showDeleteModal.value = false
  emit('delete', props.device.id)
}

// Click outside to close kebab menu
function handleClickOutside(event: MouseEvent) {
  if (kebabRef.value && !kebabRef.value.contains(event.target as Node)) {
    showKebabMenu.value = false
  }
}

onMounted(() => {
  if (import.meta.client) {
    document.addEventListener('click', handleClickOutside)
  }
})

onUnmounted(() => {
  if (import.meta.client) {
    document.removeEventListener('click', handleClickOutside)
  }
})

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
  @apply bg-neutral-100 dark:bg-neutral-800 rounded-lg p-6 border border-neutral-200 dark:border-neutral-700;
  @apply hover:border-primary transition-colors;
}

.realtime-flash {
  @apply ring-2 ring-yellow-400;
}

.kebab-item {
  @apply w-full flex items-center px-3 py-2 text-sm text-neutral-700 dark:text-neutral-300 transition-colors text-left;
  @apply hover:bg-amber-50 hover:text-amber-900 dark:hover:bg-amber-900/30 dark:hover:text-amber-200;
}

.copy-btn {
  @apply p-1 rounded text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 hover:bg-neutral-200 dark:hover:bg-neutral-700 transition-colors shrink-0;
}

.snapshot-marker {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 1;
  pointer-events: none;
}

.snapshot-marker-dot {
  width: 12px;
  height: 12px;
  background: #6366f1;
  border: 2px solid white;
  border-radius: 50%;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.3);
  position: relative;
  z-index: 2;
}

.snapshot-marker-pulse {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 24px;
  height: 24px;
  background: rgba(99, 102, 241, 0.3);
  border-radius: 50%;
  animation: snapshot-pulse 2s ease-out infinite;
  z-index: 1;
}

@keyframes snapshot-pulse {
  0% { transform: translate(-50%, -50%) scale(1); opacity: 0.6; }
  100% { transform: translate(-50%, -50%) scale(2.5); opacity: 0; }
}
</style>
