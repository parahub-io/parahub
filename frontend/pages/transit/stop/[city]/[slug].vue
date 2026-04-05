<template>
  <div class="max-w-2xl mx-auto px-4 py-2">
    <button @click="navigateTo(localePath('/transit'))" class="flex items-center gap-1.5 px-3 py-2.5 mb-4 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-700 transition-colors min-h-[44px]">
      <ArrowLeft class="w-4 h-4" />
      {{ $t('transit.back') }}
    </button>

    <div v-if="pending" class="flex justify-center py-12">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
    </div>
    <template v-else-if="stopData">
      <div class="flex items-center gap-3 mb-4">
        <img src="/img/bus-stop.png" alt="" class="w-10 h-10 flex-shrink-0" />
        <div>
          <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100">{{ stopData.name }}</h1>
          <span class="inline-block px-2 py-0.5 text-xs font-medium rounded mt-0.5"
            :class="stopData.location_type === 1
              ? 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300'
              : 'bg-neutral-200 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-300'"
          >
            {{ stopData.location_type === 1 ? 'Station' : 'Stop' }}
          </span>
        </div>
      </div>

      <!-- Stop Mini-Map -->
      <div
        class="route-mini-map mb-4 cursor-pointer rounded-lg overflow-hidden border border-neutral-200 dark:border-neutral-700 hover:border-secondary-300 dark:hover:border-secondary-600 transition-colors"
        @click="showOnMap"
      >
        <div ref="miniMapEl" class="mini-map-inner" style="height: 200px" />
      </div>

      <!-- Serving Routes -->
      <div v-if="stopData.routes?.length" class="mb-6">
        <h2 class="text-sm font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider mb-2">{{ $t('transit.serving_routes') }}</h2>
        <div class="flex flex-wrap gap-2">
          <button
            v-for="r in stopData.routes"
            :key="r.id"
            @click="openRoute(r)"
            class="px-3 py-2.5 rounded font-bold text-sm transition-opacity hover:opacity-80 min-h-[44px] flex items-center"
            :style="routeBadgeStyle(r)"
          >
            {{ r.short_name }}
          </button>
        </div>
      </div>

      <!-- ETA: approaching vehicles -->
      <div v-if="etaVehicles.length" class="mb-4">
        <h2 class="text-sm font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
          <Clock class="w-3.5 h-3.5" />
          {{ $t('transit.approaching') }}
        </h2>
        <div class="space-y-1.5">
          <div
            v-for="v in etaVehicles"
            :key="v.vehicle_id"
            class="flex items-center gap-3 p-2.5 bg-secondary/10 dark:bg-secondary/20 border border-secondary/30 dark:border-secondary/40 rounded-lg"
          >
            <span
              class="px-2 py-0.5 rounded font-bold text-xs min-w-[2.5rem] text-center flex-shrink-0"
              :style="`background-color: #${v.route_color}; color: ${textColorFor(v.route_color)}`"
            >{{ v.route_name }}</span>
            <div class="flex-1 min-w-0 text-sm text-neutral-700 dark:text-neutral-300 truncate">{{ v.headsign }}</div>
            <div class="flex items-center gap-1.5 flex-shrink-0">
              <span class="text-sm font-semibold" :class="v.eta_minutes <= 3 ? 'text-success dark:text-success-400' : v.eta_minutes <= 10 ? 'text-secondary dark:text-secondary-400' : 'text-neutral-600 dark:text-neutral-400'">
                {{ v.eta_minutes <= 1 ? '< 1' : Math.round(v.eta_minutes) }} {{ $t('transit.min') }}
              </span>
              <span class="text-xs text-neutral-400">({{ v.stops_away }} {{ $t('transit.stops_short') }})</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Live vehicles at stop -->
      <div v-if="schedule?.live_vehicles?.length" class="mb-4">
        <h2 class="text-sm font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
          <span class="w-2 h-2 rounded-full bg-success animate-pulse inline-block"></span>
          {{ $t('transit.now_at_stop') }}
        </h2>
        <div class="space-y-1.5">
          <button
            v-for="(v, idx) in schedule.live_vehicles"
            :key="idx"
            @click="openVehicleDetail(v)"
            class="w-full flex items-center gap-3 p-2.5 bg-success/10 dark:bg-success/20 border border-success/30 dark:border-success/40 rounded-lg hover:bg-success/20 dark:hover:bg-success/30 transition-colors text-left"
          >
            <img :src="routeTypeIcon(3)" class="w-6 h-6 flex-shrink-0" />
            <span
              class="px-2 py-0.5 rounded font-bold text-xs min-w-[2.5rem] text-center flex-shrink-0"
              :style="`background-color: #${resolveColor(v)}; color: ${textColorFor(resolveColor(v))}`"
            >{{ v.route_short_name }}</span>
            <div class="flex-1 min-w-0 text-sm text-neutral-700 dark:text-neutral-300 truncate">{{ v.headsign }}</div>
          </button>
        </div>
      </div>

      <!-- Schedule -->
      <div class="mb-6">
        <h2 class="text-sm font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider mb-2">{{ $t('transit.schedule') }}</h2>
        <div v-if="schedulePending" class="flex justify-center py-4">
          <div class="animate-spin rounded-full h-6 w-6 border-b-2 border-primary"></div>
        </div>
        <div v-else-if="!schedule?.departures?.length" class="text-neutral-500 dark:text-neutral-400 text-sm py-4">
          {{ $t('transit.no_departures') }}
        </div>
        <div v-else class="border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700">
          <div
            v-for="(group, gIdx) in groupedDepartures"
            :key="gIdx"
            class="flex items-start gap-3 p-2.5 hover:bg-primary/15 dark:hover:bg-primary/10 transition-colors"
          >
            <button
              @click.stop="openDepDetail(group.departures[0])"
              class="flex-shrink-0 px-1.5 py-0.5 rounded bg-primary text-neutral-900 text-xs font-bold font-mono hover:bg-primary/80 transition-colors mt-0.5"
            >{{ group.time }}</button>
            <div class="flex-1 min-w-0 flex flex-wrap items-center gap-1.5">
              <template v-for="(dep, dIdx) in group.departures" :key="dIdx">
                <NuxtLink
                  v-if="dep.route_slug && dep.route_place_slug"
                  :to="localePath(`/transit/route/${dep.route_place_slug}/${dep.route_slug}`)"
                  class="inline-flex items-center gap-1 px-2 py-0.5 rounded font-bold text-xs min-w-[2.5rem] text-center flex-shrink-0 hover:opacity-80 transition-opacity"
                  :style="`background-color: #${resolveColor(dep)}; color: ${textColorFor(resolveColor(dep))}`"
                >
                  <img :src="routeTypeIcon(dep.route_type)" class="w-3.5 h-3.5" />
                  {{ dep.route_short_name }}
                </NuxtLink>
                <button
                  v-else
                  @click.stop="openDepDetail(dep)"
                  class="inline-flex items-center gap-1 px-2 py-0.5 rounded font-bold text-xs min-w-[2.5rem] text-center flex-shrink-0 hover:opacity-80 transition-opacity"
                  :style="`background-color: #${resolveColor(dep)}; color: ${textColorFor(resolveColor(dep))}`"
                >
                  <img :src="routeTypeIcon(dep.route_type)" class="w-3.5 h-3.5" />
                  {{ dep.route_short_name }}
                </button>
              </template>
            </div>
          </div>
        </div>
      </div>

      <!-- Carpool CTA -->
      <NuxtLink
        :to="localePath(`/transit/rides?origin_id=${stopData.id}&origin_name=${encodeURIComponent(stopData.name)}&origin_lat=${stopData.lat}&origin_lon=${stopData.lon}`)"
        class="block mb-6 p-4 rounded-lg border border-secondary-300 dark:border-secondary-700 bg-secondary-50 dark:bg-secondary-900/20 hover:bg-secondary-100 dark:hover:bg-secondary-900/40 transition-colors group"
      >
        <div class="flex items-center gap-3">
          <Car class="w-6 h-6 text-secondary-600 dark:text-secondary-400 flex-shrink-0" />
          <div class="flex-1 min-w-0">
            <div class="font-semibold text-neutral-900 dark:text-neutral-100">{{ $t('rides.cta_stop.title') }}</div>
            <div class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t('rides.cta_stop.description') }}</div>
          </div>
          <span class="btn-secondary btn-sm flex-shrink-0 group-hover:bg-secondary-600 group-hover:text-white transition-colors">{{ $t('rides.cta_stop.button') }}</span>
        </div>
      </NuxtLink>

      <!-- Departure Detail Modal -->
      <Teleport to="body">
        <div v-if="depDetail" class="fixed inset-0 z-50 flex items-end sm:items-center justify-center" @click.self="depDetail = null">
          <div class="fixed inset-0 bg-black/50" @click="depDetail = null"></div>
          <div class="relative bg-white dark:bg-neutral-900 w-full sm:max-w-lg sm:rounded-xl rounded-t-xl max-h-[85vh] overflow-y-auto shadow-xl">
            <div class="sticky top-0 bg-white dark:bg-neutral-900 border-b border-neutral-200 dark:border-neutral-700 px-4 py-3 flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span
                  class="px-2 py-0.5 rounded font-bold text-xs"
                  :style="`background-color: #${resolveColor(depDetail)}; color: ${textColorFor(resolveColor(depDetail))}`"
                >{{ depDetail.route_short_name }}</span>
                <h3 class="font-bold text-sm text-neutral-900 dark:text-neutral-100">{{ formatTime(depDetail.departure_time) }}</h3>
              </div>
              <button @click="depDetail = null" class="btn-ghost btn-icon btn-sm"><X class="w-4 h-4" /></button>
            </div>
            <div class="px-4 py-3 space-y-3 text-sm">
              <!-- Route & Trip -->
              <div class="space-y-1.5">
                <div class="flex items-center gap-2">
                  <span class="text-neutral-500 dark:text-neutral-400 w-24 flex-shrink-0">{{ $t('transit.route') }}</span>
                  <span class="text-neutral-900 dark:text-neutral-100 font-medium">{{ depDetail.route_short_name }}</span>
                  <span v-if="depDetail.route_long_name" class="text-neutral-500 dark:text-neutral-400">{{ depDetail.route_long_name }}</span>
                </div>
                <div class="flex items-center gap-2">
                  <span class="text-neutral-500 dark:text-neutral-400 w-24 flex-shrink-0">{{ $t('transit.direction') }}</span>
                  <span class="text-neutral-900 dark:text-neutral-100">{{ depDetail.headsign }}</span>
                </div>
                <div class="flex items-center gap-2">
                  <span class="text-neutral-500 dark:text-neutral-400 w-24 flex-shrink-0">{{ $t('transit.departure') }}</span>
                  <span class="text-neutral-900 dark:text-neutral-100 font-mono font-bold">{{ depDetail.departure_time }}</span>
                </div>
                <div class="flex items-center gap-2">
                  <span class="text-neutral-500 dark:text-neutral-400 w-24 flex-shrink-0">Trip ID</span>
                  <span class="text-neutral-900 dark:text-neutral-100 font-mono text-xs">{{ depDetail.trip_id }}</span>
                </div>
                <div v-if="depDetail.service_id" class="flex items-center gap-2">
                  <span class="text-neutral-500 dark:text-neutral-400 w-24 flex-shrink-0">Service ID</span>
                  <span class="text-neutral-900 dark:text-neutral-100 font-mono text-xs">{{ depDetail.service_id }}</span>
                </div>
              </div>

              <div class="border-t border-neutral-200 dark:border-neutral-700"></div>

              <!-- Provider / Data source -->
              <div class="space-y-1.5">
                <h4 class="text-xs font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">{{ $t('transit.provider') }}</h4>
                <div v-if="schedule?.agency_name" class="flex items-center gap-2">
                  <span class="text-neutral-500 dark:text-neutral-400 w-24 flex-shrink-0">{{ $t('transit.agency') }}</span>
                  <a v-if="schedule.agency_url" :href="schedule.agency_url" target="_blank" rel="noopener" class="text-link">{{ schedule.agency_name }}</a>
                  <span v-else class="text-neutral-900 dark:text-neutral-100">{{ schedule.agency_name }}</span>
                </div>
                <div v-if="schedule?.agency_timezone" class="flex items-center gap-2">
                  <span class="text-neutral-500 dark:text-neutral-400 w-24 flex-shrink-0">{{ $t('transit.timezone') }}</span>
                  <span class="text-neutral-900 dark:text-neutral-100">{{ schedule.agency_timezone }}</span>
                </div>
                <div v-if="schedule?.data_source_name" class="flex items-center gap-2">
                  <span class="text-neutral-500 dark:text-neutral-400 w-24 flex-shrink-0">{{ $t('transit.data_source') }}</span>
                  <a v-if="schedule.data_source_url" :href="schedule.data_source_url" target="_blank" rel="noopener" class="text-link text-xs break-all">{{ schedule.data_source_name }}</a>
                  <span v-else class="text-neutral-900 dark:text-neutral-100">{{ schedule.data_source_name }}</span>
                </div>
                <div class="flex items-center gap-2">
                  <span class="text-neutral-500 dark:text-neutral-400 w-24 flex-shrink-0">{{ $t('transit.schedule_date') }}</span>
                  <span class="text-neutral-900 dark:text-neutral-100">{{ schedule?.date }}</span>
                </div>
              </div>

              <!-- Link to route page -->
              <div v-if="depDetail.route_slug && depDetail.route_place_slug" class="pt-1">
                <NuxtLink
                  :to="localePath(`/transit/route/${depDetail.route_place_slug}/${depDetail.route_slug}`)"
                  class="btn-secondary btn-sm w-full justify-center"
                  @click="depDetail = null"
                >{{ $t('transit.view_route') }}</NuxtLink>
              </div>
            </div>
          </div>
        </div>
      </Teleport>

      <!-- Vehicle Detail Modal -->
      <Teleport to="body">
        <div v-if="vehicleDetail" class="fixed inset-0 z-50 flex items-end sm:items-center justify-center" @click.self="vehicleDetail = null">
          <div class="fixed inset-0 bg-black/50" @click="vehicleDetail = null"></div>
          <div class="relative bg-white dark:bg-neutral-900 w-full sm:max-w-lg sm:rounded-xl rounded-t-xl max-h-[85vh] overflow-y-auto shadow-xl">
            <div class="sticky top-0 bg-white dark:bg-neutral-900 border-b border-neutral-200 dark:border-neutral-700 px-4 py-3 flex items-center justify-between">
              <div class="flex items-center gap-2">
                <img :src="routeTypeIcon(3)" class="w-6 h-6" />
                <h3 class="font-bold text-sm text-neutral-900 dark:text-neutral-100">{{ vehicleDetail.vehicle_id }}</h3>
              </div>
              <button @click="vehicleDetail = null" class="btn-ghost btn-icon btn-sm"><X class="w-4 h-4" /></button>
            </div>
            <div v-if="vehicleDetailLoading" class="flex justify-center py-8">
              <div class="animate-spin rounded-full h-6 w-6 border-b-2 border-primary"></div>
            </div>
            <div v-else class="px-4 py-3 space-y-3 text-sm">
              <div v-if="vehicleDetail.vdata" class="space-y-1.5">
                <h4 class="text-xs font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">GTFS-RT</h4>
                <div class="grid grid-cols-2 gap-1 text-xs font-mono">
                  <div>{{ $t('transit.route') }}: <span class="text-neutral-900 dark:text-neutral-100 font-bold">{{ vehicleDetail.vdata.rn }}</span></div>
                  <div>{{ $t('transit.direction') }}: <span class="text-neutral-900 dark:text-neutral-100">{{ vehicleDetail.vdata.hs }}</span></div>
                  <div>pos: <span class="text-neutral-900 dark:text-neutral-100">{{ Number(vehicleDetail.vdata.lat).toFixed(5) }}, {{ Number(vehicleDetail.vdata.lon).toFixed(5) }}</span></div>
                  <div>speed: <span class="text-neutral-900 dark:text-neutral-100">{{ vehicleDetail.vdata.s }} km/h</span></div>
                  <div>bearing: <span class="text-neutral-900 dark:text-neutral-100">{{ vehicleDetail.vdata.b }}°</span></div>
                  <div>status: <span class="text-neutral-900 dark:text-neutral-100">{{ vehicleDetail.vdata.st }}</span></div>
                  <div>stop: <span class="text-neutral-900 dark:text-neutral-100">{{ vehicleDetail.vdata.sid }}</span></div>
                  <div>trip: <span class="text-neutral-900 dark:text-neutral-100 break-all">{{ vehicleDetail.vdata.tid }}</span></div>
                  <div v-if="vehicleDetail.vdata.z" class="col-span-2 text-amber-600 font-bold">ZOMBIE (stale data)</div>
                </div>
                <div v-if="vehicleDetail.stop_name" class="text-xs">
                  <span class="text-neutral-500 dark:text-neutral-400">stop:</span>
                  <span class="text-neutral-900 dark:text-neutral-100 ml-1">{{ vehicleDetail.stop_name }}</span>
                </div>
                <div class="text-xs text-neutral-400">
                  updated: {{ vehicleDetail.vdata.t ? new Date(vehicleDetail.vdata.t * 1000).toLocaleTimeString() : '?' }}
                </div>
              </div>

              <div v-if="vehicleDetail.vprev" class="border-t border-neutral-200 dark:border-neutral-700 pt-3 space-y-1.5">
                <h4 class="text-xs font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">STT Tracking</h4>
                <div class="grid grid-cols-2 gap-1 text-xs font-mono">
                  <div>state:
                    <span class="px-1 py-0.5 rounded text-[10px] font-bold uppercase"
                      :class="{
                        'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200': vehicleDetail.vprev.st === 'c',
                        'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200': vehicleDetail.vprev.st === 't',
                        'bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400': vehicleDetail.vprev.st === 'd',
                      }"
                    >{{ { c: 'confirmed', t: 'tentative', d: 'dual' }[vehicleDetail.vprev.st] || vehicleDetail.vprev.st }}</span>
                  </div>
                  <div>dir: <span class="text-neutral-900 dark:text-neutral-100">{{ vehicleDetail.vprev.d }}</span></div>
                  <div>stop idx: <span class="text-neutral-900 dark:text-neutral-100">{{ vehicleDetail.vprev.idx }}</span></div>
                  <div>stall: <span class="text-neutral-900 dark:text-neutral-100">{{ vehicleDetail.vprev.stall }}</span></div>
                  <div v-if="vehicleDetail.vprev.d_alt != null">alt dir: <span class="text-neutral-900 dark:text-neutral-100">{{ vehicleDetail.vprev.d_alt }} (idx {{ vehicleDetail.vprev.idx_alt }})</span></div>
                </div>
              </div>

              <div v-if="vehicleDetail.data_source_name" class="border-t border-neutral-200 dark:border-neutral-700 pt-3 space-y-1">
                <h4 class="text-xs font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">{{ $t('transit.data_source') }}</h4>
                <div class="text-xs">
                  <a v-if="vehicleDetail.data_source_url" :href="vehicleDetail.data_source_url" target="_blank" rel="noopener" class="text-link">{{ vehicleDetail.data_source_name }}</a>
                  <span v-else class="text-neutral-900 dark:text-neutral-100">{{ vehicleDetail.data_source_name }}</span>
                </div>
                <div class="text-xs text-neutral-400 font-mono">ds: {{ vehicleDetail.data_source_id?.slice(0, 12) }}...</div>
              </div>
            </div>
          </div>
        </div>
      </Teleport>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { ArrowLeft, Car, Clock, X } from 'lucide-vue-next'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const localePath = useLocalePath()
const colorMode = useColorMode()
const { routeBadgeStyle, resolveColor, textColorFor, formatTime, routeTypeIcon } = useTransitHelpers()

const city = route.params.city as string
const slug = route.params.slug as string

const { data: stopData, pending } = await useFetch(`/api/v1/geo/transit/stops/${city}/${slug}/`)
const { data: schedule, pending: schedulePending } = await useFetch(`/api/v1/geo/transit/stops/${city}/${slug}/schedule/`)

useSeoMeta({
  title: () => stopData.value?.name ? `${stopData.value.name} — Parahub` : t('transit.title'),
  ogTitle: () => stopData.value?.name || t('transit.title'),
  description: () => stopData.value?.name ? `${stopData.value.name} — transit stop schedules and real-time arrivals` : t('transit.title'),
  ogDescription: () => stopData.value?.name ? `${stopData.value.name} — transit stop schedules and real-time arrivals` : t('transit.title'),
  ogImage: '/og-image.jpg',
  ogType: 'website',
  twitterCard: 'summary_large_image',
})

// ETA: approaching vehicles
const etaVehicles = ref<any[]>([])
let etaTimer: ReturnType<typeof setInterval> | null = null

async function fetchEta() {
  try {
    const data = await $fetch(`/api/v1/geo/transit/stops/${city}/${slug}/eta/`)
    etaVehicles.value = (data as any)?.vehicles ?? []
  } catch {}
}

onMounted(() => {
  fetchEta()
  etaTimer = setInterval(fetchEta, 30000)

  // Mini-map is at the top now — create immediately
  if (miniMapEl.value && !miniMapCreated) createMiniMap()
})

onUnmounted(() => {
  if (etaTimer) clearInterval(etaTimer)
  if (miniMap) { miniMap.remove(); miniMap = null }
})

function openRoute(r: any) {
  if (r.slug && r.place_slug) {
    navigateTo(localePath(`/transit/route/${r.place_slug}/${r.slug}`))
  } else {
    navigateTo(localePath(`/transit/route/${city}/${r.slug || r.id}`))
  }
}

// Group departures by formatted time
const groupedDepartures = computed(() => {
  const deps = schedule.value?.departures?.slice(0, 15)
  if (!deps?.length) return []
  const groups: { time: string; departures: any[] }[] = []
  let current: { time: string; departures: any[] } | null = null
  for (const dep of deps) {
    const t = formatTime(dep.departure_time)
    if (current && current.time === t) {
      current.departures.push(dep)
    } else {
      current = { time: t, departures: [dep] }
      groups.push(current)
    }
  }
  return groups
})

// Departure detail modal
const depDetail = ref<any>(null)

function openDepDetail(dep: any) {
  depDetail.value = dep
}

// Vehicle detail modal
const vehicleDetail = ref<any>(null)
const vehicleDetailLoading = ref(false)

async function openVehicleDetail(v: any) {
  const vid = v?.vehicle_id || v?.v
  const dsId = stopData.value?.data_source_id
  if (!vid || !dsId) {
    vehicleDetail.value = { vehicle_id: vid || '?', vdata: v }
    return
  }
  vehicleDetail.value = { vehicle_id: vid }
  vehicleDetailLoading.value = true
  try {
    const data = await $fetch(`/api/v1/geo/transit/vehicles/state/`, { params: { ds_id: dsId, vid } })
    vehicleDetail.value = data
  } catch {
    vehicleDetail.value = { vehicle_id: vid, vdata: v }
  }
  vehicleDetailLoading.value = false
}

// Show on map
function showOnMap() {
  if (!stopData.value) return
  router.push(localePath(`/map?lat=${stopData.value.lat}&lng=${stopData.value.lon}&zoom=16&transit=1&returnTo=${encodeURIComponent(route.fullPath)}`))
}

// ── Mini-Map ──
const miniMapEl = ref<HTMLElement | null>(null)
let miniMap: any = null
let miniMapCreated = false

const getMiniMapStyle = () =>
  colorMode.value === 'dark'
    ? '/map-styles/dark-liberty-parahub.json'
    : '/map-styles/liberty-parahub.json'

async function createMiniMap() {
  if (miniMapCreated || !miniMapEl.value || !stopData.value) return
  miniMapCreated = true

  const mod = await import('maplibre-gl')
  const maplibregl = mod.default || mod
  await import('maplibre-gl/dist/maplibre-gl.css')

  miniMap = new maplibregl.Map({
    container: miniMapEl.value,
    style: getMiniMapStyle(),
    center: [stopData.value.lon, stopData.value.lat],
    zoom: 16,
    interactive: false,
    attributionControl: false,
    trackResize: false,
    fadeDuration: 0,
    pixelRatio: Math.min(window.devicePixelRatio || 1, 2),
  })

  miniMap.once('load', async () => {
    miniMap.resize()

    // Load bus-stop icon and add as symbol marker
    const { data: img } = await miniMap.loadImage('/img/bus-stop.png')
    if (!miniMap) return
    miniMap.addImage('bus-stop-icon', img)

    miniMap.addSource('stop-point', {
      type: 'geojson',
      data: {
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [stopData.value.lon, stopData.value.lat] },
        properties: {},
      },
    })
    miniMap.addLayer({
      id: 'stop-point-icon',
      type: 'symbol',
      source: 'stop-point',
      layout: {
        'icon-image': 'bus-stop-icon',
        'icon-size': 0.17,
        'icon-allow-overlap': true,
      },
    })
  })
}

watch(() => colorMode.value, () => {
  if (miniMap) miniMap.setStyle(getMiniMapStyle())
})
</script>

<style scoped>
.mini-map-inner {
  width: 100%;
  height: 100%;
}

.mini-map-inner :deep(.maplibregl-ctrl-bottom-left),
.mini-map-inner :deep(.maplibregl-ctrl-bottom-right) {
  display: none;
}
</style>
