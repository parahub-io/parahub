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
        :create-to="authStore.isAuthenticated ? localePath('/energy/create') : undefined"
        :create-label="authStore.isAuthenticated ? $t('energy.empty.cta') : undefined"
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
          :to="localePath('/energy/create')"
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
      <div class="mt-10 p-4 bg-neutral-50 dark:bg-neutral-800/50 rounded-xl border border-neutral-200 dark:border-neutral-700 flex items-center gap-6">
        <div class="flex-1 min-w-0">
          <h3 class="text-sm font-semibold text-neutral-700 dark:text-neutral-300 mb-3">{{ $t('energy.how.title') }}</h3>
          <ol class="space-y-2">
            <li v-for="(step, i) in howSteps" :key="i" class="flex items-start gap-2.5 text-sm text-neutral-600 dark:text-neutral-400">
              <span class="flex-shrink-0 w-5 h-5 rounded-full bg-neutral-200 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-300 flex items-center justify-center text-xs font-bold">{{ i + 1 }}</span>
              {{ step }}
            </li>
          </ol>
        </div>
        <img src="/images/energy/sharing.webp" alt="" class="hidden sm:block h-32 w-auto object-contain flex-shrink-0" loading="lazy" />
      </div>

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Zap, MapPin, Users, Radio, Plus, ChevronRight, Coins } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'

definePageMeta({ order: 10 })

const { t } = useI18n()
const authStore = useAuthStore()
const localePath = useLocalePath()

// Public cells list: SSR'd + Suspense-blocking + payload-cached. Auth-only
// bits (myStatus, myCooperatives) stay client-side in onMounted.
const cellsData = useListData<any[]>('/api/v1/energy/cells/map/', {
  default: () => [],
})
const { data: cells, isInitial: loading } = cellsData

const myStatus = ref<any>(null)

const cellDisplayStatus = (cell: any): string => {
  // A cell without producers is "waiting to be joined" regardless of stored
  // status — fresh cells are born OFFLINE and would otherwise read as dead.
  if (cell.producers_count === 0) return 'WAITING'
  return cell.status
}

const howSteps = computed(() => [
  t('energy.how.step1'),
  t('energy.how.step2'),
  t('energy.how.step3'),
  t('energy.how.step4'),
])

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

onMounted(() => {
  // Cells already loaded via useListData; only the auth-gated extras here.
  fetchMyStatus()
})

// Suspense barrier — must stay last in setup (see useListData docs).
await cellsData
</script>
