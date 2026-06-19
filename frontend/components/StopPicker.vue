<template>
  <div class="relative">
    <input
      ref="inputRef"
      v-model="query"
      type="text"
      :placeholder="placeholder || $t('rides.stop_picker.placeholder')"
      class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
      @focus="showDropdown = true"
      @input="onInput"
      @keydown.escape="showDropdown = false"
    />
    <!-- Selected stop indicator -->
    <div v-if="modelValue && !showDropdown" class="absolute right-2 top-1/2 -translate-y-1/2">
      <button @click="clear" class="text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300">
        <X class="w-4 h-4" />
      </button>
    </div>
    <!-- Loading -->
    <div v-if="loading" class="absolute right-2 top-1/2 -translate-y-1/2">
      <div class="w-4 h-4 border-2 border-secondary border-t-transparent rounded-full animate-spin"></div>
    </div>

    <!-- Dropdown -->
    <div
      v-if="showDropdown && filteredStops.length > 0"
      class="absolute z-50 w-full mt-1 bg-white dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-600 rounded-lg shadow-lg max-h-60 overflow-y-auto"
    >
      <button
        v-for="stop in filteredStops"
        :key="stop.id"
        type="button"
        class="w-full text-left px-3 py-2 hover:bg-secondary-50 dark:hover:bg-secondary-900/30 border-b border-neutral-100 dark:border-neutral-700 last:border-b-0"
        @click="selectStop(stop)"
      >
        <div class="font-medium text-sm text-neutral-900 dark:text-neutral-100">{{ stop.name }}</div>
        <div v-if="stop.routes" class="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
          {{ stop.routes }}
        </div>
      </button>
    </div>

    <!-- No results -->
    <div
      v-if="showDropdown && !loading && query.length >= 2 && filteredStops.length === 0"
      class="absolute z-50 w-full mt-1 bg-white dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-600 rounded-lg shadow-lg p-3 text-sm text-neutral-500"
    >
      {{ $t('rides.stop_picker.no_results') }}
    </div>

    <!-- Click outside handler -->
    <div v-if="showDropdown" class="fixed inset-0 z-40" @click="showDropdown = false"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { X } from 'lucide-vue-next'

interface StopItem {
  id: string
  name: string
  lat: number
  lon: number
  routes?: string
}

const props = defineProps<{
  modelValue: StopItem | null
  placeholder?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: StopItem | null]
}>()

const inputRef = ref<HTMLInputElement | null>(null)
const query = ref('')
const stops = ref<StopItem[]>([])      // nearby suggestions (initial load, GPS / map centre)
const results = ref<StopItem[]>([])    // server-side name search results (city-scoped)
const loading = ref(false)
const showDropdown = ref(false)
let debounceTimer: ReturnType<typeof setTimeout> | null = null

// < 2 chars → nearby suggestions; otherwise server-side search results (loaded in onInput).
// The old code only substring-filtered the one-shot nearby set, so any stop outside the
// initial GPS/map-centre radius (e.g. a Lisbon stop while the map sat on Prague) was
// unfindable. Name search now hits the API, scoped to the selected transit city.
const filteredStops = computed(() =>
  query.value.length >= 2 ? results.value : stops.value.slice(0, 20)
)

// Load nearby stops on mount based on geolocation
onMounted(() => {
  loadNearbyStops()
})

// If modelValue is set externally, reflect in input
watch(() => props.modelValue, (val) => {
  if (val) {
    query.value = val.name
  }
}, { immediate: true })

async function loadNearbyStops(lat?: number, lon?: number) {
  if (lat !== undefined && lon !== undefined) {
    await fetchStops(lat, lon)
    return
  }

  // Try geolocation
  if (typeof navigator !== 'undefined' && navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
      (pos) => fetchStops(pos.coords.latitude, pos.coords.longitude),
      () => fetchStopsFromMapCenter(),
      { timeout: 5000 }
    )
  } else {
    fetchStopsFromMapCenter()
  }
}

async function fetchStopsFromMapCenter() {
  // Fallback: use map center if available
  try {
    const mapStore = useMapStore()
    if (mapStore.center) {
      await fetchStops(mapStore.center[1], mapStore.center[0])
    }
  } catch {
    // No map store available
  }
}

async function fetchStops(lat: number, lon: number) {
  loading.value = true
  try {
    const data = await $fetch<any>(`/api/v1/geo/transit/stops/nearby/`, {
      params: { lat, lon, r: 5000 }
    })
    if (data?.features) {
      const raw: StopItem[] = data.features.map((f: any) => ({
        id: f.properties.id,
        name: f.properties.name,
        lat: f.geometry.coordinates[1],
        lon: f.geometry.coordinates[0],
        routes: f.properties.route_names?.join(', ') || '',
      }))
      // Deduplicate stops with same name (different agencies) — merge routes
      const byName = new Map<string, StopItem>()
      for (const stop of raw) {
        const existing = byName.get(stop.name)
        if (existing) {
          if (stop.routes) {
            const merged = new Set(existing.routes ? existing.routes.split(', ') : [])
            for (const r of stop.routes.split(', ')) merged.add(r)
            existing.routes = [...merged].join(', ')
          }
        } else {
          byName.set(stop.name, { ...stop })
        }
      }
      stops.value = [...byName.values()]
    }
  } catch (err) {
    console.error('Failed to load stops:', err)
  } finally {
    loading.value = false
  }
}

function onInput() {
  showDropdown.value = true
  const q = query.value.trim()
  if (debounceTimer) clearTimeout(debounceTimer)
  if (q.length < 2) {
    results.value = []
    loading.value = false
    return
  }
  loading.value = true
  debounceTimer = setTimeout(() => searchStops(q), 250)
}

// Server-side name search. Scoped to the selected transit city (same `transit_city` key the
// transit page uses; a region scope descends to its cities, so a metro-area selection covers
// suburban stops). Falls back to a global search when the city-scoped query is empty — the
// rides page has no city picker of its own, so a stale/foreign selected city must never
// dead-end a valid stop. No city set → global from the start.
async function searchStops(q: string) {
  loading.value = true
  try {
    const city = typeof localStorage !== 'undefined' ? localStorage.getItem('transit_city') : null
    let found = await fetchSearch(q, city)
    if (city && found.length === 0) {
      found = await fetchSearch(q, null) // stop isn't in the selected city — search everywhere
    }
    // Drop a stale response if the user kept typing while we awaited.
    if (q === query.value.trim()) results.value = found
  } catch (err) {
    console.error('Stop search failed:', err)
    results.value = []
  } finally {
    loading.value = false
  }
}

async function fetchSearch(q: string, city: string | null): Promise<StopItem[]> {
  const params: Record<string, string> = { q }
  if (city) params.city = city
  const data = await $fetch<any>('/api/v1/geo/transit/search/', { params })
  return (data?.stops || []).map((s: any) => ({
    id: s.id,
    name: s.name,
    lat: s.lat,
    lon: s.lon,
    routes: Array.isArray(s.routes)
      ? s.routes.map((r: any) => (typeof r === 'string' ? r : r.short_name)).filter(Boolean).join(', ')
      : '',
  }))
}

function selectStop(stop: StopItem) {
  query.value = stop.name
  showDropdown.value = false
  emit('update:modelValue', stop)
}

function clear() {
  query.value = ''
  emit('update:modelValue', null)
  inputRef.value?.focus()
}
</script>
