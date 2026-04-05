<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" @click.self="$emit('close')">
    <div class="bg-white dark:bg-neutral-800 rounded-xl shadow-2xl w-full max-w-lg p-6">
      <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-2">
        {{ $t('mesh.set_location') }}
      </h3>
      <p class="text-sm text-neutral-500 dark:text-neutral-400 mb-2">
        {{ $t('mesh.click_map') }}
      </p>

      <!-- Quick fly-to properties -->
      <div v-if="propertiesWithCoords.length" class="flex flex-wrap gap-1.5 mb-3">
        <button
          v-for="prop in propertiesWithCoords" :key="prop.id"
          type="button"
          @click="flyToProperty(prop)"
          class="inline-flex items-center gap-1 px-2 py-1 rounded text-xs border border-neutral-200 dark:border-neutral-600 text-neutral-600 dark:text-neutral-300 hover:bg-primary-50 dark:hover:bg-primary-900/20 hover:border-primary transition-colors"
        >
          <Home class="w-3 h-3" />
          {{ prop.name }}
        </button>
      </div>

      <!-- Map container -->
      <div ref="mapContainer" class="w-full h-64 rounded-lg overflow-hidden border border-neutral-200 dark:border-neutral-600 mb-4" />

      <!-- Coordinates display -->
      <div v-if="selectedLat !== null" class="mb-4 text-sm text-neutral-700 dark:text-neutral-300 font-mono">
        {{ selectedLat.toFixed(6) }}, {{ selectedLng!.toFixed(6) }}
      </div>
      <div v-else class="mb-4 text-sm text-neutral-400">
        {{ $t('mesh.no_location') }}
      </div>

      <!-- Actions -->
      <div class="flex justify-end gap-3">
        <button
          @click="$emit('close')"
          class="px-4 py-2 text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded-lg"
          :disabled="saving"
        >
          {{ $t('mesh.cancel') }}
        </button>
        <button
          @click="handleSave"
          :disabled="saving || selectedLat === null"
          class="btn-secondary btn-sm flex items-center gap-2"
        >
          <Loader2 v-if="saving" class="w-4 h-4 animate-spin" />
          {{ $t('mesh.save') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Loader2, Home } from 'lucide-vue-next'

interface Props {
  deviceId: string
  initialLat?: number
  initialLng?: number
}

interface Emits {
  (e: 'close'): void
  (e: 'saved', lat: number, lng: number): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()
const store = useIoTStore()
const propertyStore = usePropertyStore()
const colorMode = useColorMode()

const mapContainer = ref<HTMLElement | null>(null)
const selectedLat = ref<number | null>(props.initialLat ?? null)
const selectedLng = ref<number | null>(props.initialLng ?? null)
const saving = ref(false)

const propertiesWithCoords = computed(() =>
  propertyStore.properties.filter(p => p.latitude && p.longitude)
)

let map: any = null
let marker: any = null

const flyToProperty = (prop: { latitude: number; longitude: number }) => {
  if (map) {
    map.flyTo({ center: [prop.longitude, prop.latitude], zoom: 17, essential: true, speed: 4.5 })
  }
}

const getStyleUrl = () =>
  colorMode.value === 'dark'
    ? '/map-styles/dark-liberty-parahub.json'
    : '/map-styles/liberty-parahub.json'

onMounted(async () => {
  if (!mapContainer.value) return

  const mod = await import('maplibre-gl')
  const maplibregl = mod.default || mod
  await import('maplibre-gl/dist/maplibre-gl.css')

  const { mapCenter, mapZoom } = useMapState()
  const center: [number, number] = props.initialLng && props.initialLat
    ? [props.initialLng, props.initialLat]
    : mapCenter.value

  const zoom = props.initialLat ? 15 : mapZoom.value

  map = new maplibregl.Map({
    container: mapContainer.value,
    style: getStyleUrl(),
    center,
    zoom,
    attributionControl: false,
    fadeDuration: 0,
  })

  map.once('load', () => {
    map.resize()
  })

  // Place initial marker if coordinates exist
  if (props.initialLat && props.initialLng) {
    marker = new maplibregl.Marker({ color: '#ef4444' })
      .setLngLat([props.initialLng, props.initialLat])
      .addTo(map)
  }

  // Click to place marker
  map.on('click', (e: any) => {
    const { lng, lat } = e.lngLat
    selectedLat.value = lat
    selectedLng.value = lng

    if (marker) {
      marker.setLngLat([lng, lat])
    } else {
      marker = new maplibregl.Marker({ color: '#ef4444' })
        .setLngLat([lng, lat])
        .addTo(map)
    }
  })
})

onUnmounted(() => {
  if (map) {
    map.remove()
    map = null
  }
})

const handleSave = async () => {
  if (selectedLat.value === null || selectedLng.value === null || saving.value) return
  saving.value = true

  try {
    await store.setDeviceLocation(props.deviceId, selectedLat.value, selectedLng.value)
    emit('saved', selectedLat.value, selectedLng.value)
    emit('close')
  } catch (err: any) {
    console.error('Failed to save location:', err)
  } finally {
    saving.value = false
  }
}
</script>
