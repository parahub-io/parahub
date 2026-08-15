<template>
  <div class="min-h-screen bg-neutral-50 dark:bg-neutral-900">
    <Head>
      <Title>{{ $t('events.create_event') }} - Parahub</Title>
    </Head>

    <div class="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
      <!-- Header -->
      <div class="mb-8">
        <NuxtLink
          :to="localePath('/events')"
          class="text-link text-sm flex items-center gap-1 mb-4"
        >
          <ArrowLeft :size="16" />
          {{ $t('events.back_to_events') }}
        </NuxtLink>
        <h1 class="text-2xl md:text-3xl font-bold text-neutral-900 dark:text-neutral-100">
          {{ $t('events.create_event') }}
        </h1>
      </div>

      <!-- Form -->
      <form @submit.prevent="submitForm" class="space-y-6">
        <!-- Post as establishment (renders nothing when the user has no orgs) -->
        <EstablishmentSelector v-model="form.establishment_id" />

        <!-- Title -->
        <div>
          <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
            {{ $t('events.form.title') }} *
          </label>
          <input
            v-model="form.title"
            type="text"
            required
            minlength="3"
            maxlength="255"
            class="w-full px-4 py-3 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
            :placeholder="$t('events.form.title_placeholder')"
          />
        </div>

        <!-- Description -->
        <div>
          <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
            {{ $t('events.form.description') }} *
          </label>
          <textarea
            v-model="form.description"
            required
            minlength="10"
            rows="5"
            class="w-full px-4 py-3 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
            :placeholder="$t('events.form.description_placeholder')"
          />
        </div>

        <!-- Category -->
        <div>
          <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
            {{ $t('events.form.category') }}
          </label>
          <CategorySelect
            v-model="form.category_id"
            mode="create"
            domain="events"
            :placeholder="$t('events.form.category_placeholder')"
          />
        </div>

        <!-- Event type -->
        <div>
          <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
            {{ $t('events.form.event_type') }} *
          </label>
          <div class="grid grid-cols-3 gap-3">
            <button
              type="button"
              @click="form.event_type = 'OFFLINE'"
              :class="form.event_type === 'OFFLINE' ? 'border-secondary bg-secondary-50 dark:bg-secondary-900/30' : 'border-neutral-300 dark:border-neutral-600'"
              class="px-4 py-3 border-2 rounded-lg text-center"
            >
              <MapPin class="w-6 h-6 mx-auto mb-1" :class="form.event_type === 'OFFLINE' ? 'text-secondary' : 'text-neutral-400'" />
              <span class="text-sm font-medium text-neutral-900 dark:text-neutral-100">{{ $t('events.types.offline') }}</span>
            </button>
            <button
              type="button"
              @click="form.event_type = 'ONLINE'"
              :class="form.event_type === 'ONLINE' ? 'border-secondary bg-secondary-50 dark:bg-secondary-900/30' : 'border-neutral-300 dark:border-neutral-600'"
              class="px-4 py-3 border-2 rounded-lg text-center"
            >
              <Video class="w-6 h-6 mx-auto mb-1" :class="form.event_type === 'ONLINE' ? 'text-secondary' : 'text-neutral-400'" />
              <span class="text-sm font-medium text-neutral-900 dark:text-neutral-100">{{ $t('events.types.online') }}</span>
            </button>
            <button
              type="button"
              @click="form.event_type = 'HYBRID'"
              :class="form.event_type === 'HYBRID' ? 'border-secondary bg-secondary-50 dark:bg-secondary-900/30' : 'border-neutral-300 dark:border-neutral-600'"
              class="px-4 py-3 border-2 rounded-lg text-center"
            >
              <Globe class="w-6 h-6 mx-auto mb-1" :class="form.event_type === 'HYBRID' ? 'text-secondary' : 'text-neutral-400'" />
              <span class="text-sm font-medium text-neutral-900 dark:text-neutral-100">{{ $t('events.types.hybrid') }}</span>
            </button>
          </div>
        </div>

        <!-- Date and time -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
              {{ $t('events.form.starts_at') }} *
            </label>
            <input
              v-model="form.starts_at"
              type="datetime-local"
              required
              class="w-full px-4 py-3 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
              {{ $t('events.form.ends_at') }}
            </label>
            <input
              v-model="form.ends_at"
              type="datetime-local"
              class="w-full px-4 py-3 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
            />
          </div>
        </div>

        <!-- Timezone -->
        <div>
          <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
            {{ $t('events.form.timezone') }}
          </label>
          <div class="relative" ref="tzDropdownRef">
            <button
              type="button"
              class="w-full px-4 py-3 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent text-left flex items-center justify-between"
              @click="tzOpen = !tzOpen"
            >
              <span>{{ form.timezone }} ({{ tzOffsetLabel(form.timezone) }})</span>
              <ChevronDown :size="16" class="text-neutral-400 transition-transform" :class="{ 'rotate-180': tzOpen }" />
            </button>
            <div
              v-if="tzOpen"
              class="absolute z-50 mt-1 w-full bg-white dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-600 rounded-lg shadow-lg max-h-64 overflow-hidden flex flex-col"
            >
              <div class="p-2 border-b border-neutral-200 dark:border-neutral-700">
                <input
                  ref="tzSearchInput"
                  v-model="tzSearch"
                  type="text"
                  class="w-full px-3 py-2 text-sm border border-neutral-300 dark:border-neutral-600 rounded bg-neutral-50 dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-1 focus:ring-primary"
                  :placeholder="$t('events.form.timezone_search')"
                />
              </div>
              <ul class="overflow-y-auto max-h-52">
                <li
                  v-for="tz in filteredTimezones"
                  :key="tz"
                  class="px-4 py-2 text-sm cursor-pointer hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors"
                  :class="{ 'bg-primary-100 dark:bg-primary-900/40 font-medium': tz === form.timezone }"
                  @click="selectTimezone(tz)"
                >
                  {{ tz }} <span class="text-neutral-400">({{ tzOffsetLabel(tz) }})</span>
                </li>
                <li v-if="filteredTimezones.length === 0" class="px-4 py-3 text-sm text-neutral-400 text-center">
                  {{ $t('map.search.no_results') }}
                </li>
              </ul>
            </div>
          </div>
        </div>

        <!-- Location (for offline/hybrid) -->
        <div v-if="form.event_type !== 'ONLINE'" class="space-y-4">
          <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
            {{ $t('events.form.location') }} *
          </label>

          <!-- Location name (text) -->
          <div>
            <input
              v-model="form.location_name"
              type="text"
              maxlength="255"
              class="w-full px-4 py-3 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
              :placeholder="$t('events.form.location_name_placeholder')"
            />
            <p class="text-xs text-neutral-500 mt-1">{{ $t('events.form.location_hint') }}</p>
          </div>

          <!-- Quick fly-to: the user's own places (properties + organizations) -->
          <div v-if="myPlaces.length" class="flex flex-wrap gap-1.5">
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

          <!-- Map picker -->
          <div
            ref="locationMapEl"
            class="w-full h-[250px] rounded-lg overflow-hidden border border-neutral-200 dark:border-neutral-600 cursor-crosshair"
          />
          <p v-if="form.latitude !== null && form.longitude !== null" class="text-xs text-neutral-500 font-mono">
            {{ form.latitude.toFixed(6) }}, {{ form.longitude.toFixed(6) }}
          </p>
          <p v-else class="text-xs text-neutral-400">
            {{ $t('events.form.click_map_hint') }}
          </p>
        </div>

        <!-- Online URL (for online/hybrid) -->
        <div v-if="form.event_type !== 'OFFLINE'">
          <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
            {{ $t('events.form.online_url') }} *
          </label>
          <input
            v-model="form.online_url"
            type="url"
            :required="form.event_type !== 'OFFLINE'"
            class="w-full px-4 py-3 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
            :placeholder="$t('events.form.online_url_placeholder')"
          />
        </div>

        <!-- Max participants -->
        <div>
          <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
            {{ $t('events.form.max_participants') }}
          </label>
          <input
            v-model.number="form.max_participants"
            type="number"
            min="1"
            max="10000"
            class="w-full px-4 py-3 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
            :placeholder="$t('events.form.max_participants_placeholder')"
          />
          <p class="text-xs text-neutral-500 mt-1">{{ $t('events.form.max_participants_hint') }}</p>
        </div>

        <!-- Cover image upload -->
        <div>
          <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
            {{ $t('events.form.cover_image') }}
          </label>
          <div
            class="relative border-2 border-dashed rounded-lg transition-colors cursor-pointer"
            :class="coverDragOver
              ? 'border-primary bg-primary-100 dark:bg-primary-900/40'
              : 'border-neutral-300 dark:border-neutral-600 hover:border-neutral-400 dark:hover:border-neutral-500'"
            @dragover.prevent="coverDragOver = true"
            @dragleave="coverDragOver = false"
            @drop.prevent="onCoverDrop"
            @click="$refs.coverInput.click()"
          >
            <!-- Preview -->
            <div v-if="coverPreview" class="relative">
              <img :src="coverPreview" alt="" class="w-full h-48 object-cover rounded-lg" />
              <button
                type="button"
                @click.stop="removeCoverImage"
                class="absolute top-2 right-2 p-1.5 bg-neutral-900/70 text-white rounded-full hover:bg-neutral-900/90"
              >
                <X :size="16" />
              </button>
            </div>
            <!-- Upload prompt -->
            <div v-else class="flex flex-col items-center justify-center py-8 px-4">
              <ImagePlus class="w-8 h-8 text-neutral-400 mb-2" />
              <p class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t('events.form.cover_image_drop') }}</p>
              <p class="text-xs text-neutral-400 mt-1">JPEG, PNG · max 10 MB</p>
            </div>
          </div>
          <input
            ref="coverInput"
            type="file"
            accept="image/jpeg,image/png,image/webp"
            class="hidden"
            @change="onCoverFileSelect"
          />
        </div>

        <!-- Error message -->
        <UiAlert v-if="errorMessage" variant="error">{{ errorMessage }}</UiAlert>

        <!-- Submit button -->
        <UiButton type="submit" variant="primary" class="w-full" :icon="Calendar" :loading="submitting">
          {{ $t('events.form.submit') }}
        </UiButton>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onActivated, onDeactivated, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, MapPin, Video, Globe, Calendar, ChevronDown, ImagePlus, X, Home, Building2 } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'
import { useToastStore } from '~/stores/toast'
import CategorySelect from '~/components/CategorySelect.vue'
import { CALENDAR_GLYPH } from '~/composables/useMapToggleableLayer'
import { createPlaceSquareElement } from '~/utils/pickerMarker'

definePageMeta({
  middleware: 'auth'
})

const router = useRouter()
const localePath = useLocalePath()
const { t } = useI18n()
const authStore = useAuthStore()
const toastStore = useToastStore()
const propertyStore = usePropertyStore()
const colorMode = useColorMode()

const form = reactive({
  title: '',
  description: '',
  category_id: '',
  event_type: 'OFFLINE',
  starts_at: '',
  ends_at: '',
  timezone: 'UTC', // replaced with the browser zone after hydration (see onActivated)
  location_name: '',
  latitude: null,
  longitude: null,
  online_url: '',
  max_participants: null,
  establishment_id: null,
})

const submitting = ref(false)
const errorMessage = ref('')
const coverFile = ref(null)
const coverPreview = ref(null)
const coverDragOver = ref(false)

function onCoverFileSelect(e) {
  const file = e.target.files?.[0]
  if (file) setCoverFile(file)
}

function onCoverDrop(e) {
  coverDragOver.value = false
  const file = e.dataTransfer.files?.[0]
  if (file && file.type.startsWith('image/')) setCoverFile(file)
}

function setCoverFile(file) {
  if (file.size > 10 * 1024 * 1024) {
    errorMessage.value = t('events.form.errors.image_too_large')
    return
  }
  coverFile.value = file
  coverPreview.value = URL.createObjectURL(file)
}

function removeCoverImage() {
  if (coverPreview.value) URL.revokeObjectURL(coverPreview.value)
  coverFile.value = null
  coverPreview.value = null
}

// --- Timezone picker ---
const tzOpen = ref(false)
const tzSearch = ref('')
const tzDropdownRef = ref(null)
const tzSearchInput = ref(null)

const allTimezones = (() => {
  try {
    return Intl.supportedValuesOf('timeZone')
  } catch {
    // Fallback for older browsers
    return ['UTC', 'Europe/London', 'Europe/Paris', 'Europe/Berlin', 'Europe/Moscow', 'Europe/Lisbon',
      'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles', 'America/Sao_Paulo',
      'Asia/Tokyo', 'Asia/Shanghai', 'Asia/Dubai', 'Asia/Kolkata', 'Asia/Bangkok',
      'Australia/Sydney', 'Pacific/Auckland', 'Africa/Cairo', 'Africa/Johannesburg']
  }
})()

function tzOffsetLabel(tz) {
  try {
    const now = new Date()
    const fmt = new Intl.DateTimeFormat('en-US', { timeZone: tz, timeZoneName: 'shortOffset' })
    const parts = fmt.formatToParts(now)
    const offsetPart = parts.find(p => p.type === 'timeZoneName')
    return offsetPart?.value || ''
  } catch {
    return ''
  }
}

const filteredTimezones = computed(() => {
  const q = tzSearch.value.toLowerCase().trim()
  if (!q) return allTimezones
  return allTimezones.filter(tz => tz.toLowerCase().includes(q))
})

function selectTimezone(tz) {
  form.timezone = tz
  tzOpen.value = false
  tzSearch.value = ''
}

watch(tzOpen, (open) => {
  if (open) {
    nextTick(() => tzSearchInput.value?.focus())
  }
})

function onClickOutsideTz(e) {
  if (tzDropdownRef.value && !tzDropdownRef.value.contains(e.target)) {
    tzOpen.value = false
    tzSearch.value = ''
  }
}

// --- Location map picker ---
const locationMapEl = ref(null)
let locationMap = null
let locationMarker = null
let maplibregl = null

// The venue wears the static-place square (PK/design-system § Map Markers):
// indigo fill, calendar glyph — never a stock MapLibre teardrop.
const venueMarker = () => new maplibregl.Marker({
  element: createPlaceSquareElement('#4E4EC8', CALENDAR_GLYPH),
  anchor: 'center',
})

function placeMarker(lat, lng) {
  form.latitude = Math.round(lat * 1e6) / 1e6
  form.longitude = Math.round(lng * 1e6) / 1e6
  if (locationMarker) {
    locationMarker.setLngLat([lng, lat])
  } else if (locationMap && maplibregl) {
    locationMarker = venueMarker().setLngLat([lng, lat]).addTo(locationMap)
  }
}

// --- The user's own places: fly-to shortcuts over the picker ---
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

async function fetchMyOrgs() {
  try {
    await authStore.ensureToken()
    if (!authStore.token) return
    myOrgs.value = await $fetch('/api/v1/geo/establishments/mine/', {
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
  } catch (e) {
    console.error('Failed to load my organizations:', e)
  }
}

function flyToPlace(place) {
  if (locationMap) {
    locationMap.flyTo({ center: [place.longitude, place.latitude], zoom: 17, essential: true, speed: 4.5 })
  }
  placeMarker(place.latitude, place.longitude)
  // The place name is a sensible default caption — never overwrite what the user typed.
  if (!form.location_name) form.location_name = place.name
}

const getStyleUrl = () =>
  colorMode.value === 'dark'
    ? '/map-styles/dark-liberty-parahub.json'
    : '/map-styles/liberty-parahub.json'

async function initLocationMap() {
  if (locationMap || !locationMapEl.value) return

  const mod = await import('maplibre-gl')
  maplibregl = mod.default || mod
  await import('maplibre-gl/dist/maplibre-gl.css')

  const { mapCenter, mapZoom } = useMapState()
  const hasCoords = form.latitude !== null && form.longitude !== null
  locationMap = new maplibregl.Map({
    container: locationMapEl.value,
    style: getStyleUrl(),
    center: hasCoords ? [form.longitude, form.latitude] : mapCenter.value,
    zoom: hasCoords ? 17 : mapZoom.value,
    attributionControl: false,
    fadeDuration: 0,
  })

  locationMap.once('load', () => locationMap.resize())

  // Restore the pin when the map is re-created (cached page re-entry).
  if (hasCoords) {
    locationMarker = venueMarker().setLngLat([form.longitude, form.latitude]).addTo(locationMap)
  }

  locationMap.on('click', (e) => placeMarker(e.lngLat.lat, e.lngLat.lng))
}

function destroyLocationMap() {
  if (locationMap) {
    locationMap.remove()
    locationMap = null
    locationMarker = null
  }
}

// Init/destroy map when event type changes
watch(
  () => form.event_type,
  (val) => {
    if (val !== 'ONLINE') {
      nextTick(() => initLocationMap())
    } else {
      destroyLocationMap()
    }
  },
  { flush: 'post' }
)

// Theme switch
watch(() => colorMode.value, () => {
  if (locationMap) locationMap.setStyle(getStyleUrl())
})

// Pages are KeepAlive-cached (app.vue): onMounted/onUnmounted do not fire on
// cached navigation, so the GL context and the document listener are bound to
// activation instead.
const tzDetected = ref(false)

onActivated(() => {
  // Reading the browser zone during setup renders 'UTC' on the server and the
  // real zone on the client — a hydration mismatch. Detect once, after mount.
  if (!tzDetected.value) {
    tzDetected.value = true
    form.timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  }
  propertyStore.fetchProperties()
  fetchMyOrgs()
  if (form.event_type !== 'ONLINE') {
    nextTick(() => initLocationMap())
  }
  document.addEventListener('click', onClickOutsideTz)
})

onDeactivated(() => {
  destroyLocationMap()
  document.removeEventListener('click', onClickOutsideTz)
})

const submitForm = async () => {
  errorMessage.value = ''

  // Validation
  if (!form.title || form.title.length < 3) {
    errorMessage.value = t('events.form.errors.title_min')
    return
  }

  if (!form.description || form.description.length < 10) {
    errorMessage.value = t('events.form.errors.description_min')
    return
  }

  if (!form.starts_at) {
    errorMessage.value = t('events.form.errors.starts_required')
    return
  }

  if (form.event_type !== 'ONLINE' && !form.location_name && !form.latitude) {
    errorMessage.value = t('events.form.errors.location_required')
    return
  }

  if (form.event_type !== 'OFFLINE' && !form.online_url) {
    errorMessage.value = t('events.form.errors.online_url_required')
    return
  }

  submitting.value = true

  try {
    await authStore.ensureToken()

    // Prepare payload
    const payload = {
      title: form.title,
      description: form.description,
      event_type: form.event_type,
      starts_at: new Date(form.starts_at).toISOString(),
      timezone: form.timezone
    }

    if (form.category_id) {
      payload.category_id = form.category_id
    }

    if (form.ends_at) {
      payload.ends_at = new Date(form.ends_at).toISOString()
    }

    if (form.location_name) {
      payload.location_name = form.location_name
    }

    if (form.latitude && form.longitude) {
      payload.location = {
        latitude: form.latitude,
        longitude: form.longitude
      }
    }

    if (form.online_url) {
      payload.online_url = form.online_url
    }

    if (form.max_participants) {
      payload.max_participants = form.max_participants
    }

    if (form.establishment_id) {
      payload.establishment_id = form.establishment_id
    }

    const response = await $fetch('/api/v1/geo/events/', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
      body: payload
    })

    // Upload cover image if selected
    if (coverFile.value && response.id) {
      try {
        const formData = new FormData()
        formData.append('image', coverFile.value)
        await $fetch(`/api/v1/geo/events/${response.id}/cover-image/`, {
          method: 'POST',
          credentials: 'include',
          headers: { 'Authorization': `Bearer ${authStore.token}` },
          body: formData
        })
      } catch (imgErr) {
        console.warn('Cover image upload failed:', imgErr)
        // Don't block event creation
      }
    }

    toastStore.success(t('events.created_successfully'))
    router.push(localePath(`/events/${response.id}`))
  } catch (e) {
    console.error('Error creating event:', e)
    errorMessage.value = e.data?.detail || e.message || t('events.form.errors.failed')
  } finally {
    submitting.value = false
  }
}
</script>
