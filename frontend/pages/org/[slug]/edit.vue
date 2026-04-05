<template>
  <div class="min-h-screen bg-neutral-50 dark:bg-neutral-900">
    <div class="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
      <!-- Loading -->
      <div v-if="loading" class="flex items-center justify-center py-32" role="status">
        <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100" />
        <span class="sr-only">{{ $t('common.loading') }}</span>
      </div>

      <!-- Not owner -->
      <div v-else-if="!isOwner" class="flex items-center justify-center py-32">
        <div class="text-center">
          <AlertCircle class="w-12 h-12 text-red-500 mx-auto mb-3" />
          <h2 class="text-xl font-bold text-neutral-900 dark:text-neutral-100 mb-2">{{ $t('directory.form.no_access') }}</h2>
          <UiButton variant="primary" size="sm" :to="localePath(`/org/${slug}`)">
            {{ $t('common.back') }}
          </UiButton>
        </div>
      </div>

      <!-- Form -->
      <template v-else>
        <NuxtLink
          :to="localePath(`/org/${slug}`)"
          class="text-link text-sm flex items-center gap-1 mb-4"
        >
          <ArrowLeft :size="16" />
          {{ establishment.name }}
        </NuxtLink>

        <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100 mb-6">
          {{ $t('common.edit') }}
        </h1>

        <form @submit.prevent="save" class="space-y-6">
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

          <!-- Location -->
          <div class="card p-4 space-y-4">
            <h2 class="text-sm font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
              <MapPin class="w-4 h-4 text-neutral-400" />
              {{ $t('directory.form.location') }}
            </h2>

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
          </div>

          <!-- Submit -->
          <UiButton variant="primary" class="w-full" :loading="saving" type="submit">
            {{ $t('common.save') }}
          </UiButton>
        </form>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ArrowLeft, AlertCircle, FileText, Phone, MapPin, Building2, Search, X } from 'lucide-vue-next'

definePageMeta({ middleware: 'auth' })

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const localePath = useLocalePath()
const authStore = useAuthStore()
const colorMode = useColorMode()

const slug = computed(() => String(route.params.slug))

const loading = ref(true)
const saving = ref(false)
const establishment = ref<any>(null)

const form = reactive({
  name: '',
  description: '',
  phone: '',
  email: '',
  website: '',
  floor: '',
  office_number: '',
  latitude: null as number | null,
  longitude: null as number | null,
})

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
      headers: { 'Authorization': `Bearer ${authStore.accessToken}` },
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
    // Update map to building location
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
    // 1. Try to find an actual OSM building polygon at click point
    const osmData = await $fetch<any>(`/api/v1/geo/osm/at-point?lat=${lat}&lon=${lng}&layer=building`)
    const osmBuilding = osmData?.features?.[0]

    // 2. Reverse geocode for address details
    const geo = await $fetch<any>(`/api/v1/geo/geocode/reverse?lat=${lat}&lon=${lng}`)
    if (!geo?.address) return

    // 3. Build request body — include osm_way_id if OSM building found
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
      // Use address from OSM housenumber if available
      if (osmBuilding.address) {
        body.street = osmBuilding.address.street || body.street
        body.house_number = osmBuilding.address.housenumber || body.house_number
      }
    }

    // 4. Create/find WorldObject building
    await authStore.ensureToken()
    const building = await $fetch<any>('/api/v1/geo/buildings/', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.accessToken}` },
      body,
    })
    linkedBuilding.value = building
  } catch (err: any) {
    // Silently fail — user can still search manually
    console.warn('Reverse geocode failed:', err)
  } finally {
    reverseGeoLoading.value = false
  }
}

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

const isOwner = computed(() => {
  return authStore.profile?.id && establishment.value?.owner_id === authStore.profile.id
})

// Map
const mapEl = ref<HTMLElement | null>(null)
let map: any = null
let marker: any = null

const getStyleUrl = () =>
  colorMode.value === 'dark'
    ? '/map-styles/dark-liberty-parahub.json'
    : '/map-styles/liberty-parahub.json'

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
    // Reverse geocode and auto-link building
    await reverseGeocodeAndLink(lat, lng)
  })
}

// Theme switch
watch(() => colorMode.value, () => {
  if (map) map.setStyle(getStyleUrl())
})

const save = async () => {
  saving.value = true
  try {
    await authStore.ensureToken()
    const e = establishment.value
    const body: Record<string, any> = {
      name: form.name,
      description: form.description,
      phone: form.phone,
      email: form.email,
      website: form.website,
      floor: form.floor,
      office_number: form.office_number,
      slug: e.slug,
      is_online: e.is_online ?? false,
      organization_type: e.organization_type,
      requires_terms_acceptance: e.requires_terms_acceptance ?? false,
      member_visibility: e.member_visibility || 'PUBLIC',
      world_object_id: linkedBuilding.value?.id || null,
      category_id: e.category_id || null,
    }
    if (form.latitude !== null && form.longitude !== null) {
      body.location = { latitude: form.latitude, longitude: form.longitude }
    }
    await $fetch(`/api/v1/geo/establishments/${e.id}/`, {
      method: 'PUT',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.accessToken}` },
      body,
    })
    router.push(localePath(`/org/${slug.value}`))
  } catch (err: any) {
    const { useToastStore } = await import('~/stores/toast')
    useToastStore().error(err.data?.detail || err.data?.message || t('common.error_server'))
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  try {
    await authStore.ensureToken()
    establishment.value = await $fetch(`/api/v1/geo/establishments/${slug.value}/`, {
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
    })
    const e = establishment.value
    form.name = e.name || ''
    form.description = e.description || ''
    form.phone = e.phone || ''
    form.email = e.email || ''
    form.website = e.website || ''
    form.floor = e.floor || ''
    form.office_number = e.office_number || ''
    if (e.world_object) {
      linkedBuilding.value = e.world_object
    }
    const loc = e.location || e.world_object?.location
    form.latitude = loc?.lat ?? null
    form.longitude = loc?.lon ?? null
  } catch {
    // Not found or error
  } finally {
    loading.value = false
  }
  await nextTick()
  initMap()
})

onUnmounted(() => {
  if (map) { map.remove(); map = null; marker = null }
})

useHead({ title: computed(() => `${t('common.edit')} — ${establishment.value?.name || slug.value}`) })
</script>
