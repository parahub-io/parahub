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
      v-if="showDropdown && !loading && query.length >= 2 && filteredStops.length === 0 && stops.length > 0"
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
const stops = ref<StopItem[]>([])
const loading = ref(false)
const showDropdown = ref(false)
let debounceTimer: ReturnType<typeof setTimeout> | null = null

const filteredStops = computed(() => {
  if (!query.value || query.value.length < 2) return stops.value.slice(0, 20)
  const q = query.value.toLowerCase()
  return stops.value.filter(s => s.name.toLowerCase().includes(q)).slice(0, 20)
})

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
