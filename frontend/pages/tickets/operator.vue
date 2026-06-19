<template>
  <div class="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8 py-6">
    <PageHeader :title="$t('tickets.operator_title')" :subtitle="$t('tickets.operator_subtitle')" />

    <!-- Context tabs: personal + managed establishments -->
    <UiTabs
      v-if="contexts.length > 1"
      v-model="activeContext"
      :tabs="contextTabs"
      variant="pills"
      class="mb-4"
    />

    <!-- Range + export -->
    <div class="flex flex-wrap items-center gap-2 mb-6">
      <button
        v-for="d in [7, 30, 90]"
        :key="d"
        class="px-3 h-9 rounded-lg border text-sm transition-colors"
        :class="days === d
          ? 'bg-secondary text-white border-secondary'
          : 'border-neutral-300 dark:border-neutral-600 text-neutral-700 dark:text-neutral-300 hover:bg-primary-100 dark:hover:bg-primary-900/40'"
        @click="days = d"
      >
        {{ $t('tickets.days_short', { n: d }) }}
      </button>
      <div class="flex-1" />
      <UiButton variant="outline" size="sm" :to="localePath('/tickets/scan')">
        <ScanLine class="w-4 h-4 mr-1.5" />
        {{ $t('tickets.scan_title') }}
      </UiButton>
      <UiButton variant="outline" size="sm" :loading="csvLoading" :disabled="loading" @click="downloadCsv">
        <Download class="w-4 h-4 mr-1.5" />
        {{ $t('tickets.export_csv') }}
      </UiButton>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="py-12 text-center" role="status">
      <div class="h-12 w-12 mx-auto border-4 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100 rounded-full animate-spin" />
      <span class="sr-only">{{ $t('common.loading') }}</span>
    </div>

    <template v-else-if="stats">
      <!-- Summary cards -->
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        <div class="card p-4">
          <div class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('tickets.sold') }}</div>
          <div class="mt-1 text-2xl font-bold text-neutral-900 dark:text-white">
            {{ stats.total_sold.toLocaleString() }}
          </div>
        </div>
        <div class="card p-4">
          <div class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('tickets.revenue_sats') }}</div>
          <div class="mt-1 text-2xl font-bold text-secondary dark:text-secondary-400">
            {{ stats.revenue_sats.toLocaleString() }}
          </div>
        </div>
        <div class="card p-4">
          <div class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('tickets.revenue_eur') }}</div>
          <div class="mt-1 text-2xl font-bold text-neutral-900 dark:text-white">
            {{ formatEur(stats.revenue_eur) }} €
          </div>
        </div>
      </div>

      <!-- Pending refunds (independent of the period stats) -->
      <template v-if="refunds.length">
        <h2 class="flex items-center gap-2 font-semibold text-neutral-900 dark:text-white mb-3">
          <Undo2 class="w-4 h-4" />
          {{ $t('tickets.refunds_pending') }}
          <UiBadge variant="warning" type="soft" size="sm">{{ refunds.length }}</UiBadge>
        </h2>
        <div class="border border-amber-200 dark:border-amber-800/50 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700 mb-6">
          <div v-for="r in refunds" :key="r.ticket_id" class="px-4 py-3 space-y-2">
            <div class="flex items-center gap-4">
              <div class="flex-1 min-w-0">
                <div class="font-medium text-neutral-900 dark:text-white truncate">{{ r.ticket_type_name }}</div>
                <div class="text-xs text-neutral-500 dark:text-neutral-400">
                  {{ r.buyer_name }}<template v-if="r.reason"> — {{ r.reason }}</template>
                </div>
              </div>
              <div class="text-sm font-medium text-secondary dark:text-secondary-400 whitespace-nowrap">
                {{ r.amount_paid_sats.toLocaleString() }} sats
                <span v-if="r.price_eur" class="text-neutral-400 font-normal">({{ formatEur(r.price_eur) }} €)</span>
              </div>
            </div>
            <div class="flex flex-wrap items-center gap-2">
              <code
                v-if="r.buyer_spark_address || r.buyer_ln_address"
                class="text-xs text-neutral-500 dark:text-neutral-400 bg-neutral-100 dark:bg-neutral-800 rounded px-2 py-1 truncate max-w-[16rem] cursor-pointer"
                :title="$t('wallet.copyAddress')"
                @click="copyAddress(r)"
              >{{ r.buyer_spark_address || r.buyer_ln_address }}</code>
              <span v-else class="text-xs text-amber-600 dark:text-amber-400">{{ $t('tickets.refund_no_address') }}</span>
              <div class="flex-1" />
              <UiButton variant="outline" size="sm" :loading="resolvingId === r.ticket_id" @click="confirmRefund = r">
                {{ $t('tickets.refund_mark_refunded') }}
              </UiButton>
              <UiButton variant="ghost" size="sm" :loading="resolvingId === r.ticket_id" @click="resolveRefund(r, 'reject')">
                {{ $t('tickets.refund_reject') }}
              </UiButton>
            </div>
          </div>
        </div>
      </template>

      <!-- Empty state -->
      <div v-if="stats.total_sold === 0" class="py-12 text-center">
        <TicketIcon class="w-12 h-12 mx-auto text-neutral-300 dark:text-neutral-600" />
        <h3 class="mt-3 font-medium text-neutral-900 dark:text-white">{{ $t('tickets.no_sales') }}</h3>
      </div>

      <template v-else>
        <!-- Daily sales bars -->
        <div v-if="stats.daily.length" class="card p-4 mb-6">
          <h2 class="flex items-center gap-2 font-semibold text-neutral-900 dark:text-white mb-4">
            <ChartColumn class="w-4 h-4" />
            {{ $t('tickets.daily_sales') }}
          </h2>
          <div class="flex items-end gap-1 h-32">
            <div
              v-for="row in stats.daily"
              :key="row.date"
              class="flex-1 min-w-0 flex flex-col items-center gap-1"
              :title="`${row.date}: ${row.count} / ${row.sats.toLocaleString()} sats`"
            >
              <div class="text-[10px] text-neutral-500 dark:text-neutral-400">{{ row.count }}</div>
              <div
                class="w-full rounded-t bg-secondary dark:bg-secondary-400"
                :style="{ height: `${Math.max(4, (row.count / maxDailyCount) * 88)}px` }"
              />
              <div class="text-[10px] text-neutral-400 truncate w-full text-center">{{ shortDate(row.date) }}</div>
            </div>
          </div>
        </div>

        <!-- By type (flush table) -->
        <h2 class="flex items-center gap-2 font-semibold text-neutral-900 dark:text-white mb-3">
          <TicketIcon class="w-4 h-4" />
          {{ $t('tickets.by_type') }}
        </h2>
        <div class="border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700">
          <div
            v-for="row in stats.by_type"
            :key="row.id"
            class="flex items-center gap-4 px-4 py-3 hover:bg-primary-100 dark:hover:bg-primary-900/40"
          >
            <div class="flex-1 min-w-0">
              <div class="font-medium text-neutral-900 dark:text-white truncate">{{ row.name }}</div>
              <div v-if="row.target" class="text-xs text-neutral-500 dark:text-neutral-400">{{ row.target }}</div>
            </div>
            <div class="text-sm text-neutral-500 dark:text-neutral-400 w-16 text-right">
              ×{{ row.count.toLocaleString() }}
            </div>
            <div class="text-sm font-medium text-secondary dark:text-secondary-400 w-28 text-right">
              {{ row.sats.toLocaleString() }} sats
            </div>
            <div class="text-sm text-neutral-700 dark:text-neutral-300 w-20 text-right">
              <template v-if="row.eur">{{ formatEur(row.eur) }} €</template>
              <template v-else>—</template>
            </div>
          </div>
        </div>
      </template>
    </template>

    <UiConfirmModal
      :model-value="!!confirmRefund"
      :title="$t('tickets.refund_mark_refunded')"
      :message="confirmRefund ? $t('tickets.refund_confirm_message', {
        sats: confirmRefund.amount_paid_sats.toLocaleString(),
        buyer: confirmRefund.buyer_name,
      }) : ''"
      :confirm-label="$t('tickets.refund_mark_refunded')"
      variant="warning"
      :icon="Undo2"
      :loading="!!resolvingId"
      @update:model-value="confirmRefund = null"
      @confirm="confirmRefund && resolveRefund(confirmRefund, 'refund')"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { ChartColumn, Download, ScanLine, Ticket as TicketIcon, Undo2 } from 'lucide-vue-next'

definePageMeta({ middleware: 'auth' })

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const localePath = useLocalePath()
const authStore = useAuthStore()

useHead({ title: computed(() => `${t('tickets.operator_title')} — Parahub`) })

interface OperatorContext {
  establishment_id: string | null
  name: string
  types_count: number
}

interface Stats {
  total_sold: number
  revenue_sats: number
  revenue_eur: number
  daily: { date: string; count: number; sats: number }[]
  by_type: { id: string; name: string; target: string; count: number; sats: number; eur: number }[]
}

interface RefundRequest {
  ticket_id: string
  ticket_type_name: string
  buyer_name: string
  buyer_ln_address: string
  buyer_spark_address: string
  amount_paid_sats: number
  price_eur: number | null
  reason: string
  requested_at: string | null
}

const contexts = ref<OperatorContext[]>([])
const activeContext = ref('personal')
const days = ref(30)
const stats = ref<Stats | null>(null)
const refunds = ref<RefundRequest[]>([])
const confirmRefund = ref<RefundRequest | null>(null)
const resolvingId = ref<string | null>(null)
const loading = ref(true)
const csvLoading = ref(false)

const contextTabs = computed(() => contexts.value.map(c => ({
  id: c.establishment_id ?? 'personal',
  label: c.name,
  badge: c.types_count || undefined,
})))

const establishmentParam = computed(() =>
  activeContext.value === 'personal' ? undefined : activeContext.value
)

const maxDailyCount = computed(() =>
  Math.max(1, ...(stats.value?.daily.map(d => d.count) ?? [1]))
)

async function authedFetch<T>(url: string, opts: Record<string, any> = {}): Promise<T> {
  await authStore.ensureToken()
  return $fetch<T>(url, {
    credentials: 'include',
    headers: { Authorization: `Bearer ${authStore.token}` },
    ...opts,
  })
}

async function loadContexts() {
  contexts.value = await authedFetch<OperatorContext[]>('/api/v1/tickets/operator/contexts/')
  const ctx = route.query.ctx as string | undefined
  if (ctx && contexts.value.some(c => c.establishment_id === ctx)) {
    activeContext.value = ctx
  } else {
    // Default to the establishment context when personal has no types
    const personal = contexts.value.find(c => c.establishment_id === null)
    const firstOrg = contexts.value.find(c => c.establishment_id !== null && c.types_count > 0)
    if (personal && personal.types_count === 0 && firstOrg) {
      activeContext.value = firstOrg.establishment_id!
    }
  }
}

async function loadStats() {
  loading.value = true
  try {
    const [s, r] = await Promise.all([
      authedFetch<Stats>('/api/v1/tickets/operator/stats/', {
        query: { days: days.value, establishment_id: establishmentParam.value },
      }),
      authedFetch<RefundRequest[]>('/api/v1/tickets/operator/refunds/', {
        query: { establishment_id: establishmentParam.value },
      }).catch(() => [] as RefundRequest[]),
    ])
    stats.value = s
    refunds.value = r
  } finally {
    loading.value = false
  }
}

async function resolveRefund(r: RefundRequest, action: 'refund' | 'reject') {
  resolvingId.value = r.ticket_id
  try {
    await authedFetch(`/api/v1/tickets/${r.ticket_id}/refund-resolve/`, {
      method: 'POST',
      body: { action },
    })
    refunds.value = refunds.value.filter(x => x.ticket_id !== r.ticket_id)
  } finally {
    resolvingId.value = null
    confirmRefund.value = null
  }
}

function copyAddress(r: RefundRequest) {
  navigator.clipboard?.writeText(r.buyer_spark_address || r.buyer_ln_address)
}

async function downloadCsv() {
  csvLoading.value = true
  try {
    const blob = await authedFetch<Blob>('/api/v1/tickets/operator/sales.csv', {
      query: { days: days.value, establishment_id: establishmentParam.value },
      responseType: 'blob',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'ticket-sales.csv'
    a.click()
    URL.revokeObjectURL(url)
  } finally {
    csvLoading.value = false
  }
}

watch([activeContext, days], () => {
  router.replace({
    query: activeContext.value === 'personal' ? {} : { ctx: activeContext.value },
  })
  loadStats()
})

function formatEur(v: number) {
  return v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function shortDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { month: 'numeric', day: 'numeric' })
}

onMounted(async () => {
  try {
    await loadContexts()
  } catch {
    contexts.value = []
  }
  await loadStats().catch(() => { loading.value = false })
})
</script>
