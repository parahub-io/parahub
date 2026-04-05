<template>
  <div class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-6">
    <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4">
      {{ editing ? $t('property.edit_property') : $t('property.add_property') }}
    </h3>

    <form @submit.prevent="submit" class="space-y-4">
      <!-- Name -->
      <div>
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
          {{ $t('property.name') }}
        </label>
        <input v-model="form.name" type="text" required maxlength="100"
               class="input-base w-full"
               :placeholder="$t('property.name_placeholder')" />
      </div>

      <!-- Type -->
      <div>
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
          {{ $t('property.type') }}
        </label>
        <div class="flex flex-wrap gap-2">
          <button v-for="pt in propertyTypes" :key="pt.value" type="button"
                  @click="form.propertyType = pt.value"
                  class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm border transition-colors"
                  :class="form.propertyType === pt.value
                    ? 'border-primary bg-primary-100 dark:bg-primary-900/30 text-neutral-900 dark:text-neutral-100 font-medium'
                    : 'border-neutral-200 dark:border-neutral-700 text-neutral-600 dark:text-neutral-400 hover:bg-neutral-50 dark:hover:bg-neutral-700'">
            <component :is="pt.icon" class="w-4 h-4" />
            {{ $t(`property.types.${pt.value}`) }}
          </button>
        </div>
      </div>

      <!-- Location: map picker -->
      <div>
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
          {{ $t('property.location') }}
        </label>
        <!-- Quick fly-to other properties -->
        <div v-if="otherPropertiesWithCoords.length" class="flex flex-wrap gap-1.5 mb-2">
          <button
            v-for="p in otherPropertiesWithCoords" :key="p.id"
            type="button"
            @click="flyToProperty(p)"
            class="inline-flex items-center gap-1 px-2 py-1 rounded text-xs border border-neutral-200 dark:border-neutral-600 text-neutral-600 dark:text-neutral-400 hover:bg-primary-50 dark:hover:bg-primary-900/20 hover:border-primary transition-colors"
          >
            <Home class="w-3 h-3" />
            {{ p.name }}
          </button>
        </div>
        <div ref="mapContainer"
             class="w-full h-48 rounded-lg overflow-hidden border border-neutral-200 dark:border-neutral-600 cursor-crosshair" />
        <div class="mt-1.5 text-sm font-mono" :class="form.latitude != null ? 'text-neutral-700 dark:text-neutral-300' : 'text-neutral-400'">
          {{ form.latitude != null ? `${form.latitude.toFixed(6)}, ${form.longitude!.toFixed(6)}` : $t('property.click_map_hint') }}
        </div>
      </div>

      <!-- Address -->
      <div>
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
          {{ $t('property.address') }}
        </label>
        <input v-model="form.address" type="text" maxlength="500"
               class="input-base w-full"
               :placeholder="$t('property.address_placeholder')" />
      </div>

      <!-- Error -->
      <UiAlert v-if="error" variant="error">{{ error }}</UiAlert>

      <!-- Actions -->
      <div class="flex items-center gap-3 pt-2">
        <button type="submit" class="btn-primary gap-1" :disabled="submitting">
          <Loader2 v-if="submitting" class="w-4 h-4 animate-spin" />
          {{ editing ? $t('property.save') : $t('property.add') }}
        </button>
        <button type="button" @click="$emit('cancel')" class="btn-outline">
          {{ $t('property.cancel') }}
        </button>
      </div>
    </form>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { Loader2, House, Building, Landmark, Trees, Warehouse, MapPin, Home } from 'lucide-vue-next'
import type { Property } from '~/stores/property'

const colorMode = useColorMode()
const propertyStore = usePropertyStore()

const props = defineProps<{
  prop?: Property | null
}>()

const emit = defineEmits<{
  submit: []
  cancel: []
}>()

const editing = computed(() => !!props.prop)
const submitting = ref(false)
const error = ref('')

const propertyTypes = [
  { value: 'house', icon: House },
  { value: 'apartment', icon: Building },
  { value: 'office', icon: Landmark },
  { value: 'dacha', icon: Trees },
  { value: 'garage', icon: Warehouse },
  { value: 'land', icon: MapPin },
  { value: 'other', icon: MapPin },
]

const form = reactive({
  name: props.prop?.name || '',
  propertyType: props.prop?.property_type || 'house',
  latitude: props.prop?.latitude || null as number | null,
  longitude: props.prop?.longitude || null as number | null,
  address: props.prop?.address || '',
  buildingId: props.prop?.world_object_id || '',
})

// Other properties for fly-to (exclude current one being edited)
const otherPropertiesWithCoords = computed(() =>
  propertyStore.properties.filter(p =>
    p.latitude && p.longitude && (!props.prop || p.id !== props.prop.id)
  )
)

const flyToProperty = (p: { latitude: number; longitude: number }) => {
  if (map) {
    map.flyTo({ center: [p.longitude, p.latitude], zoom: 17, essential: true, speed: 4.5 })
  }
}

const mapContainer = ref<HTMLElement | null>(null)
let map: any = null
let marker: any = null

const getStyleUrl = () =>
  colorMode.value === 'dark'
    ? '/map-styles/dark-liberty-parahub.json'
    : '/map-styles/liberty-parahub.json'

onMounted(async () => {
  if (!mapContainer.value) return

  const mod = await import('maplibre-gl')
  const maplibregl = mod.default || mod
  await import('maplibre-gl/dist/maplibre-gl.css')

  const hasCoords = form.latitude != null && form.longitude != null
  const { mapCenter, mapZoom } = useMapState()
  const center: [number, number] = hasCoords
    ? [form.longitude!, form.latitude!]
    : mapCenter.value
  const zoom = hasCoords ? 15 : mapZoom.value

  map = new maplibregl.Map({
    container: mapContainer.value,
    style: getStyleUrl(),
    center,
    zoom,
    attributionControl: false,
    fadeDuration: 0,
  })

  map.once('load', () => map.resize())

  if (hasCoords) {
    marker = new maplibregl.Marker({ color: '#FFE216' })
      .setLngLat([form.longitude!, form.latitude!])
      .addTo(map)
  }

  map.on('click', (e: any) => {
    const { lng, lat } = e.lngLat
    form.latitude = Math.round(lat * 1e6) / 1e6
    form.longitude = Math.round(lng * 1e6) / 1e6

    if (marker) {
      marker.setLngLat([lng, lat])
    } else {
      marker = new maplibregl.Marker({ color: '#FFE216' })
        .setLngLat([lng, lat])
        .addTo(map)
    }
  })
})

onUnmounted(() => {
  if (map) { map.remove(); map = null }
})

async function submit() {
  error.value = ''
  submitting.value = true
  try {
    const data: Record<string, any> = {
      name: form.name,
      property_type: form.propertyType,
    }
    if (form.latitude != null) data.latitude = form.latitude
    if (form.longitude != null) data.longitude = form.longitude
    if (form.address) data.address = form.address
    if (form.buildingId) data.world_object_id = form.buildingId

    if (editing.value && props.prop) {
      await propertyStore.updateProperty(props.prop.id, data)
    } else {
      await propertyStore.createProperty(data)
    }
    emit('submit')
  } catch (e: any) {
    error.value = e.data?.detail || e.message || 'Failed'
  } finally {
    submitting.value = false
  }
}
</script>
