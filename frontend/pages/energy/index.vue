<template>
  <div>
    <Head>
      <Title>{{ $t('energy.title') }} — Parahub</Title>
      <Meta name="description" :content="$t('energy.subtitle')" />
    </Head>

    <div class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-6">

      <PageHeader
        :title="$t('energy.title')"
        :subtitle="$t('energy.subtitle')"
        :create-label="authStore.isAuthenticated ? $t('energy.empty.cta') : undefined"
        @create="showCreateModal = true"
      />

      <!-- My shares link -->
      <div v-if="authStore.isAuthenticated" class="flex justify-end -mt-2 mb-4">
        <NuxtLink
          :to="localePath('/energy/my-shares')"
          class="text-xs text-secondary-600 dark:text-secondary-400 hover:underline flex items-center gap-1"
        >
          <Coins :size="14" />
          {{ $t('energy.shares.my_shares_title') }}
        </NuxtLink>
      </div>

      <!-- My membership banner -->
      <div
        v-if="myStatus?.is_member"
        class="mb-6 p-4 rounded-xl border flex items-center gap-3"
        :class="myStatus.cell_status === 'GREEN'
          ? 'bg-success-50 dark:bg-success-900/20 border-success-200 dark:border-success-800'
          : myStatus.cell_status === 'YELLOW'
            ? 'bg-warning-50 dark:bg-warning-900/20 border-warning-200 dark:border-warning-800'
            : 'bg-neutral-50 dark:bg-neutral-800 border-neutral-200 dark:border-neutral-700'"
      >
        <div
          class="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0"
          :class="myStatus.cell_status === 'GREEN'
            ? 'bg-success-100 dark:bg-success-900/40'
            : myStatus.cell_status === 'YELLOW'
              ? 'bg-warning-100 dark:bg-warning-900/40'
              : 'bg-neutral-100 dark:bg-neutral-700'"
        >
          <Zap
            :size="20"
            :class="myStatus.cell_status === 'GREEN' ? 'text-success-600' : myStatus.cell_status === 'YELLOW' ? 'text-warning-600' : 'text-neutral-500'"
          />
        </div>
        <div class="flex-1 min-w-0">
          <div class="font-medium text-neutral-900 dark:text-neutral-100 text-sm">
            {{ myStatus.role === 'producer' ? $t('energy.my.producer_in', { name: myStatus.cell_name }) : $t('energy.my.consumer_in', { name: myStatus.cell_name }) }}
          </div>
          <div class="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
            {{ $t(`energy.status.${myStatus.cell_status}`) }}
            <span v-if="myStatus.current_price_eur" class="ml-2 font-medium"
              :class="myStatus.cell_status === 'GREEN' ? 'text-success-700 dark:text-success-400' : ''"
            >
              {{ myStatus.current_price_eur }} €/kWh
            </span>
          </div>
        </div>
        <NuxtLink
          :to="localePath('/map')"
          class="flex-shrink-0 text-xs text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300 flex items-center gap-1"
        >
          <MapPin :size="14" />
          {{ $t('map.loading_map').replace('...', '') }}
        </NuxtLink>
      </div>

      <!-- Economics explainer (shown when no membership) -->
      <div v-if="!myStatus?.is_member" class="mb-6 grid grid-cols-3 gap-3">
        <div class="p-3 bg-error-50 dark:bg-error-900/15 rounded-xl border border-error-200 dark:border-error-900/40 text-center">
          <div class="text-xs text-error-500 dark:text-error-400 mb-1">{{ $t('energy.econ.sell_label') }}</div>
          <div class="text-xl font-bold text-error dark:text-error-400">0.05€</div>
          <div class="text-xs text-neutral-400 mt-0.5">/kWh</div>
        </div>
        <div class="p-3 bg-success-50 dark:bg-success-900/15 rounded-xl border border-success-200 dark:border-success-800/50 text-center relative">
          <div class="absolute -top-2.5 left-1/2 -translate-x-1/2 bg-success-500 text-white text-[10px] font-bold px-2 py-0.5 rounded-full">{{ $t('energy.econ.p2p_badge') }}</div>
          <div class="text-xs text-success-600 dark:text-success-400 mb-1">{{ $t('energy.econ.p2p_label') }}</div>
          <div class="text-xl font-bold text-success-600 dark:text-success-400">0.08€</div>
          <div class="text-xs text-neutral-400 mt-0.5">/kWh</div>
        </div>
        <div class="p-3 bg-neutral-50 dark:bg-neutral-800 rounded-xl border border-neutral-200 dark:border-neutral-700 text-center">
          <div class="text-xs text-neutral-500 mb-1">{{ $t('energy.econ.grid_label') }}</div>
          <div class="text-xl font-bold text-neutral-600 dark:text-neutral-300">0.20€</div>
          <div class="text-xs text-neutral-400 mt-0.5">/kWh</div>
        </div>
      </div>
      <p v-if="!myStatus?.is_member" class="text-xs text-neutral-400 dark:text-neutral-500 text-center -mt-4 mb-6">
        {{ $t('energy.eu_note') }}
      </p>

      <!-- Loading -->
      <div v-if="loading" class="flex justify-center py-16">
        <div class="animate-spin rounded-full h-10 w-10 border-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-white" />
      </div>

      <!-- Cell list -->
      <div v-else-if="cells.length" class="space-y-3">
        <h2 class="text-sm font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wide mb-3">
          {{ $t('energy.layer_title') }}
        </h2>
        <NuxtLink
          v-for="cell in cells"
          :key="cell.id"
          :to="localePath(`/energy/${cell.id}`)"
          class="card p-4 flex items-center gap-4 hover:border-neutral-300 dark:hover:border-neutral-600 transition-colors block"
        >
          <!-- Status dot -->
          <div
            class="w-3 h-3 rounded-full flex-shrink-0"
            :class="{
              'bg-success-500': cellDisplayStatus(cell) === 'GREEN',
              'bg-warning-400': cellDisplayStatus(cell) === 'YELLOW' || cellDisplayStatus(cell) === 'WAITING',
              'bg-error-400': cellDisplayStatus(cell) === 'RED',
              'bg-neutral-300 dark:bg-neutral-600': cellDisplayStatus(cell) === 'OFFLINE',
            }"
          />

          <!-- Info -->
          <div class="flex-1 min-w-0">
            <div class="font-medium text-neutral-900 dark:text-neutral-100 text-sm truncate">{{ cell.name }}</div>
            <div class="flex items-center gap-3 mt-0.5 flex-wrap">
              <span class="text-xs"
                :class="{
                  'text-success-600 dark:text-success-400': cellDisplayStatus(cell) === 'GREEN',
                  'text-warning-600 dark:text-warning-400': cellDisplayStatus(cell) === 'YELLOW' || cellDisplayStatus(cell) === 'WAITING',
                  'text-error-500': cellDisplayStatus(cell) === 'RED',
                  'text-neutral-400': cellDisplayStatus(cell) === 'OFFLINE',
                }"
              >
                {{ $t(`energy.status.${cellDisplayStatus(cell)}`) }}
              </span>
              <span v-if="cell.current_price_eur" class="text-xs font-medium text-success-600 dark:text-success-400">
                {{ $t('energy.cell.price_label', { price: cell.current_price_eur }) }}
              </span>
              <span class="text-xs text-neutral-400 flex items-center gap-1">
                <Users :size="11" />
                {{ cell.producers_count + cell.consumers_count }}
              </span>
              <span class="text-xs text-neutral-400 flex items-center gap-1">
                <Radio :size="11" />
                {{ cell.radius_km }} km
              </span>
            </div>
          </div>

          <!-- Arrow -->
          <ChevronRight :size="18" class="flex-shrink-0 text-neutral-300 dark:text-neutral-600" />
        </NuxtLink>
      </div>

      <!-- Empty state -->
      <div v-else class="text-center py-12">
        <img src="/images/para/searching.webp" alt="Para" class="mx-auto h-32 w-auto mb-4" />
        <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-1">
          {{ $t('energy.empty.title') }}
        </h3>
        <p class="text-sm text-neutral-500 dark:text-neutral-400 max-w-xs mx-auto mb-6">
          {{ $t('energy.empty.subtitle') }}
        </p>
        <UiButton
          v-if="authStore.isAuthenticated"
          variant="primary"
          size="sm"
          :icon="Plus"
          @click="showCreateModal = true"
        >
          {{ $t('energy.empty.cta') }}
        </UiButton>
        <UiButton
          v-else
          variant="primary"
          size="sm"
          :to="localePath('/login')"
        >
          {{ $t('energy.empty.login_cta') }}
        </UiButton>
      </div>

      <!-- How it works (bottom explainer, always visible) -->
      <div class="mt-10 p-4 bg-neutral-50 dark:bg-neutral-800/50 rounded-xl border border-neutral-200 dark:border-neutral-700">
        <h3 class="text-sm font-semibold text-neutral-700 dark:text-neutral-300 mb-3">{{ $t('energy.how.title') }}</h3>
        <ol class="space-y-2">
          <li v-for="(step, i) in howSteps" :key="i" class="flex items-start gap-2.5 text-sm text-neutral-600 dark:text-neutral-400">
            <span class="flex-shrink-0 w-5 h-5 rounded-full bg-neutral-200 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-300 flex items-center justify-center text-xs font-bold">{{ i + 1 }}</span>
            {{ step }}
          </li>
        </ol>
      </div>

    </div>

    <!-- Create cell modal -->
    <Teleport to="body">
      <div
        v-if="showCreateModal"
        class="fixed inset-0 z-50 flex items-end sm:items-center justify-center"
        @click.self="showCreateModal = false"
      >
        <div class="absolute inset-0 bg-black/40" @click="showCreateModal = false" />
        <div class="relative w-full max-w-md bg-white dark:bg-neutral-900 rounded-t-2xl sm:rounded-2xl shadow-2xl p-6 mx-0 sm:mx-4">
          <div class="flex items-center justify-between mb-5">
            <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
              {{ $t('energy.empty.cta') }}
            </h2>
            <button @click="showCreateModal = false" class="p-1 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-500">
              <X :size="20" />
            </button>
          </div>

          <form @submit.prevent="createCell" class="space-y-4">
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                {{ $t('energy.form.cell_name') }} *
              </label>
              <input
                v-model="form.name"
                type="text"
                required
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

            <div class="grid grid-cols-2 gap-3">
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
            </div>

            <!-- Cooperative selector -->
            <div v-if="myCooperatives.length || authStore.isAuthenticated">
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
                @click="showNewCoopForm = true"
                class="text-xs text-secondary-600 dark:text-secondary-400 hover:underline mt-1"
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

            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                {{ $t('energy.form.location_hint') }}
              </label>
              <button
                type="button"
                @click="useMyLocation"
                :disabled="locationLoading"
                class="w-full flex items-center justify-center gap-2 px-3 py-2 border border-dashed border-neutral-300 dark:border-neutral-600 rounded-lg text-sm text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300 hover:border-neutral-400 transition-colors disabled:opacity-50"
              >
                <LocateFixed :size="16" :class="locationLoading ? 'animate-spin' : ''" />
                <span v-if="form.latitude">
                  {{ form.latitude.toFixed(4) }}, {{ form.longitude.toFixed(4) }}
                </span>
                <span v-else>{{ $t('energy.form.use_location') }}</span>
              </button>
            </div>

            <div class="flex gap-3 pt-2">
              <UiButton
                variant="outline"
                class="flex-1"
                @click="showCreateModal = false"
              >
                {{ $t('common.cancel') }}
              </UiButton>
              <UiButton
                variant="primary"
                tag="button"
                type="submit"
                class="flex-1"
                :disabled="creating || !form.name || !form.latitude"
                :loading="creating"
              >
                {{ $t('common.create') }}
              </UiButton>
            </div>
          </form>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Zap, MapPin, Users, Radio, Plus, X, LocateFixed, ChevronRight, Coins } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'
import { useToastStore } from '~/stores/toast'

definePageMeta({ order: 10 })

const { t } = useI18n()
const authStore = useAuthStore()
const localePath = useLocalePath()
const toastStore = useToastStore()

// Public cells list: SSR'd + Suspense-blocking + payload-cached. Auth-only
// bits (myStatus, myCooperatives) stay client-side in onMounted.
const cellsData = useListData<any[]>('/api/v1/energy/cells/map/', {
  default: () => [],
})
const { data: cells, isInitial: loading } = cellsData

const myStatus = ref<any>(null)
const showCreateModal = ref(false)
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

const cellDisplayStatus = (cell: any): string => {
  if (cell.producers_count === 0 && cell.status !== 'OFFLINE') return 'WAITING'
  return cell.status
}

const howSteps = computed(() => [
  t('energy.how.step1'),
  t('energy.how.step2'),
  t('energy.how.step3'),
  t('energy.how.step4'),
])

const fetchCells = () => cellsData.refresh()

const fetchMyStatus = async () => {
  if (!authStore.isAuthenticated) return
  try {
    await authStore.ensureToken()
    const data = await $fetch<any>('/api/v1/energy/my/', {
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    myStatus.value = data
  } catch (e) {
    console.error('[energy] Failed to load my status', e)
  }
}

const useMyLocation = () => {
  if (!navigator.geolocation) return
  locationLoading.value = true
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      form.value.latitude = pos.coords.latitude
      form.value.longitude = pos.coords.longitude
      locationLoading.value = false
    },
    () => {
      toastStore.error(t('energy.form.location_error'))
      locationLoading.value = false
    },
  )
}

const fetchMyCooperatives = async () => {
  if (!authStore.isAuthenticated) return
  try {
    await authStore.ensureToken()
    const data = await $fetch<any[]>('/api/v1/geo/establishments/', {
      params: { organization_type: 'COOPERATIVE', my: 'true' },
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    myCooperatives.value = data || []
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

const createCell = async () => {
  if (!form.value.name || !form.value.latitude) return
  creating.value = true
  try {
    await authStore.ensureToken()
    await $fetch('/api/v1/energy/cells/', {
      method: 'POST',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
      body: {
        name: form.value.name,
        description: form.value.description,
        radius_km: form.value.radius_km,
        transformer_id: form.value.transformer_id,
        latitude: form.value.latitude,
        longitude: form.value.longitude,
        establishment_id: form.value.establishment_id || undefined,
      },
    })
    toastStore.success(t('energy.form.created'))
    showCreateModal.value = false
    form.value = { name: '', description: '', radius_km: 2, transformer_id: '', latitude: null, longitude: null, establishment_id: '' }
    await fetchCells()
  } catch (e) {
    toastStore.error(t('common.error'))
  } finally {
    creating.value = false
  }
}

onMounted(() => {
  // Cells already loaded via useListData; only the auth-gated extras here.
  fetchMyStatus()
  fetchMyCooperatives()
})

// Suspense barrier — must stay last in setup (see useListData docs).
await cellsData
</script>
