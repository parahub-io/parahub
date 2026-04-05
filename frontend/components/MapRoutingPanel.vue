<template>
  <div
    class="fixed bottom-0 left-0 right-0 w-full md:top-[calc(5rem+72px)] md:bottom-auto md:right-auto md:left-0 md:h-[calc(100vh-5rem-72px)] md:w-96 bg-white dark:bg-neutral-900 shadow-2xl z-50 flex flex-col rounded-t-2xl md:rounded-none"
    :style="isMobile ? sheetStyle : {}"
  >
    <!-- Mobile drag handle -->
    <div
      class="md:hidden flex justify-center pt-3 pb-2 touch-none cursor-grab flex-shrink-0"
      v-bind="dragHandleAttrs"
    >
      <div class="w-12 h-1 bg-neutral-300 dark:bg-neutral-600 rounded-full"></div>
    </div>

    <!-- Header -->
    <div class="p-4 border-b border-neutral-200 dark:border-neutral-700 flex items-center justify-between flex-shrink-0">
      <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
        <Navigation :size="20" />
        {{ $t('map.routing.title') }}
      </h2>
      <button
        @click="handleClose"
        class="p-2 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded-full transition"
      >
        <X :size="20" class="text-neutral-600 dark:text-neutral-400" />
      </button>
    </div>

    <!-- Mobile peek summary (visible when collapsed with a route) -->
    <div
      v-if="isMobile && (routeData || motisData)"
      class="md:hidden px-4 py-3 border-b border-neutral-200 dark:border-neutral-700 flex-shrink-0"
    >
      <div class="flex items-center justify-between gap-3">
        <div class="min-w-0">
          <p class="text-base font-semibold text-neutral-900 dark:text-neutral-100 truncate">
            <template v-if="routeData">
              {{ formatDistance(routeData.summary.length) }} &middot; {{ formatTime(routeData.summary.time) }}
            </template>
            <template v-else-if="currentItinerary">
              {{ formatTimeHHMM(currentItinerary.startTime) }} → {{ formatTimeHHMM(currentItinerary.endTime) }}
              &middot; {{ formatDuration(currentItinerary.duration) }}
            </template>
          </p>
          <p class="text-xs text-neutral-500 mt-0.5 truncate">
            <template v-if="routeData && routeData.legs?.[0]?.maneuvers?.[0]">
              {{ routeData.legs[0].maneuvers[0].instruction }}
            </template>
            <template v-else-if="currentItinerary?.legs?.[0]">
              {{ currentItinerary.legs[0].mode === 'WALK'
                ? $t('map.routing.walk_duration', { min: Math.ceil(currentItinerary.legs[0].duration / 60) })
                : (currentItinerary.legs[0].routeShortName || currentItinerary.legs[0].routeLongName || currentItinerary.legs[0].mode) }}
            </template>
          </p>
        </div>
        <button
          @click="snapTo('full')"
          class="flex-shrink-0 px-3 py-1.5 text-xs font-medium bg-primary text-neutral-900 rounded-full"
        >
          {{ $t('map.routing.show_steps') }}
        </button>
      </div>
    </div>

    <!-- Mode tabs -->
    <UiTabs v-model="costing" :tabs="routingTabs" full-width class="flex-shrink-0" />

    <!-- Departure time picker (multimodal only) -->
    <div v-if="costing === 'multimodal'" class="px-4 py-2 border-b border-neutral-200 dark:border-neutral-700 flex-shrink-0">
      <label class="flex items-center gap-2 text-sm text-neutral-600 dark:text-neutral-400">
        <Clock :size="16" />
        {{ $t('map.routing.depart_at') }}
      </label>
      <input
        type="datetime-local"
        v-model="departureTime"
        class="mt-1 w-full px-3 py-1.5 text-sm rounded-lg border border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
      />
    </div>

    <!-- Origin / Destination inputs -->
    <div class="p-4 flex gap-2 flex-shrink-0">
      <!-- Dots + swap column -->
      <div class="flex flex-col items-center pt-2.5 gap-0">
        <div class="w-3 h-3 rounded-full bg-green-500 border-2 border-white dark:border-neutral-900 shadow"></div>
        <div class="w-px h-6 bg-neutral-300 dark:bg-neutral-600"></div>
        <button
          @click="swapPoints"
          class="p-0.5 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded transition"
          :title="$t('map.routing.swap')"
        >
          <ArrowUpDown class="w-3.5 h-3.5 text-neutral-400" />
        </button>
        <div class="w-px h-6 bg-neutral-300 dark:bg-neutral-600"></div>
        <div class="w-3 h-3 rounded-full bg-red-500 border-2 border-white dark:border-neutral-900 shadow"></div>
      </div>

      <!-- Input fields -->
      <div class="flex-1 flex flex-col gap-2">
        <!-- Origin -->
        <div class="relative">
          <input
            ref="originInputRef"
            v-model="originQuery"
            @focus="handleInputFocus('origin')"
            @blur="handleInputBlur('origin')"
            @input="searchGeocode('origin'); originSelectedIdx = -1"
            @keydown.down.prevent="navigateResults('origin', 1)"
            @keydown.up.prevent="navigateResults('origin', -1)"
            @keydown.enter.prevent="confirmResult('origin')"
            :placeholder="$t('map.routing.origin_placeholder')"
            class="w-full px-3 py-2 text-sm rounded-lg border border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
          />
          <button
            v-if="!origin"
            @click="useMyLocation('origin')"
            class="absolute right-2 top-1/2 -translate-y-1/2 p-1 hover:bg-neutral-200 dark:hover:bg-neutral-700 rounded transition"
            :title="$t('map.routing.use_my_location')"
          >
            <LocateFixed class="w-3.5 h-3.5 text-neutral-400" />
          </button>
          <button
            v-else
            @click="clearPoint('origin')"
            class="absolute right-2 top-1/2 -translate-y-1/2 p-1 hover:bg-neutral-200 dark:hover:bg-neutral-700 rounded transition"
          >
            <X class="w-3.5 h-3.5 text-neutral-400" />
          </button>
          <!-- Autocomplete dropdown -->
          <div
            v-if="originFocused && originResults.length > 0"
            class="absolute top-full left-0 right-0 mt-1 bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg shadow-lg z-10 max-h-48 overflow-y-auto"
          >
            <button
              v-for="(r, i) in originResults"
              :key="r.id"
              @mousedown.prevent="selectResult('origin', r)"
              @mouseenter="originSelectedIdx = i; showPreviewMarker(r)"
              @mouseleave="originSelectedIdx = -1; hidePreviewMarker()"
              :class="['w-full px-3 py-2 text-left text-sm transition truncate', i === originSelectedIdx ? 'bg-primary-100 dark:bg-primary-900/40' : 'hover:bg-primary-100 dark:hover:bg-primary-900/40']"
            >
              {{ r.name }}
            </button>
          </div>
        </div>

        <!-- Destination -->
        <div class="relative">
          <input
            ref="destInputRef"
            v-model="destQuery"
            @focus="handleInputFocus('destination')"
            @blur="handleInputBlur('destination')"
            @input="searchGeocode('destination'); destSelectedIdx = -1"
            @keydown.down.prevent="navigateResults('destination', 1)"
            @keydown.up.prevent="navigateResults('destination', -1)"
            @keydown.enter.prevent="confirmResult('destination')"
            :placeholder="$t('map.routing.destination_placeholder')"
            class="w-full px-3 py-2 text-sm rounded-lg border border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
          />
          <button
            v-if="!destination"
            @click="useMyLocation('destination')"
            class="absolute right-2 top-1/2 -translate-y-1/2 p-1 hover:bg-neutral-200 dark:hover:bg-neutral-700 rounded transition"
            :title="$t('map.routing.use_my_location')"
          >
            <LocateFixed class="w-3.5 h-3.5 text-neutral-400" />
          </button>
          <button
            v-else
            @click="clearPoint('destination')"
            class="absolute right-2 top-1/2 -translate-y-1/2 p-1 hover:bg-neutral-200 dark:hover:bg-neutral-700 rounded transition"
          >
            <X class="w-3.5 h-3.5 text-neutral-400" />
          </button>
          <!-- Autocomplete dropdown -->
          <div
            v-if="destFocused && destResults.length > 0"
            class="absolute top-full left-0 right-0 mt-1 bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg shadow-lg z-10 max-h-48 overflow-y-auto"
          >
            <button
              v-for="(r, i) in destResults"
              :key="r.id"
              @mousedown.prevent="selectResult('destination', r)"
              @mouseenter="destSelectedIdx = i; showPreviewMarker(r)"
              @mouseleave="destSelectedIdx = -1; hidePreviewMarker()"
              :class="['w-full px-3 py-2 text-left text-sm transition truncate', i === destSelectedIdx ? 'bg-primary-100 dark:bg-primary-900/40' : 'hover:bg-primary-100 dark:hover:bg-primary-900/40']"
            >
              {{ r.name }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center py-6 flex-shrink-0">
      <div class="animate-spin w-5 h-5 border-2 border-secondary border-t-transparent rounded-full"></div>
      <span class="ml-2 text-sm text-neutral-500">{{ $t('map.routing.searching') }}</span>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="px-4 py-3 flex-shrink-0">
      <p class="text-sm text-red-500">{{ $t('map.routing.error') }}</p>
    </div>

    <!-- MOTIS transit results -->
    <template v-else-if="motisData">
      <!-- Itinerary selector (if multiple) -->
      <div v-if="motisData.itineraries.length > 1" class="px-4 py-2 border-b border-neutral-200 dark:border-neutral-700 flex-shrink-0">
        <div class="flex gap-2 overflow-x-auto pb-1">
          <button
            v-for="(it, idx) in motisData.itineraries"
            :key="idx"
            @click="selectItinerary(idx)"
            :class="[
              'flex-shrink-0 px-3 py-1.5 text-xs font-medium rounded-full border transition',
              idx === selectedItinerary
                ? 'bg-primary text-neutral-900 border-primary'
                : 'bg-neutral-50 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400 border-neutral-200 dark:border-neutral-700 hover:border-primary'
            ]"
          >
            {{ $t('map.routing.itinerary_n', { n: idx + 1 }) }}
            ({{ formatDuration(it.duration) }}<template v-if="it.transfers">, {{ $t('map.routing.transfers_count', it.transfers) }}</template><template v-else>, {{ $t('map.routing.direct_route') }}</template>)
          </button>
        </div>
      </div>

      <!-- Selected itinerary summary -->
      <div class="px-4 py-3 border-b border-neutral-200 dark:border-neutral-700 flex-shrink-0">
        <div class="flex items-center justify-between">
          <p class="text-base font-semibold text-neutral-900 dark:text-neutral-100">
            {{ formatTimeHHMM(currentItinerary.startTime) }} → {{ formatTimeHHMM(currentItinerary.endTime) }}
          </p>
          <p class="text-sm text-neutral-500">
            {{ formatDuration(currentItinerary.duration) }}
            <template v-if="currentItinerary.transfers">
              &middot; {{ $t('map.routing.transfers_count', currentItinerary.transfers) }}
            </template>
          </p>
        </div>
      </div>

      <!-- Legs list -->
      <div class="flex-1 overflow-y-auto min-h-0">
        <div
          v-for="(leg, li) in currentItinerary.legs"
          :key="li"
          class="border-b border-neutral-100 dark:border-neutral-800"
        >
          <!-- WALK leg -->
          <div v-if="leg.mode === 'WALK'" class="flex items-center gap-3 px-4 py-2.5 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors cursor-default"
            @mouseenter="showPreviewMarker({ lat: leg.from.lat, lon: leg.from.lon })"
            @mouseleave="hidePreviewMarker"
          >
            <Footprints class="w-4 h-4 text-neutral-400 flex-shrink-0" />
            <p class="text-sm text-neutral-600 dark:text-neutral-400">
              {{ $t('map.routing.walk_duration', { min: Math.ceil(leg.duration / 60) }) }}
              <span v-if="leg.distance" class="text-neutral-400">({{ formatDistanceM(leg.distance) }})</span>
            </p>
          </div>

          <!-- Transit leg (BUS, TRAM, RAIL, SUBWAY, FERRY) -->
          <div v-else class="px-4 py-3 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors cursor-default"
            @mouseenter="showPreviewMarker({ lat: leg.from.lat, lon: leg.from.lon })"
            @mouseleave="hidePreviewMarker"
          >
            <!-- Route badge + headsign -->
            <div class="flex items-center gap-2 flex-wrap">
              <component :is="transitModeIcon(leg.mode)" class="w-4 h-4 flex-shrink-0" :style="{ color: legColor(leg) }" />
              <span
                class="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold"
                :style="transitBadgeStyle(leg)"
              >
                {{ leg.routeShortName || leg.routeLongName || leg.mode }}
              </span>
              <span v-if="leg.headsign" class="text-xs text-neutral-500 dark:text-neutral-400">
                → {{ leg.headsign }}
              </span>
            </div>

            <!-- Agency -->
            <p v-if="leg.agencyName" class="text-xs text-neutral-400 mt-0.5">{{ leg.agencyName }}</p>

            <!-- Board / Alight -->
            <div class="mt-2 space-y-1.5">
              <div class="flex items-center gap-2 text-sm">
                <div class="w-2.5 h-2.5 rounded-full border-2 flex-shrink-0" :style="{ borderColor: legColor(leg) }"></div>
                <span class="tabular-nums font-medium text-neutral-900 dark:text-neutral-100">{{ formatTimeHHMM(leg.startTime) }}</span>
                <span class="text-neutral-700 dark:text-neutral-300 truncate">{{ leg.from.name }}</span>
              </div>

              <!-- Intermediate stops (expandable) -->
              <div v-if="leg.intermediateStops?.length" class="ml-1">
                <button
                  @click="toggleStops(li)"
                  class="flex items-center gap-1 text-xs text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300 transition"
                >
                  <ChevronDown :size="14" :class="['transition-transform', expandedLegs.includes(li) && 'rotate-180']" />
                  {{ $t('map.routing.intermediate_stops', leg.intermediateStops.length) }}
                </button>
                <div v-if="expandedLegs.includes(li)" class="mt-1 ml-2 border-l-2 pl-3 space-y-1" :style="{ borderColor: legColor(leg) }">
                  <div
                    v-for="(stop, si) in leg.intermediateStops"
                    :key="si"
                    class="flex items-center gap-2 text-xs"
                  >
                    <div class="w-1.5 h-1.5 rounded-full -ml-[13px] flex-shrink-0" :style="{ backgroundColor: legColor(leg) }"></div>
                    <span class="text-neutral-400 tabular-nums">{{ formatTimeHHMM(stop.arrival || stop.departure) }}</span>
                    <span class="text-neutral-600 dark:text-neutral-400 truncate">{{ stop.name }}</span>
                  </div>
                </div>
              </div>

              <div class="flex items-center gap-2 text-sm">
                <div class="w-2.5 h-2.5 rounded-full flex-shrink-0" :style="{ backgroundColor: legColor(leg) }"></div>
                <span class="tabular-nums font-medium text-neutral-900 dark:text-neutral-100">{{ formatTimeHHMM(leg.endTime) }}</span>
                <span class="text-neutral-700 dark:text-neutral-300 truncate">{{ leg.to.name }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- Valhalla route summary + maneuvers -->
    <template v-else-if="routeData">
      <!-- Summary -->
      <div class="px-4 py-3 border-b border-neutral-200 dark:border-neutral-700 flex-shrink-0">
        <p class="text-base font-semibold text-neutral-900 dark:text-neutral-100">
          {{ formatDistance(routeData.summary.length) }} &middot; {{ formatTime(routeData.summary.time) }}
        </p>
      </div>

      <!-- Maneuvers list -->
      <div class="flex-1 overflow-y-auto min-h-0">
        <template v-for="(leg, li) in routeData.legs" :key="li">
          <div
            v-for="(m, mi) in leg.maneuvers"
            :key="`${li}-${mi}`"
            class="flex items-start gap-3 px-4 py-2.5 border-b border-neutral-100 dark:border-neutral-800 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors cursor-default"
            @mouseenter="showManeuverMarker(m)"
            @mouseleave="hidePreviewMarker"
          >
            <component
              :is="maneuverIcon(m.type)"
              :class="[
                'w-4 h-4 mt-0.5 flex-shrink-0',
                isTransitManeuver(m.type) ? 'text-purple-500' : 'text-neutral-500 dark:text-neutral-400'
              ]"
            />
            <div class="flex-1 min-w-0">
              <p class="text-sm text-neutral-900 dark:text-neutral-100">{{ m.instruction }}</p>

              <!-- Transit route badge + headsign -->
              <div v-if="m.transit_info" class="mt-1 flex items-center gap-2 flex-wrap">
                <span
                  class="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold"
                  :style="valhallaTransitBadgeStyle(m.transit_info)"
                >
                  {{ m.transit_info.short_name || m.transit_info.long_name }}
                </span>
                <span v-if="m.transit_info.headsign" class="text-xs text-neutral-500 dark:text-neutral-400">
                  {{ $t('map.routing.towards') }} {{ m.transit_info.headsign }}
                </span>
              </div>

              <!-- Transit stops timeline -->
              <div v-if="m.transit_info?.transit_stops?.length" class="mt-2 ml-1 border-l-2 border-purple-200 dark:border-purple-800 pl-3 space-y-1.5">
                <div
                  v-for="(stop, si) in m.transit_info.transit_stops"
                  :key="si"
                  class="flex items-center gap-2 text-xs"
                >
                  <div class="w-2 h-2 rounded-full bg-purple-400 -ml-[17px] flex-shrink-0"></div>
                  <span class="text-neutral-500 dark:text-neutral-400 tabular-nums">
                    {{ formatStopTime(stop.departure_date_time || stop.arrival_date_time) }}
                  </span>
                  <span class="text-neutral-700 dark:text-neutral-300 truncate">{{ stop.name }}</span>
                </div>
              </div>

              <!-- Distance/time for non-transit maneuvers -->
              <p v-if="!m.transit_info" class="text-xs text-neutral-400 mt-0.5">
                {{ formatDistance(m.length) }} &middot; {{ formatTime(m.time) }}
              </p>
            </div>
          </div>
        </template>
      </div>
    </template>

    <!-- Empty state (no route yet) -->
    <div v-else class="flex-1 flex items-center justify-center px-4">
      <p class="text-sm text-neutral-400 text-center">
        {{ $t('map.routing.origin_placeholder') }}
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import {
  Navigation, X, ArrowUpDown, LocateFixed,
  Car, Footprints, Bike, Bus, Clock, TrainFront, TramFront, Ship,
  ArrowUp, ArrowUpRight, ArrowUpLeft, ArrowRight, ArrowLeft,
  CornerRightDown, CornerLeftDown, MapPin, MoveRight, ArrowRightLeft,
  ChevronDown,
} from 'lucide-vue-next'
import { useRouting } from '~/composables/useRouting'
import { useBottomSheet } from '~/composables/useBottomSheet'

const { t } = useI18n()
const mapStore = useMapStore()

// Mobile bottom sheet
const isMobile = ref(false)
const checkMobile = () => { isMobile.value = window.innerWidth < 768 }
onMounted(() => { checkMobile(); window.addEventListener('resize', checkMobile) })
onUnmounted(() => { window.removeEventListener('resize', checkMobile) })

const {
  origin, destination, costing, departureTime,
  routeData, motisData, selectedItinerary,
  routeGeoJSON, routeBounds, decodedShapeCoords,
  loading, error,
  awaitingMapClick,
  swapPoints, clearRoute, selectItinerary,
} = useRouting()

const emit = defineEmits<{
  close: []
  'route-ready': [geojson: any, bounds: any]
  'route-cleared': []
}>()

const { sheetStyle, dragHandleAttrs, snapTo } = useBottomSheet({
  initialSnap: 'half',
  onDismiss: () => handleClose()
})

// Expanded intermediate stops
const expandedLegs = ref<number[]>([])

const toggleStops = (legIdx: number) => {
  const i = expandedLegs.value.indexOf(legIdx)
  if (i >= 0) expandedLegs.value.splice(i, 1)
  else expandedLegs.value.push(legIdx)
}

// Current MOTIS itinerary
const currentItinerary = computed(() => {
  if (!motisData.value) return null
  return motisData.value.itineraries[selectedItinerary.value] || motisData.value.itineraries[0]
})

// Mode tabs
const modes = [
  { value: 'auto' as const, icon: Car, label: 'map.routing.auto' },
  { value: 'pedestrian' as const, icon: Footprints, label: 'map.routing.pedestrian' },
  { value: 'bicycle' as const, icon: Bike, label: 'map.routing.bicycle' },
  { value: 'multimodal' as const, icon: Bus, label: 'map.routing.transit' },
]

const routingTabs = computed(() => modes.map(m => ({
  id: m.value,
  label: t(m.label),
  icon: m.icon,
})))

// Geocode search state
const originQuery = ref(origin.value?.name || '')
const destQuery = ref(destination.value?.name || '')
const originResults = ref<any[]>([])
const destResults = ref<any[]>([])
const originFocused = ref(false)
const destFocused = ref(false)
const originSelectedIdx = ref(-1)
const destSelectedIdx = ref(-1)
const originInputRef = ref<HTMLInputElement | null>(null)
const destInputRef = ref<HTMLInputElement | null>(null)
let searchTimer: ReturnType<typeof setTimeout> | null = null

// Geocode search (debounced 300ms)
const searchGeocode = (which: 'origin' | 'destination') => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(async () => {
    const q = which === 'origin' ? originQuery.value : destQuery.value
    if (!q || q.length < 2) {
      if (which === 'origin') originResults.value = []
      else destResults.value = []
      return
    }

    try {
      const mapCenter = mapStore.mapInstance?.getCenter()
      const focusLat = mapCenter?.lat || 38.7
      const focusLon = mapCenter?.lng || -9.14
      const data = await $fetch<any>(`/api/v1/geo/geocode/search?q=${encodeURIComponent(q)}&limit=5&lang=en&focus_lat=${focusLat}&focus_lon=${focusLon}`)
      const results = (data?.features || []).map((f: any) => ({
        id: f.properties?.id || f.properties?.gid || Math.random(),
        name: f.properties?.label || f.properties?.name || 'Unknown',
        lat: f.geometry?.coordinates?.[1],
        lon: f.geometry?.coordinates?.[0],
      }))
      if (which === 'origin') originResults.value = results
      else destResults.value = results
    } catch (e) {
      console.warn('[MapRoutingPanel] Geocode search failed:', e)
    }
  }, 300)
}

const navigateResults = (which: 'origin' | 'destination', dir: number) => {
  const results = which === 'origin' ? originResults.value : destResults.value
  const idxRef = which === 'origin' ? originSelectedIdx : destSelectedIdx
  if (!results.length) return
  let next = idxRef.value + dir
  if (next < 0) next = results.length - 1
  if (next >= results.length) next = 0
  idxRef.value = next
  showPreviewMarker(results[next])
}

const confirmResult = (which: 'origin' | 'destination') => {
  const results = which === 'origin' ? originResults.value : destResults.value
  const idx = which === 'origin' ? originSelectedIdx.value : destSelectedIdx.value
  const r = idx >= 0 ? results[idx] : results[0]
  if (r) selectResult(which, r)
}

const selectResult = (which: 'origin' | 'destination', r: any) => {
  hidePreviewMarker()
  const point = { lat: r.lat, lon: r.lon, name: r.name }
  if (which === 'origin') {
    origin.value = point
    originQuery.value = r.name
    originResults.value = []
    originFocused.value = false
  } else {
    destination.value = point
    destQuery.value = r.name
    destResults.value = []
    destFocused.value = false
  }
  awaitingMapClick.value = null
}

const handleInputFocus = (which: 'origin' | 'destination') => {
  if (which === 'origin') {
    originFocused.value = true
    if (!origin.value) awaitingMapClick.value = 'origin'
  } else {
    destFocused.value = true
    if (!destination.value) awaitingMapClick.value = 'destination'
  }
}

const handleInputBlur = (which: 'origin' | 'destination') => {
  setTimeout(() => {
    if (which === 'origin') originFocused.value = false
    else destFocused.value = false
  }, 200)
}

const clearPoint = (which: 'origin' | 'destination') => {
  if (which === 'origin') {
    origin.value = null
    originQuery.value = ''
    originResults.value = []
  } else {
    destination.value = null
    destQuery.value = ''
    destResults.value = []
  }
  emit('route-cleared')
}

const useMyLocation = (which: 'origin' | 'destination') => {
  const loc = mapStore.userLocation
  if (!loc) {
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          const point = {
            lat: pos.coords.latitude,
            lon: pos.coords.longitude,
            name: t('map.routing.use_my_location'),
          }
          if (which === 'origin') {
            origin.value = point
            originQuery.value = point.name
          } else {
            destination.value = point
            destQuery.value = point.name
          }
        },
        () => console.warn('[MapRoutingPanel] Geolocation denied'),
        { enableHighAccuracy: true, timeout: 5000 }
      )
    }
    return
  }
  const point = {
    lat: loc[1],
    lon: loc[0],
    name: t('map.routing.use_my_location'),
  }
  if (which === 'origin') {
    origin.value = point
    originQuery.value = point.name
  } else {
    destination.value = point
    destQuery.value = point.name
  }
}

// Watch for route results → emit to parent + snap to peek on mobile
watch(routeGeoJSON, (geojson) => {
  if (geojson && routeBounds.value) {
    emit('route-ready', geojson, routeBounds.value)
    if (isMobile.value) snapTo('peek')
  }
})

// Reset expanded stops when itinerary changes
watch(selectedItinerary, () => {
  expandedLegs.value = []
})

// Sync input text when origin/destination change externally (e.g. map click)
watch(origin, (val) => {
  if (val) originQuery.value = val.name
  else originQuery.value = ''
})
watch(destination, (val) => {
  if (val) destQuery.value = val.name
  else destQuery.value = ''
})

const handleClose = () => {
  clearRoute()
  emit('route-cleared')
  emit('close')
}

// Format helpers
const formatDistance = (km: number): string => {
  if (km < 1) return `${Math.round(km * 1000)} ${t('map.routing.m')}`
  return `${km.toFixed(1)} ${t('map.routing.km')}`
}

const formatDistanceM = (meters: number): string => {
  if (meters >= 1000) return `${(meters / 1000).toFixed(1)} ${t('map.routing.km')}`
  return `${Math.round(meters)} ${t('map.routing.m')}`
}

const formatTime = (seconds: number): string => {
  const h = Math.floor(seconds / 3600)
  const m = Math.round((seconds % 3600) / 60)
  if (h > 0) return `${h} ${t('map.routing.hours')} ${m} ${t('map.routing.minutes')}`
  return `${m} ${t('map.routing.minutes')}`
}

const formatDuration = (seconds: number): string => {
  const h = Math.floor(seconds / 3600)
  const m = Math.round((seconds % 3600) / 60)
  if (h > 0) return `${h}${t('map.routing.hours')} ${m}${t('map.routing.minutes')}`
  return `${m} ${t('map.routing.minutes')}`
}

/** Format ISO datetime → HH:MM */
const formatTimeHHMM = (dt?: string) => {
  if (!dt) return ''
  try {
    const d = new Date(dt)
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
  } catch {
    const match = dt.match(/(\d{2}):(\d{2})/)
    return match ? `${match[1]}:${match[2]}` : dt
  }
}

// Transit maneuver detection (Valhalla types 30-36)
const isTransitManeuver = (type: number) => type >= 30 && type <= 36

// Valhalla transit route badge styling from GTFS colors
const valhallaTransitBadgeStyle = (info: any) => {
  const bg = info.color != null ? `#${info.color.toString(16).padStart(6, '0')}` : '#8b5cf6'
  const text = info.text_color != null ? `#${info.text_color.toString(16).padStart(6, '0')}` : '#ffffff'
  return { backgroundColor: bg, color: text }
}

// MOTIS transit leg badge styling
const transitBadgeStyle = (leg: any) => {
  const bg = leg.routeColor ? `#${leg.routeColor.replace(/^#/, '')}` : '#8b5cf6'
  const text = leg.routeTextColor ? `#${leg.routeTextColor.replace(/^#/, '')}` : '#ffffff'
  return { backgroundColor: bg, color: text }
}

const legColor = (leg: any): string => {
  if (leg.routeColor) return `#${leg.routeColor.replace(/^#/, '')}`
  const modeColors: Record<string, string> = { BUS: '#ef4444', TRAM: '#22c55e', SUBWAY: '#8b5cf6', RAIL: '#3b82f6', FERRY: '#06b6d4' }
  return modeColors[leg.mode] || '#8b5cf6'
}

const transitModeIcon = (mode: string) => {
  switch (mode) {
    case 'BUS': return Bus
    case 'TRAM': return TramFront
    case 'RAIL': case 'SUBWAY': return TrainFront
    case 'FERRY': return Ship
    default: return Bus
  }
}

// Format stop time from ISO datetime string → HH:MM
const formatStopTime = (dt?: string) => {
  if (!dt) return ''
  const match = dt.match(/(\d{2}):(\d{2})/)
  return match ? `${match[1]}:${match[2]}` : dt
}

// Maneuver type → icon
const maneuverIcon = (type: number) => {
  switch (type) {
    case 0: case 1: case 2: case 3: case 9: case 24: case 25: case 26:
      return ArrowUp
    case 4:
      return MapPin
    case 5: case 20:
      return ArrowUpRight
    case 6: case 21:
      return ArrowUpLeft
    case 7: case 10: case 15:
      return ArrowRight
    case 8: case 11: case 16:
      return ArrowLeft
    case 12:
      return CornerRightDown
    case 13:
      return CornerLeftDown
    case 17: case 18: case 19:
      return MoveRight
    case 30: case 32:
      return Bus
    case 31:
      return ArrowRightLeft
    case 33: case 34:
      return Footprints
    case 35: case 36:
      return MapPin
    default:
      return ArrowUp
  }
}

// Preview marker on hover
let previewMarker: any = null

const showPreviewMarker = async (r: any) => {
  hidePreviewMarker()
  if (!r.lat || !r.lon || !mapStore.mapInstance) return
  const maplibregl = await import('maplibre-gl').then(m => m.default || m)
  const { createLockOnElement } = await import('~/utils/lockOnMarker')
  previewMarker = new maplibregl.Marker({ element: createLockOnElement(), anchor: 'center' }).setLngLat([r.lon, r.lat]).addTo(mapStore.mapInstance)
}

const showManeuverMarker = (m: any) => {
  if (m.begin_shape_index == null || !decodedShapeCoords.value.length) return
  const coord = decodedShapeCoords.value[m.begin_shape_index]
  if (!coord) return
  showPreviewMarker({ lon: coord[0], lat: coord[1] })
}

const hidePreviewMarker = () => {
  if (previewMarker) { previewMarker.remove(); previewMarker = null }
}

onUnmounted(() => {
  if (searchTimer) clearTimeout(searchTimer)
  hidePreviewMarker()
})
</script>

<style>
/* Geocode preview marker (unscoped — added to map DOM dynamically) */
.geocode-preview-marker {
  width: 80px;
  height: 80px;
  pointer-events: none;
}
.geocode-preview-container {
  position: relative;
  width: 100%;
  height: 100%;
}
.geocode-preview-dot {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 8px;
  height: 8px;
  background: #f4c110;
  border-radius: 50%;
  transform: translate(-50%, -50%);
  z-index: 4;
  box-shadow: 0 0 8px rgba(244, 193, 16, 0.6);
}
.geocode-preview-bracket {
  position: absolute;
  top: 50%;
  left: 50%;
  color: #f4c110;
  opacity: 0;
}
.geocode-preview-b1 {
  animation: geocode-lock-in 0.5s 0s cubic-bezier(0, 0.55, 0.45, 1) forwards,
             geocode-lock-spin 12s 0.5s linear infinite;
}
@keyframes geocode-lock-in {
  0% {
    width: 400px;
    height: 400px;
    transform: translate(-50%, -50%);
    opacity: 0.3;
  }
  60% { opacity: 1; }
  100% {
    width: 36px;
    height: 36px;
    transform: translate(-50%, -50%);
    opacity: 1;
  }
}
@keyframes geocode-lock-spin {
  from {
    width: 36px;
    height: 36px;
    transform: translate(-50%, -50%) rotate(0deg);
    opacity: 1;
  }
  to {
    width: 36px;
    height: 36px;
    transform: translate(-50%, -50%) rotate(360deg);
    opacity: 1;
  }
}
/* Lock-on crosshair flash lines */
.lockon-crosshair {
  position: absolute;
  background: #f4c110;
  opacity: 0.5;
  pointer-events: none;
  z-index: 1;
  transition: opacity 1s cubic-bezier(0, 0, 0.2, 1);
}
.lockon-crosshair-fade {
  opacity: 0;
}
</style>
