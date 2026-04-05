<template>
  <div class="min-h-screen bg-neutral-50 dark:bg-neutral-900">
    <Head>
      <Title>{{ $t('events.create_event') }} - Parahub</Title>
    </Head>

    <div class="max-w-2xl mx-auto px-4 py-8">
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
              <MapPin class="w-6 h-6 mx-auto mb-1 text-green-600" />
              <span class="text-sm font-medium text-neutral-900 dark:text-neutral-100">{{ $t('events.types.offline') }}</span>
            </button>
            <button
              type="button"
              @click="form.event_type = 'ONLINE'"
              :class="form.event_type === 'ONLINE' ? 'border-secondary bg-secondary-50 dark:bg-secondary-900/30' : 'border-neutral-300 dark:border-neutral-600'"
              class="px-4 py-3 border-2 rounded-lg text-center"
            >
              <Video class="w-6 h-6 mx-auto mb-1 text-secondary" />
              <span class="text-sm font-medium text-neutral-900 dark:text-neutral-100">{{ $t('events.types.online') }}</span>
            </button>
            <button
              type="button"
              @click="form.event_type = 'HYBRID'"
              :class="form.event_type === 'HYBRID' ? 'border-secondary bg-secondary-50 dark:bg-secondary-900/30' : 'border-neutral-300 dark:border-neutral-600'"
              class="px-4 py-3 border-2 rounded-lg text-center"
            >
              <Globe class="w-6 h-6 mx-auto mb-1 text-purple-600" />
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

          <!-- Map picker -->
          <div
            ref="locationMapEl"
            class="w-full h-[250px] rounded-lg overflow-hidden border border-neutral-200 dark:border-neutral-600"
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
        <div class="flex gap-4">
          <button
            type="submit"
            :disabled="submitting"
            class="flex-1 flex items-center justify-center gap-2 px-6 py-3 bg-secondary text-white rounded-lg font-medium hover:bg-secondary-600 disabled:opacity-50"
          >
            <Loader2 v-if="submitting" class="w-5 h-5 animate-spin" />
            <Calendar v-else :size="20" />
            {{ $t('events.form.submit') }}
          </button>
          <NuxtLink
            :to="localePath('/events')"
            class="px-6 py-3 border border-neutral-300 dark:border-neutral-600 rounded-lg font-medium text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800"
          >
            {{ $t('common.cancel') }}
          </NuxtLink>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, MapPin, Video, Globe, Calendar, Loader2, ChevronDown, ImagePlus, X } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'
import { useToastStore } from '~/stores/toast'
import { useMapStore } from '~/stores/map'
import CategorySelect from '~/components/CategorySelect.vue'

definePageMeta({
  middleware: 'auth'
})

const router = useRouter()
const localePath = useLocalePath()
const { t } = useI18n()
const authStore = useAuthStore()
const toastStore = useToastStore()
const mapStore = useMapStore()
const colorMode = useColorMode()

const form = reactive({
  title: '',
  description: '',
  category_id: '',
  event_type: 'OFFLINE',
  starts_at: '',
  ends_at: '',
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
  location_name: '',
  latitude: null,
  longitude: null,
  online_url: '',
  max_participants: null,
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
    errorMessage.value = 'Image must be less than 10 MB'
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

const getStyleUrl = () =>
  colorMode.value === 'dark'
    ? '/map-styles/dark-liberty-parahub.json'
    : '/map-styles/liberty-parahub.json'

async function initLocationMap() {
  if (locationMap || !locationMapEl.value) return

  const mod = await import('maplibre-gl')
  const maplibregl = mod.default || mod
  await import('maplibre-gl/dist/maplibre-gl.css')

  const { mapCenter, mapZoom } = useMapState()
  const center = mapCenter.value
  locationMap = new maplibregl.Map({
    container: locationMapEl.value,
    style: getStyleUrl(),
    center,
    zoom: mapZoom.value,
    attributionControl: false,
    fadeDuration: 0,
  })

  locationMap.once('load', () => locationMap.resize())

  locationMap.on('click', (e) => {
    const { lng, lat } = e.lngLat
    form.latitude = Math.round(lat * 1e6) / 1e6
    form.longitude = Math.round(lng * 1e6) / 1e6

    if (locationMarker) {
      locationMarker.setLngLat([lng, lat])
    } else {
      locationMarker = new maplibregl.Marker({ color: '#ef4444' })
        .setLngLat([lng, lat])
        .addTo(locationMap)
    }
  })
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

// Init map on mount if not ONLINE
onMounted(() => {
  if (form.event_type !== 'ONLINE') {
    nextTick(() => initLocationMap())
  }
  document.addEventListener('click', onClickOutsideTz)
})

onUnmounted(() => {
  destroyLocationMap()
  document.removeEventListener('click', onClickOutsideTz)
})

const submitForm = async () => {
  errorMessage.value = ''

  // Validation
  if (!form.title || form.title.length < 3) {
    errorMessage.value = 'Title must be at least 3 characters'
    return
  }

  if (!form.description || form.description.length < 10) {
    errorMessage.value = 'Description must be at least 10 characters'
    return
  }

  if (!form.starts_at) {
    errorMessage.value = 'Start date/time is required'
    return
  }

  if (form.event_type !== 'ONLINE' && !form.location_name && !form.latitude) {
    errorMessage.value = 'Location is required for offline/hybrid events'
    return
  }

  if (form.event_type !== 'OFFLINE' && !form.online_url) {
    errorMessage.value = 'Online URL is required for online/hybrid events'
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
    errorMessage.value = e.data?.detail || e.message || 'Failed to create event'
  } finally {
    submitting.value = false
  }
}
</script>
