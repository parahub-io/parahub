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

      <!-- Center: current/next stop. Shrinks when the ladder is open so both
           fit on a phone; the ladder toggle restores the full-size display. -->
      <div class="hud-center" :class="{ 'hud-center-compact': ladderVisible }">
        <div class="current-stop-label">{{ $t('transit.driver.current_stop') }}</div>
        <div class="current-stop-name">
          {{ currentStop?.name || '—' }}
        </div>
        <div v-if="nextStop" class="next-stop">
          <ArrowDown class="w-5 h-5 inline-block mr-1 opacity-50" />
          {{ nextStop.name }}
          <!-- People who said they are waiting for THIS line in THIS direction
               at the stop ahead. Server-filtered: a count that mixed in the
               other line's passengers is the one number a driver must not act on. -->
          <span
            v-if="waitingAtNextStop"
            class="next-waiting"
            :title="$t('transit.driver.waiting_ahead', { n: waitingAtNextStop })"
          >
            <PersonStanding class="w-5 h-5" />{{ waitingAtNextStop }}
          </span>
        </div>
      </div>

      <!-- Route ladder: where every vehicle on this route is right now, both
           directions side by side — the same live picture passengers get on
           the route page, so the driver can read the headway ahead/behind. -->
      <div v-if="ladderVisible" ref="ladderEl" class="hud-ladder">
        <div class="ladder-grid" :style="{ gridTemplateColumns: `repeat(${ladderViews.length}, minmax(0, 1fr))` }">
          <div v-for="view in ladderViews" :key="view.direction_id" class="ladder-col">
            <div class="ladder-head" :class="{ 'ladder-head-mine': view.direction_id === shiftInfo?.direction_id }">
              <span class="ladder-dot" :style="{ background: DIR_DOT_COLORS[view.direction_id] ?? DIR_DOT_UNKNOWN }"></span>
              <span class="ladder-headsign">{{ view.headsign || (view.direction_id === 0 ? 'A → B' : 'B → A') }}</span>
              <span class="ladder-count" :title="$t('transit.driver.vehicles_on_route')">{{ vehicleCount(view) }}</span>
            </div>
            <div class="ladder-rows">
              <div
                v-for="(s, i) in view.stops"
                :key="`${view.direction_id}-${i}`"
                class="ladder-row"
                :class="{ 'ladder-row-mine': isMyStop(s.source_id, view.direction_id) }"
              >
                <span class="ladder-gutter">
                  <template v-if="vehicleAtStop(s.source_id, view.direction_id)">
                    <img
                      :src="routeTypeIcon(ladderRouteType)"
                      :alt="routeTypeFallback(ladderRouteType)"
                      class="ladder-bus"
                      :class="{
                        'ladder-bus-mine': isMyStop(s.source_id, view.direction_id),
                        'ladder-bus-zombie': vehicleAtStop(s.source_id, view.direction_id).z,
                      }"
                      :title="isMyStop(s.source_id, view.direction_id)
                        ? $t('transit.driver.your_vehicle')
                        : vehicleAtStop(s.source_id, view.direction_id).v"
                    />
                  </template>
                  <span v-else-if="etasFor(view.direction_id)[s.source_id] != null" class="ladder-eta">
                    {{ formatLadderEta(s.source_id, view.direction_id) }}
                  </span>
                </span>
                <span class="ladder-stop">{{ s.name }}</span>
                <span
                  v-if="ladderWaiting(s.source_id, view.direction_id)"
                  class="ladder-waiting"
                  :title="$t('transit.driver.waiting_ahead', { n: ladderWaiting(s.source_id, view.direction_id) })"
                >
                  <PersonStanding class="w-3.5 h-3.5" />{{ ladderWaiting(s.source_id, view.direction_id) }}
                </span>
              </div>
            </div>
          </div>
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

          <!-- Route ladder toggle -->
          <button
            v-if="ladderViews.length"
            @click="toggleLadder"
            class="control-btn"
            :class="{ 'control-btn-active': showLadder }"
            :title="$t('transit.driver.route_ladder')"
          >
            <Route class="w-6 h-6" />
          </button>

          <!-- Ticket scanner. Opens in place: leaving /driver would drop the
               GPS socket, and a driver WS disconnect ends the shift. -->
          <button
            @click="scanOpen = true"
            class="control-btn"
            :title="$t('transit.driver.scan_tickets')"
          >
            <ScanLine class="w-6 h-6" />
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

      <!-- Ticket scanner overlay — mounted over the HUD, never a navigation:
           the shift lives in this page's WebSocket, and dropping it ends the
           shift server-side. Teleported because the layout's <main> carries
           z-10 — a stacking context no in-page z-index can climb out of, so an
           overlay left inside it renders UNDER the app nav bar. -->
      <Teleport to="body">
        <div v-if="scanOpen" class="fixed inset-0 z-[60] flex flex-col bg-neutral-950">
          <TicketsTicketScanner class="flex-1" :show-operator-link="false" @close="scanOpen = false" />
        </div>
      </Teleport>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  Bus, Search, ShieldAlert, X, Play, Square,
  ArrowDown, ArrowLeftRight, Volume2, VolumeX,
  Gauge, Crosshair, PersonStanding, Radio, Route, ScanLine,
} from 'lucide-vue-next'

definePageMeta({
  middleware: 'auth',
  keepalive: false,
})

const { t } = useI18n()
const authStore = useAuthStore()
const { routeBadgeStyle, routeTypeIcon, routeTypeFallback } = useTransitHelpers()
const {
  isActive, connectionStatus, currentStop, nextStop,
  speed, gpsAccuracy, positionCount, error: driverError,
  shiftInfo, headsign, ttsEnabled, waitingByStop,
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

// ── Ticket scanner overlay ──
// Mounted over the HUD instead of navigating to /tickets/scan: the shift is held
// open by this page's driver WebSocket, and a disconnect ends it server-side.
const scanOpen = ref(false)

// ── Route ladder: live vehicle distribution, both directions ──
// Fixed direction colors (colorblind-safe pair), same as the route mini-map.
const DIR_DOT_COLORS: Record<number, string> = { 0: '#2563eb', 1: '#f97316' }
const DIR_DOT_UNKNOWN = '#6b7280'
const LADDER_LS_KEY = 'parahub_driver_ladder'

const routeDetail = ref<any>(null)
const showLadder = ref(true)
const ladderEl = ref<HTMLElement | null>(null)

const {
  liveVehicles, etasFor, vehicleAtStop,
  connect: openRouteWs, disconnect: closeRouteWs,
} = useTransitRouteLive()

const ladderRouteType = computed(() => routeDetail.value?.route_type ?? shiftInfo.value?.route_type ?? 3)
const myVehicleId = computed(() => shiftInfo.value?.vehicle_id || '')

// Both directions, rendered side by side — same shape as the passenger route
// page. Single-direction routes (loop/one-way/legacy) collapse to one column.
const ladderViews = computed(() => {
  const rd = routeDetail.value
  if (!rd) return []
  const dirs = rd.directions ?? []
  const stops0 = rd.stops ?? []
  const stops1 = rd.stops_dir1 ?? []
  const headsignOf = (d: number) =>
    (dirs.find((x: any) => x.direction_id === d) || {}).headsign || ''
  if (dirs.length > 1) {
    return [
      { direction_id: 0, headsign: headsignOf(0), stops: stops0 },
      // Fallback to reversed dir0 when inbound RouteStops weren't imported (legacy feeds)
      { direction_id: 1, headsign: headsignOf(1), stops: stops1.length ? stops1 : [...stops0].reverse() },
    ]
  }
  const only = dirs[0]?.direction_id ?? 0
  return [{
    direction_id: only,
    headsign: headsignOf(only),
    stops: only === 1 && stops1.length ? stops1 : stops0,
  }]
})

const ladderVisible = computed(() => showLadder.value && ladderViews.value.length > 0)

function isMyStop(stopSourceId: string, dirId: number): boolean {
  return vehicleAtStop(stopSourceId, dirId)?.v === myVehicleId.value
}

// Waiting counts arrive already filtered to this driver's route AND direction,
// so the opposite ladder column must not borrow them.
function ladderWaiting(stopSourceId: string, dirId: number): number {
  if (dirId !== shiftInfo.value?.direction_id) return 0
  return waitingByStop.value[stopSourceId]?.n || 0
}

const waitingAtNextStop = computed(() =>
  nextStop.value ? (waitingByStop.value[nextStop.value.id]?.n || 0) : 0,
)

// Vehicles this column actually renders — direction-matched and snapped to one
// of its stops, so the header count never promises an icon the list can't show.
function vehicleCount(view: { direction_id: number; stops: any[] }): number {
  const ids = new Set(view.stops.map((s: any) => s.source_id))
  return liveVehicles.value.filter(
    (v: any) => (v.d === view.direction_id || v.d == null) && v.sid && ids.has(v.sid)
  ).length
}

// ETA clock label in the AGENCY's timezone, not the driver's browser zone
function formatLadderEta(stopSourceId: string, dirId: number): string {
  const eta = etasFor(dirId)[stopSourceId]
  if (eta == null) return ''
  const date = new Date(Date.now() + eta * 1000)
  const tz = routeDetail.value?.agency_timezone
  if (tz) {
    try {
      return new Intl.DateTimeFormat('en-GB', {
        hour: '2-digit', minute: '2-digit', hour12: false, timeZone: tz,
      }).format(date)
    } catch { /* invalid tz → browser-local fallback below */ }
  }
  return `${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`
}

function toggleLadder() {
  showLadder.value = !showLadder.value
  try { localStorage.setItem(LADDER_LS_KEY, showLadder.value ? '1' : '0') } catch {}
}

async function loadRouteDetail() {
  const s = shiftInfo.value
  if (!s?.place_slug || !s?.route_slug) {
    routeDetail.value = null
    return
  }
  try {
    routeDetail.value = await $fetch<any>(
      `/api/v1/geo/transit/routes/${s.place_slug}/${s.route_slug}/`
    )
  } catch {
    routeDetail.value = null
  }
}

function connectRouteWs() {
  const s = shiftInfo.value
  if (s?.data_source_id && s?.route_source_id) {
    openRouteWs(s.data_source_id, s.route_source_id)
  }
}

// Shift start / resume / stop drives both the stop lists and the live socket
watch(() => shiftInfo.value?.id, (id) => {
  if (!id) {
    closeRouteWs()
    routeDetail.value = null
    return
  }
  loadRouteDetail()
  connectRouteWs()
}, { immediate: true })

// Keep the driver's own bus in view as it walks the line; only re-scrolls when
// it actually hops a stop, so manual scrolling isn't fought.
const myLadderStop = computed(
  () => liveVehicles.value.find((v: any) => v.v === myVehicleId.value)?.sid || ''
)
watch([myLadderStop, ladderVisible], async ([sid, visible]) => {
  if (!sid || !visible) return
  await nextTick()
  ladderEl.value?.querySelector('.ladder-row-mine')
    ?.scrollIntoView({ block: 'center', behavior: 'smooth' })
})

// Check for existing active shift on mount
onMounted(async () => {
  try {
    const stored = localStorage.getItem(LADDER_LS_KEY)
    if (stored !== null) showLadder.value = stored === '1'
  } catch {}
  connectRouteWs()  // no-op until a shift exists

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

// The driver WS deliberately survives navigation (app.vue KeepAlive-caches every
// page, and dropping it would end the shift). The ladder socket is cosmetic, so
// it pauses while the page is off-screen.
onActivated(() => { connectRouteWs() })
onDeactivated(() => { closeRouteWs() })
onUnmounted(() => { closeRouteWs() })
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

/* Waiting passengers at the stop ahead — amber, the HUD's "something to act on"
   colour, and never rendered at zero. */
.next-waiting {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  margin-left: 10px;
  padding: 2px 8px 2px 6px;
  border-radius: 9999px;
  background: rgba(250, 204, 21, 0.16);
  color: #facc15;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.ladder-waiting {
  display: inline-flex;
  align-items: center;
  gap: 1px;
  flex-shrink: 0;
  margin-left: 4px;
  color: #facc15;
  font-size: 0.7rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

/* With the ladder open the big display yields most of the height to it, but
   stays the first thing the eye lands on. */
.hud-center-compact {
  flex: 0 0 auto;
  padding: 12px 0;
}

.hud-center-compact .current-stop-name {
  font-size: clamp(1.5rem, 5.5vw, 2.5rem);
}

.hud-center-compact .next-stop {
  margin-top: 6px;
  font-size: clamp(0.875rem, 3vw, 1.125rem);
}

/* ═══════════════ ROUTE LADDER ═══════════════ */
.hud-ladder {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  scrollbar-gutter: stable;
  border-top: 1px solid #27272a;
  padding-top: 8px;
}

.ladder-grid {
  display: grid;
  gap: 8px;
  align-items: start;
}

.ladder-col {
  min-width: 0;
}

.ladder-head {
  position: sticky;
  top: 0;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 6px;
  background: #0a0a0a;
  border-bottom: 1px solid #27272a;
  font-size: 0.7rem;
  color: #71717a;
}

.ladder-head-mine {
  color: #d4d4d8;
}

.ladder-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.ladder-headsign {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ladder-count {
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
  font-weight: 700;
  color: #d4d4d8;
}

.ladder-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 1px 6px;
  border-radius: 6px;
  min-height: 28px;
}

.ladder-row-mine {
  background: rgba(239, 242, 22, 0.12);
}

.ladder-gutter {
  flex-shrink: 0;
  width: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.ladder-bus {
  width: 26px;
  height: 26px;
}

.ladder-bus-mine {
  filter: drop-shadow(0 0 3px var(--color-primary, #eff216));
}

/* Stale feed position — shown, but visibly not a live fix */
.ladder-bus-zombie {
  opacity: 0.4;
}

.ladder-eta {
  font-size: 0.7rem;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-variant-numeric: tabular-nums;
  color: #71717a;
}

.ladder-stop {
  flex: 1;
  min-width: 0;
  font-size: 0.8rem;
  color: #d4d4d8;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ladder-row-mine .ladder-stop {
  color: #fafafa;
  font-weight: 700;
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
