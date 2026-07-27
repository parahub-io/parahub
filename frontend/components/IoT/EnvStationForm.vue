<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" @click.self="$emit('close')">
    <div class="bg-white dark:bg-neutral-800 rounded-xl shadow-2xl w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto">
      <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4">
        {{ $t('map.env.add_station') }}
      </h3>

      <!-- Name -->
      <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ $t('map.env.name') }}</label>
      <input v-model="name" type="text" :placeholder="$t('map.env.name_placeholder')"
             class="w-full mb-4 px-3 py-2 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100" />

      <!-- Type -->
      <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ $t('map.env.type') }}</label>
      <div class="grid grid-cols-3 gap-2 mb-4">
        <button v-for="opt in sourceOptions" :key="opt.value" type="button"
                @click="source = opt.value"
                class="px-2 py-2 rounded-lg border text-sm transition-colors"
                :class="source === opt.value
                  ? 'border-primary bg-primary-50 dark:bg-primary-900/20 text-neutral-900 dark:text-neutral-100'
                  : 'border-neutral-300 dark:border-neutral-600 text-neutral-600 dark:text-neutral-300 hover:border-primary'">
          {{ opt.label }}
        </button>
      </div>

      <!-- Serial (AirGradient) -->
      <div v-if="source === 'AIRGRADIENT'" class="mb-4">
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ $t('map.env.serial') }}</label>
        <input v-model="externalId" type="text" placeholder="d83bda1ac64c"
               class="w-full px-3 py-2 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 font-mono text-sm" />
        <p class="text-xs text-neutral-400 mt-1">{{ $t('map.env.serial_hint') }}</p>
      </div>

      <!-- Public -->
      <label class="flex items-center gap-2 mb-4 text-sm text-neutral-700 dark:text-neutral-300 cursor-pointer">
        <input v-model="isPublic" type="checkbox" class="rounded border-neutral-300 dark:border-neutral-600" />
        {{ $t('map.env.public_toggle') }}
      </label>

      <!-- Location -->
      <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ $t('map.env.location') }}</label>
      <p class="text-xs text-neutral-400 mb-2">{{ $t('map.env.click_map') }}</p>
      <div v-if="propertiesWithCoords.length" class="flex flex-wrap gap-1.5 mb-2">
        <button v-for="prop in propertiesWithCoords" :key="prop.id" type="button"
                @click="flyToProperty(prop)"
                class="inline-flex items-center gap-1 px-2 py-1 rounded text-xs border border-neutral-200 dark:border-neutral-600 text-neutral-600 dark:text-neutral-300 hover:border-primary">
          <Home class="w-3 h-3" /> {{ prop.name }}
        </button>
      </div>
      <div ref="mapContainer" class="w-full h-56 rounded-lg overflow-hidden border border-neutral-200 dark:border-neutral-600 mb-2" />
      <div class="mb-4 text-sm font-mono" :class="selectedLat !== null ? 'text-neutral-700 dark:text-neutral-300' : 'text-neutral-400'">
        {{ selectedLat !== null ? `${selectedLat.toFixed(6)}, ${selectedLng!.toFixed(6)}` : $t('mesh.no_location') }}
      </div>

      <p v-if="error" class="text-sm text-red-500 mb-3">{{ error }}</p>

      <!-- Actions -->
      <div class="flex justify-end gap-3">
        <button @click="$emit('close')" :disabled="saving"
                class="px-4 py-2 text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded-lg">
          {{ $t('mesh.cancel') }}
        </button>
        <button @click="handleCreate" :disabled="saving || !canSubmit"
                class="btn-secondary btn-sm flex items-center gap-2">
          <Loader2 v-if="saving" class="w-4 h-4 animate-spin" />
          {{ $t('map.env.create') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { Loader2, Home } from 'lucide-vue-next'
import type { EnvSource } from '~/stores/env'

const emit = defineEmits<{ (e: 'close'): void; (e: 'created'): void }>()

const { t: $t } = useI18n()
const envStore = useEnvStore()
const propertyStore = usePropertyStore()
const colorMode = useColorMode()

const mapContainer = ref<HTMLElement | null>(null)
const name = ref('')
const source = ref<EnvSource>('AIRGRADIENT')
const externalId = ref('')
const isPublic = ref(true)
const selectedLat = ref<number | null>(null)
const selectedLng = ref<number | null>(null)
const saving = ref(false)
const error = ref('')

const sourceOptions: Array<{ value: EnvSource; label: string }> = [
  { value: 'AIRGRADIENT', label: 'AirGradient' },
  { value: 'ECOWITT', label: 'Ecowitt' },
  { value: 'GENERIC', label: $t('map.env.generic') },
]

const propertiesWithCoords = computed(() =>
  propertyStore.properties.filter(p => p.latitude && p.longitude)
)

const canSubmit = computed(() => name.value.trim().length > 0 && selectedLat.value !== null)

let map: any = null
let marker: any = null

const getStyleUrl = () =>
  colorMode.value === 'dark'
    ? '/map-styles/dark-liberty-parahub.json'
    : '/map-styles/liberty-parahub.json'

const placeMarker = async (lng: number, lat: number) => {
  selectedLat.value = lat
  selectedLng.value = lng
  if (!map) return
  if (marker) {
    marker.setLngLat([lng, lat])
  } else {
    const mod = await import('maplibre-gl')
    const maplibregl = mod.default || mod
    marker = new maplibregl.Marker({ color: '#ef4444' }).setLngLat([lng, lat]).addTo(map)
  }
}

const flyToProperty = (prop: { latitude: number; longitude: number }) => {
  if (map) map.flyTo({ center: [prop.longitude, prop.latitude], zoom: 17, essential: true, speed: 4.5 })
  placeMarker(prop.longitude, prop.latitude)
}

onMounted(async () => {
  if (!mapContainer.value) return
  const mod = await import('maplibre-gl')
  const maplibregl = mod.default || mod
  await import('maplibre-gl/dist/maplibre-gl.css')

  const { mapCenter, mapZoom } = useMapState()
  map = new maplibregl.Map({
    container: mapContainer.value,
    style: getStyleUrl(),
    center: mapCenter.value,
    zoom: mapZoom.value,
    attributionControl: false,
    fadeDuration: 0,
  })
  map.once('load', () => map.resize())
  map.on('click', (e: any) => placeMarker(e.lngLat.lng, e.lngLat.lat))
})

onUnmounted(() => { if (map) { map.remove(); map = null } })

const handleCreate = async () => {
  if (!canSubmit.value || saving.value) return
  saving.value = true
  error.value = ''
  try {
    await envStore.createStation({
      name: name.value.trim(),
      source: source.value,
      latitude: selectedLat.value!,
      longitude: selectedLng.value!,
      is_public: isPublic.value,
      external_id: externalId.value.trim() || undefined,
    })
    emit('created')
    emit('close')
  } catch (e: any) {
    error.value = e?.data?.detail || $t('map.env.create_failed')
  } finally {
    saving.value = false
  }
}
</script>
