<template>
  <div class="max-w-2xl mx-auto px-4 py-2">
    <button @click="navigateTo(localePath('/transit'))" class="flex items-center gap-1.5 px-3 py-2.5 mb-4 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-700 transition-colors min-h-[44px]">
      <ArrowLeft class="w-4 h-4" />
      {{ $t('transit.back') }}
    </button>

    <div v-if="pending" class="flex justify-center py-12">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
    </div>
    <template v-else-if="routeData">
      <h1 class="sr-only">{{ routeData.short_name }} — {{ routeData.long_name }}</h1>
      <div class="flex items-center gap-3 mb-2">
        <img :src="routeTypeIcon(routeData.route_type)" :alt="routeTypeFallback(routeData.route_type)" class="w-10 h-10 flex-shrink-0" />
        <div>
          <span class="inline-block px-2.5 py-1 rounded font-bold text-lg" :style="routeBadgeStyle(routeData)">{{ routeData.short_name }}</span>
          <span v-if="isNightRoute" class="inline-flex items-center gap-1 ml-1.5 px-2 py-0.5 rounded-full bg-indigo-100 dark:bg-indigo-900/50 text-indigo-700 dark:text-indigo-300 text-xs font-medium">
            <Moon class="w-3 h-3" />{{ $t('transit.night_route') }}
          </span>
          <div class="text-sm text-neutral-600 dark:text-neutral-400 mt-0.5">{{ routeData.long_name }}</div>
        </div>
      </div>

      <!-- Direction Toggle -->
      <div v-if="routeData.directions?.length > 1" class="flex gap-2 mb-4">
        <button
          v-for="d in routeData.directions"
          :key="d.direction_id"
          @click="routeDirection = d.direction_id"
          class="flex-1 py-3 text-sm font-medium rounded-lg border transition-colors truncate px-3 min-h-[44px]"
          :class="routeDirection === d.direction_id
            ? 'bg-secondary-600 text-white border-secondary-600'
            : 'bg-white dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300 border-neutral-300 dark:border-neutral-600 hover:border-secondary-300'"
        >
          {{ d.headsign || (d.direction_id === 0 ? 'A → B' : 'B → A') }}
        </button>
      </div>

      <!-- Stops List -->
      <div class="mb-6">
        <h2 class="text-sm font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider mb-2">
          {{ $t('transit.stops_count', { count: routeStops.length }) }}
        </h2>
        <div class="border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700">
          <div
            v-for="s in routeStops"
            :key="s.id"
            class="flex items-center gap-2 hover:bg-primary/15 dark:hover:bg-primary/10 transition-colors min-h-[44px]"
          >
            <button
              v-if="stopEtas[s.source_id] != null"
              @click.stop="openEtaDetail(s.source_id)"
              class="flex-shrink-0 ml-2 px-1.5 py-0.5 rounded bg-primary text-neutral-900 text-xs font-bold font-mono hover:bg-primary/80 transition-colors"
            >{{ formatStopEta(s.source_id) }}</button>
            <span
              v-else-if="vehicleAtStop(s.source_id) || dirStopIds.has(s.source_id)"
              class="flex-shrink-0 ml-2 px-1.5 py-0.5 rounded bg-primary text-neutral-900 text-xs font-bold font-mono"
              :title="$t('transit.vehicle_here')"
            >{{ nowTimeStr }}</span>
            <span
              v-else-if="stopSchedule[s.source_id]"
              class="flex-shrink-0 ml-2 px-1.5 py-0.5 rounded bg-neutral-200 dark:bg-neutral-700 text-neutral-700 dark:text-neutral-300 text-xs font-mono"
              :title="$t('transit.scheduled')"
            >{{ stopSchedule[s.source_id] }}</span>
            <span
              v-else-if="isFirstStop(s.source_id) && firstDeparture"
              class="flex-shrink-0 ml-2 px-1.5 py-0.5 rounded text-xs font-mono bg-indigo-100 dark:bg-indigo-900/50 text-indigo-700 dark:text-indigo-300"
              :title="$t('transit.next_departure')"
            >{{ firstDeparture }}</span>
            <span v-else class="flex-shrink-0 ml-2 w-10"></span>
            <button
              @click="openStop(s)"
              class="flex-1 flex items-center gap-2 p-3 pl-0 min-w-0 text-left"
            >
              <span class="text-sm text-neutral-900 dark:text-neutral-100 flex-1 min-w-0">{{ s.name }}</span>
              <button
                v-if="vehicleAtStop(s.source_id)"
                @click.stop="openVehicleDetail(vehicleAtStop(s.source_id))"
                class="flex-shrink-0 p-0.5 rounded-full hover:bg-primary/30 transition-colors"
                :class="vehicleAtStop(s.source_id).z ? 'opacity-40' : ''"
              >
                <img :src="routeTypeIcon(routeData.route_type)" class="w-6 h-6" :title="vehicleAtStop(s.source_id).z ? t('transit.zombie') : t('transit.vehicle_here')" />
              </button>
              <button
                v-else-if="dirStopIds.has(s.source_id)"
                @click.stop="openVehicleDetail({ sid: s.source_id })"
                class="flex-shrink-0 p-0.5 rounded-full hover:bg-primary/30 transition-colors"
              >
                <img :src="routeTypeIcon(routeData.route_type)" class="w-6 h-6" :title="t('transit.vehicle_here')" />
              </button>
            </button>
          </div>
        </div>
      </div>

      <!-- Route Mini-Map -->
      <div
        class="route-mini-map mb-4 cursor-pointer rounded-lg overflow-hidden border border-neutral-200 dark:border-neutral-700 hover:border-secondary-300 dark:hover:border-secondary-600 transition-colors"
        @click="showRouteOnMap"
      >
        <div ref="miniMapEl" class="mini-map-inner aspect-[1.618]" />
      </div>

      <!-- Tickets -->
      <div v-if="ticketTypes.length" class="mb-6">
        <h2 class="text-sm font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider mb-2">
          {{ $t('tickets.title') }}
        </h2>
        <TicketsTicketPurchaseCard :ticket-types="ticketTypes" :buying-id="buyingTicketId" @buy="startBuy" />
      </div>

      <TicketsTicketBuyModal
        :ticket-type="buyingTicketType"
        @close="buyingTicketType = null; buyingTicketId = null"
        @purchased="onPurchased"
        @show-qr="qrTicket = $event"
      />
      <TicketsTicketQRModal :ticket="qrTicket" @close="qrTicket = null" />

      <!-- ETA Detail Modal -->
      <Teleport to="body">
        <div v-if="etaDetail" class="fixed inset-0 z-50 flex items-end sm:items-center justify-center" @click.self="etaDetail = null">
          <div class="fixed inset-0 bg-black/50" @click="etaDetail = null"></div>
          <div class="relative bg-white dark:bg-neutral-900 w-full sm:max-w-lg sm:rounded-xl rounded-t-xl max-h-[85vh] overflow-y-auto shadow-xl">
            <div class="sticky top-0 bg-white dark:bg-neutral-900 border-b border-neutral-200 dark:border-neutral-700 px-4 py-3 flex items-center justify-between">
              <h3 class="font-bold text-sm text-neutral-900 dark:text-neutral-100">
                ETA {{ etaDetail.stop_source_id }} <span class="text-neutral-400 font-normal">#{{ etaDetail.stop_index }}</span>
              </h3>
              <button @click="etaDetail = null" class="btn-ghost btn-icon btn-sm"><X class="w-4 h-4" /></button>
            </div>
            <div class="px-4 py-3 space-y-4 text-xs font-mono">
              <!-- Meta -->
              <div class="grid grid-cols-2 gap-2 text-neutral-600 dark:text-neutral-400">
                <div>route: <span class="text-neutral-900 dark:text-neutral-100">{{ etaDetail.route_source_id }}</span></div>
                <div>dir: <span class="text-neutral-900 dark:text-neutral-100">{{ etaDetail.direction }}</span></div>
                <div>ds: <span class="text-neutral-900 dark:text-neutral-100">{{ etaDetail.data_source_id?.slice(0, 8) }}...</span></div>
                <div>stops: <span class="text-neutral-900 dark:text-neutral-100">{{ etaDetail.total_stops }}</span></div>
              </div>

              <!-- Vehicles -->
              <div v-for="v in etaDetail.vehicles" :key="v.vehicle_id"
                class="border rounded-lg p-3 space-y-2"
                :class="v.is_approaching
                  ? 'border-primary bg-primary/5'
                  : 'border-neutral-200 dark:border-neutral-700'"
              >
                <div class="flex items-center justify-between">
                  <span class="font-bold text-neutral-900 dark:text-neutral-100">
                    {{ v.vehicle_id }}
                  </span>
                  <span
                    class="px-1.5 py-0.5 rounded text-[10px] font-bold uppercase"
                    :class="{
                      'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200': v.state.status === 'confirmed',
                      'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200': v.state.status === 'tentative',
                      'bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400': v.state.status === 'dual',
                    }"
                  >{{ v.state.status }}</span>
                </div>

                <!-- Vehicle state -->
                <div class="grid grid-cols-2 gap-1 text-neutral-500 dark:text-neutral-400">
                  <div>idx: <span class="text-neutral-800 dark:text-neutral-200">{{ v.state.stop_index }}</span> ({{ v.state.stop_id }})</div>
                  <div>stall: <span class="text-neutral-800 dark:text-neutral-200">{{ v.state.stall_count }}</span></div>
                  <div>pos: <span class="text-neutral-800 dark:text-neutral-200">{{ Number(v.state.lat).toFixed(4) }}, {{ Number(v.state.lon).toFixed(4) }}</span></div>
                  <div>spd: <span class="text-neutral-800 dark:text-neutral-200">{{ v.live.speed ?? '?' }} km/h</span></div>
                  <div v-if="v.live.headsign">hs: <span class="text-neutral-800 dark:text-neutral-200">{{ v.live.headsign }}</span></div>
                  <div v-if="v.live.zombie" class="text-amber-600">ZOMBIE</div>
                </div>

                <!-- ETA breakdown -->
                <template v-if="v.is_approaching">
                  <div class="flex items-center gap-2 text-neutral-900 dark:text-neutral-100">
                    <span class="bg-primary px-1.5 py-0.5 rounded font-bold text-neutral-900">
                      {{ Math.round(v.eta_seconds / 60) }} min
                    </span>
                    <span class="text-neutral-500 dark:text-neutral-400">
                      {{ v.stops_away }} stops &middot;
                      {{ v.observed_segments }} observed / {{ v.fallback_segments }} fallback
                    </span>
                  </div>
                  <!-- Segment chain -->
                  <div class="space-y-0.5">
                    <div v-for="(seg, i) in v.segments" :key="i"
                      class="flex items-center gap-1"
                      :class="seg.observed ? 'text-neutral-700 dark:text-neutral-300' : 'text-neutral-400 dark:text-neutral-500'"
                    >
                      <span class="w-16 text-right">{{ seg.from }}</span>
                      <span class="text-neutral-400">&rarr;</span>
                      <span class="w-16">{{ seg.to }}</span>
                      <span class="ml-auto tabular-nums" :class="seg.observed ? 'text-green-700 dark:text-green-400' : 'text-amber-600 dark:text-amber-400'">
                        {{ seg.avg_s }}s
                      </span>
                      <span v-if="seg.observed" class="text-neutral-400">({{ seg.samples }})</span>
                      <span v-else class="text-amber-500">fallback</span>
                    </div>
                  </div>
                </template>
                <div v-else class="text-neutral-400 italic">not approaching</div>
              </div>

              <div v-if="!etaDetail.vehicles?.length" class="text-neutral-400 text-center py-4">
                No vehicles tracking this route
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
                <img :src="routeTypeIcon(routeData.route_type)" class="w-6 h-6" />
                <h3 class="font-bold text-sm text-neutral-900 dark:text-neutral-100">{{ vehicleDetail.vehicle_id }}</h3>
              </div>
              <button @click="vehicleDetail = null" class="btn-ghost btn-icon btn-sm"><X class="w-4 h-4" /></button>
            </div>
            <div v-if="vehicleDetailLoading" class="flex justify-center py-8">
              <div class="animate-spin rounded-full h-6 w-6 border-b-2 border-primary"></div>
            </div>
            <div v-else class="px-4 py-3 space-y-3 text-sm">
              <!-- GTFS-RT data -->
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
                  <span class="text-neutral-500 dark:text-neutral-400">{{ $t('transit.direction') }} stop:</span>
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

              <!-- Data source -->
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
import { ArrowLeft, Moon, X } from 'lucide-vue-next'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const localePath = useLocalePath()
const colorMode = useColorMode()
const { routeTypeIcon, routeTypeFallback, resolveColor, routeBadgeStyle } = useTransitHelpers()

const city = route.params.city as string
const slug = route.params.slug as string

const { data: routeData, pending } = await useFetch(`/api/v1/geo/transit/routes/${city}/${slug}/`)

useSeoMeta({
  title: () => routeData.value?.short_name ? `${routeData.value.short_name} ${routeData.value.long_name} — Parahub` : t('transit.title'),
  ogTitle: () => routeData.value?.short_name ? `${routeData.value.short_name} ${routeData.value.long_name}` : t('transit.title'),
  description: () => routeData.value?.long_name ? `Route ${routeData.value.short_name} — ${routeData.value.long_name}` : t('transit.title'),
  ogDescription: () => routeData.value?.long_name ? `Route ${routeData.value.short_name} — ${routeData.value.long_name}` : t('transit.title'),
  ogImage: '/og-image.jpg',
  ogType: 'website',
  twitterCard: 'summary_large_image',
})

const routeDirection = ref(0)

const routeStops = computed(() => {
  if (!routeData.value) return []
  if (routeDirection.value === 1) {
    const dir1 = routeData.value.stops_dir1
    return dir1?.length ? dir1 : [...(routeData.value.stops ?? [])].reverse()
  }
  return routeData.value.stops ?? []
})

const routeCenter = computed(() => {
  if (!routeData.value?.stops?.length) return { lat: 0, lon: 0 }
  const stops = routeData.value.stops
  const mid = stops[Math.floor(stops.length / 2)]
  return { lat: mid.lat, lon: mid.lon }
})

function openStop(s: any) {
  if (s.slug && s.place_slug) {
    navigateTo(localePath(`/transit/stop/${s.place_slug}/${s.slug}`))
  } else {
    navigateTo(localePath(`/transit/stop/${city}/${s.slug || s.id}`))
  }
}

// GTFS static schedule: {direction: {stop_source_id: "HH:MM"}}
const scheduleData = ref<{
  schedule: Record<string, Record<string, string>>
  first_departure: Record<string, string>
  is_night: boolean
}>({ schedule: {}, first_departure: {}, is_night: false })

const isNightRoute = computed(() => scheduleData.value.is_night)
const stopSchedule = computed(() => scheduleData.value.schedule[String(routeDirection.value)] ?? {})
const firstDeparture = computed(() => scheduleData.value.first_departure[String(routeDirection.value)] ?? null)

function isFirstStop(sourceId: string): boolean {
  const stops = routeStops.value
  return stops.length > 0 && stops[0].source_id === sourceId
}

async function loadSchedule() {
  try {
    const data = await $fetch<typeof scheduleData.value>(
      `/api/v1/geo/transit/routes/${city}/${slug}/schedule/`
    )
    scheduleData.value = data
  } catch {}
}

// Route-wide ETA predictions: both directions from WS
// allEtas: {0: {stop_src: seconds}, 1: {stop_src: seconds}}
const allEtas = ref<Record<number, Record<string, number>>>({})
const stopEtas = computed(() => allEtas.value[routeDirection.value] ?? {})

function formatStopEta(stopSourceId: string): string {
  const eta = stopEtas.value[stopSourceId]
  if (eta == null) return ''
  const arrival = new Date(Date.now() + eta * 1000)
  return `${arrival.getHours().toString().padStart(2, '0')}:${arrival.getMinutes().toString().padStart(2, '0')}`
}

// Current time string, re-evaluated on each WS update
const nowTimeStr = computed(() => {
  void liveVehicles.value  // trigger reactivity on WS tick
  const now = new Date()
  return `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`
})

// ETA detail modal (REST endpoint for full breakdown)
const etaDetail = ref<any>(null)

async function openEtaDetail(stopSourceId: string) {
  try {
    const data = await $fetch(
      `/api/v1/geo/transit/routes/${city}/${slug}/eta/${stopSourceId}/`,
      { params: { direction: routeDirection.value } }
    )
    etaDetail.value = data
  } catch {}
}

// Vehicle detail modal
const vehicleDetail = ref<any>(null)
const vehicleDetailLoading = ref(false)

async function openVehicleDetail(v: any) {
  const vid = v?.v
  const dsId = routeData.value?.data_source_id
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

// Live vehicle positions + ETAs via WebSocket
const liveStopIds = ref<string[]>([])
const liveVehicles = ref<any[]>([])
let liveWs: WebSocket | null = null

// Stop IDs filtered by current direction
const dirStopIds = computed(() => {
  const ids = new Set<string>()
  for (const v of liveVehicles.value) {
    if (v.d === routeDirection.value && v.sid) ids.add(v.sid)
  }
  return ids
})

function vehicleAtStop(stopSourceId: string) {
  return liveVehicles.value.find(v => v.sid === stopSourceId && v.d === routeDirection.value) || null
}

let liveWsIntentionalClose = false
let liveWsReconnectTimer: ReturnType<typeof setTimeout> | null = null

function connectLiveWS() {
  if (!import.meta.client) return
  const dsId = routeData.value?.data_source_id
  const sourceId = routeData.value?.source_id
  if (!dsId || !sourceId) return

  liveWsIntentionalClose = false
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const ws = new WebSocket(`${proto}://${location.host}/ws/v1/transit/`)
  liveWs = ws

  ws.onopen = () => {
    ws.send(JSON.stringify({ type: 'subscribe_route', ds_id: dsId, route_source_id: sourceId }))
  }

  ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data)
      if (msg.type === 'route_vehicles' || msg.type === 'route_live') {
        liveStopIds.value = msg.stop_ids || []
        liveVehicles.value = msg.vehicles || []
        if (msg.etas) {
          // Convert string keys to numbers: {"0": {...}} → {0: {...}}
          const parsed: Record<number, Record<string, number>> = {}
          for (const [k, v] of Object.entries(msg.etas)) {
            parsed[Number(k)] = v as Record<string, number>
          }
          allEtas.value = parsed
        }
      }
    } catch {}
  }

  ws.onclose = () => {
    liveWs = null
    if (!liveWsIntentionalClose) {
      scheduleLiveWsReconnect()
    }
  }
}

function scheduleLiveWsReconnect(delayMs = 3000) {
  if (liveWsReconnectTimer) clearTimeout(liveWsReconnectTimer)
  if (liveWsIntentionalClose) return
  liveWsReconnectTimer = setTimeout(() => {
    liveWsReconnectTimer = null
    if (!liveWsIntentionalClose) connectLiveWS()
  }, delayMs)
}

function onLiveWsVisibilityChange() {
  if (document.visibilityState !== 'visible') return
  if (!liveWs || liveWs.readyState === WebSocket.CLOSED || liveWs.readyState === WebSocket.CLOSING) {
    scheduleLiveWsReconnect(0)
  }
}

onMounted(() => {
  loadSchedule()
  connectLiveWS()
  document.addEventListener('visibilitychange', onLiveWsVisibilityChange)

  // Lazy mini-map: create when container enters viewport
  if (miniMapEl.value) {
    miniMapObserver = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !miniMapCreated) createMiniMap()
      },
      { rootMargin: '200px' }
    )
    miniMapObserver.observe(miniMapEl.value)
  }
})

onUnmounted(() => {
  document.removeEventListener('visibilitychange', onLiveWsVisibilityChange)
  liveWsIntentionalClose = true
  if (liveWsReconnectTimer) clearTimeout(liveWsReconnectTimer)
  liveWs?.close()
  liveWs = null
  miniMapObserver?.disconnect()
  miniMapObserver = null
  if (miniMap) { miniMap.remove(); miniMap = null }
})

// ── Tickets ──
const ticketTypes = ref<any[]>([])
const buyingTicketId = ref<string | null>(null)
const buyingTicketType = ref<any | null>(null)
const qrTicket = ref<any | null>(null)
const authStore = useAuthStore()

async function loadTicketTypes() {
  if (!routeData.value?.id) return
  try {
    const data = await $fetch<any[]>(`/api/v1/tickets/types/`, {
      params: { route_id: routeData.value.id },
    })
    ticketTypes.value = data || []
  } catch {}
}

function startBuy(tt: any) {
  if (!tt.operator_ln_address && !tt.operator_spark_address) {
    alert(t('tickets.error_no_ln_address'))
    return
  }
  buyingTicketId.value = tt.id
  buyingTicketType.value = tt
}

function onPurchased() {
  loadTicketTypes()
}

watch(() => routeData.value, () => loadTicketTypes(), { immediate: true })

function showRouteOnMap() {
  if (!routeData.value) return
  ;(window as any)._transitRouteData = routeData.value
  const c = routeCenter.value
  router.push(localePath(`/map?lat=${c.lat}&lng=${c.lon}&zoom=13&transit=1&routeCity=${city}&routeSlug=${slug}&returnTo=${encodeURIComponent(route.fullPath)}`))
}

// ── Mini-Map ──
const miniMapEl = ref<HTMLElement | null>(null)
let miniMap: any = null
let miniMapCreated = false
let miniMapObserver: IntersectionObserver | null = null

const getMiniMapStyle = () =>
  colorMode.value === 'dark'
    ? '/map-styles/dark-liberty-parahub.json'
    : '/map-styles/liberty-parahub.json'

async function createMiniMap() {
  if (miniMapCreated || !miniMapEl.value || !routeData.value) return
  miniMapCreated = true

  const mod = await import('maplibre-gl')
  const maplibregl = mod.default || mod
  await import('maplibre-gl/dist/maplibre-gl.css')

  const c = routeCenter.value
  miniMap = new maplibregl.Map({
    container: miniMapEl.value,
    style: getMiniMapStyle(),
    center: [c.lon, c.lat],
    zoom: 12,
    interactive: false,
    attributionControl: false,
    trackResize: false,
    fadeDuration: 0,
    pixelRatio: Math.min(window.devicePixelRatio || 1, 2),
  })

  miniMap.once('load', async () => {
    miniMap.resize()

    const raw = resolveColor(routeData.value) || '4E4EC8'
    const routeColor = raw.startsWith('#') ? raw : `#${raw}`

    // Route line
    const geom = routeData.value?.geometry
    if (geom) {
      miniMap.addSource('route-line', {
        type: 'geojson',
        data: { type: 'Feature', geometry: geom, properties: {} },
      })
      miniMap.addLayer({
        id: 'route-line',
        type: 'line',
        source: 'route-line',
        paint: { 'line-color': routeColor, 'line-width': 3, 'line-opacity': 0.8 },
        layout: { 'line-cap': 'round', 'line-join': 'round' },
      })
    }

    // Stop circles
    const stops = routeData.value?.stops
    if (stops?.length) {
      miniMap.addSource('route-stops', {
        type: 'geojson',
        data: {
          type: 'FeatureCollection',
          features: stops.map((s: any) => ({
            type: 'Feature',
            geometry: { type: 'Point', coordinates: [s.lon, s.lat] },
            properties: {},
          })),
        },
      })
      miniMap.addLayer({
        id: 'route-stops',
        type: 'circle',
        source: 'route-stops',
        paint: {
          'circle-radius': 3,
          'circle-color': routeColor,
          'circle-stroke-width': 1,
          'circle-stroke-color': '#ffffff',
        },
      })

      // Fit bounds
      const bounds = new maplibregl.LngLatBounds()
      stops.forEach((s: any) => bounds.extend([s.lon, s.lat]))
      miniMap.fitBounds(bounds, { padding: 20, duration: 0 })
    }

    // Vehicle icons (direction 0 = route color bg, direction 1 = complementary bg)
    const iconName = _resolveTransitIcon(routeData.value?.route_type ?? 3)
    await _loadMiniMapIcon(miniMap, `mini-${iconName}`, `/img/transit/${iconName}.svg`, 32)
    miniMap.addSource('route-vehicles', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
    // Colored circle behind icon (direction indicator)
    miniMap.addLayer({
      id: 'route-vehicles-bg',
      type: 'circle',
      source: 'route-vehicles',
      paint: {
        'circle-radius': 8,
        'circle-color': ['case', ['==', ['get', 'dir'], 0], routeColor, _complementaryColor(routeColor)],
        'circle-stroke-width': 1.5,
        'circle-stroke-color': '#ffffff',
        'circle-opacity': 0.85,
      },
    })
    // Transit type icon on top
    miniMap.addLayer({
      id: 'route-vehicles-icon',
      type: 'symbol',
      source: 'route-vehicles',
      layout: {
        'icon-image': `mini-${iconName}`,
        'icon-size': 0.4,
        'icon-rotation-alignment': 'viewport',
        'icon-allow-overlap': true,
        'icon-ignore-placement': true,
      },
    })
    updateMiniMapVehicles()
  })
}

function _complementaryColor(hex: string): string {
  const h = hex.replace('#', '')
  const r = 255 - parseInt(h.substring(0, 2), 16)
  const g = 255 - parseInt(h.substring(2, 4), 16)
  const b = 255 - parseInt(h.substring(4, 6), 16)
  return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`
}

const _ROUTE_TYPE_ICON: Record<number, string> = {
  0: 'tram', 1: 'metro', 2: 'train', 3: 'bus', 4: 'ferry',
  7: 'train', 11: 'trolleybus', 200: '2bus', 1100: 'airplane', 1501: 'bus-taxi',
}
function _resolveTransitIcon(rt: number): string {
  if (_ROUTE_TYPE_ICON[rt]) return _ROUTE_TYPE_ICON[rt]
  if (rt >= 200 && rt <= 299) return '2bus'
  if (rt >= 900 && rt <= 999) return 'tram'
  if (rt >= 100 && rt <= 199) return 'train'
  if (rt >= 400 && rt <= 499) return 'metro'
  if (rt >= 700 && rt <= 799) return 'bus'
  return 'bus'
}

function _loadMiniMapIcon(map: any, id: string, url: string, size: number): Promise<void> {
  return new Promise(resolve => {
    if (map.hasImage(id)) { resolve(); return }
    const img = new Image(size, size)
    img.crossOrigin = 'anonymous'
    img.onload = () => {
      const canvas = document.createElement('canvas')
      canvas.width = size; canvas.height = size
      const ctx = canvas.getContext('2d')!
      ctx.drawImage(img, 0, 0, size, size)
      const data = ctx.getImageData(0, 0, size, size)
      map.addImage(id, { width: size, height: size, data: new Uint8Array(data.data.buffer) })
      resolve()
    }
    img.onerror = () => resolve()
    img.src = url
  })
}

function updateMiniMapVehicles() {
  if (!miniMap || !miniMap.getSource('route-vehicles')) return
  const geojson = {
    type: 'FeatureCollection' as const,
    features: liveVehicles.value.map((v: any) => ({
      type: 'Feature' as const,
      geometry: { type: 'Point' as const, coordinates: [v.lon, v.lat] },
      properties: { dir: v.d ?? 0 },
    })),
  }
  ;(miniMap.getSource('route-vehicles') as any).setData(geojson)
}

watch(liveVehicles, updateMiniMapVehicles)

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
