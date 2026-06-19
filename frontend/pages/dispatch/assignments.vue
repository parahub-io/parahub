<template>
  <div>
    <Head>
      <Title>{{ $t('dispatch.page_title') }}</Title>
    </Head>

    <!-- Access denied -->
    <div v-if="!isStaff" class="text-center py-20">
      <ShieldAlert class="w-12 h-12 text-neutral-400 mx-auto mb-4" />
      <p class="text-neutral-500">{{ $t('dispatch.staff_only') }}</p>
    </div>

    <div v-else class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-5">
      <!-- Header row -->
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div class="flex items-center gap-3">
          <div class="dispatch-icon">
            <Radio class="w-5 h-5" />
          </div>
          <div>
            <h1 class="text-xl font-bold text-neutral-900 dark:text-neutral-100">{{ $t('dispatch.title') }}</h1>
            <p class="text-xs text-neutral-500 dark:text-neutral-400">{{ $t('dispatch.subtitle') }}</p>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <input
            v-model="store.selectedDate"
            type="date"
            class="dispatch-date-input"
            @change="reload"
          />
          <UiButton variant="primary" size="sm" :icon="Plus" @click="showCreate = true">
            {{ $t('dispatch.assign') }}
          </UiButton>
        </div>
      </div>

      <!-- Stats bar -->
      <div class="dispatch-stats">
        <div class="stat-item">
          <span class="stat-value text-green-500">{{ activeCount }}</span>
          <span class="stat-label">{{ $t('dispatch.stats_active') }}</span>
        </div>
        <div class="stat-sep" />
        <div class="stat-item">
          <span class="stat-value">{{ assignedCount }}</span>
          <span class="stat-label">{{ $t('dispatch.stats_assigned') }}</span>
        </div>
        <div class="stat-sep" />
        <div class="stat-item">
          <span class="stat-value">{{ routeCount }}</span>
          <span class="stat-label">{{ $t('dispatch.stats_routes') }}</span>
        </div>
        <div class="stat-sep" />
        <div class="stat-item">
          <span class="stat-value text-neutral-400">{{ completedCount }}</span>
          <span class="stat-label">{{ $t('dispatch.stats_done') }}</span>
        </div>
      </div>

      <!-- Filter tabs -->
      <UiTabs v-model="tab" :tabs="tabItems">

      <!-- Loading -->
      <div v-if="store.loading" class="flex justify-center py-12">
        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>

      <!-- Error -->
      <UiAlert v-else-if="store.error" variant="error" dismissible @dismiss="store.error = null">
        {{ store.error }}
      </UiAlert>

      <!-- Empty state -->
      <div v-else-if="filtered.length === 0" class="text-center py-12">
        <img src="/images/para/shrug.png" alt="Para" class="mx-auto h-32 w-auto mb-3" />
        <p class="text-neutral-500 dark:text-neutral-400 text-sm">
          {{ tab === 'all' ? $t('dispatch.no_assignments') : tab === 'active' ? $t('dispatch.no_active') : $t('dispatch.no_completed') }}
        </p>
        <UiButton v-if="tab === 'active'" variant="outline" size="sm" :icon="Plus" class="mt-4" @click="showCreate = true">
          {{ $t('dispatch.create_first') }}
        </UiButton>
      </div>

      <!-- Assignment cards -->
      <TransitionGroup v-else name="card-list" tag="div" class="space-y-2">
        <div
          v-for="a in filtered"
          :key="a.id"
          class="assignment-card"
          :class="{ 'opacity-50': ['COMPLETED', 'CANCELLED'].includes(a.status) }"
        >
          <!-- Route color stripe -->
          <div
            class="route-stripe"
            :style="{ backgroundColor: `#${a.route_color || '6b7280'}` }"
          />

          <div class="flex-1 min-w-0 py-3 pr-3">
            <!-- Top: route + status -->
            <div class="flex items-center gap-2 mb-1.5">
              <span
                class="route-badge"
                :style="{
                  backgroundColor: `#${a.route_color || '6b7280'}`,
                  color: getContrastColor(a.route_color || '6b7280'),
                }"
              >
                {{ a.route_name }}
              </span>
              <span class="text-xs text-neutral-500 dark:text-neutral-400">{{ $t('dispatch.dir') }} {{ a.direction_id }}</span>
              <UiBadge
                :variant="statusVariant(a.status)"
                type="soft"
                size="sm"
              >
                {{ a.status }}
              </UiBadge>
              <span v-if="a.display_vehicle_id" class="text-xs font-mono text-neutral-500 dark:text-neutral-400 ml-auto hidden sm:inline">
                #{{ a.display_vehicle_id }}
              </span>
            </div>

            <!-- Middle: device + position -->
            <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
              <span class="text-neutral-700 dark:text-neutral-300 flex items-center gap-1.5">
                <Smartphone class="w-3.5 h-3.5 text-neutral-400" />
                {{ a.device_name }}
              </span>
              <span v-if="a.latitude" class="font-mono text-xs text-neutral-500 dark:text-neutral-400 tabular-nums">
                {{ a.latitude.toFixed(5) }}, {{ a.longitude?.toFixed(5) }}
              </span>
              <span v-if="a.speed != null && a.speed > 0" class="text-xs text-blue-500 dark:text-blue-400 font-medium tabular-nums">
                {{ Math.round(a.speed) }} km/h
              </span>
              <span v-if="!a.latitude && ['ASSIGNED', 'ACTIVE'].includes(a.status)" class="text-xs text-neutral-400 italic">
                {{ $t('dispatch.no_position') }}
              </span>
            </div>

            <!-- Notes -->
            <p v-if="a.notes" class="text-xs text-neutral-400 mt-1 truncate">{{ a.notes }}</p>
          </div>

          <!-- Actions -->
          <div v-if="['ASSIGNED', 'ACTIVE'].includes(a.status)" class="flex items-center gap-1 pr-3 shrink-0">
            <button
              class="action-btn text-green-600 dark:text-green-400 hover:bg-green-50 dark:hover:bg-green-900/30"
              :title="$t('dispatch.complete')"
              @click="completeAssignment(a.id)"
            >
              <CheckCircle class="w-4 h-4" />
            </button>
            <button
              class="action-btn text-red-500 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30"
              :title="$t('dispatch.cancel')"
              @click="cancelAssignment(a.id)"
            >
              <XCircle class="w-4 h-4" />
            </button>
          </div>
        </div>
      </TransitionGroup>
      </UiTabs>

      <!-- Create Assignment Modal -->
      <Modal v-model="showCreate" :title="$t('dispatch.new_assignment')" size="lg">
        <form @submit.prevent="handleCreate" class="space-y-4">
          <!-- Route search -->
          <div>
            <label class="form-label">{{ $t('dispatch.route') }}</label>
            <div class="relative">
              <input
                v-model="routeSearch"
                type="text"
                :placeholder="$t('dispatch.search_routes')"
                class="form-input w-full"
                @input="searchRoutes"
              />
              <!-- Route dropdown -->
              <div v-if="routeResults.length > 0 && !selectedRoute" class="route-dropdown">
                <button
                  v-for="r in routeResults"
                  :key="r.id"
                  type="button"
                  class="route-option"
                  @click="selectRoute(r)"
                >
                  <span
                    class="inline-block w-10 text-center rounded text-xs font-bold py-0.5 mr-2"
                    :style="{
                      backgroundColor: `#${r.route_color || '6b7280'}`,
                      color: getContrastColor(r.route_color || '6b7280'),
                    }"
                  >
                    {{ r.short_name }}
                  </span>
                  <span class="text-sm truncate">{{ r.long_name }}</span>
                </button>
              </div>
              <!-- Selected route chip -->
              <div v-if="selectedRoute" class="flex items-center gap-2 mt-2">
                <span
                  class="route-badge"
                  :style="{
                    backgroundColor: `#${selectedRoute.route_color || '6b7280'}`,
                    color: getContrastColor(selectedRoute.route_color || '6b7280'),
                  }"
                >
                  {{ selectedRoute.short_name }}
                </span>
                <span class="text-sm text-neutral-600 dark:text-neutral-400 truncate">{{ selectedRoute.long_name }}</span>
                <button type="button" class="text-neutral-400 hover:text-neutral-600" @click="clearRoute">
                  <X class="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>

          <!-- Device select -->
          <div>
            <label class="form-label">{{ $t('dispatch.gps_device') }}</label>
            <select v-model="form.device_id" class="form-input w-full" required>
              <option value="">{{ $t('dispatch.select_device') }}</option>
              <option v-for="d in store.availableDevices" :key="d.id" :value="d.id">
                {{ d.name }}
                <template v-if="d.has_position"> ({{ $t('dispatch.has_signal') }})</template>
              </option>
            </select>
          </div>

          <!-- Direction + Vehicle ID row -->
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="form-label">{{ $t('dispatch.direction') }}</label>
              <select v-model.number="form.direction_id" class="form-input w-full">
                <option :value="0">{{ $t('dispatch.outbound') }}</option>
                <option :value="1">{{ $t('dispatch.inbound') }}</option>
              </select>
            </div>
            <div>
              <label class="form-label">{{ $t('dispatch.vehicle_id') }}</label>
              <input v-model="form.display_vehicle_id" type="text" class="form-input w-full" :placeholder="$t('dispatch.vehicle_id_placeholder')" />
            </div>
          </div>

          <!-- Notes -->
          <div>
            <label class="form-label">{{ $t('dispatch.notes') }}</label>
            <textarea v-model="form.notes" rows="2" class="form-input w-full" :placeholder="$t('dispatch.notes_placeholder')" />
          </div>

          <div class="flex justify-end gap-2 pt-2">
            <UiButton variant="ghost" size="sm" type="button" @click="showCreate = false">{{ $t('dispatch.cancel') }}</UiButton>
            <UiButton variant="primary" size="sm" type="submit" :loading="creating" :disabled="!canCreate">
              {{ $t('dispatch.create_assignment') }}
            </UiButton>
          </div>
        </form>
      </Modal>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  ShieldAlert, Radio, Plus, Bus, Smartphone,
  CheckCircle, XCircle, X,
} from 'lucide-vue-next'

definePageMeta({
  middleware: 'auth',
  order: 5,
  keepalive: true,
})

const { t } = useI18n()
const authStore = useAuthStore()
const store = useDispatchStore()
const isStaff = computed(() => authStore.user?.is_staff ?? false)

// --- Tab filter ---
const tab = useTabSync(['active', 'completed', 'all'])

const activeCount = computed(() => store.assignments.filter(a => a.status === 'ACTIVE').length)
const assignedCount = computed(() => store.assignments.filter(a => a.status === 'ASSIGNED').length)
const completedCount = computed(() => store.assignments.filter(a => ['COMPLETED', 'CANCELLED'].includes(a.status)).length)
const routeCount = computed(() => new Set(store.activeAssignments.map(a => a.route_id)).size)

const tabItems = computed(() => [
  { id: 'active', label: t('dispatch.tab_active'), badge: activeCount.value + assignedCount.value },
  { id: 'completed', label: t('dispatch.tab_done'), badge: completedCount.value },
  { id: 'all', label: t('dispatch.tab_all'), badge: store.assignments.length },
])

const filtered = computed(() => {
  if (tab.value === 'active') return store.activeAssignments
  if (tab.value === 'completed') return store.completedAssignments
  return store.assignments
})

// --- Data loading ---
const reload = async () => {
  await Promise.all([
    store.fetchAssignments(),
    store.fetchRoutes(),
    store.fetchAvailableDevices(),
  ])
}

onMounted(async () => {
  if (isStaff.value) await reload()
})

// Auto-refresh every 30s for live positions
let refreshTimer: ReturnType<typeof setInterval> | null = null
onMounted(() => {
  refreshTimer = setInterval(() => {
    if (isStaff.value && store.activeAssignments.length > 0) {
      store.fetchAssignments()
    }
  }, 30_000)
})
onUnmounted(() => { if (refreshTimer) clearInterval(refreshTimer) })

// --- Create assignment ---
const showCreate = ref(false)
const creating = ref(false)
const routeSearch = ref('')
const routeResults = ref<any[]>([])
const selectedRoute = ref<any>(null)

const form = reactive({
  device_id: '',
  direction_id: 0,
  display_vehicle_id: '',
  notes: '',
})

const canCreate = computed(() => selectedRoute.value && form.device_id)

const searchRoutes = async () => {
  if (routeSearch.value.length < 1) { routeResults.value = []; return }
  try {
    const data = await $fetch<{ stops: any[]; routes: any[] }>(
      `/api/v1/geo/transit/search/?q=${encodeURIComponent(routeSearch.value)}`
    )
    routeResults.value = data.routes.slice(0, 10)
  } catch { routeResults.value = [] }
}

const selectRoute = (r: any) => {
  selectedRoute.value = r
  routeSearch.value = ''
  routeResults.value = []
}

const clearRoute = () => {
  selectedRoute.value = null
  routeSearch.value = ''
}

const handleCreate = async () => {
  if (!canCreate.value) return
  creating.value = true
  try {
    await store.createAssignment({
      device_id: form.device_id,
      route_id: selectedRoute.value.id,
      direction_id: form.direction_id,
      date: store.selectedDate,
      display_vehicle_id: form.display_vehicle_id,
      notes: form.notes,
    })
    showCreate.value = false
    // Reset form
    selectedRoute.value = null
    form.device_id = ''
    form.direction_id = 0
    form.display_vehicle_id = ''
    form.notes = ''
    await store.fetchRoutes()
  } catch (e: any) {
    store.error = e.data?.detail || e.message || t('dispatch.error_create')
  } finally {
    creating.value = false
  }
}

// --- Actions ---
const completeAssignment = async (id: string) => {
  try {
    await store.updateAssignment(id, { status: 'COMPLETED' })
    await store.fetchRoutes()
  } catch (e: any) {
    store.error = e.data?.detail || e.message || t('dispatch.error_action')
  }
}

const cancelAssignment = async (id: string) => {
  try {
    await store.updateAssignment(id, { status: 'CANCELLED' })
    await store.fetchRoutes()
  } catch (e: any) {
    store.error = e.data?.detail || e.message || t('dispatch.error_action')
  }
}

// --- Helpers ---
const statusVariant = (s: string) => {
  if (s === 'ACTIVE') return 'success' as const
  if (s === 'ASSIGNED') return 'warning' as const
  if (s === 'COMPLETED') return 'neutral' as const
  return 'error' as const
}

const getContrastColor = (hex: string) => {
  const r = parseInt(hex.substring(0, 2), 16)
  const g = parseInt(hex.substring(2, 4), 16)
  const b = parseInt(hex.substring(4, 6), 16)
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
  return luminance > 0.55 ? '#000000' : '#ffffff'
}
</script>

<style scoped>
.dispatch-icon {
  @apply w-10 h-10 rounded-lg flex items-center justify-center;
  @apply bg-primary/10 text-primary;
}

.dispatch-stats {
  @apply flex items-center gap-3 px-4 py-2.5 rounded-lg;
  @apply bg-neutral-50 dark:bg-neutral-800/50 border border-neutral-200 dark:border-neutral-700;
}

.stat-item {
  @apply flex items-center gap-1.5;
}

.stat-value {
  @apply text-lg font-bold tabular-nums text-neutral-900 dark:text-neutral-100;
}

.stat-label {
  @apply text-xs text-neutral-500 dark:text-neutral-400 uppercase tracking-wide;
}

.stat-sep {
  @apply w-px h-6 bg-neutral-200 dark:bg-neutral-700;
}

.dispatch-date-input {
  @apply px-3 py-1.5 text-sm rounded-lg border;
  @apply border-neutral-300 dark:border-neutral-600;
  @apply bg-white dark:bg-neutral-800;
  @apply text-neutral-900 dark:text-neutral-100;
  @apply focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary;
}

.assignment-card {
  @apply flex items-center rounded-lg overflow-hidden transition-all;
  @apply bg-white dark:bg-neutral-800;
  @apply border border-neutral-200 dark:border-neutral-700;
  @apply hover:border-neutral-300 dark:hover:border-neutral-600;
}

.route-stripe {
  @apply w-1.5 self-stretch shrink-0;
}

.route-badge {
  @apply inline-block px-2.5 py-0.5 rounded text-xs font-bold;
}

.action-btn {
  @apply p-2 rounded-lg transition-colors;
}

.form-label {
  @apply block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1;
}

.form-input {
  @apply px-3 py-2 text-sm rounded-lg border;
  @apply border-neutral-300 dark:border-neutral-600;
  @apply bg-white dark:bg-neutral-800;
  @apply text-neutral-900 dark:text-neutral-100;
  @apply placeholder:text-neutral-400;
  @apply focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary;
}

.route-dropdown {
  @apply absolute z-20 left-0 right-0 mt-1 max-h-52 overflow-y-auto rounded-lg;
  @apply bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 shadow-lg;
}

.route-option {
  @apply w-full flex items-center px-3 py-2 text-left;
  @apply hover:bg-neutral-50 dark:hover:bg-neutral-700/50 transition-colors;
}

/* Card list transitions */
.card-list-enter-active,
.card-list-leave-active {
  transition: all 0.3s ease;
}

.card-list-enter-from {
  opacity: 0;
  transform: translateY(-10px);
}

.card-list-leave-to {
  opacity: 0;
  transform: translateX(20px);
}

.card-list-move {
  transition: transform 0.3s ease;
}
</style>
