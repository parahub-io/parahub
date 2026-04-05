<template>
  <div class="max-w-2xl mx-auto px-4 py-6">
    <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100 mb-6">{{ $t('rides.title') }}</h1>

    <!-- Tabs -->
    <UiTabs v-model="activeTab" :tabs="rideTabs" full-width class="mb-6">

    <!-- Passenger Tab -->
    <div v-if="activeTab === 'passenger'">
      <!-- Create Request Form -->
      <div v-if="authStore.isAuthenticated" class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4 mb-6">
        <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4">{{ $t('rides.create.title') }}</h2>

        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ $t('rides.create.origin') }}</label>
            <StopPicker v-model="form.originStop" :placeholder="$t('rides.create.origin_placeholder')" />
          </div>

          <div>
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ $t('rides.create.destination') }}</label>
            <StopPicker v-model="form.destinationStop" :placeholder="$t('rides.create.destination_placeholder')" />
          </div>

          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ $t('rides.create.price') }}</label>
              <div class="relative">
                <input
                  v-model.number="form.priceSats"
                  type="number"
                  min="0"
                  class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100"
                />
                <span class="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-neutral-400">sats</span>
              </div>
            </div>
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ $t('rides.create.passengers') }}</label>
              <input
                v-model.number="form.passengersCount"
                type="number"
                min="1"
                max="10"
                class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100"
              />
            </div>
          </div>

          <div>
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ $t('rides.create.note') }}</label>
            <input
              v-model="form.note"
              type="text"
              :placeholder="$t('rides.create.note_placeholder')"
              maxlength="500"
              class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100"
            />
          </div>

          <button
            @click="createRequest"
            :disabled="!canCreate || creating"
            class="btn-secondary w-full transition-colors"
          >
            {{ creating ? $t('rides.create.creating') : $t('rides.create.submit') }}
          </button>

          <p v-if="createError" class="text-sm text-red-500">{{ createError }}</p>
        </div>
      </div>

      <!-- Login CTA -->
      <div v-else class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-6 mb-6 text-center">
        <p class="text-neutral-600 dark:text-neutral-400 mb-3">{{ $t('rides.login_required') }}</p>
        <NuxtLink :to="localePath('/login')" class="btn-secondary inline-block">
          {{ $t('auth.login') }}
        </NuxtLink>
      </div>

      <!-- My Active Requests -->
      <div v-if="myRequests.length > 0">
        <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-3">{{ $t('rides.my_requests.title') }}</h2>
        <div class="space-y-3">
          <NuxtLink
            v-for="req in myRequests"
            :key="req.id"
            :to="localePath(`/transit/rides/${req.id}`)"
            class="block bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4 hover:border-secondary-400 transition-colors"
          >
            <div class="flex items-center justify-between mb-2">
              <div class="font-medium text-neutral-900 dark:text-neutral-100">
                {{ req.origin_stop?.name }} → {{ req.destination_stop?.name }}
              </div>
              <span class="text-sm font-semibold text-amber-600 dark:text-amber-400">{{ req.price_sats }} sats</span>
            </div>
            <div class="flex items-center gap-3 text-sm text-neutral-500">
              <span>{{ req.bookings_count ?? 0 }} {{ $t('rides.offers') }}</span>
              <span>{{ timeAgo(req.created_at) }}</span>
            </div>
          </NuxtLink>
        </div>
      </div>
    </div>

    <!-- Driver Tab -->
    <div v-if="activeTab === 'driver'">
      <!-- Search mode toggle -->
      <div class="flex gap-2 mb-4">
        <button
          @click="driverMode = 'nearby'"
          :class="[
            'flex-1 px-3 py-2 rounded-lg text-sm font-medium transition-colors border',
            driverMode === 'nearby'
              ? 'bg-green-50 dark:bg-green-900/30 border-green-300 dark:border-green-700 text-green-700 dark:text-green-300'
              : 'bg-white dark:bg-neutral-800 border-neutral-200 dark:border-neutral-700 text-neutral-600 dark:text-neutral-400 hover:border-neutral-300',
          ]"
        >
          <MapPin class="w-4 h-4 inline mr-1" />
          {{ $t('rides.search.mode_nearby') }}
        </button>
        <button
          @click="driverMode = 'route'"
          :class="[
            'flex-1 px-3 py-2 rounded-lg text-sm font-medium transition-colors border',
            driverMode === 'route'
              ? 'bg-green-50 dark:bg-green-900/30 border-green-300 dark:border-green-700 text-green-700 dark:text-green-300'
              : 'bg-white dark:bg-neutral-800 border-neutral-200 dark:border-neutral-700 text-neutral-600 dark:text-neutral-400 hover:border-neutral-300',
          ]"
        >
          <Route class="w-4 h-4 inline mr-1" />
          {{ $t('rides.search.mode_route') }}
        </button>
      </div>

      <!-- Nearby search mode -->
      <div v-if="driverMode === 'nearby'">
        <div class="mb-4">
          <button
            @click="searchNearby"
            :disabled="searching"
            class="btn-success w-full transition-colors flex items-center justify-center gap-2"
          >
            <MapPin class="w-5 h-5" />
            {{ searching ? $t('rides.search.searching') : $t('rides.search.find_nearby') }}
          </button>
        </div>

        <div class="mb-6">
          <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
            {{ $t('rides.search.radius') }}: {{ searchRadius }} km
          </label>
          <input v-model.number="searchRadius" type="range" min="1" max="50" step="1" class="w-full" />
        </div>
      </div>

      <!-- Route corridor search mode -->
      <div v-if="driverMode === 'route'">
        <div class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4 mb-4">
          <div class="space-y-3">
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ $t('rides.search.route_from') }}</label>
              <StopPicker v-model="routeForm.origin" :placeholder="$t('rides.search.route_from_placeholder')" />
            </div>
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ $t('rides.search.route_to') }}</label>
              <StopPicker v-model="routeForm.destination" :placeholder="$t('rides.search.route_to_placeholder')" />
            </div>
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                {{ $t('rides.search.corridor') }}: {{ routeForm.corridorKm }} km
              </label>
              <input v-model.number="routeForm.corridorKm" type="range" min="0.1" max="5" step="0.1" class="w-full" />
            </div>
            <button
              @click="searchByRoute"
              :disabled="!canSearchRoute || searching"
              class="btn-success w-full transition-colors flex items-center justify-center gap-2"
            >
              <Route class="w-5 h-5" />
              {{ searching ? $t('rides.search.searching') : $t('rides.search.search_route') }}
            </button>
            <p v-if="routeError" class="text-sm text-red-500">{{ routeError }}</p>
          </div>
        </div>
      </div>

      <!-- Results -->
      <div v-if="searchResults.length > 0" class="space-y-3">
        <NuxtLink
          v-for="req in searchResults"
          :key="req.id"
          :to="localePath(`/transit/rides/${req.id}`)"
          class="block bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4 hover:border-green-400 transition-colors"
        >
          <div class="flex items-center justify-between mb-2">
            <div class="font-medium text-neutral-900 dark:text-neutral-100">
              {{ req.origin_stop?.name }} → {{ req.destination_stop?.name }}
            </div>
            <span class="text-sm font-semibold text-amber-600 dark:text-amber-400">{{ req.price_sats }} sats</span>
          </div>
          <div class="flex items-center gap-3 text-sm text-neutral-500">
            <span>{{ req.passenger?.display_name }}</span>
            <span v-if="req.distance_m != null">{{ formatDistance(req.distance_m) }}</span>
            <span v-if="req.origin_distance_m != null" class="text-green-600 dark:text-green-400">
              {{ $t('rides.search.detour') }}: {{ formatDistance(req.origin_distance_m) }}
            </span>
            <span>{{ req.passengers_count }} {{ $t('rides.passengers_label', req.passengers_count) }}</span>
          </div>
          <div v-if="req.note" class="mt-1 text-sm text-neutral-600 dark:text-neutral-400 italic">{{ req.note }}</div>
        </NuxtLink>
      </div>

      <div v-else-if="searchDone && !searching" class="text-center py-8 text-neutral-500">
        {{ $t('rides.search.no_results') }}
      </div>
    </div>
    </UiTabs>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onActivated } from 'vue'
import { MapPin, Route } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'

const { t } = useI18n()
const authStore = useAuthStore()
const route = useRoute()
const router = useRouter()
const localePath = useLocalePath()

useSeoMeta({
  title: t('rides.title') + ' - Parahub',
  ogTitle: t('rides.title') + ' - Parahub',
  description: t('rides.landing_meta'),
  ogDescription: t('rides.landing_meta'),
  ogImage: '/og-image.jpg',
  ogType: 'website',
  twitterCard: 'summary_large_image',
})

const activeTab = ref('passenger')
const rideTabs = computed(() => [
  { id: 'passenger', label: t('rides.tabs.find_ride') },
  { id: 'driver', label: t('rides.tabs.give_ride') },
])

// --- Passenger state ---
interface StopItem {
  id: string
  name: string
  lat: number
  lon: number
}

const form = ref({
  originStop: null as StopItem | null,
  destinationStop: null as StopItem | null,
  priceSats: 100,
  passengersCount: 1,
  note: '',
})

const creating = ref(false)
const createError = ref('')
const myRequests = ref<any[]>([])

const canCreate = computed(() => {
  return form.value.originStop && form.value.destinationStop && form.value.priceSats >= 0
})

async function createRequest() {
  if (!canCreate.value) return
  creating.value = true
  createError.value = ''

  try {
    await authStore.ensureToken()
    const data = await $fetch<any>('/api/v1/rides/requests/', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
      body: {
        origin_stop_id: form.value.originStop!.id,
        destination_stop_id: form.value.destinationStop!.id,
        price_sats: form.value.priceSats,
        passengers_count: form.value.passengersCount,
        note: form.value.note,
      }
    })
    // Reset form before navigating away
    form.value = { originStop: null, destinationStop: null, priceSats: 100, passengersCount: 1, note: '' }
    router.push(localePath(`/transit/rides/${data.id}`))
  } catch (err: any) {
    createError.value = err?.data?.message || err?.data?.detail || t('rides.create.error')
  } finally {
    creating.value = false
  }
}

async function loadMyRequests() {
  if (!authStore.isAuthenticated) return
  try {
    await authStore.ensureToken()
    myRequests.value = await $fetch<any[]>('/api/v1/rides/requests/', {
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
    })
  } catch {
    // ignore
  }
}

// --- Driver state ---
const driverMode = ref<'nearby' | 'route'>('nearby')
const searchResults = ref<any[]>([])
const searching = ref(false)
const searchDone = ref(false)
const searchRadius = ref(2)
const routeForm = ref({
  origin: null as StopItem | null,
  destination: null as StopItem | null,
  corridorKm: 0.5,
})
const routeError = ref('')

const canSearchRoute = computed(() => {
  return routeForm.value.origin && routeForm.value.destination
})

async function searchNearby() {
  searching.value = true
  searchDone.value = false
  searchResults.value = []

  try {
    const pos = await new Promise<GeolocationPosition>((resolve, reject) => {
      navigator.geolocation.getCurrentPosition(resolve, reject, { timeout: 10000 })
    })

    await authStore.ensureToken()
    searchResults.value = await $fetch<any[]>('/api/v1/rides/search/', {
      params: {
        lat: pos.coords.latitude,
        lon: pos.coords.longitude,
        radius_km: searchRadius.value,
      },
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
    })
  } catch (err) {
    console.error('Search failed:', err)
  } finally {
    searching.value = false
    searchDone.value = true
  }
}

async function searchByRoute() {
  if (!canSearchRoute.value) return
  searching.value = true
  searchDone.value = false
  searchResults.value = []
  routeError.value = ''

  try {
    await authStore.ensureToken()
    searchResults.value = await $fetch<any[]>('/api/v1/rides/search/route/', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
      body: {
        origin: { lat: routeForm.value.origin!.lat, lon: routeForm.value.origin!.lon },
        destination: { lat: routeForm.value.destination!.lat, lon: routeForm.value.destination!.lon },
        corridor_km: routeForm.value.corridorKm,
      },
    })
  } catch (err: any) {
    routeError.value = err?.data?.message || err?.data?.detail || t('rides.search.route_error')
    console.error('Route search failed:', err)
  } finally {
    searching.value = false
    searchDone.value = true
  }
}

// --- Helpers ---
function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return t('rides.time.now')
  if (mins < 60) return t('rides.time.minutes_ago', { n: mins })
  return t('rides.time.hours_ago', { n: Math.floor(mins / 60) })
}

function formatDistance(meters: number): string {
  if (meters < 1000) return `${Math.round(meters)} m`
  return `${(meters / 1000).toFixed(1)} km`
}

onMounted(() => {
  // Pre-fill origin from query params (e.g. from transit stop CTA)
  const { origin_id, origin_name, origin_lat, origin_lon } = route.query
  if (origin_id && origin_name && origin_lat && origin_lon) {
    form.value.originStop = {
      id: String(origin_id),
      name: String(origin_name),
      lat: Number(origin_lat),
      lon: Number(origin_lon),
    }
  }

  loadMyRequests()
})

// Reload data when re-activated via keepalive (e.g. SPA back-navigation)
onActivated(() => {
  loadMyRequests()
})
</script>
