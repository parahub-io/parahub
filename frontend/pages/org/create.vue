<template>
  <div class="min-h-screen bg-neutral-50 dark:bg-neutral-900">
    <div class="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-6">

      <!-- WoT gate: requires 3+ verifications (or foundation member) -->
      <div v-if="!canCreate" class="flex items-center justify-center py-32">
        <div class="text-center max-w-sm">
          <ShieldAlert class="w-12 h-12 text-amber-500 mx-auto mb-3" />
          <h2 class="text-xl font-bold text-neutral-900 dark:text-neutral-100 mb-2">
            {{ $t('directory.create.wot_required_title') }}
          </h2>
          <p class="text-sm text-neutral-500 dark:text-neutral-400 mb-4">
            {{ $t('directory.create.wot_required') }}
          </p>
          <UiButton variant="primary" size="sm" :to="localePath('/directory')">
            {{ $t('common.back') }}
          </UiButton>
        </div>
      </div>

      <!-- Form -->
      <template v-else>
        <NuxtLink
          :to="localePath('/directory')"
          class="text-link text-sm flex items-center gap-1 mb-4"
        >
          <ArrowLeft :size="16" />
          {{ $t('directory.title') }}
        </NuxtLink>

        <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100 mb-1">
          {{ $t('directory.create.title') }}
        </h1>
        <p class="text-sm text-neutral-500 dark:text-neutral-400 mb-6">
          {{ $t('directory.create.subtitle') }}
        </p>

        <form @submit.prevent="submit" class="space-y-6">
          <!-- Basic info -->
          <div class="card p-4 space-y-4">
            <h2 class="text-sm font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
              <FileText class="w-4 h-4 text-neutral-400" />
              {{ $t('directory.form.basic_info') }}
            </h2>

            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                {{ $t('directory.form.name') }} *
              </label>
              <input
                v-model="form.name"
                type="text"
                required
                class="w-full px-4 py-3 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
              />
            </div>

            <!-- Organization type -->
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                {{ $t('directory.create.type_label') }} *
              </label>
              <div class="grid grid-cols-2 sm:grid-cols-3 gap-2">
                <button
                  v-for="type in ORG_TYPES"
                  :key="type"
                  type="button"
                  @click="form.organization_type = type"
                  class="px-3 py-2.5 rounded-lg text-sm font-medium border transition-colors"
                  :class="form.organization_type === type
                    ? 'bg-primary/15 border-primary/40 text-neutral-900 dark:text-neutral-100'
                    : 'bg-white dark:bg-neutral-800 border-neutral-300 dark:border-neutral-600 text-neutral-600 dark:text-neutral-400 hover:border-neutral-400 dark:hover:border-neutral-500'"
                >
                  {{ $t(`directory.organizations.type_${type.toLowerCase()}`) }}
                </button>
              </div>
            </div>

            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                {{ $t('directory.form.description') }}
              </label>
              <textarea
                v-model="form.description"
                rows="4"
                class="w-full px-4 py-3 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
              />
            </div>

            <!-- Category (optional) -->
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                {{ $t('directory.create.category_label') }}
              </label>
              <CategorySelect
                v-model="form.category_id"
                domain="directory"
                mode="filter"
              />
            </div>
          </div>

          <!-- Contact -->
          <div class="card p-4 space-y-4">
            <h2 class="text-sm font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
              <Phone class="w-4 h-4 text-neutral-400" />
              {{ $t('directory.form.contacts') }}
            </h2>

            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                  {{ $t('directory.form.phone') }}
                </label>
                <input
                  v-model="form.phone"
                  type="tel"
                  class="w-full px-4 py-3 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
                />
              </div>
              <div>
                <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                  {{ $t('directory.form.email') }}
                </label>
                <input
                  v-model="form.email"
                  type="email"
                  class="w-full px-4 py-3 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
                />
              </div>
            </div>

            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                {{ $t('directory.form.website') }}
              </label>
              <input
                v-model="form.website"
                type="url"
                placeholder="https://"
                class="w-full px-4 py-3 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
              />
            </div>
          </div>

          <!-- Location (optional) -->
          <div class="card p-4 space-y-4">
            <div class="flex items-center justify-between gap-3">
              <h2 class="text-sm font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
                <MapPin class="w-4 h-4 text-neutral-400" />
                {{ $t('directory.form.location') }}
              </h2>
              <!-- Toggle: has physical location? -->
              <button
                type="button"
                role="switch"
                :aria-checked="hasLocation"
                @click="hasLocation = !hasLocation"
                class="relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 dark:focus:ring-offset-neutral-900"
                :class="hasLocation ? 'bg-primary' : 'bg-neutral-300 dark:bg-neutral-600'"
              >
                <span
                  class="inline-block h-4 w-4 transform rounded-full bg-white transition-transform"
                  :class="hasLocation ? 'translate-x-6' : 'translate-x-1'"
                />
              </button>
            </div>
            <p class="text-xs text-neutral-500 dark:text-neutral-400 -mt-2">
              {{ hasLocation ? $t('directory.create.has_location_hint') : $t('directory.create.online_hint') }}
            </p>

            <template v-if="hasLocation">
              <!-- Building (WorldObject) search -->
              <div>
                <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1 flex items-center gap-1.5">
                  <Building2 class="w-3.5 h-3.5" />
                  {{ $t('directory.form.building_search') }}
                </label>

                <!-- Linked building badge -->
                <div v-if="linkedBuilding" class="flex items-center gap-2 px-3 py-2 rounded-lg bg-primary/10 border border-primary/20 mb-2">
                  <Building2 class="w-4 h-4 text-primary shrink-0" />
                  <span class="text-sm text-neutral-900 dark:text-neutral-100 truncate flex-1">
                    {{ linkedBuilding.full_address || `${linkedBuilding.street || ''} ${linkedBuilding.house_number || ''}`.trim() || linkedBuilding.id }}
                  </span>
                  <button
                    type="button"
                    class="text-neutral-400 hover:text-red-500 transition-colors shrink-0"
                    :title="$t('directory.form.building_unlink')"
                    @click="unlinkBuilding"
                  >
                    <X class="w-4 h-4" />
                  </button>
                </div>

                <!-- Search input -->
                <div v-else class="relative">
                  <div class="relative">
                    <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400 pointer-events-none" />
                    <input
                      v-model="buildingQuery"
                      type="text"
                      :placeholder="$t('directory.form.building_search')"
                      class="w-full pl-9 pr-4 py-3 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
                      @input="searchBuilding"
                    />
                  </div>
                  <!-- Dropdown results -->
                  <ul
                    v-if="buildingResults.length"
                    class="absolute z-20 w-full mt-1 bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-600 rounded-lg shadow-lg max-h-48 overflow-y-auto"
                  >
                    <li
                      v-for="(r, i) in buildingResults"
                      :key="i"
                      class="px-3 py-2 text-sm cursor-pointer hover:bg-neutral-100 dark:hover:bg-neutral-700 text-neutral-900 dark:text-neutral-100"
                      @click="selectBuilding(r)"
                    >
                      {{ r.label }}
                    </li>
                  </ul>
                </div>
              </div>

              <div class="grid grid-cols-2 gap-4">
                <div>
                  <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                    {{ $t('directory.establishments.floor') }}
                  </label>
                  <input
                    v-model="form.floor"
                    type="text"
                    class="w-full px-4 py-3 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
                  />
                </div>
                <div>
                  <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                    {{ $t('directory.establishments.office') }}
                  </label>
                  <input
                    v-model="form.office_number"
                    type="text"
                    class="w-full px-4 py-3 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
                  />
                </div>
              </div>

              <!-- Map picker -->
              <div
                ref="mapEl"
                class="w-full h-[300px] rounded-lg overflow-hidden border border-neutral-200 dark:border-neutral-600"
              />
              <!-- Reverse geocoding status -->
              <div v-if="reverseGeoLoading" class="flex items-center gap-2 text-xs text-neutral-500">
                <div class="animate-spin rounded-full h-3 w-3 border-b border-neutral-400" />
                {{ $t('directory.form.detecting_address') }}
              </div>
              <p v-else-if="form.latitude !== null && form.longitude !== null" class="text-xs text-neutral-500 font-mono">
                {{ form.latitude.toFixed(6) }}, {{ form.longitude.toFixed(6) }}
              </p>
              <p v-else class="text-xs text-neutral-400">
                {{ $t('directory.form.click_map_to_detect') }}
              </p>
            </template>
          </div>

          <!-- Submit -->
          <UiButton variant="primary" class="w-full" :loading="saving" :disabled="!canSubmit" type="submit">
            {{ $t('directory.create.submit') }}
          </UiButton>
        </form>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ArrowLeft, ShieldAlert, FileText, Phone, MapPin, Building2, Search, X } from 'lucide-vue-next'

definePageMeta({ middleware: 'auth' })

const router = useRouter()
const { t } = useI18n()
const localePath = useLocalePath()
const authStore = useAuthStore()
const colorMode = useColorMode()

const ORG_TYPES = ['ASSOCIATION', 'COOPERATIVE', 'COMPANY', 'NGO', 'COMMUNITY', 'GOVERNMENT']

// WoT gate — mirrors backend (3+ verifications or foundation member)
const canCreate = computed(() =>
  !!(authStore.user?.profile?.is_verified_wot || authStore.user?.profile?.is_foundation_member)
)

const saving = ref(false)

const form = reactive({
  name: '',
  organization_type: '',
  description: '',
  category_id: null as string | null,
  phone: '',
  email: '',
  website: '',
  floor: '',
  office_number: '',
  latitude: null as number | null,
  longitude: null as number | null,
})

const canSubmit = computed(() => form.name.trim().length > 0 && !!form.organization_type)

// Physical location toggle (off = online-only organization)
const hasLocation = ref(false)

// Building (WorldObject) search
const linkedBuilding = ref<any>(null)
const buildingQuery = ref('')
const buildingResults = ref<any[]>([])
const reverseGeoLoading = ref(false)
let buildingSearchTimeout: any = null

const searchBuilding = () => {
  clearTimeout(buildingSearchTimeout)
  buildingSearchTimeout = setTimeout(async () => {
    if (buildingQuery.value.length < 3) {
      buildingResults.value = []
      return
    }
    try {
      const data = await $fetch<any>(`/api/v1/geo/geocode/search?q=${encodeURIComponent(buildingQuery.value)}`)
      buildingResults.value = data.features?.map((f: any) => ({
        label: f.properties?.label || f.properties?.name,
        name: f.properties?.name,
        locality: f.properties?.locality || f.properties?.region,
        lat: f.geometry?.coordinates?.[1],
        lon: f.geometry?.coordinates?.[0],
        street: f.properties?.street,
        house_number: f.properties?.housenumber,
        postal_code: f.properties?.postalcode,
        country_a: f.properties?.country_a,
      })) || []
    } catch {
      buildingResults.value = []
    }
  }, 300)
}

const selectBuilding = async (r: any) => {
  buildingResults.value = []
  buildingQuery.value = ''
  try {
    await authStore.ensureToken()
    const building = await $fetch<any>('/api/v1/geo/buildings/', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
      body: {
        location: { latitude: r.lat, longitude: r.lon },
        country: (r.country_a || 'PT').substring(0, 2),
        city: r.locality || '',
        street: r.street || '',
        house_number: r.house_number || '',
        postal_code: r.postal_code || '',
        full_address: r.label || r.name,
      },
    })
    linkedBuilding.value = building
    form.latitude = r.lat
    form.longitude = r.lon
    updateMarker(r.lon, r.lat)
  } catch (err: any) {
    console.error('Failed to link building:', err)
  }
}

const unlinkBuilding = () => {
  linkedBuilding.value = null
}

const reverseGeocodeAndLink = async (lat: number, lng: number) => {
  reverseGeoLoading.value = true
  try {
    const osmData = await $fetch<any>(`/api/v1/geo/osm/at-point?lat=${lat}&lon=${lng}&layer=building`)
    const osmBuilding = osmData?.features?.[0]

    const geo = await $fetch<any>(`/api/v1/geo/geocode/reverse?lat=${lat}&lon=${lng}`)
    if (!geo?.address) return

    const body: Record<string, any> = {
      location: { latitude: lat, longitude: lng },
      country: geo.address.country_code || (geo.address.country_a || 'PT').substring(0, 2),
      city: geo.address.city || '',
      street: geo.address.street || '',
      house_number: geo.address.housenumber || '',
      postal_code: geo.address.postcode || '',
      full_address: geo.display_name || '',
    }
    if (osmBuilding?.osm_id) {
      body.osm_way_id = Math.abs(osmBuilding.osm_id)
      if (osmBuilding.address) {
        body.street = osmBuilding.address.street || body.street
        body.house_number = osmBuilding.address.housenumber || body.house_number
      }
    }

    await authStore.ensureToken()
    const building = await $fetch<any>('/api/v1/geo/buildings/', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
      body,
    })
    linkedBuilding.value = building
  } catch (err: any) {
    console.warn('Reverse geocode failed:', err)
  } finally {
    reverseGeoLoading.value = false
  }
}

// Map
const mapEl = ref<HTMLElement | null>(null)
let map: any = null
let marker: any = null

const getStyleUrl = () =>
  colorMode.value === 'dark'
    ? '/map-styles/dark-liberty-parahub.json'
    : '/map-styles/liberty-parahub.json'

const updateMarker = (lng: number, lat: number) => {
  if (!map) return
  if (marker) {
    marker.setLngLat([lng, lat])
  } else {
    import('maplibre-gl').then((mod) => {
      const maplibregl = mod.default || mod
      marker = new maplibregl.Marker({ color: '#ef4444' })
        .setLngLat([lng, lat])
        .addTo(map!)
    })
  }
  map.flyTo({ center: [lng, lat], zoom: 17 })
}

const initMap = async () => {
  if (map || !mapEl.value) return
  const mod = await import('maplibre-gl')
  const maplibregl = mod.default || mod
  await import('maplibre-gl/dist/maplibre-gl.css')

  const { mapCenter, mapZoom } = useMapState()
  const center = form.latitude && form.longitude
    ? [form.longitude, form.latitude]
    : [mapCenter.value?.[0] ?? -9.14, mapCenter.value?.[1] ?? 38.74]
  const zoom = form.latitude ? 17 : (mapZoom.value ?? 13)

  map = new maplibregl.Map({
    container: mapEl.value!,
    style: getStyleUrl(),
    center: center as [number, number],
    zoom,
    attributionControl: false,
    fadeDuration: 0,
  })
  map.once('load', () => map.resize())

  if (form.latitude && form.longitude) {
    marker = new maplibregl.Marker({ color: '#ef4444' })
      .setLngLat([form.longitude, form.latitude])
      .addTo(map)
  }

  map.on('click', async (e: any) => {
    const { lat, lng } = e.lngLat
    form.latitude = Math.round(lat * 1e6) / 1e6
    form.longitude = Math.round(lng * 1e6) / 1e6
    if (marker) {
      marker.setLngLat([lng, lat])
    } else {
      marker = new maplibregl.Marker({ color: '#ef4444' })
        .setLngLat([lng, lat])
        .addTo(map)
    }
    await reverseGeocodeAndLink(lat, lng)
  })
}

const destroyMap = () => {
  if (map) { map.remove(); map = null; marker = null }
}

// Init/destroy map as the location toggle flips; clear location data when turned off
watch(hasLocation, async (on) => {
  if (on) {
    await nextTick()
    initMap()
  } else {
    destroyMap()
    linkedBuilding.value = null
    buildingQuery.value = ''
    buildingResults.value = []
    form.latitude = null
    form.longitude = null
    form.floor = ''
    form.office_number = ''
  }
})

watch(() => colorMode.value, () => {
  if (map) map.setStyle(getStyleUrl())
})

const submit = async () => {
  if (!canSubmit.value) return
  saving.value = true
  try {
    await authStore.ensureToken()
    const body: Record<string, any> = {
      name: form.name.trim(),
      organization_type: form.organization_type,
      description: form.description,
      category_id: form.category_id || null,
      phone: form.phone,
      email: form.email,
      website: form.website,
      is_online: !hasLocation.value,
    }
    if (hasLocation.value) {
      body.world_object_id = linkedBuilding.value?.id || null
      body.floor = form.floor
      body.office_number = form.office_number
      if (form.latitude !== null && form.longitude !== null) {
        body.location = { latitude: form.latitude, longitude: form.longitude }
      }
    }
    const res = await $fetch<any>('/api/v1/geo/establishments/', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
      body,
    })
    const { useToastStore } = await import('~/stores/toast')
    useToastStore().success(t('directory.create.success'))
    router.push(localePath(`/org/${res.slug || res.id}`))
  } catch (err: any) {
    const { useToastStore } = await import('~/stores/toast')
    const status = err?.response?.status || err?.statusCode
    const msg = status === 403
      ? t('directory.create.wot_required')
      : (err.data?.detail || err.data?.message || t('common.error_server'))
    useToastStore().error(msg)
  } finally {
    saving.value = false
  }
}

onUnmounted(() => {
  destroyMap()
})

useHead({ title: computed(() => t('directory.create.title')) })
</script>
