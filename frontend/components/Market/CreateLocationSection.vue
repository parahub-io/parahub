<template>
  <div>
    <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
      {{ $t('market.create_modal.location_label') }}
    </label>

    <!-- Quick fly-to: the user's own places (properties + organizations) -->
    <div v-if="myPlaces.length" class="flex flex-wrap gap-1.5 mb-2">
      <button
        v-for="place in visiblePlaces"
        :key="place.key"
        type="button"
        class="inline-flex items-center gap-1 px-2 py-1 rounded text-xs border border-neutral-200 dark:border-neutral-600 text-neutral-600 dark:text-neutral-300 hover:bg-primary-100 dark:hover:bg-primary-900/40 hover:border-primary transition-colors"
        @click="flyToPlace(place)"
      >
        <component :is="place.icon" class="w-3 h-3" />
        {{ place.name }}
      </button>
      <button
        v-if="myPlaces.length > PLACES_COLLAPSED && !showAllPlaces"
        type="button"
        class="inline-flex items-center px-2 py-1 rounded text-xs border border-neutral-200 dark:border-neutral-600 text-neutral-500 dark:text-neutral-400 hover:bg-primary-100 dark:hover:bg-primary-900/40 hover:border-primary transition-colors"
        @click="showAllPlaces = true"
      >
        +{{ myPlaces.length - PLACES_COLLAPSED }}
      </button>
    </div>

    <!-- Mini map preview -->
    <div v-if="modelValue.latitude && modelValue.longitude" class="mb-3 rounded-lg overflow-hidden border border-neutral-200 dark:border-neutral-700">
      <StaticMapPreview
        ref="mapPreview"
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
import { ref, computed, onMounted } from 'vue'
import { useAuthStore } from '~/stores/auth'
import { useMapStore } from '~/stores/map'
import { usePropertyStore } from '~/stores/property'
import { MapPin, Navigation, Home, Building2 } from 'lucide-vue-next'
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
const propertyStore = usePropertyStore()
const toastStore = useToastStore()
const { t: $t } = useI18n()

const mapPreview = ref(null)
const loadingTransitStop = ref(false)
const nearestStopName = ref('')

const roundCoordinate = (value) => {
  return Math.round(value * 100000) / 100000
}

// Same rounding ladder as MarketItemCard — the stop search reaches 15 km, so
// the tens-of-km bucket is live here too.
const formatDistance = (meters) => {
  if (meters < 1000) return `${Math.round(meters)} ${$t('market.distance.meters')}`
  const km = meters / 1000
  return km < 10
    ? `${km.toFixed(1)} ${$t('market.distance.km')}`
    : `${Math.round(km)} ${$t('market.distance.km')}`
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

// --- The user's own places: fly-to shortcuts over the picker ---
// An item almost always sits at the seller's home or in their establishment,
// and the form's "post as" selector already names the org — the picker offers
// the same places so the point never has to be found by hand.
const myOrgs = ref([])

const myPlaces = computed(() => [
  ...propertyStore.properties
    .filter(p => p.latitude && p.longitude)
    .map(p => ({ key: `property:${p.id}`, name: p.name, icon: Home, latitude: p.latitude, longitude: p.longitude })),
  ...myOrgs.value
    .filter(o => o.latitude && o.longitude)
    .map(o => ({ key: `org:${o.id}`, name: o.name, icon: Building2, latitude: o.latitude, longitude: o.longitude })),
])

// Long affiliation lists would push the picker off screen — collapse past this
// many, never drop any (the "+N" chip reveals the rest).
const PLACES_COLLAPSED = 6
const showAllPlaces = ref(false)
const visiblePlaces = computed(() =>
  showAllPlaces.value ? myPlaces.value : myPlaces.value.slice(0, PLACES_COLLAPSED)
)

const fetchMyOrgs = async () => {
  try {
    await authStore.ensureToken()
    if (!authStore.token) return
    myOrgs.value = await $fetch('/api/v1/geo/establishments/mine/', {
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
  } catch (error) {
    console.error('Failed to load my organizations:', error)
  }
}

const flyToPlace = (place) => {
  // The flight carries the coordinates back through `moveend`; writing them
  // here as well would jumpTo() mid-animation. Falls back when the map is
  // still lazy-loading.
  if (!mapPreview.value?.flyTo(place.latitude, place.longitude)) {
    updateCoordinates(roundCoordinate(place.latitude), roundCoordinate(place.longitude))
  }
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
    nearestStopName.value = `${stopName} (${formatDistance(closestStop.distance_meters)})`
  } catch (error) {
    console.error('Failed to find transit stop:', error)
    toastStore.error($t('market.notifications.stop_search_error'))
  } finally {
    loadingTransitStop.value = false
  }
}

// Default to last map view on mount
onMounted(() => {
  if (!propertyStore.properties.length) propertyStore.fetchProperties().catch(() => {})
  fetchMyOrgs()

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
