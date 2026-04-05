<template>
  <div>
    <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
      {{ $t('market.create_modal.location_label') }}
    </label>

    <!-- Mini map preview -->
    <div v-if="modelValue.latitude && modelValue.longitude" class="mb-3 rounded-lg overflow-hidden border border-neutral-200 dark:border-neutral-700">
      <StaticMapPreview
        :latitude="modelValue.latitude"
        :longitude="modelValue.longitude"
        :height="250"
        :zoom="15"
        interactive
        @update:center="onMapMove"
      />
    </div>

    <!-- Location action buttons -->
    <div class="flex gap-2 mb-3">
      <UiButton type="button" variant="outline" size="sm" :icon="MapPin" @click="getCurrentLocation">
        <span class="hidden sm:inline">{{ $t('market.create_modal.location_current') }}</span>
        <span class="sm:hidden">GPS</span>
      </UiButton>

      <UiButton type="button" variant="outline" size="sm" :icon="Navigation" :disabled="loadingTransitStop" @click="findNearestTransitStop">
        <span class="hidden sm:inline">{{ loadingTransitStop ? $t('market.create_modal.location_searching') : $t('market.create_modal.location_nearest_stop') }}</span>
        <span class="sm:hidden">{{ loadingTransitStop ? '...' : $t('market.create_modal.location_nearest_stop_short') }}</span>
      </UiButton>
    </div>

    <!-- Nearest stop name display -->
    <UiAlert v-if="nearestStopName" variant="success" class="mb-3">
      <strong>{{ $t('market.create_modal.location_stop_found') }}</strong> {{ nearestStopName }}
    </UiAlert>

  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useAuthStore } from '~/stores/auth'
import { useMapStore } from '~/stores/map'
import { MapPin, Navigation } from 'lucide-vue-next'
import StaticMapPreview from '~/components/IoT/StaticMapPreview.vue'

const props = defineProps({
  modelValue: {
    type: Object,
    required: true
  }
})

const emit = defineEmits(['update:modelValue'])

const authStore = useAuthStore()
const mapStore = useMapStore()
const toastStore = useToastStore()
const { t: $t } = useI18n()

const loadingTransitStop = ref(false)
const nearestStopName = ref('')

const roundCoordinate = (value) => {
  return Math.round(value * 100000) / 100000
}

const updateCoordinates = (lat, lon) => {
  emit('update:modelValue', { latitude: lat, longitude: lon })
}

// Set coordinates from outside (e.g. EXIF GPS)
const setCoordinates = (lat, lon) => {
  updateCoordinates(lat, lon)
}

// Sync coordinates when user drags/zooms the mini map
const onMapMove = (lat, lon) => {
  updateCoordinates(lat, lon)
}

const getCurrentLocation = () => {
  if (!navigator.geolocation) {
    toastStore.error($t('market.notifications.location_unsupported'))
    return
  }

  navigator.geolocation.getCurrentPosition(
    (position) => {
      updateCoordinates(
        roundCoordinate(position.coords.latitude),
        roundCoordinate(position.coords.longitude)
      )
    },
    (error) => {
      console.error('Geolocation error:', error)
      toastStore.error($t('market.notifications.location_error'))
    }
  )
}

const findNearestTransitStop = async () => {
  loadingTransitStop.value = true
  nearestStopName.value = ''

  try {
    let lat, lon

    if (props.modelValue.latitude && props.modelValue.longitude) {
      lat = props.modelValue.latitude
      lon = props.modelValue.longitude
    } else if (mapStore.center[0] || mapStore.center[1]) {
      lon = mapStore.center[0]
      lat = mapStore.center[1]
    } else {
      toastStore.error($t('market.notifications.set_coordinates_first'))
      return
    }

    const radiusOptions = [5000, 10000, 15000]
    let response = null

    await authStore.ensureToken()

    for (const searchRadius of radiusOptions) {
      const result = await $fetch(`/api/v1/geo/osm/nearest-stops?lat=${lat}&lon=${lon}&radius=${searchRadius}`, {
        credentials: 'include',
        headers: authStore.token ? { 'Authorization': `Bearer ${authStore.token}` } : {}
      })

      if (result.stops && result.stops.length > 0) {
        response = result
        break
      }
    }

    if (!response || !response.stops || response.stops.length === 0) {
      toastStore.error($t('market.notifications.no_stops_found'))
      return
    }

    const closestStop = response.stops[0]

    updateCoordinates(
      roundCoordinate(closestStop.lat),
      roundCoordinate(closestStop.lon)
    )

    const stopName = closestStop.name || closestStop.tags?.name || 'Stop'
    const distance = closestStop.distance_meters
    const distanceStr = distance < 1000
      ? `${Math.round(distance)}м`
      : `${(distance / 1000).toFixed(1)}км`
    nearestStopName.value = `${stopName} (${distanceStr})`
  } catch (error) {
    console.error('Failed to find transit stop:', error)
    toastStore.error($t('market.notifications.stop_search_error'))
  } finally {
    loadingTransitStop.value = false
  }
}

// Default to last map view on mount
onMounted(() => {
  if (props.modelValue.latitude || props.modelValue.longitude) return

  // Try mapStore (works with SPA navigation from /map)
  const [sLng, sLat] = mapStore.center
  const isDefault = sLng === -9.1393 && sLat === 38.7223

  if (!isDefault) {
    updateCoordinates(roundCoordinate(sLat), roundCoordinate(sLng))
    return
  }

  // Fallback: read from localStorage (useMapState persists there)
  try {
    const saved = localStorage.getItem('parahub_map_center')
    if (saved) {
      const [lng, lat] = JSON.parse(saved)
      if (isFinite(lng) && isFinite(lat)) {
        updateCoordinates(roundCoordinate(lat), roundCoordinate(lng))
        return
      }
    }
  } catch {}

  // Last resort: use Lisbon default
  updateCoordinates(roundCoordinate(sLat), roundCoordinate(sLng))
})

defineExpose({ setCoordinates })
</script>
