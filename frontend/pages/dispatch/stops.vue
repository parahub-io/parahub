<template>
  <div>
    <Head>
      <Title>{{ $t('transit_manage.stops_title') }}</Title>
    </Head>

    <!-- Access check: stops belong to the operator that runs them -->
    <div v-if="checked && !canManage" class="text-center py-20">
      <ShieldAlert class="w-12 h-12 text-neutral-400 mx-auto mb-4" />
      <p class="text-neutral-500">{{ $t('dispatch.no_operator') }}</p>
      <p class="mt-1 text-sm text-neutral-400 max-w-md mx-auto">{{ $t('dispatch.no_operator_hint') }}</p>
    </div>

    <div v-else class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-5">
      <PageHeader
        :title="$t('dispatch.title')"
        :subtitle="$t('transit_manage.stops_subtitle')"
        :create-label="store.selectedAgency ? $t('transit_manage.new_stop') : undefined"
        class="!mb-0"
        @create="showCreate = true"
      />

      <UiRouteTabs :tabs="dispatchTabs" />

      <!-- Search -->
      <input
        v-model="searchQuery"
        type="text"
        :placeholder="$t('transit_manage.search_stops')"
        class="form-input w-full"
        @input="debouncedSearch"
      />

      <!-- Stops list -->
      <div v-if="store.loading" class="flex justify-center py-12" role="status">
        <div class="animate-spin rounded-full h-12 w-12 border-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-white" />
        <span class="sr-only">{{ $t('common.loading') }}</span>
      </div>

      <div
        v-else-if="filteredStops.length"
        class="border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700"
      >
        <div
          v-for="s in filteredStops"
          :key="s.id"
          class="p-3 flex items-center gap-3 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors"
        >
          <MapPin class="w-4 h-4 text-success shrink-0" />
          <div class="flex-1 min-w-0">
            <div v-if="editingStopId === s.id" class="flex items-center gap-2">
              <input v-model="editStopName" type="text" class="form-input flex-1 text-sm" @keyup.enter="saveStopEdit(s)" />
              <button :aria-label="$t('transit_manage.save_edit')" class="text-success p-1" @click="saveStopEdit(s)"><Check class="w-4 h-4" /></button>
              <button :aria-label="$t('transit_manage.cancel_edit')" class="text-neutral-400 p-1" @click="editingStopId = ''"><X class="w-4 h-4" /></button>
            </div>
            <template v-else>
              <span class="text-sm text-neutral-800 dark:text-neutral-200">{{ s.name }}</span>
              <span class="text-xs text-neutral-400 ml-2 font-mono tabular-nums hidden sm:inline">{{ s.lat.toFixed(5) }}, {{ s.lon.toFixed(5) }}</span>
            </template>
          </div>
          <div class="flex items-center shrink-0">
            <button :aria-label="$t('transit_manage.edit_stop')" class="p-2 text-neutral-400 hover:text-neutral-600 min-w-[44px] min-h-[44px] flex items-center justify-center" @click="startEditStop(s)">
              <Pencil class="w-4 h-4" />
            </button>
            <button
              :aria-label="pendingDeleteStopId === s.id ? $t('common.confirm') : $t('transit_manage.delete_stop')"
              class="p-2 min-w-[44px] min-h-[44px] flex items-center justify-center transition-colors"
              :class="pendingDeleteStopId === s.id ? 'text-white bg-error rounded' : 'text-error hover:text-error-600'"
              @click="handleDeleteStop(s.id)"
            >
              <component :is="pendingDeleteStopId === s.id ? Check : Trash2" class="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      <div v-else class="text-center py-12">
        <img src="/images/para/searching.webp" alt="Para" class="mx-auto h-32 w-auto mb-3">
        <p class="text-neutral-500 dark:text-neutral-400 text-sm">{{ $t('transit_manage.no_stops') }}</p>
      </div>
    </div>

    <!-- Create Stop Modal -->
    <Modal v-model="showCreate" :title="$t('transit_manage.new_stop')" size="lg">
      <form @submit.prevent="handleCreate" class="space-y-4">
        <div>
          <label class="form-label">{{ $t('transit_manage.stop_name') }}</label>
          <input v-model="createForm.name" type="text" class="form-input w-full" required placeholder="e.g. Main Station" />
        </div>
        <!-- Inline map for stop placement -->
        <div>
          <div ref="createMapEl" class="w-full h-48 rounded-lg overflow-hidden border border-neutral-200 dark:border-neutral-600" />
          <p class="text-xs text-neutral-500 mt-1">{{ $t('transit_manage.coords_hint') }}</p>
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label class="form-label">{{ $t('transit_manage.latitude') }}</label>
            <input v-model.number="createForm.lat" type="number" step="any" class="form-input w-full" required />
          </div>
          <div>
            <label class="form-label">{{ $t('transit_manage.longitude') }}</label>
            <input v-model.number="createForm.lon" type="number" step="any" class="form-input w-full" required />
          </div>
        </div>
        <UiButton type="submit" variant="primary" class="w-full" :loading="creating">
          {{ $t('transit_manage.create_stop') }}
        </UiButton>
      </form>
    </Modal>
  </div>
</template>

<script setup lang="ts">
import {
  ShieldAlert, MapPin, Pencil, Trash2, Check, X,
} from 'lucide-vue-next'
import { useTransitManageStore, type ManagedStop } from '~/stores/transitManage'

definePageMeta({
  middleware: 'auth',
})

const colorMode = useColorMode()
const store = useTransitManageStore()
const authStore = useAuthStore()
const isStaff = computed(() => authStore.user?.is_staff)
// The agency list is the access answer — see dispatch/routes.vue
const checked = ref(false)
const canManage = computed(() => isStaff.value || store.agencies.length > 0)
const dispatchTabs = useDispatchTabs()

const showCreate = ref(false)
const creating = ref(false)
const searchQuery = ref('')
const editingStopId = ref('')
const editStopName = ref('')
const pendingDeleteStopId = ref<string | null>(null)
let pendingDeleteStopTimer: ReturnType<typeof setTimeout> | null = null

const createForm = reactive({ name: '', lat: 0, lon: 0 })

// --- Inline map for stop creation ---
const createMapEl = ref<HTMLElement | null>(null)
let createMap: any = null
let createMarker: any = null

const getStyleUrl = () =>
  colorMode.value === 'dark'
    ? '/map-styles/dark-liberty-parahub.json'
    : '/map-styles/liberty-parahub.json'

function destroyCreateMap() {
  if (createMap) { createMap.remove(); createMap = null }
  createMarker = null
}

async function initCreateMap() {
  await nextTick()
  if (!createMapEl.value) return

  const mod = await import('maplibre-gl')
  const maplibregl = mod.default || mod
  await import('maplibre-gl/dist/maplibre-gl.css')

  const { mapCenter, mapZoom } = useMapState()
  const hasCoords = createForm.lat !== 0 || createForm.lon !== 0
  const center: [number, number] = hasCoords
    ? [createForm.lon, createForm.lat]
    : mapCenter.value
  const zoom = hasCoords ? 15 : mapZoom.value

  createMap = new maplibregl.Map({
    container: createMapEl.value,
    style: getStyleUrl(),
    center,
    zoom,
    attributionControl: false,
    fadeDuration: 0,
  })

  createMap.once('load', () => createMap.resize())

  if (hasCoords) {
    createMarker = new maplibregl.Marker({ color: '#10b981' })
      .setLngLat([createForm.lon, createForm.lat])
      .addTo(createMap)
  }

  createMap.on('click', (e: any) => {
    const { lng, lat } = e.lngLat
    createForm.lat = Math.round(lat * 1e6) / 1e6
    createForm.lon = Math.round(lng * 1e6) / 1e6

    if (createMarker) {
      createMarker.setLngLat([lng, lat])
    } else {
      createMarker = new maplibregl.Marker({ color: '#10b981' })
        .setLngLat([lng, lat])
        .addTo(createMap)
    }
  })
}

watch(showCreate, (open) => {
  if (open) {
    initCreateMap()
  } else {
    destroyCreateMap()
  }
})

onUnmounted(() => {
  destroyCreateMap()
})

const filteredStops = computed(() => {
  const q = searchQuery.value.toLowerCase()
  return q ? store.stops.filter(s => s.name.toLowerCase().includes(q)) : store.stops
})

let searchTimeout: ReturnType<typeof setTimeout>
function debouncedSearch() {
  clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => {
    if (store.selectedAgency) store.fetchStops(store.selectedAgency.id, searchQuery.value)
  }, 300)
}

function startEditStop(s: ManagedStop) {
  editingStopId.value = s.id
  editStopName.value = s.name
}

async function saveStopEdit(s: ManagedStop) {
  await store.updateStop(s.id, { name: editStopName.value })
  editingStopId.value = ''
}

async function handleCreate() {
  if (!store.selectedAgency) return
  creating.value = true
  try {
    await store.createStop({
      agency_id: store.selectedAgency.id,
      name: createForm.name,
      lat: createForm.lat,
      lon: createForm.lon,
    })
    showCreate.value = false
    createForm.name = ''
    createForm.lat = 0
    createForm.lon = 0
  } finally {
    creating.value = false
  }
}

async function handleDeleteStop(id: string) {
  if (pendingDeleteStopId.value !== id) {
    pendingDeleteStopId.value = id
    if (pendingDeleteStopTimer) clearTimeout(pendingDeleteStopTimer)
    pendingDeleteStopTimer = setTimeout(() => { pendingDeleteStopId.value = null }, 3000)
    return
  }
  pendingDeleteStopId.value = null
  if (pendingDeleteStopTimer) clearTimeout(pendingDeleteStopTimer)
  try {
    await store.deleteStop(id)
  } catch (e: any) {
    useToastStore().error(e.data?.detail || 'Failed to delete')
  }
}

onMounted(async () => {
  await store.fetchAgencies()
  checked.value = true
  if (store.selectedAgency) {
    await store.fetchStops(store.selectedAgency.id)
  }
})
</script>
