<template>
  <div class="py-6 w-full">
    <div class="w-full px-4 sm:px-6 lg:px-8">
      <div class="max-w-3xl mx-auto w-full">
        <!-- Loading -->
        <div v-if="loading" class="flex justify-center items-center min-h-[400px]">
          <Loader2 class="h-12 w-12 animate-spin text-primary" />
        </div>

        <!-- Error -->
        <div v-else-if="error" class="bg-red-100 dark:bg-red-900/20 border border-red-300 dark:border-red-800 rounded-lg p-6 text-center">
          <AlertTriangle class="w-16 h-16 text-red-500 mx-auto mb-4" />
          <h2 class="text-xl font-semibold text-red-800 dark:text-red-200 mb-2">{{ t('arbiter_stats.not_found') }}</h2>
          <NuxtLink :to="localePath('/')" class="btn-primary mt-4 inline-block">{{ t('common.back') }}</NuxtLink>
        </div>

        <!-- Stats content -->
        <div v-else-if="stats" class="space-y-6">
          <!-- Header -->
          <div class="flex items-center gap-4">
            <div class="w-12 h-12 rounded-full bg-secondary/10 flex items-center justify-center">
              <Scale class="w-6 h-6 text-secondary" />
            </div>
            <div>
              <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100">{{ stats.display_name }}</h1>
              <NuxtLink :to="localePath(`/u/${stats.hna}`)" class="text-link text-sm">@{{ stats.hna }}</NuxtLink>
            </div>
          </div>

          <!-- Summary cards -->
          <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div class="card p-4 text-center">
              <div class="text-2xl font-bold text-neutral-900 dark:text-neutral-100">{{ stats.total_cases }}</div>
              <div class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">{{ t('arbiter_stats.total_cases') }}</div>
            </div>
            <div class="card p-4 text-center">
              <div class="text-2xl font-bold" :class="ratingColor">{{ stats.avg_rating ? stats.avg_rating.toFixed(1) : '—' }}</div>
              <div class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">{{ t('arbiter_stats.avg_rating') }} <span v-if="stats.rating_count">({{ stats.rating_count }})</span></div>
            </div>
            <div class="card p-4 text-center">
              <div class="text-2xl font-bold" :class="escalationColor">{{ (stats.escalation_rate * 100).toFixed(0) }}%</div>
              <div class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">{{ t('arbiter_stats.escalation_rate') }}</div>
            </div>
            <div class="card p-4 text-center">
              <div class="text-2xl font-bold text-neutral-900 dark:text-neutral-100">{{ stats.avg_resolution_days ? stats.avg_resolution_days.toFixed(1) : '—' }}</div>
              <div class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">{{ t('arbiter_stats.avg_days') }}</div>
            </div>
          </div>

          <!-- Verdict breakdown -->
          <div class="card p-5">
            <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4">{{ t('arbiter_stats.verdict_breakdown') }}</h2>
            <div v-if="stats.total_cases > 0" class="space-y-3">
              <div v-for="vt in verdictTypes" :key="vt.key" class="flex items-center gap-3">
                <div class="w-28 text-sm text-neutral-600 dark:text-neutral-400 shrink-0">{{ vt.label }}</div>
                <div class="flex-1 h-6 bg-neutral-100 dark:bg-neutral-700 rounded-full overflow-hidden">
                  <div
                    class="h-full rounded-full transition-all duration-500"
                    :class="vt.barClass"
                    :style="{ width: verdictPercent(vt.key) + '%' }"
                  />
                </div>
                <div class="w-16 text-right text-sm font-medium text-neutral-900 dark:text-neutral-100">
                  {{ verdictCount(vt.key) }} <span class="text-neutral-400 text-xs">({{ verdictPercent(vt.key).toFixed(0) }}%)</span>
                </div>
              </div>
            </div>
            <div v-else class="text-neutral-500 dark:text-neutral-400 text-sm text-center py-4">
              {{ t('arbiter_stats.no_cases') }}
            </div>
          </div>

          <!-- Rating distribution -->
          <div class="card p-5">
            <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4">{{ t('arbiter_stats.rating_distribution') }}</h2>
            <div v-if="stats.rating_count > 0" class="space-y-2">
              <div v-for="star in [5, 4, 3, 2, 1]" :key="star" class="flex items-center gap-3">
                <div class="w-12 text-sm text-neutral-600 dark:text-neutral-400 flex items-center gap-1">
                  {{ star }} <Star class="w-3.5 h-3.5 text-amber-500 fill-amber-500" />
                </div>
                <div class="flex-1 h-5 bg-neutral-100 dark:bg-neutral-700 rounded-full overflow-hidden">
                  <div
                    class="h-full bg-amber-500 rounded-full transition-all duration-500"
                    :style="{ width: ratingPercent(star) + '%' }"
                  />
                </div>
                <div class="w-10 text-right text-sm text-neutral-600 dark:text-neutral-400">
                  {{ stats.rating_distribution[String(star)] || 0 }}
                </div>
              </div>
            </div>
            <div v-else class="text-neutral-500 dark:text-neutral-400 text-sm text-center py-4">
              {{ t('arbiter_stats.no_ratings') }}
            </div>
          </div>

          <!-- Total awarded -->
          <div v-if="stats.total_awarded" class="card p-5">
            <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-2">{{ t('arbiter_stats.total_awarded') }}</h2>
            <div class="text-3xl font-bold text-secondary">{{ Number(stats.total_awarded).toLocaleString() }} EUR</div>
          </div>

          <!-- Recent verdicts -->
          <div v-if="stats.recent_verdicts.length > 0" class="card p-5">
            <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4">{{ t('arbiter_stats.recent_verdicts') }}</h2>
            <div class="border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700">
              <div
                v-for="v in stats.recent_verdicts"
                :key="v.contract_id"
                class="px-4 py-3 flex items-center justify-between gap-3 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors"
              >
                <div class="min-w-0">
                  <NuxtLink :to="localePath(`/contracts?highlight=${v.contract_id}`)" class="text-link text-sm font-medium truncate block">
                    {{ v.contract_title }}
                  </NuxtLink>
                  <div class="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
                    {{ formatDate(v.created_at) }}
                    <span v-if="v.amount_awarded"> · {{ v.amount_awarded }} {{ v.currency }}</span>
                  </div>
                </div>
                <UiBadge :variant="verdictBadgeVariant(v.verdict_type)" type="soft" size="sm">
                  {{ verdictLabel(v.verdict_type) }}
                </UiBadge>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { Loader2, AlertTriangle, Scale, Star } from 'lucide-vue-next'

const { t } = useI18n()
const localePath = useLocalePath()
const route = useRoute()
const authStore = useAuthStore()

const loading = ref(true)
const error = ref(false)
const stats = ref(null)

const verdictTypes = computed(() => [
  { key: 'FAVOR_CREATOR', label: t('contracts.verdict.favor_creator'), barClass: 'bg-emerald-500' },
  { key: 'FAVOR_PARTNER', label: t('contracts.verdict.favor_partner'), barClass: 'bg-sky-500' },
  { key: 'PARTIAL', label: t('contracts.verdict.partial'), barClass: 'bg-amber-500' },
  { key: 'DISMISSED', label: t('contracts.verdict.dismissed'), barClass: 'bg-neutral-400' },
])

const ratingColor = computed(() => {
  if (!stats.value?.avg_rating) return 'text-neutral-400'
  if (stats.value.avg_rating >= 4) return 'text-emerald-600 dark:text-emerald-400'
  if (stats.value.avg_rating >= 3) return 'text-amber-600 dark:text-amber-400'
  return 'text-red-600 dark:text-red-400'
})

const escalationColor = computed(() => {
  if (!stats.value) return 'text-neutral-400'
  if (stats.value.escalation_rate <= 0.1) return 'text-emerald-600 dark:text-emerald-400'
  if (stats.value.escalation_rate <= 0.3) return 'text-amber-600 dark:text-amber-400'
  return 'text-red-600 dark:text-red-400'
})

function verdictCount(key) {
  return stats.value?.verdict_breakdown?.[key] || 0
}

function verdictPercent(key) {
  if (!stats.value?.total_cases) return 0
  return (verdictCount(key) / stats.value.total_cases) * 100
}

function ratingPercent(star) {
  if (!stats.value?.rating_count) return 0
  return ((stats.value.rating_distribution[String(star)] || 0) / stats.value.rating_count) * 100
}

function verdictBadgeVariant(type) {
  const map = { FAVOR_CREATOR: 'success', FAVOR_PARTNER: 'secondary', PARTIAL: 'warning', DISMISSED: 'neutral' }
  return map[type] || 'neutral'
}

function verdictLabel(type) {
  const map = {
    FAVOR_CREATOR: t('contracts.verdict.favor_creator'),
    FAVOR_PARTNER: t('contracts.verdict.favor_partner'),
    PARTIAL: t('contracts.verdict.partial'),
    DISMISSED: t('contracts.verdict.dismissed'),
  }
  return map[type] || type
}

function formatDate(iso) {
  return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

async function fetchStats() {
  loading.value = true
  try {
    await authStore.ensureToken()
    const data = await $fetch(`/api/v1/contracts/arbiter-profiles/${route.params.id}/stats/`, {
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    stats.value = data
  } catch (e) {
    error.value = true
  } finally {
    loading.value = false
  }
}

useHead(() => ({
  title: stats.value ? `${stats.value.display_name} — ${t('arbiter_stats.title')}` : t('arbiter_stats.title'),
}))

onMounted(fetchStats)
</script>
