<template>
  <div class="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
    <Head>
      <Title>{{ $t('energy.empty.cta') }} — Parahub</Title>
    </Head>

    <NuxtLink
      :to="localePath('/energy')"
      class="inline-flex items-center gap-1 text-sm text-neutral-500 dark:text-neutral-400 hover:text-secondary dark:hover:text-secondary-400 transition-colors mb-4"
    >
      <ArrowLeft class="w-4 h-4" />
      {{ $t('energy.title') }}
    </NuxtLink>

    <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100 mb-6">
      {{ $t('energy.empty.cta') }}
    </h1>

    <!-- Step indicator -->
    <div class="flex items-center gap-2 mb-8 flex-wrap">
      <button
        v-for="(s, idx) in steps"
        :key="s.id"
        type="button"
        :class="[
          'px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
          idx === step ? 'bg-primary text-neutral-900'
            : idx < step ? 'bg-primary/20 text-secondary dark:text-primary cursor-pointer'
            : 'bg-neutral-100 dark:bg-neutral-800 text-neutral-400',
        ]"
        @click="goToStep(idx)"
      >
        {{ idx + 1 }}. {{ s.label }}
      </button>
    </div>

    <!-- ═══ Step: basics ═══ -->
    <div v-if="step === 0" class="space-y-4">
      <img src="/images/energy/cell.webp" alt="" class="mx-auto h-24 sm:h-28 w-auto object-contain" />
      <div>
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
          {{ $t('energy.form.cell_name') }} *
        </label>
        <input
          v-model="form.name"
          type="text"
          class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none"
          placeholder="e.g. Bairro Alto Solar"
        />
      </div>

      <div>
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
          {{ $t('energy.form.description') }}
        </label>
        <textarea
          v-model="form.description"
          rows="2"
          class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none resize-none"
        />
      </div>

      <div>
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
          {{ $t('energy.form.radius_km') }}
        </label>
        <select
          v-model="form.radius_km"
          class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none"
        >
          <option value="2">{{ $t('energy.form.radius_2_lv') }}</option>
          <option value="4">{{ $t('energy.form.radius_4_mv') }}</option>
        </select>
      </div>

      <div>
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
          {{ $t('energy.form.transformer_id') }}
        </label>
        <input
          v-model="form.transformer_id"
          type="text"
          placeholder="PT-XXXXXX"
          class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none"
        />
        <p class="text-xs text-neutral-400 mt-1">{{ $t('energy.form.transformer_hint') }}</p>
      </div>

      <div class="pt-2">
        <UiButton variant="primary" class="w-full" :disabled="!form.name.trim()" @click="step = 1">
          {{ $t('common.continue') }}
        </UiButton>
      </div>
    </div>

    <!-- ═══ Step: cooperative (optional) ═══ -->
    <div v-else-if="step === 1" class="space-y-4">
      <img src="/images/energy/cooperative.webp" alt="" class="mx-auto h-24 sm:h-28 w-auto object-contain" loading="lazy" />
      <p class="text-sm text-neutral-500 dark:text-neutral-400">
        {{ $t('energy.cooperative.hint') }}
      </p>

      <div>
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
          {{ $t('energy.cooperative.label') }}
        </label>
        <select
          v-if="!showNewCoopForm"
          v-model="form.establishment_id"
          class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none"
        >
          <option value="">{{ $t('energy.cooperative.none') }}</option>
          <option v-for="coop in myCooperatives" :key="coop.id" :value="coop.id">{{ coop.name }}</option>
        </select>
        <button
          v-if="!showNewCoopForm"
          type="button"
          class="text-xs text-secondary-600 dark:text-secondary-400 hover:underline mt-1"
          @click="showNewCoopForm = true"
        >
          + {{ $t('energy.cooperative.create_new') }}
        </button>
        <div v-if="showNewCoopForm" class="flex gap-2 mt-1">
          <input
            v-model="newCoopName"
            :placeholder="$t('energy.cooperative.name_placeholder')"
            class="flex-1 px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none text-neutral-900 dark:text-neutral-100"
          />
          <UiButton variant="primary" size="sm" :loading="creatingCoop" @click="createCooperative">{{ $t('common.create') }}</UiButton>
          <UiButton variant="outline" size="sm" @click="showNewCoopForm = false">{{ $t('common.cancel') }}</UiButton>
        </div>
      </div>

      <div class="flex gap-3 pt-2">
        <UiButton variant="outline" class="flex-1" @click="step = 0">{{ $t('common.back') }}</UiButton>
        <UiButton variant="primary" class="flex-1" @click="step = 2">{{ $t('common.continue') }}</UiButton>
      </div>
    </div>

    <!-- ═══ Step: location ═══ -->
    <div v-else class="space-y-4">
      <img src="/images/energy/location.webp" alt="" class="mx-auto h-24 sm:h-28 w-auto object-contain" loading="lazy" />
      <div>
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
          {{ $t('energy.form.location_hint') }} *
        </label>
        <p class="text-xs text-neutral-400 mb-2">{{ $t('energy.form.click_map') }}</p>
        <div v-if="propertiesWithCoords.length" class="flex flex-wrap gap-1.5 mb-2">
          <button
            v-for="prop in propertiesWithCoords"
            :key="prop.id"
            type="button"
            class="inline-flex items-center gap-1 px-2 py-1 rounded text-xs border border-neutral-200 dark:border-neutral-600 text-neutral-600 dark:text-neutral-300 hover:border-primary"
            @click="flyToProperty(prop)"
          >
            <Home class="w-3 h-3" /> {{ prop.name }}
          </button>
        </div>
        <div ref="mapContainer" class="w-full h-64 rounded-lg overflow-hidden border border-neutral-200 dark:border-neutral-600 cursor-crosshair" />
        <div class="flex items-center justify-between mt-1.5 gap-2">
          <div class="text-sm font-mono" :class="form.latitude !== null ? 'text-neutral-700 dark:text-neutral-300' : 'text-neutral-400'">
            {{ form.latitude !== null ? `${form.latitude.toFixed(6)}, ${form.longitude!.toFixed(6)}` : $t('mesh.no_location') }}
          </div>
          <UiButton variant="ghost" size="sm" :loading="locationLoading" :icon="LocateFixed" @click="useMyLocation">
            {{ $t('energy.form.use_location') }}
          </UiButton>
        </div>
      </div>

      <div class="flex gap-3 pt-2">
        <UiButton variant="outline" @click="step = 1">{{ $t('common.back') }}</UiButton>
        <UiButton
          variant="primary"
          class="flex-1"
          :disabled="creating || !form.name.trim() || form.latitude === null"
          :loading="creating"
          @click="createCell"
        >
          {{ $t('common.create') }}
        </UiButton>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onActivated, onDeactivated, onUnmounted } from 'vue'
import { ArrowLeft, Home, LocateFixed } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'
import { useToastStore } from '~/stores/toast'
import { ZAP_GLYPH } from '~/composables/useMapToggleableLayer'
import { ENERGY_STATUS_COLORS } from '~/composables/useMapIoTLayers'
import { createDeviceHexElement } from '~/utils/pickerMarker'

definePageMeta({
  middleware: 'auth',
})

const { t } = useI18n()
const router = useRouter()
const localePath = useLocalePath()
const colorMode = useColorMode()
const authStore = useAuthStore()
const toastStore = useToastStore()
const propertyStore = usePropertyStore()

const step = ref(0)
const creating = ref(false)
const locationLoading = ref(false)

const form = ref({
  name: '',
  description: '',
  radius_km: 2,
  transformer_id: '',
  latitude: null as number | null,
  longitude: null as number | null,
  establishment_id: '' as string,
})

const myCooperatives = ref<any[]>([])
const showNewCoopForm = ref(false)
const newCoopName = ref('')
const creatingCoop = ref(false)

const steps = computed(() => [
  { id: 'basics', label: t('energy.form.step_basics') },
  { id: 'cooperative', label: t('energy.cooperative.step_label') },
  { id: 'location', label: t('energy.form.step_location') },
])

const goToStep = (idx: number) => {
  if (idx < step.value) step.value = idx
}

const fetchMyCooperatives = async () => {
  try {
    await authStore.ensureToken()
    const data = await $fetch<{ items: any[]; count: number }>('/api/v1/geo/establishments/', {
      params: { organization_type: 'COOPERATIVE', my: 'true' },
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    myCooperatives.value = data?.items || []
  } catch { myCooperatives.value = [] }
}

const createCooperative = async () => {
  if (!newCoopName.value.trim()) return
  creatingCoop.value = true
  try {
    await authStore.ensureToken()
    const est = await $fetch<any>('/api/v1/geo/establishments/', {
      method: 'POST',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
      body: { name: newCoopName.value.trim(), organization_type: 'COOPERATIVE' },
    })
    toastStore.success(t('energy.cooperative.created'))
    myCooperatives.value.push(est)
    form.value.establishment_id = est.id
    showNewCoopForm.value = false
    newCoopName.value = ''
  } catch (e: any) {
    toastStore.error(e?.data?.detail || t('common.error'))
  } finally { creatingCoop.value = false }
}

// ── Location map (mounts when the location step is visible) ──
const mapContainer = ref<HTMLElement | null>(null)
let map: any = null
let marker: any = null
let maplibregl: any = null

const propertiesWithCoords = computed(() =>
  propertyStore.properties.filter(p => p.latitude && p.longitude)
)

// The picker places the same OFFLINE energy hex the new cell will wear on /map.
const newCellMarker = () =>
  new maplibregl.Marker({ element: createDeviceHexElement(ENERGY_STATUS_COLORS.OFFLINE, ZAP_GLYPH), anchor: 'center' })

const placeMarker = (lng: number, lat: number) => {
  form.value.latitude = Math.round(lat * 1e6) / 1e6
  form.value.longitude = Math.round(lng * 1e6) / 1e6
  if (marker) {
    marker.setLngLat([lng, lat])
  } else if (map && maplibregl) {
    marker = newCellMarker().setLngLat([lng, lat]).addTo(map)
  }
}

const flyToProperty = (prop: { latitude: number; longitude: number }) => {
  if (map) map.flyTo({ center: [prop.longitude, prop.latitude], zoom: 17, essential: true, speed: 4.5 })
  placeMarker(prop.longitude, prop.latitude)
}

const useMyLocation = () => {
  if (!navigator.geolocation) return
  locationLoading.value = true
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      if (map) map.flyTo({ center: [pos.coords.longitude, pos.coords.latitude], zoom: 17, essential: true, speed: 4.5 })
      placeMarker(pos.coords.longitude, pos.coords.latitude)
      locationLoading.value = false
    },
    () => {
      toastStore.error(t('energy.form.location_error'))
      locationLoading.value = false
    },
  )
}

const getStyleUrl = () =>
  colorMode.value === 'dark'
    ? '/map-styles/dark-liberty-parahub.json'
    : '/map-styles/liberty-parahub.json'

async function initMap() {
  if (!mapContainer.value || map) return
  const mod = await import('maplibre-gl')
  maplibregl = mod.default || mod
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
  if (form.value.latitude !== null && form.value.longitude !== null) {
    marker = newCellMarker()
      .setLngLat([form.value.longitude, form.value.latitude])
      .addTo(map)
  }
}

function destroyMap() {
  if (map) { map.remove(); map = null; marker = null }
}

watch(
  () => step.value === 2,
  async (active) => {
    if (active) { await nextTick(); initMap() } else { destroyMap() }
  },
)

onUnmounted(destroyMap)

// Pages are KeepAlive-cached (app.vue): onActivated fires on first mount AND on
// cached re-entry; onDeactivated releases the GL context while the page is cached.
onActivated(async () => {
  fetchMyCooperatives()
  propertyStore.fetchProperties()
  if (step.value === 2) { await nextTick(); initMap() }
})
onDeactivated(destroyMap)

const createCell = async () => {
  if (!form.value.name.trim() || form.value.latitude === null) return
  creating.value = true
  try {
    await authStore.ensureToken()
    const cell = await $fetch<any>('/api/v1/energy/cells/', {
      method: 'POST',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
      body: {
        name: form.value.name.trim(),
        description: form.value.description,
        radius_km: form.value.radius_km,
        transformer_id: form.value.transformer_id,
        latitude: form.value.latitude,
        longitude: form.value.longitude,
        establishment_id: form.value.establishment_id || undefined,
      },
    })
    toastStore.success(t('energy.form.created'))
    // Reset wizard state before leaving: pages are KeepAlive-cached, so the
    // next visit re-enters this same instance.
    form.value = { name: '', description: '', radius_km: 2, transformer_id: '', latitude: null, longitude: null, establishment_id: '' }
    showNewCoopForm.value = false
    newCoopName.value = ''
    step.value = 0
    router.push(localePath(`/energy/${cell.id}`))
  } catch (e: any) {
    toastStore.error(e?.data?.detail || t('common.error'))
  } finally {
    creating.value = false
  }
}

</script>
