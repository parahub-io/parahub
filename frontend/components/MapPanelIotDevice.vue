<template>
  <div>
    <!-- Device photo -->
    <MapFeatureImage
      :image-url="deviceImageUrl"
      :alt="iotDeviceData?.name"
      :can-upload="authStore.isAuthenticated"
      @upload="onPhotoUpload"
      class="flex-shrink-0"
    />

    <div class="px-4 pt-2 space-y-4">
    <template v-if="iotDeviceData">
      <!-- Signal lost banner -->
      <UiAlert v-if="signalLostText" variant="error" :icon="WifiOff">
        {{ t('map.iot.signal_lost') }} · {{ signalLostText }}
      </UiAlert>

      <!-- Status badge -->
      <div class="flex items-center gap-3 flex-wrap">
        <div class="flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium"
          :class="{
            'bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-300': iotDeviceData.status === 'online',
            'bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300': iotDeviceData.status === 'recent',
            'bg-neutral-100 dark:bg-neutral-800 text-neutral-500 dark:text-neutral-400': iotDeviceData.status === 'offline' || iotDeviceData.status === 'unknown',
          }"
        >
          <span class="w-2.5 h-2.5 rounded-full"
            :class="{
              'bg-green-500': iotDeviceData.status === 'online',
              'bg-amber-500': iotDeviceData.status === 'recent',
              'bg-neutral-400': iotDeviceData.status === 'offline' || iotDeviceData.status === 'unknown',
            }"
          ></span>
          {{ iotDeviceData.status === 'online' ? t('map.iot.online') : iotDeviceData.status === 'recent' ? t('map.iot.recent') : t('map.iot.offline') }}
        </div>
        <div v-if="iotDeviceData.speed && !signalLostText" class="flex items-center gap-2 px-3 py-1.5 bg-secondary-50 dark:bg-secondary-900/30 rounded-full text-sm font-medium text-secondary-700 dark:text-secondary-300">
          {{ iotDeviceData.speed }}
        </div>
        <!-- Follow / Re-center button -->
        <button
          v-if="iotDeviceData.deviceType === 'tracker'"
          @click="emit('recenter')"
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium transition ml-auto"
          :class="isFollowing
            ? 'bg-secondary-50 dark:bg-secondary-900/30 text-secondary-700 dark:text-secondary-300'
            : 'border border-neutral-200 dark:border-neutral-700 text-neutral-600 dark:text-neutral-400 hover:border-neutral-300 dark:hover:border-neutral-600'"
        >
          <Crosshair :size="14" :class="{ 'animate-pulse': isFollowing }" />
          {{ isFollowing ? t('map.iot.following') : t('map.iot.recenter') }}
        </button>
      </div>

      <!-- Device details -->
      <div class="space-y-2 text-sm">
        <div v-if="iotDeviceData.deviceType" class="flex items-center justify-between py-1.5 border-b border-neutral-100 dark:border-neutral-800">
          <span class="text-neutral-500 dark:text-neutral-400">{{ t('map.iot.type') }}</span>
          <span class="text-neutral-900 dark:text-neutral-100">{{ iotDeviceData.deviceType === 'tracker' ? t('map.iot.type_tracker') : iotDeviceData.deviceType === 'mesh_router' ? t('map.iot.type_mesh_router') : t('map.iot.type_energy_cell') }}</span>
        </div>
        <div v-if="iotDeviceData.hardware_profile && iotDeviceData.hardware_profile !== 'unknown'" class="flex items-center justify-between py-1.5 border-b border-neutral-100 dark:border-neutral-800">
          <span class="text-neutral-500 dark:text-neutral-400">{{ t('map.iot.hardware') }}</span>
          <span class="font-mono text-neutral-900 dark:text-neutral-100">{{ iotDeviceData.hardware_profile }}</span>
        </div>
        <div v-if="iotDeviceData.firmware_role && iotDeviceData.firmware_role !== 'unknown'" class="flex items-center justify-between py-1.5 border-b border-neutral-100 dark:border-neutral-800">
          <span class="text-neutral-500 dark:text-neutral-400">{{ t('map.iot.role') }}</span>
          <span class="text-neutral-900 dark:text-neutral-100">{{ iotDeviceData.firmware_role }}</span>
        </div>
        <div v-if="iotDeviceData.price" class="flex items-center justify-between py-1.5">
          <span class="text-neutral-500 dark:text-neutral-400">{{ t('map.iot.price') }}</span>
          <span class="text-neutral-900 dark:text-neutral-100">{{ iotDeviceData.price }} €/kWh</span>
        </div>
        <!-- Owner attribution (owner opt-in via show_owner) -->
        <div v-if="iotDeviceData.owner_cri" class="flex items-center justify-between py-1.5 border-b border-neutral-100 dark:border-neutral-800">
          <span class="text-neutral-500 dark:text-neutral-400">{{ t('map.panel.owner') }}</span>
          <NuxtLink :to="localePath(`/@${iotDeviceData.owner_cri}`)" class="text-link font-medium truncate">{{ iotDeviceData.owner_name }}</NuxtLink>
        </div>
      </div>

      <!-- Owner mesh router details (owner-gated fetch; absent for strangers) -->
      <div v-if="meshDetail" class="space-y-2 text-sm border-t border-neutral-200 dark:border-neutral-700 pt-3">
        <div v-if="!iotDeviceData.firmware_role && meshCi.firmware_role && meshCi.firmware_role !== 'unknown'" class="flex items-center justify-between py-1.5 border-b border-neutral-100 dark:border-neutral-800">
          <span class="text-neutral-500 dark:text-neutral-400">{{ t('map.iot.role') }}</span>
          <span class="text-neutral-900 dark:text-neutral-100">{{ meshCi.firmware_role }}</span>
        </div>
        <div v-if="meshCi.firmware_version" class="flex items-center justify-between py-1.5 border-b border-neutral-100 dark:border-neutral-800">
          <span class="text-neutral-500 dark:text-neutral-400">{{ t('iot.firmware') }}</span>
          <span class="font-mono text-neutral-900 dark:text-neutral-100">
            {{ meshCi.firmware_version }}
            <span
              v-if="meshHasUpdate"
              class="text-amber-600 dark:text-amber-400"
              :title="t('iot.firmware_update_banner', { current: meshCi.firmware_version, latest: meshDetail.latest_firmware_version })"
            >↑ {{ meshDetail.latest_firmware_version }}</span>
          </span>
        </div>
        <div v-if="meshCi.uptime" class="flex items-center justify-between py-1.5 border-b border-neutral-100 dark:border-neutral-800">
          <span class="text-neutral-500 dark:text-neutral-400">{{ t('iot.uptime') }}</span>
          <span class="text-neutral-900 dark:text-neutral-100">{{ formatUptime(meshCi.uptime) }}</span>
        </div>
        <div v-if="meshDetail.last_seen" class="flex items-center justify-between py-1.5 border-b border-neutral-100 dark:border-neutral-800">
          <span class="text-neutral-500 dark:text-neutral-400">{{ t('iot.last_heartbeat') }}</span>
          <span class="text-neutral-900 dark:text-neutral-100" :title="formatDate(meshDetail.last_seen)">{{ formatRelativeTime(meshDetail.last_seen) }}</span>
        </div>
        <div v-if="meshVpnLabel" class="flex items-center justify-between py-1.5 border-b border-neutral-100 dark:border-neutral-800">
          <span class="text-neutral-500 dark:text-neutral-400">VPN</span>
          <span class="text-neutral-900 dark:text-neutral-100">{{ meshVpnLabel }}</span>
        </div>
        <div v-if="meshCi.private_ssid" class="flex items-center justify-between py-1.5 border-b border-neutral-100 dark:border-neutral-800">
          <span class="text-neutral-500 dark:text-neutral-400">SSID</span>
          <span class="font-mono text-neutral-900 dark:text-neutral-100">{{ meshCi.private_ssid }}</span>
        </div>
        <div v-if="meshNeighborCount !== null" class="flex items-center justify-between py-1.5 border-b border-neutral-100 dark:border-neutral-800">
          <span class="text-neutral-500 dark:text-neutral-400">{{ t('map.iot.mesh_neighbors') }}</span>
          <span class="text-neutral-900 dark:text-neutral-100">{{ meshNeighborCount }}</span>
        </div>

        <!-- Live stats (SSH sample) -->
        <div class="flex items-center justify-between py-1.5 border-b border-neutral-100 dark:border-neutral-800">
          <span class="text-neutral-500 dark:text-neutral-400">{{ t('map.iot.uplink_load') }}</span>
          <span v-if="liveLoading" class="inline-block w-3.5 h-3.5 border-2 border-neutral-300 border-t-neutral-600 dark:border-neutral-600 dark:border-t-neutral-300 rounded-full animate-spin"></span>
          <span v-else-if="liveStats?.available" class="flex items-center gap-1.5 text-neutral-900 dark:text-neutral-100" :title="liveStats.uplink_dev">
            <span class="font-mono">↓ {{ fmtBps(liveStats.rx_bps) }} · ↑ {{ fmtBps(liveStats.tx_bps) }}</span>
            <button @click="loadLiveStats" class="text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300" :aria-label="t('map.iot.uplink_load')">
              <RefreshCw :size="13" />
            </button>
          </span>
          <span v-else class="flex items-center gap-1.5 text-neutral-400 dark:text-neutral-500">
            {{ t('map.iot.live_unavailable') }}
            <button @click="loadLiveStats" class="hover:text-neutral-600 dark:hover:text-neutral-300" :aria-label="t('map.iot.uplink_load')">
              <RefreshCw :size="13" />
            </button>
          </span>
        </div>
        <div v-if="liveStats?.available" class="flex items-center justify-between py-1.5 border-b border-neutral-100 dark:border-neutral-800">
          <span class="text-neutral-500 dark:text-neutral-400">{{ t('map.iot.wifi_clients') }}</span>
          <span class="text-neutral-900 dark:text-neutral-100">{{ liveStats.wifi_clients }}</span>
        </div>
        <div v-if="liveStats?.available" class="flex items-center justify-between py-1.5 border-b border-neutral-100 dark:border-neutral-800">
          <span class="text-neutral-500 dark:text-neutral-400">Load · RAM</span>
          <span class="font-mono text-neutral-900 dark:text-neutral-100">{{ liveStats.load_1m }}<template v-if="liveStats.mem_used_pct !== null"> · {{ liveStats.mem_used_pct }}%</template></span>
        </div>

        <!-- 24h uplink sparkline (telemetry history, ph41+) -->
        <div v-if="panelUplinkSeries" class="py-1.5 border-b border-neutral-100 dark:border-neutral-800">
          <div class="text-neutral-500 dark:text-neutral-400 mb-1">{{ t('map.iot.uplink_24h') }}</div>
          <UiTimeChart :series="panelUplinkSeries" :height="56" compact :format="fmtBps" />
        </div>

        <!-- Guest clients (as of last heartbeat) -->
        <div v-if="meshGuestLeases !== null" class="py-1.5">
          <div class="flex items-center justify-between">
            <span class="text-neutral-500 dark:text-neutral-400">{{ t('map.iot.guest_clients') }}</span>
            <span class="text-neutral-900 dark:text-neutral-100">{{ meshGuestLeases.length }}</span>
          </div>
          <ul v-if="meshGuestLeases.length" class="mt-1.5 space-y-0.5">
            <li v-for="lease in meshGuestLeases" :key="lease.mac" class="flex items-center justify-between gap-2 text-xs text-neutral-600 dark:text-neutral-400">
              <span class="truncate">{{ lease.host || lease.mac }}</span>
              <span class="font-mono shrink-0">{{ lease.ip }}</span>
            </li>
          </ul>
        </div>

        <!-- Network identifiers -->
        <div v-if="meshDetail.device_id" class="flex justify-between items-center gap-2 py-1.5 border-b border-neutral-100 dark:border-neutral-800">
          <span class="text-neutral-500 dark:text-neutral-400 shrink-0">MAC</span>
          <div class="flex items-center gap-1 min-w-0">
            <span class="font-mono text-neutral-900 dark:text-neutral-100 truncate">{{ meshDetail.device_id }}</span>
            <button @click="copyWithToast(meshDetail.device_id)" class="shrink-0 text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300" :aria-label="t('iot.copy')">
              <Copy :size="14" />
            </button>
          </div>
        </div>
        <div v-if="meshCi.yggdrasil_address" class="flex justify-between items-center gap-2 py-1.5 border-b border-neutral-100 dark:border-neutral-800">
          <span class="text-neutral-500 dark:text-neutral-400 shrink-0">Yggdrasil</span>
          <div class="flex items-center gap-1 min-w-0">
            <span class="font-mono text-xs text-neutral-900 dark:text-neutral-100 break-all">{{ meshCi.yggdrasil_address }}</span>
            <button @click="copyWithToast(meshCi.yggdrasil_address)" class="shrink-0 text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300" :aria-label="t('iot.copy')">
              <Copy :size="14" />
            </button>
          </div>
        </div>
        <div v-if="meshCi.mesh_ip" class="flex justify-between items-center gap-2 py-1.5 border-b border-neutral-100 dark:border-neutral-800">
          <span class="text-neutral-500 dark:text-neutral-400 shrink-0">Mesh IP</span>
          <div class="flex items-center gap-1 min-w-0">
            <span class="font-mono text-neutral-900 dark:text-neutral-100">{{ meshCi.mesh_ip }}</span>
            <button @click="copyWithToast(meshCi.mesh_ip)" class="shrink-0 text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300" :aria-label="t('iot.copy')">
              <Copy :size="14" />
            </button>
          </div>
        </div>

        <UiButton
          variant="outline" size="sm" :icon="Settings"
          :to="localePath(meshDetail.property_id ? `/iot/${meshDetail.property_id}` : '/iot')"
          class="w-full mt-2"
        >
          {{ t('map.iot.manage') }}
        </UiButton>
      </div>

      <!-- Movement History (trackers only) -->
      <div v-if="iotDeviceData.deviceType === 'tracker'" class="border-t border-neutral-200 dark:border-neutral-700 pt-4">
        <h3 class="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-3">{{ t('map.iot.history') }}</h3>

        <!-- Quick range buttons -->
        <div class="flex gap-2 mb-3">
          <button
            v-for="preset in historyPresets" :key="preset.key"
            @click="applyHistoryPreset(preset.key)"
            class="px-2.5 py-1 text-xs font-medium rounded-full border transition"
            :class="activePreset === preset.key
              ? 'bg-primary-100 dark:bg-primary-900/40 border-primary text-neutral-900 dark:text-neutral-100'
              : 'border-neutral-200 dark:border-neutral-700 text-neutral-600 dark:text-neutral-400 hover:border-neutral-300 dark:hover:border-neutral-600'"
          >
            {{ preset.label }}
          </button>
        </div>

        <!-- Custom date range -->
        <div class="flex gap-2 mb-3">
          <input
            v-model="historyStart"
            type="datetime-local"
            class="flex-1 min-w-0 text-xs px-2 py-1.5 rounded border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100"
          />
          <input
            v-model="historyEnd"
            type="datetime-local"
            class="flex-1 min-w-0 text-xs px-2 py-1.5 rounded border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100"
          />
        </div>

        <!-- Show / Clear buttons -->
        <div class="flex gap-2 mb-3">
          <button
            @click="loadTrail"
            :disabled="trailLoading"
            class="flex-1 px-3 py-1.5 text-xs font-medium rounded bg-primary hover:bg-primary-400 text-neutral-900 transition disabled:opacity-50"
          >
            <template v-if="trailLoading">
              <span class="inline-block w-3 h-3 border-2 border-neutral-900/30 border-t-neutral-900 rounded-full animate-spin mr-1"></span>
            </template>
            {{ t('map.iot.history_show') }}
          </button>
          <button
            v-if="trailVisible"
            @click="clearTrailFromPanel"
            class="px-3 py-1.5 text-xs font-medium rounded border border-neutral-200 dark:border-neutral-700 text-neutral-600 dark:text-neutral-400 hover:bg-neutral-50 dark:hover:bg-neutral-800 transition"
          >
            {{ t('map.iot.history_clear') }}
          </button>
        </div>

        <!-- Error -->
        <p v-if="trailError" class="text-xs text-red-500 mb-2">{{ trailError }}</p>

        <!-- Stats -->
        <div v-if="trailStats" class="flex items-center gap-3 text-xs text-neutral-500 dark:text-neutral-400">
          <span>{{ trailTotalPoints }} {{ t('map.iot.history_points') }}</span>
          <span>{{ trailStats.distanceText }}</span>
          <span>{{ trailStats.durationText }}</span>
        </div>

        <!-- Playback controls -->
        <div v-if="trailPoints.length > 1" class="mt-3 space-y-2">
          <!-- Time display -->
          <div class="flex items-center justify-between text-xs text-neutral-500 dark:text-neutral-400">
            <span class="font-mono">{{ cursorTimeText }}</span>
            <span v-if="cursorSpeed !== null" class="font-mono">{{ Math.round(cursorSpeed) }} km/h</span>
          </div>
          <!-- Slider -->
          <input
            v-model.number="cursorIndex"
            type="range"
            :min="0"
            :max="trailPoints.length - 1"
            :step="1"
            class="w-full h-1.5 accent-primary cursor-pointer"
            @input="onSliderInput"
          />
          <!-- Play / Pause -->
          <div class="flex items-center gap-2">
            <button
              @click="togglePlayback"
              class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded transition"
              :class="isPlaying
                ? 'bg-neutral-200 dark:bg-neutral-700 text-neutral-700 dark:text-neutral-300'
                : 'bg-primary hover:bg-primary-400 text-neutral-900'"
            >
              <Pause v-if="isPlaying" :size="12" />
              <Play v-else :size="12" />
              {{ isPlaying ? t('map.iot.history_pause') : t('map.iot.history_play') }}
            </button>
            <span class="text-xs text-neutral-400 dark:text-neutral-500">1 min = 0.5s</span>
          </div>
        </div>

        <!-- No data -->
        <p v-if="trailNoData" class="text-xs text-neutral-400 dark:text-neutral-500">{{ t('map.iot.history_no_data') }}</p>
      </div>
    </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'
import { Copy, Crosshair, Pause, Play, RefreshCw, Settings, WifiOff } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'
import MapFeatureImage from '~/components/MapFeatureImage.vue'

const { t } = useI18n()
const authStore = useAuthStore()
const toastStore = useToastStore()
const localePath = useLocalePath()
const { formatUptime, formatRelativeTime, formatDate } = useIoT()

const props = defineProps<{
  iotDeviceData: any
  isFollowing: boolean
}>()

const emit = defineEmits<{
  (e: 'show-trail', geojson: any): void
  (e: 'clear-trail'): void
  (e: 'trail-cursor', pos: { lng: number; lat: number; heading?: number }): void
  (e: 'recenter'): void
}>()

// ======== Signal lost detection (>5 min) ========
const nowTick = ref(Date.now())
let signalTickTimer: ReturnType<typeof setInterval> | null = null

if (import.meta.client) {
  signalTickTimer = setInterval(() => { nowTick.value = Date.now() }, 60_000)
}

const signalLostText = computed(() => {
  if (props.iotDeviceData?.deviceType !== 'tracker') return ''
  const lu = props.iotDeviceData?.last_update
  if (!lu) return ''
  const age = nowTick.value - new Date(lu).getTime()
  if (age < 300_000) return '' // < 5 min
  const minutes = Math.floor(age / 60_000)
  if (minutes < 60) return `${minutes} min`
  const hours = Math.floor(minutes / 60)
  const rem = minutes % 60
  return rem > 0 ? `${hours}h ${rem}m` : `${hours}h`
})

// ======== Device Photo ========
const deviceImageUrl = ref<string | null>(null)

async function loadDevicePhoto(deviceId: string) {
  if (!deviceId || deviceId.length !== 26) return
  try {
    const photos = await $fetch<any[]>('/api/v1/core/photos/', { params: { object_id: deviceId } })
    deviceImageUrl.value = photos?.[0]?.url || null
  } catch { deviceImageUrl.value = null }
}

async function onPhotoUpload(file: File) {
  const deviceId = props.iotDeviceData?.device_id
  if (!authStore.isAuthenticated || !deviceId || deviceId.length !== 26) {
    toastStore.error(t('map.panel.error_auth_required'))
    return
  }
  try {
    await authStore.ensureToken()
    const formData = new FormData()
    formData.append('image', file)
    formData.append('object_id', deviceId)
    formData.append('order', '0')
    const photo = await $fetch<{ url: string }>('/api/v1/core/photos/', {
      method: 'POST', credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
      body: formData,
    })
    deviceImageUrl.value = photo.url
    toastStore.success(t('map.panel.photo_uploaded'))
  } catch (err: any) {
    toastStore.error(err?.data?.error || 'Failed to upload photo')
  }
}

watch(() => props.iotDeviceData?.device_id, (newId) => {
  deviceImageUrl.value = null
  if (newId) loadDevicePhoto(newId)
}, { immediate: true })

// ======== Owner mesh router detail ========
// The owner-gated /devices/{id} endpoint 404s for everyone else, so the
// public basic view stays untouched for strangers.
const meshDetail = ref<any>(null)

async function loadMeshDetail(id: string) {
  if (!authStore.isAuthenticated || !id || id.length !== 26) return
  try {
    await authStore.ensureToken()
    meshDetail.value = await $fetch<any>(`/api/v1/iot/devices/${id}`, {
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
    })
  } catch { meshDetail.value = null }
}

watch(() => [props.iotDeviceData?.device_id, props.iotDeviceData?.deviceType], ([id, type]) => {
  meshDetail.value = null
  if (type === 'mesh_router' && id) loadMeshDetail(id as string)
}, { immediate: true })

const meshCi = computed(() => meshDetail.value?.connection_info || {})

// 24h telemetry history for the uplink sparkline (owner only, ph41+)
const panelStats = ref<any[]>([])

async function loadPanelStats(id: string) {
  try {
    await authStore.ensureToken()
    const res = await $fetch<any>(`/api/v1/iot/devices/${id}/stats`, {
      params: { hours: 24 },
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
    })
    panelStats.value = res?.points || []
  } catch { panelStats.value = [] }
}

watch(meshDetail, (detail) => {
  panelStats.value = []
  const id = props.iotDeviceData?.device_id
  if (detail && id) loadPanelStats(id)
})

const panelUplinkSeries = computed(() => {
  const rx = panelStats.value.map((p: any) => ({ t: Date.parse(p.t), v: p.wan_rx_bps }))
  const tx = panelStats.value.map((p: any) => ({ t: Date.parse(p.t), v: p.wan_tx_bps }))
  if (!rx.some(p => p.v != null) && !tx.some(p => p.v != null)) return null
  return [
    { key: 'rx', label: '↓', points: rx },
    { key: 'tx', label: '↑', points: tx },
  ]
})

const meshHasUpdate = computed(() => {
  const current = meshCi.value.firmware_version
  const latest = meshDetail.value?.latest_firmware_version
  return !!current && !!latest && current !== latest
})

const meshVpnLabel = computed(() => {
  const mode = meshCi.value.vpn_mode
  if (mode === 'vps') return 'VPS'
  if (mode === 'mullvad') return 'Mullvad'
  if (mode === 'none') return '—'
  return null
})

// null = old firmware that does not report topology/leases yet
const meshNeighborCount = computed(() =>
  Array.isArray(meshCi.value.mesh_macs) ? meshCi.value.mesh_macs.length : null)
const meshGuestLeases = computed(() =>
  Array.isArray(meshCi.value.guest_leases) ? meshCi.value.guest_leases : null)

async function copyWithToast(value: string) {
  try {
    await navigator.clipboard.writeText(value)
    toastStore.success(t('iot.copied_address'))
  } catch {}
}

// ======== Live router stats (SSH sample, owner only) ========
const liveStats = ref<any>(null)
const liveLoading = ref(false)

async function loadLiveStats() {
  const id = props.iotDeviceData?.device_id
  if (!id || !meshDetail.value) return
  liveLoading.value = true
  try {
    await authStore.ensureToken()
    liveStats.value = await $fetch<any>(`/api/v1/iot/devices/${id}/live-stats`, {
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
    })
  } catch { liveStats.value = null } finally { liveLoading.value = false }
}

watch(meshDetail, (detail) => {
  liveStats.value = null
  if (detail) loadLiveStats()
})

function fmtBps(bps: number): string {
  if (bps >= 1_000_000) return `${(bps / 1_000_000).toFixed(1)} Mbit/s`
  if (bps >= 1_000) return `${Math.round(bps / 1_000)} kbit/s`
  return `${bps} bit/s`
}

// Trail history state
const trailLoading = ref(false)
const trailError = ref<string | null>(null)
const trailStats = ref<{ distanceText: string; durationText: string } | null>(null)
const trailTotalPoints = ref(0)
const trailVisible = ref(false)
const trailNoData = ref(false)
const activePreset = ref<string | null>(null)
const historyStart = ref('')
const historyEnd = ref('')
const trailPoints = ref<any[]>([])

// Playback state
const cursorIndex = ref(0)
const isPlaying = ref(false)
let playbackTimer: ReturnType<typeof setInterval> | null = null

const cursorTimeText = computed(() => {
  const pt = trailPoints.value[cursorIndex.value]
  if (!pt) return ''
  const d = new Date(pt.time)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
})

const cursorSpeed = computed(() => {
  const pt = trailPoints.value[cursorIndex.value]
  return pt?.speed ?? null
})

function toLocalDatetime(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

const historyPresets = computed(() => [
  { key: 'today', label: t('map.iot.history_today') },
  { key: 'yesterday', label: t('map.iot.history_yesterday') },
  { key: '7d', label: t('map.iot.history_7d') },
])

function applyHistoryPreset(key: string) {
  activePreset.value = key
  const now = new Date()
  let start: Date
  let end: Date = now

  if (key === 'today') {
    start = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  } else if (key === 'yesterday') {
    start = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1)
    end = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  } else {
    start = new Date(now.getTime() - 7 * 86400000)
  }

  historyStart.value = toLocalDatetime(start)
  historyEnd.value = toLocalDatetime(end)
}

function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371
  const toRad = (d: number) => d * Math.PI / 180
  const dLat = toRad(lat2 - lat1)
  const dLon = toRad(lon2 - lon1)
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
}

async function loadTrail() {
  if (!historyStart.value || !historyEnd.value || !props.iotDeviceData?.device_id) return
  trailNoData.value = false
  trailLoading.value = true
  trailError.value = null
  try {
    await authStore.ensureToken()
    const data = await $fetch<any>(
      `/api/v1/iot/devices/${props.iotDeviceData.device_id}/history`,
      {
        credentials: 'include',
        headers: { 'Authorization': `Bearer ${authStore.token}` },
        params: {
          start: new Date(historyStart.value).toISOString(),
          end: new Date(historyEnd.value).toISOString(),
        },
      },
    )
    const pts = data.points || []
    trailTotalPoints.value = data.total_points || 0
    if (pts.length === 0) {
      trailNoData.value = true
      return
    }
    let totalDist = 0
    for (let i = 1; i < pts.length; i++) {
      totalDist += haversineKm(pts[i - 1].latitude, pts[i - 1].longitude, pts[i].latitude, pts[i].longitude)
    }
    const startTime = new Date(pts[0].time).getTime()
    const endTime = new Date(pts[pts.length - 1].time).getTime()
    const durationMs = endTime - startTime
    const hours = Math.floor(durationMs / 3600000)
    const minutes = Math.floor((durationMs % 3600000) / 60000)
    trailStats.value = {
      distanceText: totalDist >= 1 ? `${totalDist.toFixed(1)} km` : `${Math.round(totalDist * 1000)} m`,
      durationText: hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`,
    }
    const coords = pts.map((p: any) => [p.longitude, p.latitude])
    const features: any[] = []
    if (coords.length >= 2) {
      features.push({ type: 'Feature', properties: { role: 'trail' }, geometry: { type: 'LineString', coordinates: coords } })
    }
    features.push({ type: 'Feature', properties: { role: 'start' }, geometry: { type: 'Point', coordinates: coords[0] } })
    if (pts.length > 1) {
      features.push({ type: 'Feature', properties: { role: 'end' }, geometry: { type: 'Point', coordinates: coords[coords.length - 1] } })
    }
    trailPoints.value = pts
    cursorIndex.value = 0
    trailVisible.value = true
    emit('show-trail', { type: 'FeatureCollection', features })
    emitCursor(0)
  } catch (e: any) {
    trailError.value = e?.data?.detail || e?.message || 'Failed to load history'
  } finally {
    trailLoading.value = false
  }
}

function emitCursor(idx: number) {
  const pt = trailPoints.value[idx]
  if (pt) {
    emit('trail-cursor', { lng: pt.longitude, lat: pt.latitude, heading: pt.heading })
  }
}

function onSliderInput() {
  emitCursor(cursorIndex.value)
}

function togglePlayback() {
  if (isPlaying.value) stopPlayback()
  else startPlayback()
}

function startPlayback() {
  if (trailPoints.value.length < 2) return
  if (cursorIndex.value >= trailPoints.value.length - 1) {
    cursorIndex.value = 0
    emitCursor(0)
  }
  isPlaying.value = true
  const INTERVAL_MS = 100
  const SPEED_FACTOR = 120
  playbackTimer = setInterval(() => {
    const pts = trailPoints.value
    const cur = cursorIndex.value
    if (cur >= pts.length - 1) { stopPlayback(); return }
    const curTime = new Date(pts[cur].time).getTime()
    const targetTime = curTime + INTERVAL_MS * SPEED_FACTOR
    let next = cur + 1
    while (next < pts.length - 1 && new Date(pts[next].time).getTime() < targetTime) { next++ }
    cursorIndex.value = next
    emitCursor(next)
  }, INTERVAL_MS)
}

function stopPlayback() {
  isPlaying.value = false
  if (playbackTimer) { clearInterval(playbackTimer); playbackTimer = null }
}

function clearTrailFromPanel() {
  stopPlayback()
  trailVisible.value = false
  trailNoData.value = false
  trailStats.value = null
  trailTotalPoints.value = 0
  trailPoints.value = []
  cursorIndex.value = 0
  emit('clear-trail')
}

// Clear trail when device changes
watch(() => props.iotDeviceData?.device_id, () => {
  if (trailVisible.value) clearTrailFromPanel()
  activePreset.value = null
  historyStart.value = ''
  historyEnd.value = ''
  trailNoData.value = false
})

onUnmounted(() => {
  if (playbackTimer) { clearInterval(playbackTimer); playbackTimer = null }
  if (signalTickTimer) { clearInterval(signalTickTimer); signalTickTimer = null }
})
</script>
