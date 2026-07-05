<template>
  <div>
    <Head>
      <Title>{{ $t('transit_manage.routes_title') }}</Title>
    </Head>

    <!-- Staff check -->
    <div v-if="!isStaff" class="text-center py-20">
      <ShieldAlert class="w-12 h-12 text-neutral-400 mx-auto mb-4" />
      <p class="text-neutral-500">{{ $t('dispatch.staff_only') }}</p>
    </div>

    <div v-else class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-5">
      <!-- Header -->
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div class="flex items-center gap-3">
          <div class="dispatch-icon" style="background: rgba(59,130,246,0.15); color: #3b82f6;">
            <RouteIcon class="w-5 h-5" />
          </div>
          <div>
            <h1 class="text-xl font-bold text-neutral-900 dark:text-neutral-100">{{ $t('transit_manage.routes_heading') }}</h1>
            <p class="text-xs text-neutral-500 dark:text-neutral-400">{{ $t('transit_manage.routes_subtitle') }}</p>
          </div>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <!-- Agency selector -->
          <select
            v-if="store.agencies.length > 1"
            v-model="selectedAgencyId"
            class="form-input text-sm"
            @change="onAgencyChange"
          >
            <option v-for="a in store.agencies" :key="a.id" :value="a.id">{{ a.name }}</option>
          </select>
          <NuxtLink :to="localePath('/dispatch/assignments')" class="btn-sm btn-outline">
            <Radio class="w-3.5 h-3.5" /> {{ $t('dispatch.title') }}
          </NuxtLink>
          <UiButton variant="primary" size="sm" :icon="Plus" @click="showCreateRoute = true">
            {{ $t('transit_manage.new_route') }}
          </UiButton>
        </div>
      </div>

      <!-- No agency -->
      <div v-if="!store.agencies.length && !store.loading" class="text-center py-12">
        <Building2 class="w-12 h-12 text-neutral-300 dark:text-neutral-600 mx-auto mb-3" />
        <p class="text-neutral-500 dark:text-neutral-400 text-sm mb-4">{{ $t('transit_manage.no_agency') }}</p>
        <UiButton variant="primary" size="sm" @click="showCreateAgency = true">
          {{ $t('transit_manage.create_agency') }}
        </UiButton>
      </div>

      <!-- Loading -->
      <div v-else-if="store.loading" class="flex justify-center py-12">
        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100" />
      </div>

      <!-- Route list -->
      <template v-else-if="store.routes.length">
        <!-- Sub-nav: Routes | Stops -->
        <div class="flex gap-2 border-b border-neutral-200 dark:border-neutral-700 pb-2">
          <NuxtLink :to="localePath('/dispatch/routes')" class="tab-active text-sm font-medium px-3 py-1.5">
            <RouteIcon class="w-3.5 h-3.5 inline mr-1" /> {{ $t('transit_manage.routes') }} ({{ store.routes.length }})
          </NuxtLink>
          <NuxtLink :to="localePath('/dispatch/stops')" class="tab-inactive text-sm px-3 py-1.5 text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300">
            <MapPin class="w-3.5 h-3.5 inline mr-1" /> {{ $t('transit_manage.stops') }} ({{ store.stops.length }})
          </NuxtLink>
        </div>

        <div class="space-y-2">
          <div
            v-for="r in store.routes"
            :key="r.id"
            class="card p-0 flex items-stretch cursor-pointer hover:border-neutral-300 dark:hover:border-neutral-600 transition-colors"
            @click="editRoute = r"
          >
            <!-- Color stripe -->
            <div class="w-1 rounded-l shrink-0" :style="{ backgroundColor: `#${r.route_color || '6b7280'}` }" />
            <div class="flex-1 p-3 min-w-0">
              <div class="flex items-center gap-2 mb-1">
                <span
                  class="route-badge text-xs"
                  :style="{ backgroundColor: `#${r.route_color}`, color: getContrastColor(r.route_color) }"
                >
                  {{ r.short_name }}
                </span>
                <span class="text-sm text-neutral-700 dark:text-neutral-300 truncate">{{ r.long_name }}</span>
                <UiBadge v-if="r.has_shape" variant="success" type="dot" size="sm">shape</UiBadge>
              </div>
              <div class="flex gap-4 text-xs text-neutral-500 dark:text-neutral-400">
                <span><ArrowRight class="w-3 h-3 inline" /> {{ r.stops_outbound.length }} {{ $t('transit_manage.stops_out') }}</span>
                <span v-if="r.stops_inbound.length"><ArrowLeft class="w-3 h-3 inline" /> {{ r.stops_inbound.length }} {{ $t('transit_manage.stops_in') }}</span>
                <span class="capitalize">{{ routeTypeLabel(r.route_type) }}</span>
              </div>
            </div>
            <div class="flex items-center pr-3">
              <ChevronRight class="w-4 h-4 text-neutral-400" />
            </div>
          </div>
        </div>
      </template>

      <!-- Empty routes -->
      <div v-else class="text-center py-12">
        <RouteIcon class="w-12 h-12 text-neutral-300 dark:text-neutral-600 mx-auto mb-3" />
        <p class="text-neutral-500 dark:text-neutral-400 text-sm">{{ $t('transit_manage.no_routes') }}</p>
        <UiButton variant="outline" size="sm" :icon="Plus" class="mt-4" @click="showCreateRoute = true">
          {{ $t('transit_manage.new_route') }}
        </UiButton>
      </div>

      <!-- GTFS Export link -->
      <div v-if="store.selectedAgency?.data_source_slug" class="card p-3 flex items-center gap-3">
        <Download class="w-4 h-4 text-neutral-400 shrink-0" />
        <div class="flex-1 min-w-0 text-sm overflow-hidden">
          <span class="text-neutral-700 dark:text-neutral-300">GTFS</span>
          <a
            :href="`/api/v1/geo/transit/manage/gtfs/export/${store.selectedAgency.id}/`"
            class="text-secondary hover:underline ml-2"
            target="_blank"
          >{{ $t('transit_manage.download_gtfs') }}</a>
          <span class="text-neutral-400 mx-2 hidden sm:inline">|</span>
          <span class="text-neutral-500 block sm:inline mt-1 sm:mt-0">GTFS-RT:
            <code class="text-xs break-all">/api/v1/geo/transit/gtfs-rt/vehicle-positions/{{ store.selectedAgency.data_source_slug }}/</code>
          </span>
        </div>
      </div>
    </div>

    <!-- Create Agency Modal -->
    <Modal v-model="showCreateAgency" :title="$t('transit_manage.create_agency')">
      <form @submit.prevent="handleCreateAgency" class="space-y-4">
        <div>
          <label class="form-label">{{ $t('transit_manage.agency_name') }}</label>
          <input v-model="agencyForm.name" type="text" class="form-input w-full" required />
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label class="form-label">{{ $t('transit_manage.timezone') }}</label>
            <input v-model="agencyForm.timezone" type="text" class="form-input w-full" />
          </div>
          <div>
            <label class="form-label">{{ $t('transit_manage.language') }}</label>
            <input v-model="agencyForm.lang" type="text" class="form-input w-full" maxlength="5" />
          </div>
        </div>
        <UiButton type="submit" variant="primary" class="w-full" :loading="creating">
          {{ $t('transit_manage.create_agency') }}
        </UiButton>
      </form>
    </Modal>

    <!-- Create Route Modal -->
    <Modal v-model="showCreateRoute" :title="$t('transit_manage.new_route')">
      <form @submit.prevent="handleCreateRoute" class="space-y-4">
        <div>
          <label class="form-label">{{ $t('transit_manage.route_name') }}</label>
          <input v-model="routeForm.short_name" type="text" class="form-input w-full" required placeholder="e.g. 42" />
        </div>
        <div>
          <label class="form-label">{{ $t('transit_manage.route_long_name') }}</label>
          <input v-model="routeForm.long_name" type="text" class="form-input w-full" placeholder="e.g. Airport — Downtown" />
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label class="form-label">{{ $t('transit_manage.route_type') }}</label>
            <select v-model.number="routeForm.route_type" class="form-input w-full">
              <option :value="3">Bus</option>
              <option :value="0">Tram</option>
              <option :value="1">Metro</option>
              <option :value="2">Rail</option>
              <option :value="4">Ferry</option>
              <option :value="7">Funicular</option>
            </select>
          </div>
          <div>
            <label class="form-label">{{ $t('transit_manage.route_color') }}</label>
            <div class="flex items-center gap-2">
              <input v-model="routeForm.route_color" type="color" class="w-8 h-8 rounded cursor-pointer border-0 p-0" />
              <input v-model="routeColorHex" type="text" class="form-input flex-1 font-mono text-sm" maxlength="7" placeholder="#3b82f6" />
            </div>
          </div>
        </div>
        <UiButton type="submit" variant="primary" class="w-full" :loading="creating">
          {{ $t('transit_manage.create_route') }}
        </UiButton>
      </form>
    </Modal>

    <!-- Route Editor Modal -->
    <Modal v-model="showRouteEditor" :title="editRoute?.short_name ? `${$t('transit_manage.edit_route')}: ${editRoute.short_name}` : ''" size="lg">
      <div v-if="editRoute" class="space-y-4">
        <!-- Metadata -->
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label class="form-label">{{ $t('transit_manage.route_name') }}</label>
            <input v-model="editRoute.short_name" type="text" class="form-input w-full" />
          </div>
          <div>
            <label class="form-label">{{ $t('transit_manage.route_long_name') }}</label>
            <input v-model="editRoute.long_name" type="text" class="form-input w-full" />
          </div>
        </div>

        <!-- Direction tabs -->
        <UiTabs v-model="editDirection" :tabs="dirTabs" variant="pills" />

        <!-- Stops for current direction -->
        <div class="space-y-1.5">
          <div class="flex items-center justify-between">
            <span class="text-sm font-medium text-neutral-700 dark:text-neutral-300">
              {{ $t('transit_manage.stop_sequence') }} ({{ currentStops.length }})
            </span>
            <UiButton variant="outline" size="sm" :icon="Plus" @click="showAddStop = true">
              {{ $t('transit_manage.add_stop') }}
            </UiButton>
          </div>

          <div v-if="!currentStops.length" class="text-center py-8 text-neutral-500 text-sm">
            {{ $t('transit_manage.no_stops_yet') }}
          </div>

          <TransitionGroup v-else name="card-list" tag="div" class="space-y-1">
            <div
              v-for="(s, idx) in currentStops"
              :key="s.stop_id"
              class="flex items-center gap-2 p-2 rounded border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800"
            >
              <span class="text-xs font-mono text-neutral-400 w-5 text-right">{{ idx + 1 }}</span>
              <MapPin class="w-3.5 h-3.5 text-neutral-400 shrink-0" />
              <span class="flex-1 text-sm text-neutral-700 dark:text-neutral-300 truncate">{{ s.stop_name }}</span>
              <button
                v-if="idx > 0"
                :aria-label="$t('transit_manage.move_stop_up')"
                class="p-2 text-neutral-400 hover:text-neutral-600 min-w-[44px] min-h-[44px] flex items-center justify-center"
                @click="moveStop(idx, -1)"
              ><ArrowUp class="w-4 h-4" /></button>
              <button
                v-if="idx < currentStops.length - 1"
                :aria-label="$t('transit_manage.move_stop_down')"
                class="p-2 text-neutral-400 hover:text-neutral-600 min-w-[44px] min-h-[44px] flex items-center justify-center"
                @click="moveStop(idx, 1)"
              ><ArrowDown class="w-4 h-4" /></button>
              <button
                :aria-label="$t('transit_manage.remove_stop')"
                class="p-2 text-red-400 hover:text-red-600 min-w-[44px] min-h-[44px] flex items-center justify-center"
                @click="removeStop(idx)"
              ><X class="w-4 h-4" /></button>
            </div>
          </TransitionGroup>
        </div>

        <!-- Actions -->
        <div class="flex gap-2 pt-2 border-t border-neutral-200 dark:border-neutral-700">
          <UiButton variant="primary" :loading="saving" @click="saveRoute" class="flex-1">
            {{ $t('transit_manage.save') }}
          </UiButton>
          <UiButton variant="error" :aria-label="$t('transit_manage.delete_route')" @click="showDeleteRouteConfirm = true">
            <Trash2 class="w-4 h-4" />
          </UiButton>
        </div>
      </div>
    </Modal>

    <!-- Add Stop to Route Modal -->
    <Modal v-model="showAddStop" :title="$t('transit_manage.add_stop')">
      <div class="space-y-3">
        <input
          v-model="stopSearchQuery"
          type="text"
          :placeholder="$t('transit_manage.search_stops')"
          class="form-input w-full"
          @input="debouncedSearchStops"
        />
        <div class="max-h-64 overflow-y-auto space-y-1">
          <button
            v-for="s in filteredStops"
            :key="s.id"
            class="w-full text-left p-2 rounded flex items-center gap-2"
            :class="currentStopIds.has(s.id) ? 'opacity-50 cursor-default' : 'hover:bg-neutral-50 dark:hover:bg-neutral-800'"
            @click="!currentStopIds.has(s.id) && addStopToRoute(s)"
          >
            <MapPin class="w-3.5 h-3.5 shrink-0" :class="currentStopIds.has(s.id) ? 'text-green-500' : 'text-neutral-400'" />
            <span class="text-sm flex-1 truncate" :class="currentStopIds.has(s.id) ? 'text-neutral-400 dark:text-neutral-500' : 'text-neutral-700 dark:text-neutral-300'">{{ s.name }}</span>
            <Check v-if="currentStopIds.has(s.id)" class="w-3.5 h-3.5 text-green-500 shrink-0" />
            <span v-else class="text-xs font-mono text-neutral-400">{{ s.lat.toFixed(4) }}, {{ s.lon.toFixed(4) }}</span>
          </button>
        </div>
        <div class="border-t border-neutral-200 dark:border-neutral-700 pt-3">
          <NuxtLink :to="localePath('/dispatch/stops')" class="text-sm text-secondary hover:underline">
            {{ $t('transit_manage.manage_stops') }}
          </NuxtLink>
        </div>
      </div>
    </Modal>

    <UiConfirmModal
      v-model="showDeleteRouteConfirm"
      :title="$t('transit_manage.delete_route')"
      :message="$t('transit_manage.confirm_delete_route')"
      :icon="Trash2"
      variant="error"
      :confirm-label="$t('common.delete')"
      @confirm="confirmDeleteRoute"
    />
  </div>
</template>

<script setup lang="ts">
import {
  ShieldAlert, Plus, RouteIcon, Radio, MapPin, ChevronRight,
  ArrowRight, ArrowLeft, ArrowUp, ArrowDown, X, Download,
  Building2, Trash2, Check,
} from 'lucide-vue-next'
import { useTransitManageStore, type ManagedRoute, type ManagedStop, type RouteStopItem } from '~/stores/transitManage'

const { t } = useI18n()
const localePath = useLocalePath()
const store = useTransitManageStore()
const authStore = useAuthStore()
const isStaff = computed(() => authStore.user?.is_staff)

// --- State ---
const selectedAgencyId = ref('')
const showCreateAgency = ref(false)
const showCreateRoute = ref(false)
const showRouteEditor = ref(false)
const showAddStop = ref(false)
const creating = ref(false)
const saving = ref(false)
const editDirection = ref('outbound')
const stopSearchQuery = ref('')

const agencyForm = reactive({ name: '', timezone: 'Europe/Lisbon', lang: 'pt' })
const routeForm = reactive({ short_name: '', long_name: '', route_type: 3, route_color: '#3b82f6' })

const routeColorHex = computed({
  get: () => `#${routeForm.route_color.replace('#', '')}`,
  set: (v: string) => { routeForm.route_color = v },
})

const dirTabs = computed(() => [
  { value: 'outbound', label: t('transit_manage.outbound') },
  { value: 'inbound', label: t('transit_manage.inbound') },
])

// Edit route
const editRoute = ref<ManagedRoute | null>(null)
const showDeleteRouteConfirm = ref(false)

watch(editRoute, (r) => {
  if (r) {
    showRouteEditor.value = true
    editDirection.value = 'outbound'
    if (store.selectedAgency) store.fetchStops(store.selectedAgency.id)
  }
})

const currentStops = computed(() => {
  if (!editRoute.value) return []
  return editDirection.value === 'inbound'
    ? editRoute.value.stops_inbound
    : editRoute.value.stops_outbound
})

function moveStop(idx: number, delta: number) {
  const arr = editDirection.value === 'inbound' ? editRoute.value!.stops_inbound : editRoute.value!.stops_outbound
  const target = idx + delta
  if (target < 0 || target >= arr.length) return
  const tmp = arr[idx]
  arr[idx] = arr[target]
  arr[target] = tmp
}

function removeStop(idx: number) {
  const arr = editDirection.value === 'inbound' ? editRoute.value!.stops_inbound : editRoute.value!.stops_outbound
  arr.splice(idx, 1)
}

function addStopToRoute(s: ManagedStop) {
  if (!editRoute.value) return
  const arr = editDirection.value === 'inbound' ? editRoute.value.stops_inbound : editRoute.value.stops_outbound
  arr.push({
    stop_id: s.id,
    stop_name: s.name,
    lat: s.lat,
    lon: s.lon,
    sequence: arr.length + 1,
  })
  showAddStop.value = false
}

const currentStopIds = computed(() => new Set(currentStops.value.map(s => s.stop_id)))

const filteredStops = computed(() => {
  const q = stopSearchQuery.value.toLowerCase()
  return q ? store.stops.filter(s => s.name.toLowerCase().includes(q)) : store.stops
})

let searchTimeout: ReturnType<typeof setTimeout>
function debouncedSearchStops() {
  clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => {
    if (store.selectedAgency) store.fetchStops(store.selectedAgency.id, stopSearchQuery.value)
  }, 300)
}

// --- Handlers ---
async function handleCreateAgency() {
  creating.value = true
  try {
    await store.createAgency(agencyForm)
    showCreateAgency.value = false
    selectedAgencyId.value = store.selectedAgency?.id || ''
    loadData()
  } finally {
    creating.value = false
  }
}

async function handleCreateRoute() {
  if (!store.selectedAgency) return
  creating.value = true
  try {
    const color = routeForm.route_color.replace('#', '')
    await store.createRoute({
      agency_id: store.selectedAgency.id,
      short_name: routeForm.short_name,
      long_name: routeForm.long_name,
      route_type: routeForm.route_type,
      route_color: color,
    })
    showCreateRoute.value = false
    routeForm.short_name = ''
    routeForm.long_name = ''
  } finally {
    creating.value = false
  }
}

async function saveRoute() {
  if (!editRoute.value) return
  saving.value = true
  try {
    // Update metadata
    await store.updateRoute(editRoute.value.id, {
      short_name: editRoute.value.short_name,
      long_name: editRoute.value.long_name,
    })

    // Update outbound stops
    if (editRoute.value.stops_outbound.length) {
      const stops = editRoute.value.stops_outbound.map((s, i) => ({ stop_id: s.stop_id, sequence: i + 1 }))
      await store.updateRouteStops(editRoute.value.id, 0, stops)
    }

    // Update inbound stops
    if (editRoute.value.stops_inbound.length) {
      const stops = editRoute.value.stops_inbound.map((s, i) => ({ stop_id: s.stop_id, sequence: i + 1 }))
      await store.updateRouteStops(editRoute.value.id, 1, stops)
    }

    showRouteEditor.value = false
    editRoute.value = null
    if (store.selectedAgency) await store.fetchRoutes(store.selectedAgency.id)
  } finally {
    saving.value = false
  }
}

async function confirmDeleteRoute() {
  if (!editRoute.value) return
  showDeleteRouteConfirm.value = false
  await store.deleteRoute(editRoute.value.id)
  showRouteEditor.value = false
  editRoute.value = null
}

function onAgencyChange() {
  store.selectedAgency = store.agencies.find(a => a.id === selectedAgencyId.value) || null
  loadData()
}

async function loadData() {
  if (!store.selectedAgency) return
  selectedAgencyId.value = store.selectedAgency.id
  await Promise.all([
    store.fetchRoutes(store.selectedAgency.id),
    store.fetchStops(store.selectedAgency.id),
  ])
}

function getContrastColor(hex: string) {
  if (!hex) return '#fff'
  const r = parseInt(hex.substring(0, 2), 16)
  const g = parseInt(hex.substring(2, 4), 16)
  const b = parseInt(hex.substring(4, 6), 16)
  return (r * 299 + g * 587 + b * 114) / 1000 > 128 ? '#000' : '#fff'
}

function routeTypeLabel(t: number) {
  const map: Record<number, string> = { 0: 'tram', 1: 'metro', 2: 'rail', 3: 'bus', 4: 'ferry', 7: 'funicular' }
  return map[t] || 'other'
}

// --- Init ---
onMounted(async () => {
  await store.fetchAgencies()
  if (store.selectedAgency) await loadData()
})
</script>

<style scoped>
.dispatch-icon {
  @apply w-10 h-10 rounded-lg flex items-center justify-center;
  background: rgba(250, 204, 21, 0.15);
  color: rgb(234, 179, 8);
}

.route-badge {
  @apply px-2 py-0.5 rounded font-bold text-xs tabular-nums whitespace-nowrap;
}

.tab-active {
  @apply border-b-2 border-primary text-neutral-900 dark:text-neutral-100;
}

.card-list-enter-active,
.card-list-leave-active { transition: all 0.2s ease; }
.card-list-enter-from,
.card-list-leave-to { opacity: 0; transform: translateY(-8px); }
</style>
