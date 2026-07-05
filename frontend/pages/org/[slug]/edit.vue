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

            <!-- Logo -->
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                {{ $t('directory.form.logo') }}
              </label>
              <div class="flex items-center gap-3">
                <div class="w-16 h-16 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-neutral-50 dark:bg-neutral-800 overflow-hidden flex items-center justify-center shrink-0">
                  <img v-if="form.logo_url" :src="form.logo_url" alt="" class="w-full h-full object-cover" />
                  <ImagePlus v-else class="w-6 h-6 text-neutral-400" />
                </div>
                <div class="flex flex-wrap gap-2">
                  <label class="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 text-neutral-700 dark:text-neutral-200 hover:bg-neutral-50 dark:hover:bg-neutral-700 cursor-pointer" :class="{ 'opacity-60 pointer-events-none': logoUploading }">
                    <Loader2 v-if="logoUploading" class="w-4 h-4 animate-spin" />
                    <ImagePlus v-else class="w-4 h-4" />
                    {{ form.logo_url ? $t('directory.form.logo_replace') : $t('directory.form.logo_upload') }}
                    <input type="file" accept="image/*" class="hidden" :disabled="logoUploading" @change="handleLogoUpload" />
                  </label>
                  <button
                    v-if="form.logo_url"
                    type="button"
                    class="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg border border-red-200 dark:border-red-900/40 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20"
                    @click="removeLogo"
                  >
                    <Trash2 class="w-4 h-4" /> {{ $t('common.delete') }}
                  </button>
                </div>
              </div>
              <p class="text-xs text-neutral-400 mt-1.5">{{ $t('directory.form.logo_hint') }}</p>
            </div>

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

            <!-- Category -->
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                {{ $t('directory.create.category_label') }}
              </label>
              <CategorySelect v-model="form.category_id" domain="directory" mode="filter" />
            </div>

            <!-- Organization type -->
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                {{ $t('directory.create.type_label') }}
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

          <!-- Opening hours -->
          <div class="card p-4 space-y-3">
            <h2 class="text-sm font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
              <Clock class="w-4 h-4 text-neutral-400" />
              {{ $t('directory.establishments.opening_hours') }}
            </h2>
            <div v-for="d in HOURS_DAYS" :key="d" class="flex items-center gap-3 flex-wrap">
              <span class="w-9 text-sm font-medium text-neutral-600 dark:text-neutral-400">{{ $t(`directory.form.days.${d}`) }}</span>
              <label class="inline-flex items-center gap-1.5 text-sm cursor-pointer select-none w-24">
                <input v-model="hoursForm[d].open" type="checkbox" class="rounded border-neutral-300 dark:border-neutral-600 text-primary focus:ring-primary" />
                <span :class="hoursForm[d].open ? 'text-neutral-900 dark:text-neutral-100' : 'text-neutral-400'">
                  {{ hoursForm[d].open ? $t('directory.form.hours_open') : $t('directory.form.hours_closed') }}
                </span>
              </label>
              <template v-if="hoursForm[d].open">
                <input v-model="hoursForm[d].from" type="time"
                  class="px-2 py-1.5 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
                <span class="text-neutral-400">–</span>
                <input v-model="hoursForm[d].to" type="time"
                  class="px-2 py-1.5 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
              </template>
            </div>
            <p v-if="Object.keys(hoursExtra).length" class="text-xs text-neutral-400 mt-1">
              {{ $t('directory.form.hours_advanced_note') }}
            </p>
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

        <!-- Danger zone -->
        <div class="card p-4 mt-6 space-y-3 border-error/40">
          <h2 class="text-sm font-semibold text-error flex items-center gap-2">
            <AlertTriangle class="w-4 h-4" />
            {{ $t('directory.form.danger_zone') }}
          </h2>
          <p class="text-sm text-neutral-600 dark:text-neutral-400">
            {{ $t('directory.form.delete_org_hint') }}
          </p>
          <UiButton variant="outline-error" :icon="Trash2" type="button" @click="showDeleteConfirm = true">
            {{ $t('directory.form.delete_org') }}
          </UiButton>
        </div>

        <!-- Delete confirmation -->
        <UiConfirmModal
          v-model="showDeleteConfirm"
          :title="$t('directory.form.delete_confirm_title')"
          :message="$t('directory.form.delete_confirm_msg', { name: establishment.name })"
          :icon="Trash2"
          variant="error"
          :confirm-label="$t('directory.form.delete_org')"
          :loading="deleting"
          @confirm="deleteOrg"
        />
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ArrowLeft, AlertCircle, AlertTriangle, FileText, Phone, MapPin, Building2, Search, X, ImagePlus, Trash2, Loader2, Clock } from 'lucide-vue-next'

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
  logo_url: '',
  category_id: null as string | null,
  organization_type: '',
  floor: '',
  office_number: '',
  latitude: null as number | null,
  longitude: null as number | null,
})

const logoUploading = ref(false)

// Organization types — same set as the create form (CONDOMINIUM is created via
// its own flow and preserved untouched when absent from this picker).
const ORG_TYPES = ['ASSOCIATION', 'COOPERATIVE', 'COMPANY', 'NGO', 'COMMUNITY', 'GOVERNMENT']

// ---- Opening hours editor (OSM-style {day|range: 'HH:MM-HH:MM'|'closed'}) ----
// A per-day open/close editor for the common case. Anything it can't represent
// losslessly (the `{raw: ...}` import form, split hours like '09:00-13:00,14:00-19:00')
// is preserved verbatim in `hoursExtra` and merged back on save — never destroyed.
const HOURS_DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
const DAY_INDEX: Record<string, number> = { sun: 0, mon: 1, tue: 2, wed: 3, thu: 4, fri: 5, sat: 6 }
const INDEX_DAY: Record<number, string> = { 0: 'sun', 1: 'mon', 2: 'tue', 3: 'wed', 4: 'thu', 5: 'fri', 6: 'sat' }

const hoursForm = reactive<Record<string, { open: boolean; from: string; to: string }>>(
  Object.fromEntries(HOURS_DAYS.map(d => [d, { open: false, from: '09:00', to: '18:00' }]))
)
const hoursExtra = ref<Record<string, string>>({})

function expandDayRange(key: string): string[] {
  const out: string[] = []
  for (const part of key.toLowerCase().split(',').map(s => s.trim())) {
    if (part.includes('-')) {
      const [a, b] = part.split('-').map(s => s.trim())
      let i = DAY_INDEX[a]; const end = DAY_INDEX[b]
      if (i === undefined || end === undefined) return []
      while (true) { out.push(INDEX_DAY[i]); if (i === end) break; i = (i + 1) % 7 }
    } else {
      if (DAY_INDEX[part] === undefined) return []
      out.push(part)
    }
  }
  return out
}

function parseOpeningHours(oh: Record<string, string> | null | undefined) {
  for (const d of HOURS_DAYS) { hoursForm[d].open = false; hoursForm[d].from = '09:00'; hoursForm[d].to = '18:00' }
  hoursExtra.value = {}
  if (!oh) return
  for (const [key, val] of Object.entries(oh)) {
    const days = expandDayRange(key)
    const closed = String(val).toLowerCase() === 'closed'
    const m = String(val).match(/^(\d{1,2}:\d{2})-(\d{1,2}:\d{2})$/)
    if (days.length && (closed || m)) {
      for (const d of days) {
        if (closed) hoursForm[d].open = false
        else { hoursForm[d].open = true; hoursForm[d].from = m![1]; hoursForm[d].to = m![2] }
      }
    } else {
      hoursExtra.value[key] = val  // raw / split / multi-range → keep as-is
    }
  }
}

function buildOpeningHours(): Record<string, string> {
  const out: Record<string, string> = { ...hoursExtra.value }
  let anyOpen = false
  for (const d of HOURS_DAYS) {
    const g = hoursForm[d]
    if (g.open && g.from && g.to) { out[d] = `${g.from}-${g.to}`; anyOpen = true }
  }
  // Only once a per-day schedule actually exists do unchecked days mean an
  // explicit "closed" (so a never-set establishment stays {} rather than
  // "closed all week", and a preserved `{raw: …}` import isn't polluted).
  if (anyOpen) {
    for (const d of HOURS_DAYS) {
      if (!hoursForm[d].open && !(d in out)) out[d] = 'closed'
    }
  }
  return out
}

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

const handleLogoUpload = async (ev: Event) => {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  logoUploading.value = true
  try {
    await authStore.ensureToken()
    // Client-side compress to keep uploads small (best-effort).
    let processed: File = file
    try {
      const imageCompression = (await import('browser-image-compression')).default
      processed = await imageCompression(file, { maxSizeMB: 1, maxWidthOrHeight: 512 })
    } catch { /* upload raw if compression unavailable */ }

    const fd = new FormData()
    fd.append('image', processed)
    const res = await $fetch<{ logo_url: string }>(`/api/v1/geo/establishments/${establishment.value.id}/logo/`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.accessToken}` },
      body: fd,
    })
    form.logo_url = res.logo_url
  } catch (err: any) {
    const { useToastStore } = await import('~/stores/toast')
    useToastStore().error(err.data?.error || err.data?.detail || t('common.error_server'))
  } finally {
    logoUploading.value = false
    input.value = ''
  }
}

// Delete (deactivate) the whole organization — owner only, soft delete on the
// backend (sets is_active=False; data is kept, support can restore).
const showDeleteConfirm = ref(false)
const deleting = ref(false)

const deleteOrg = async () => {
  deleting.value = true
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/geo/establishments/${establishment.value.id}/`, {
      method: 'DELETE',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.accessToken}` },
    })
    const { useToastStore } = await import('~/stores/toast')
    useToastStore().success(t('directory.form.deleted'))
    // Close the modal (and stop the spinner) BEFORE navigating: it renders via
    // <Teleport to="body">, and navigating away while it's still open orphans
    // the teleported node in <body> — leaving the loader hung over /directory.
    deleting.value = false
    showDeleteConfirm.value = false
    await nextTick()
    router.push(localePath('/directory'))
  } catch (err: any) {
    const { useToastStore } = await import('~/stores/toast')
    useToastStore().error(err.data?.detail || err.data?.message || t('common.error_server'))
    deleting.value = false
  }
}

const removeLogo = async () => {
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/geo/establishments/${establishment.value.id}/logo/`, {
      method: 'DELETE',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.accessToken}` },
    })
    form.logo_url = ''
  } catch (err: any) {
    const { useToastStore } = await import('~/stores/toast')
    useToastStore().error(err.data?.error || err.data?.detail || t('common.error_server'))
  }
}

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
      logo_url: form.logo_url,
      floor: form.floor,
      office_number: form.office_number,
      opening_hours: buildOpeningHours(),
      slug: e.slug,
      is_online: e.is_online ?? false,
      organization_type: form.organization_type,
      requires_terms_acceptance: e.requires_terms_acceptance ?? false,
      member_visibility: e.member_visibility || 'PUBLIC',
      world_object_id: linkedBuilding.value?.id || null,
      category_id: form.category_id || null,
      // Round-trip fields the form has no editor for — PUT resets these to empty
      // when omitted (`= payload.x or {}`), so echoing them prevents silent wipe.
      social_links: e.social_links || {},
      attributes: e.attributes || {},
      photos: e.photos || [],
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
    form.logo_url = e.logo_url || ''
    form.category_id = e.category_id || null
    form.organization_type = e.organization_type || ''
    form.floor = e.floor || ''
    form.office_number = e.office_number || ''
    parseOpeningHours(e.opening_hours)
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
