<template>
  <div class="max-w-3xl mx-auto px-4 py-6">
    <!-- Back link -->
    <NuxtLink
      :to="localePath(`/org/${slug}`)"
      class="flex items-center gap-1.5 text-sm text-neutral-500 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-neutral-100 mb-4"
    >
      <ArrowLeft class="w-4 h-4" />
      {{ $t('condo.back') }}
    </NuxtLink>

    <!-- Condo name heading -->
    <h1 class="text-xl font-bold text-neutral-900 dark:text-neutral-100 mb-4">{{ condoName || $t('condo.title') }}</h1>

    <!-- Tab navigation -->
    <UiRouteTabs
      :tabs="condoTabs"
      class="mb-6"
    />

    <!-- Loading -->
    <div v-if="pending" class="flex justify-center py-16">
      <Loader2 class="w-8 h-8 animate-spin text-primary" />
    </div>

    <!-- Empty state: no budget set and no data -->
    <div v-else-if="!summary || (Number(summary.monthly_budget) === 0 && !assemblies?.length)" class="text-center py-12">
      <img src="/images/para/building.webp" alt="" class="w-24 h-24 mx-auto mb-3 opacity-80" />
      <p class="text-sm text-neutral-500 dark:text-neutral-400 mb-1">{{ $t('condo.overview_empty_title') }}</p>
      <p class="text-xs text-neutral-400 dark:text-neutral-500 mb-4">{{ $t('condo.overview_empty_subtitle') }}</p>
      <div class="flex gap-2 justify-center">
        <UiButton variant="primary" size="sm" :to="localePath(`/condo/${slug}/quotas`)">
          {{ $t('condo.overview_set_budget') }}
        </UiButton>
        <UiButton variant="outline" size="sm" :to="localePath(`/condo/${slug}/assembly`)">
          {{ $t('condo.overview_create_assembly') }}
        </UiButton>
      </div>
    </div>

    <div v-else class="space-y-6">
      <!-- Quick stats: 4 cards -->
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div class="bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4">
          <div class="text-xs text-neutral-500 dark:text-neutral-400 mb-1 flex items-center gap-1">
            <Grid3x3 class="w-3.5 h-3.5" />
            {{ $t('condo.stat_fractions') }}
          </div>
          <div class="text-xl font-bold text-neutral-900 dark:text-neutral-100">{{ summary.fractions_total }}</div>
        </div>
        <div class="bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4">
          <div class="text-xs text-neutral-500 dark:text-neutral-400 mb-1 flex items-center gap-1">
            <Wallet class="w-3.5 h-3.5" />
            {{ $t('condo.stat_monthly_budget') }}
          </div>
          <div class="text-xl font-bold text-neutral-900 dark:text-neutral-100">
            {{ Number(summary.monthly_budget).toFixed(0) }}<span class="text-sm font-normal text-neutral-500">&nbsp;€</span>
          </div>
        </div>
        <div class="bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4">
          <div class="text-xs text-neutral-500 dark:text-neutral-400 mb-1 flex items-center gap-1">
            <TrendingUp class="w-3.5 h-3.5" />
            {{ $t('condo.stat_collection_rate') }}
          </div>
          <div class="text-xl font-bold" :class="collectionRateClass">
            {{ Math.round(Number(summary.collection_rate) * 100) }}<span class="text-sm font-normal text-neutral-500">%</span>
          </div>
        </div>
        <div class="bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4">
          <div class="text-xs text-neutral-500 dark:text-neutral-400 mb-1 flex items-center gap-1">
            <AlertCircle class="w-3.5 h-3.5" />
            {{ $t('condo.stat_outstanding') }}
          </div>
          <div class="text-xl font-bold" :class="Number(summary.outstanding_balance) > 0 ? 'text-error dark:text-error-400' : 'text-success dark:text-success-400'">
            {{ Number(summary.outstanding_balance).toFixed(0) }}<span class="text-sm font-normal text-neutral-500">&nbsp;€</span>
          </div>
        </div>
      </div>

      <!-- Current month payment status -->
      <section class="bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4">
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-base font-semibold text-neutral-900 dark:text-neutral-100">
            {{ $t('condo.overview_current_month_title', { month: formatMonth(summary.current_month) }) }}
          </h2>
          <NuxtLink :to="localePath(`/condo/${slug}/quotas`)" class="text-xs text-link inline-flex items-center gap-1">
            {{ $t('condo.overview_view_quotas') }}
            <ChevronRight class="w-3.5 h-3.5" />
          </NuxtLink>
        </div>

        <div class="flex justify-between text-sm mb-2">
          <span class="text-neutral-500">
            {{ $t('condo.fractions_paid_summary', { paid: summary.fractions_paid_current, total: summary.fractions_total }) }}
          </span>
          <span class="font-bold text-neutral-700 dark:text-neutral-300">
            <span class="text-success-700 dark:text-success-400">{{ Number(summary.current_month_collected).toFixed(2) }}</span>
            / {{ Number(summary.current_month_expected).toFixed(2) }}&nbsp;€
          </span>
        </div>
        <div class="w-full bg-neutral-200 dark:bg-neutral-700 rounded-full h-2">
          <div
            :style="{ width: currentMonthPercent + '%' }"
            class="h-2 rounded-full bg-success transition-all"
          />
        </div>
      </section>

      <!-- Budget breakdown chart -->
      <section v-if="summary.categories?.length" class="bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4">
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-base font-semibold text-neutral-900 dark:text-neutral-100">
            {{ $t('condo.overview_budget_title', { year: summary.year }) }}
          </h2>
          <NuxtLink :to="localePath(`/org/${slug}/treasury`)" class="text-xs text-link inline-flex items-center gap-1">
            {{ $t('condo.overview_view_treasury') }}
            <ChevronRight class="w-3.5 h-3.5" />
          </NuxtLink>
        </div>

        <div class="space-y-2">
          <div
            v-for="cat in summary.categories"
            :key="cat.slug"
            class="group"
          >
            <div class="flex justify-between text-xs mb-1">
              <span class="text-neutral-700 dark:text-neutral-300 truncate">{{ $t(`treasury.category.${cat.slug}`, cat.name) }}</span>
              <span class="text-neutral-500 tabular-nums">
                {{ Number(cat.annual_amount).toFixed(0) }}&nbsp;€
                <span class="text-neutral-400">· {{ Number(cat.percent).toFixed(0) }}%</span>
              </span>
            </div>
            <div class="w-full bg-neutral-100 dark:bg-neutral-800 rounded h-2">
              <div
                :style="{ width: Number(cat.percent) + '%' }"
                :class="categoryBarClass(cat.slug)"
                class="h-2 rounded transition-all"
              />
            </div>
          </div>
        </div>
      </section>

      <!-- Next assembly -->
      <section class="bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4">
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-base font-semibold text-neutral-900 dark:text-neutral-100">
            {{ $t('condo.overview_next_assembly_title') }}
          </h2>
          <NuxtLink :to="localePath(`/condo/${slug}/assembly`)" class="text-xs text-link inline-flex items-center gap-1">
            {{ $t('condo.overview_view_all_assemblies') }}
            <ChevronRight class="w-3.5 h-3.5" />
          </NuxtLink>
        </div>

        <!-- Active poll -->
        <NuxtLink
          v-if="activeAssembly"
          :to="localePath(`/governance/polls/${activeAssembly.id}`)"
          class="block p-3 rounded-lg border border-primary/30 bg-primary/5 hover:border-primary transition-colors"
        >
          <div class="flex items-start justify-between gap-2 mb-1">
            <p class="font-medium text-neutral-900 dark:text-neutral-100 truncate">{{ activeAssembly.title }}</p>
            <UiBadge variant="success" size="sm">{{ $t('condo.assembly_status_active') }}</UiBadge>
          </div>
          <p class="text-xs text-neutral-500 dark:text-neutral-400">
            <span v-if="activeAssembly.end_time">
              <Clock class="w-3 h-3 inline mr-1" />
              {{ $t('condo.overview_ends', { time: formatRelative(activeAssembly.end_time) }) }}
            </span>
            <span class="mx-1">·</span>
            {{ $t('condo.assembly_votes', { voted: activeAssembly.total_voted, eligible: activeAssembly.total_eligible }) }}
          </p>
        </NuxtLink>

        <!-- Empty -->
        <div v-else class="text-center py-4">
          <p class="text-sm text-neutral-500 dark:text-neutral-400 mb-2">{{ $t('condo.overview_no_assembly') }}</p>
          <UiButton variant="outline" size="sm" :to="localePath(`/condo/${slug}/assembly`)">
            <Plus class="w-4 h-4" />
            {{ $t('condo.overview_create_assembly') }}
          </UiButton>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ArrowLeft, Grid3x3, Receipt, Vote, Info, Loader2, Wallet, TrendingUp, AlertCircle, ChevronRight, Clock, Plus } from 'lucide-vue-next'

definePageMeta({
  middleware: 'auth',
})

const route = useRoute()
const { t, locale } = useI18n()
const localePath = useLocalePath()
const authStore = useAuthStore()

const slug = route.params.slug as string
const condoName = ref('')

const { data: condoInfo } = await useAsyncData(`condo-info-${slug}`, () =>
  $fetch<any>(`/api/v1/geo/condominiums/${slug}/info/`).catch(() => null),
  { server: false }
)
watch(condoInfo, (v) => { if (v?.name) condoName.value = v.name }, { immediate: true })

useSeoMeta({
  title: () => condoName.value ? `${condoName.value} — ${t('condo.overview_tab')}` : t('condo.meta_overview_title'),
  ogTitle: () => condoName.value ? `${condoName.value} — ${t('condo.overview_tab')}` : t('condo.meta_overview_title'),
  description: () => t('condo.meta_overview_desc'),
  ogDescription: () => t('condo.meta_overview_desc'),
  ogImage: '/og-image.jpg',
  ogType: 'website',
  twitterCard: 'summary',
})

const condoTabs = computed(() => [
  { id: 'overview', label: t('condo.overview_tab'), icon: Info, to: localePath(`/condo/${slug}`) },
  { id: 'fractions', label: t('condo.fractions_tab'), icon: Grid3x3, to: localePath(`/condo/${slug}/fractions`) },
  { id: 'quotas', label: t('condo.quotas_tab'), icon: Receipt, to: localePath(`/condo/${slug}/quotas`) },
  { id: 'assembly', label: t('condo.assembly_tab'), icon: Vote, to: localePath(`/condo/${slug}/assembly`) },
])

const summary = ref<any>(null)
const assemblies = ref<any[]>([])
const pending = ref(true)

onMounted(async () => {
  try {
    await authStore.ensureToken()
    const year = new Date().getFullYear()
    const [summaryData, assembliesData] = await Promise.all([
      $fetch<any>(`/api/v1/geo/condominiums/${slug}/financial-summary/?year=${year}`, {
        credentials: 'include',
        headers: { 'Authorization': `Bearer ${authStore.accessToken}` },
      }).catch((e) => { console.error('financial-summary failed:', e); return null }),
      $fetch<any[]>(`/api/v1/geo/condominiums/${slug}/assemblies/`, {
        credentials: 'include',
        headers: { 'Authorization': `Bearer ${authStore.accessToken}` },
      }).catch((e) => { console.error('assemblies failed:', e); return [] }),
    ])
    summary.value = summaryData
    assemblies.value = assembliesData || []
  } finally {
    pending.value = false
  }
})

const activeAssembly = computed(() => assemblies.value.find((a: any) => a.status === 'active') || null)

const currentMonthPercent = computed(() => {
  if (!summary.value || Number(summary.value.current_month_expected) <= 0) return 0
  return Math.min(100, (Number(summary.value.current_month_collected) / Number(summary.value.current_month_expected)) * 100)
})

const collectionRateClass = computed(() => {
  if (!summary.value) return 'text-neutral-900 dark:text-neutral-100'
  const rate = Number(summary.value.collection_rate)
  if (rate >= 0.9) return 'text-success dark:text-success-400'
  if (rate >= 0.6) return 'text-warning-700 dark:text-warning-400'
  return 'text-error dark:text-error-400'
})

const categoryColors = [
  'bg-primary', 'bg-secondary', 'bg-success', 'bg-warning-500',
  'bg-error-500', 'bg-info-500', 'bg-neutral-500', 'bg-neutral-400',
]
function categoryBarClass(slug: string) {
  let hash = 0
  for (let i = 0; i < slug.length; i++) hash = (hash * 31 + slug.charCodeAt(i)) >>> 0
  return categoryColors[hash % categoryColors.length]
}

function formatMonth(ym: string): string {
  if (!ym) return ''
  const [y, m] = ym.split('-').map(Number)
  return new Date(y, m - 1, 1).toLocaleString(locale.value, { month: 'long', year: 'numeric' })
}

function formatRelative(iso: string): string {
  const d = new Date(iso).getTime()
  const now = Date.now()
  const diffMs = d - now
  const absHours = Math.abs(diffMs) / 3_600_000
  if (absHours < 24) return new Date(d).toLocaleString(locale.value, { hour: '2-digit', minute: '2-digit' })
  const days = Math.round(diffMs / 86_400_000)
  const rtf = new Intl.RelativeTimeFormat(locale.value, { numeric: 'auto' })
  return rtf.format(days, 'day')
}
</script>
