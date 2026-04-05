<template>
  <div class="driver-page" :class="{ 'driver-active': isActive }">

    <!-- ═══════════════ ROUTE SELECTION STATE ═══════════════ -->
    <div v-if="!isActive" class="max-w-xl mx-auto px-4 py-6">

      <div class="flex items-center gap-3 mb-3">
        <Bus class="w-8 h-8 text-primary" />
        <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100">
          {{ $t('transit.driver.title') }}
        </h1>
      </div>
      <p class="text-sm text-neutral-600 dark:text-neutral-300 mb-6 leading-relaxed">
        {{ $t('transit.driver.description') }}
      </p>

      <!-- WoT warning -->
      <UiAlert v-if="!canAccess" variant="warning" :icon="ShieldAlert" class="mb-6">
        {{ $t('transit.driver.wot_required') }}
      </UiAlert>

      <!-- Route Search -->
      <div class="relative mb-4">
        <Search class="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-neutral-400" />
        <input
          v-model="searchQuery"
          :placeholder="$t('transit.driver.search_route')"
          :disabled="!canAccess"
          class="w-full pl-12 pr-4 py-4 text-lg bg-white dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-600 rounded-xl focus:ring-2 focus:ring-primary focus:border-transparent outline-none disabled:opacity-50"
          @input="debouncedSearch"
        />
      </div>

      <!-- Search Results -->
      <div v-if="routeResults.length && !selectedRoute" class="space-y-2 mb-6">
        <button
          v-for="r in routeResults"
          :key="r.id"
          @click="selectRoute(r)"
          class="w-full text-left flex items-center gap-3 p-4 bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-xl hover:border-secondary-400 dark:hover:border-secondary-500 transition-colors"
        >
          <span
            class="inline-block px-3 py-1.5 rounded-lg font-bold text-lg min-w-[60px] text-center"
            :style="routeBadgeStyle(r)"
          >{{ r.short_name }}</span>
          <span class="text-neutral-700 dark:text-neutral-300 text-sm flex-1 min-w-0 truncate">{{ r.long_name }}</span>
        </button>
      </div>

      <!-- Selected Route -->
      <div v-if="selectedRoute" class="mb-6">
        <div class="p-5 bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-xl">
          <!-- Route header -->
          <div class="flex items-center gap-3 mb-4">
            <span
              class="inline-block px-3 py-1.5 rounded-lg font-bold text-xl"
              :style="routeBadgeStyle(selectedRoute)"
            >{{ selectedRoute.short_name }}</span>
            <div class="flex-1 min-w-0">
              <div class="font-medium text-neutral-900 dark:text-neutral-100">{{ selectedRoute.long_name }}</div>
            </div>
            <button @click="clearSelection" class="p-2 text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300">
              <X class="w-5 h-5" />
            </button>
          </div>

          <!-- Direction Toggle -->
          <div v-if="directions.length > 1" class="grid grid-cols-2 gap-2 mb-4">
            <button
              v-for="d in directions"
              :key="d.direction_id"
              @click="selectedDirection = d.direction_id"
              class="py-3.5 px-3 text-sm font-medium rounded-lg border transition-colors truncate"
              :class="selectedDirection === d.direction_id
                ? 'bg-secondary-600 text-white border-secondary-600'
                : 'bg-neutral-100 dark:bg-neutral-700 text-neutral-700 dark:text-neutral-300 border-neutral-300 dark:border-neutral-600'"
            >
              {{ d.headsign || (d.direction_id === 0 ? 'A → B' : 'B → A') }}
            </button>
          </div>

          <!-- Start button -->
          <UiButton
            variant="primary"
            size="lg"
            :icon="Play"
            :loading="starting"
            :disabled="!canAccess"
            class="w-full !py-4 !text-lg !font-bold"
            @click="handleStart"
          >
            {{ $t('transit.driver.start_shift') }}
          </UiButton>
        </div>
      </div>

      <!-- Error -->
      <UiAlert v-if="driverError" variant="error" class="mb-4">{{ driverError }}</UiAlert>

      <!-- Active shift resume/stop -->
      <div v-if="existingShift && !selectedRoute" class="p-4 bg-white dark:bg-neutral-800 border border-secondary-300 dark:border-secondary-600 rounded-xl">
        <div class="text-sm text-neutral-500 dark:text-neutral-400 mb-2">{{ $t('transit.driver.active_shift') }}</div>
        <div class="flex items-center gap-3">
          <span
            class="inline-block px-2.5 py-1 rounded-lg font-bold"
            :style="`background-color: #${existingShift.route_color || 'EFF216'}; color: #000`"
          >{{ existingShift.route_short_name }}</span>
          <span class="text-sm text-neutral-700 dark:text-neutral-300 flex-1">{{ existingShift.route_long_name }}</span>
        </div>
        <div class="grid grid-cols-2 gap-2 mt-3">
          <UiButton
            variant="secondary"
            size="sm"
            :loading="resuming"
            @click="handleResume"
          >
            {{ $t('transit.driver.resume') }}
          </UiButton>
          <UiButton
            :variant="pendingStopExisting ? 'error' : 'outline-error'"
            size="sm"
            :loading="stopping"
            @click="handleStopExisting"
          >
            {{ pendingStopExisting ? $t('common.confirm') + '?' : $t('transit.driver.stop_shift') }}
          </UiButton>
        </div>
      </div>
    </div>

    <!-- ═══════════════ ACTIVE SHIFT STATE ═══════════════ -->
    <div v-else class="driver-hud">

      <!-- Top bar: route + headsign -->
      <div class="hud-top">
        <span
          class="route-badge"
          :style="shiftInfo ? routeBadgeStyle(shiftInfo) : ''"
        >{{ shiftInfo?.route_short_name }}</span>
        <span class="headsign">{{ headsign || shiftInfo?.route_long_name }}</span>
        <div class="connection-dot" :class="connectionClass"></div>
      </div>

      <!-- GPS error banner -->
      <div v-if="driverError" class="hud-gps-error">
        <ShieldAlert class="w-4 h-4 flex-shrink-0" />
        <span>{{ $t('transit.driver.gps_error') }}</span>
      </div>

      <!-- Center: current/next stop -->
      <div class="hud-center">
        <div class="current-stop-label">{{ $t('transit.driver.current_stop') }}</div>
        <div class="current-stop-name">
          {{ currentStop?.name || '—' }}
        </div>
        <div v-if="nextStop" class="next-stop">
          <ArrowDown class="w-5 h-5 inline-block mr-1 opacity-50" />
          {{ nextStop.name }}
        </div>
      </div>

      <!-- Status bar -->
      <div class="hud-status">
        <div class="stat">
          <Gauge class="w-4 h-4" />
          <span class="stat-value">{{ speed }}</span>
          <span class="stat-unit">km/h</span>
        </div>
        <div class="stat">
          <Crosshair class="w-4 h-4" :class="gpsClass" />
          <span class="stat-value">{{ gpsAccuracy }}</span>
          <span class="stat-unit">m</span>
        </div>
        <div class="stat" :title="$t('transit.driver.positions_sent')">
          <Radio class="w-4 h-4" />
          <span class="stat-value">{{ positionCount }}</span>
          <span class="stat-unit">{{ $t('transit.driver.positions_sent') }}</span>
        </div>
      </div>

      <!-- Bottom controls -->
      <div class="hud-bottom">
        <div class="hud-controls">
          <!-- Direction toggle -->
          <button
            v-if="shiftInfo"
            @click="toggleDirection"
            class="control-btn"
            :title="$t('transit.driver.switch_direction')"
          >
            <ArrowLeftRight class="w-6 h-6" />
          </button>

          <!-- TTS toggle -->
          <button
            @click="ttsEnabled = !ttsEnabled"
            class="control-btn"
            :class="{ 'control-btn-active': ttsEnabled }"
            :title="$t('transit.driver.tts_label')"
          >
            <Volume2 v-if="ttsEnabled" class="w-6 h-6" />
            <VolumeX v-else class="w-6 h-6" />
          </button>
        </div>

        <!-- Stop shift -->
        <UiButton
          :variant="pendingStop ? 'error' : 'outline-error'"
          size="lg"
          :icon="Square"
          class="w-full !py-5 !text-lg !font-bold"
          @click="handleStop"
        >
          {{ pendingStop ? $t('common.confirm') + '?' : $t('transit.driver.stop_shift') }}
        </UiButton>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  Bus, Search, ShieldAlert, X, Play, Square,
  ArrowDown, ArrowLeftRight, Volume2, VolumeX,
  Gauge, Crosshair, Radio,
} from 'lucide-vue-next'

definePageMeta({
  middleware: 'auth',
  keepalive: false,
})

const { t } = useI18n()
const authStore = useAuthStore()
const { routeBadgeStyle } = useTransitHelpers()
const {
  isActive, connectionStatus, currentStop, nextStop,
  speed, gpsAccuracy, positionCount, error: driverError,
  shiftInfo, headsign, ttsEnabled,
  startShift, stopShift, stopShiftById, resumeExistingShift, changeDirection,
} = useDriverMode()

useSeoMeta({ title: () => `${t('transit.driver.title')} — Parahub` })

const canAccess = computed(() =>
  authStore.user?.is_staff || authStore.activeProfile?.is_verified_wot
)

// Route selection
const searchQuery = ref('')
const routeResults = ref<any[]>([])
const selectedRoute = ref<any>(null)
const selectedDirection = ref(0)
const directions = ref<any[]>([])
const starting = ref(false)
const resuming = ref(false)
const stopping = ref(false)
const pendingStop = ref(false)
const pendingStopExisting = ref(false)
let pendingStopTimer: ReturnType<typeof setTimeout> | null = null
let pendingStopExistingTimer: ReturnType<typeof setTimeout> | null = null
const existingShift = ref<any>(null)

let searchTimer: ReturnType<typeof setTimeout> | null = null

function debouncedSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(doSearch, 400)
}

async function doSearch() {
  const q = searchQuery.value.trim()
  if (q.length < 2) {
    routeResults.value = []
    return
  }
  try {
    const data = await $fetch<any>(`/api/v1/geo/transit/search/?q=${encodeURIComponent(q)}`)
    routeResults.value = (data.routes || []).slice(0, 8)
  } catch {
    routeResults.value = []
  }
}

async function selectRoute(route: any) {
  selectedRoute.value = route
  routeResults.value = []
  searchQuery.value = ''

  // Load directions
  if (route.place_slug && route.slug) {
    try {
      const detail = await $fetch<any>(`/api/v1/geo/transit/routes/${route.place_slug}/${route.slug}/`)
      directions.value = detail.directions || []
      if (directions.value.length) {
        selectedDirection.value = directions.value[0].direction_id
      }
    } catch {
      directions.value = []
    }
  }
}

function clearSelection() {
  selectedRoute.value = null
  directions.value = []
  selectedDirection.value = 0
}

async function handleStart() {
  if (!selectedRoute.value || starting.value) return
  starting.value = true
  try {
    await startShift(selectedRoute.value.id, selectedDirection.value)
  } finally {
    starting.value = false
  }
}

async function handleStop() {
  if (!pendingStop.value) {
    pendingStop.value = true
    if (pendingStopTimer) clearTimeout(pendingStopTimer)
    pendingStopTimer = setTimeout(() => { pendingStop.value = false }, 3000)
    return
  }
  pendingStop.value = false
  if (pendingStopTimer) clearTimeout(pendingStopTimer)
  await stopShift()
  selectedRoute.value = null
  directions.value = []
}

function toggleDirection() {
  const newDir = shiftInfo.value?.direction_id === 0 ? 1 : 0
  changeDirection(newDir)
}

async function handleResume() {
  if (!existingShift.value) return
  resuming.value = true
  try {
    await resumeExistingShift(existingShift.value)
    existingShift.value = null
  } catch {
    // Error shown via driverError
  } finally {
    resuming.value = false
  }
}

async function handleStopExisting() {
  if (!existingShift.value) return
  if (!pendingStopExisting.value) {
    pendingStopExisting.value = true
    if (pendingStopExistingTimer) clearTimeout(pendingStopExistingTimer)
    pendingStopExistingTimer = setTimeout(() => { pendingStopExisting.value = false }, 3000)
    return
  }
  pendingStopExisting.value = false
  if (pendingStopExistingTimer) clearTimeout(pendingStopExistingTimer)
  stopping.value = true
  try {
    await stopShiftById(existingShift.value.id)
    existingShift.value = null
  } finally {
    stopping.value = false
  }
}

// Connection indicator
const connectionClass = computed(() => ({
  'bg-green-500': connectionStatus.value === 'connected',
  'bg-amber-500 animate-pulse': connectionStatus.value === 'connecting',
  'bg-red-500': connectionStatus.value === 'disconnected',
}))

const gpsClass = computed(() => {
  if (gpsAccuracy.value === 0) return 'text-neutral-400'
  if (gpsAccuracy.value <= 15) return 'text-green-500'
  if (gpsAccuracy.value <= 50) return 'text-amber-500'
  return 'text-red-500'
})

// Check for existing active shift on mount
onMounted(async () => {
  await authStore.ensureToken()
  if (!authStore.token) return
  try {
    const data = await $fetch<any>('/api/v1/geo/driver/active/', {
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    if (data) {
      existingShift.value = data
    }
  } catch {}
})
</script>

<style scoped>
/* Route selection: standard page layout */
.driver-page {
  min-height: 100%;
}

/* ═══════════════ ACTIVE SHIFT: HUD LAYOUT ═══════════════ */
.driver-active {
  background: #0a0a0a;
  color: #fafafa;
  height: 100%;
  min-height: 0;
}

.driver-hud {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 0 16px var(--safe-area-inset-bottom, env(safe-area-inset-bottom, 0));
}

/* Top bar */
.hud-top {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 0;
  border-bottom: 1px solid #27272a;
  flex-shrink: 0;
}

.route-badge {
  display: inline-block;
  padding: 6px 14px;
  border-radius: 8px;
  font-weight: 800;
  font-size: 1.25rem;
  line-height: 1;
}

.headsign {
  flex: 1;
  font-size: 0.95rem;
  color: #a1a1aa;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.connection-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  flex-shrink: 0;
}

/* Center: the main display */
.hud-center {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  text-align: center;
  padding: 24px 0;
  min-height: 0;
}

.current-stop-label {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  color: #71717a;
  margin-bottom: 8px;
}

.current-stop-name {
  font-size: clamp(2rem, 8vw, 4.5rem);
  font-weight: 800;
  line-height: 1.1;
  color: #fafafa;
  max-width: 100%;
  word-break: break-word;
}

.next-stop {
  margin-top: 16px;
  font-size: clamp(1rem, 3.5vw, 1.5rem);
  color: #a1a1aa;
  font-weight: 500;
}

/* Status bar */
.hud-status {
  display: flex;
  justify-content: center;
  gap: 32px;
  padding: 12px 0;
  border-top: 1px solid #27272a;
  flex-shrink: 0;
}

.stat {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #71717a;
  font-size: 0.85rem;
}

.stat-value {
  font-weight: 700;
  color: #d4d4d8;
  font-variant-numeric: tabular-nums;
}

.stat-unit {
  font-size: 0.7rem;
  color: #52525b;
}

/* Bottom controls */
.hud-bottom {
  flex-shrink: 0;
  padding: 16px 0;
}

.hud-controls {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
  justify-content: center;
}

.control-btn {
  width: 56px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  border: 1px solid #3f3f46;
  background: #18181b;
  color: #a1a1aa;
  transition: all 0.15s;
}

.control-btn:active {
  background: #27272a;
}

.control-btn-active {
  border-color: var(--color-secondary);
  color: var(--color-secondary);
}

/* GPS error banner */
.hud-gps-error {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: #7f1d1d;
  color: #fca5a5;
  border-radius: 8px;
  font-size: 0.85rem;
  margin-top: 8px;
  flex-shrink: 0;
}
</style>
