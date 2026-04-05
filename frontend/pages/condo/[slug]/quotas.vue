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
    <UiTabs
      model-value="quotas"
      :tabs="condoTabs"
      variant="nav"
      class="mb-6"
    />

    <!-- Month selector + Budget header -->
    <div class="flex items-center justify-between mb-4 gap-4">
      <div class="min-w-0">
        <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100">{{ $t('condo.month_select') }}</h2>
        <div v-if="pageData?.monthly_budget > 0" class="text-sm text-neutral-500 mt-0.5">
          {{ $t('condo.monthly_budget') }}: <span class="inline-flex items-center gap-1 font-medium text-neutral-700 dark:text-neutral-300">{{ Number(pageData.monthly_budget).toFixed(2) }}&nbsp;€
            <button v-if="pageData.is_admin" :aria-label="$t('condo.edit_budget')" class="text-link text-xs ml-1 inline-flex items-center" @click="openBudgetEdit">
              <Pencil class="w-3 h-3" />
            </button>
          </span>
        </div>
        <div v-else-if="pageData?.is_admin" class="text-sm mt-0.5">
          <button class="text-link text-xs" @click="openBudgetEdit">{{ $t('condo.set_budget') }}</button>
        </div>
      </div>
      <input v-model="month" type="month" class="input text-sm shrink-0" />
    </div>

    <!-- Delinquency alert -->
    <UiAlert v-if="pageData && pageData.delinquent_count > 0" variant="error" class="mb-4">
      {{ $t('condo.delinquency_alert', { count: pageData.delinquent_count }) }}
    </UiAlert>

    <!-- Loading -->
    <div v-if="pending" class="flex justify-center py-16">
      <Loader2 class="w-8 h-8 animate-spin text-primary" />
    </div>

    <!-- Empty state: no budget set -->
    <div v-else-if="pageData && Number(pageData.monthly_budget) === 0 && pageData.is_admin" class="text-center py-12">
      <Receipt class="w-12 h-12 text-neutral-300 dark:text-neutral-600 mx-auto mb-3" />
      <p class="text-sm text-neutral-500 dark:text-neutral-400 mb-3">{{ $t('condo.no_budget_hint') }}</p>
      <UiButton variant="primary" size="sm" @click="openBudgetEdit">{{ $t('condo.set_budget') }}</UiButton>
    </div>

    <!-- Empty state: no fractions -->
    <div v-else-if="!quotaItems?.length" class="text-center py-12">
      <Receipt class="w-12 h-12 text-neutral-300 dark:text-neutral-600 mx-auto mb-3" />
      <p class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('condo.empty_quotas') }}</p>
    </div>

    <div v-else>
      <!-- Summary bar -->
      <div class="bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4 mb-4">
        <div class="flex justify-between text-sm">
          <span class="text-neutral-500">
            {{ $t('condo.fractions_paid_summary', { paid: pageData?.fractions_paid || 0, total: pageData?.fractions_total || 0 }) }}
          </span>
          <span class="font-bold text-neutral-700 dark:text-neutral-300">
            <span class="text-success-700 dark:text-success-400">{{ totalPaid.toFixed(2) }}</span>
            / {{ totalExpected.toFixed(2) }} €
          </span>
        </div>
        <div class="mt-2 w-full bg-neutral-200 dark:bg-neutral-700 rounded-full h-2">
          <div
            :style="{ width: totalExpected > 0 ? Math.min(totalPaid / totalExpected * 100, 100) + '%' : '0%' }"
            class="h-2 rounded-full bg-success transition-all"
          />
        </div>
      </div>

      <!-- Desktop table -->
      <div class="hidden sm:block bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700 overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-neutral-50 dark:bg-neutral-800">
              <tr>
                <th class="px-4 py-2 text-left text-xs font-medium text-neutral-500">{{ $t('condo.identifier') }}</th>
                <th class="px-4 py-2 text-left text-xs font-medium text-neutral-500">{{ $t('condo.resident') }}</th>
                <th class="px-4 py-2 text-right text-xs font-medium text-neutral-500">{{ $t('condo.expected') }}</th>
                <th class="px-4 py-2 text-center text-xs font-medium text-neutral-500">{{ $t('condo.status') }}</th>
                <th class="px-4 py-2 text-right text-xs font-medium text-neutral-500"></th>
              </tr>
            </thead>
            <tbody class="divide-y divide-neutral-100 dark:divide-neutral-800">
              <tr
                v-for="q in quotaItems"
                :key="q.fraction_id"
                :class="{ 'bg-error-50 dark:bg-error-950/30': q.months_unpaid >= 2 }"
              >
                <td class="px-4 py-3">
                  <span class="font-medium text-neutral-900 dark:text-neutral-100">{{ q.identifier }}</span>
                  <span class="text-xs text-neutral-400 ml-1">{{ Number(q.permilagem).toFixed(1) }}‰</span>
                </td>
                <td class="px-4 py-3 text-neutral-600 dark:text-neutral-400">
                  <span v-if="q.resident_display_name">{{ q.resident_display_name }}</span>
                  <span v-else class="text-neutral-400 italic text-xs">{{ $t('condo.vacant') }}</span>
                </td>
                <td class="px-4 py-3 text-right font-mono text-neutral-700 dark:text-neutral-300">{{ Number(q.expected_quota).toFixed(2) }} €</td>
                <td class="px-4 py-3 text-center">
                  <UiBadge v-if="q.paid" variant="success" size="sm">{{ $t('condo.paid') }}</UiBadge>
                  <UiBadge v-else variant="error" size="sm">{{ $t('condo.unpaid') }}</UiBadge>
                  <div v-if="q.months_unpaid >= 2" class="text-xs text-error-600 dark:text-error-400 mt-0.5">
                    {{ $t('condo.months_unpaid', { count: q.months_unpaid }) }}
                  </div>
                </td>
                <td class="px-4 py-3 text-right">
                  <button
                    v-if="!q.paid && pageData?.is_admin"
                    class="text-link text-xs"
                    @click="openPayment(q)"
                  >
                    {{ $t('condo.record_payment') }}
                  </button>
                  <span v-else-if="q.payment?.confirmed_by_hna" class="text-xs text-neutral-400">
                    {{ $t('condo.confirmed_by') }}: {{ q.payment.confirmed_by_display_name || q.payment.confirmed_by_hna.split('@')[0] }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Mobile cards -->
      <div class="sm:hidden space-y-3">
        <div
          v-for="q in quotaItems"
          :key="q.fraction_id"
          class="bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4"
          :class="{ 'border-error-300 dark:border-error-700': q.months_unpaid >= 2 }"
        >
          <div class="flex items-start justify-between mb-2">
            <div>
              <span class="font-medium text-neutral-900 dark:text-neutral-100">{{ q.identifier }}</span>
              <span class="text-xs text-neutral-400 ml-1">{{ Number(q.permilagem).toFixed(1) }}‰</span>
              <div v-if="q.resident_display_name" class="text-xs text-neutral-500 mt-0.5">{{ q.resident_display_name }}</div>
              <div v-else class="text-xs text-neutral-400 italic mt-0.5">{{ $t('condo.vacant') }}</div>
            </div>
            <div class="text-right">
              <UiBadge v-if="q.paid" variant="success" size="sm">{{ $t('condo.paid') }}</UiBadge>
              <UiBadge v-else variant="error" size="sm">{{ $t('condo.unpaid') }}</UiBadge>
              <div v-if="q.months_unpaid >= 2" class="text-xs text-error-600 dark:text-error-400 mt-0.5">
                {{ $t('condo.months_unpaid', { count: q.months_unpaid }) }}
              </div>
            </div>
          </div>
          <div class="flex items-center justify-between text-sm mb-2">
            <span class="text-neutral-500">{{ $t('condo.expected') }}</span>
            <span class="font-mono text-neutral-700 dark:text-neutral-300">{{ Number(q.expected_quota).toFixed(2) }} €</span>
          </div>
          <div class="flex items-center justify-between">
            <span v-if="q.payment?.confirmed_by_hna" class="text-xs text-neutral-400">
              {{ $t('condo.confirmed_by') }}: {{ q.payment.confirmed_by_display_name || q.payment.confirmed_by_hna.split('@')[0] }}
            </span>
            <span v-else />
            <button
              v-if="!q.paid && pageData?.is_admin"
              class="text-link text-xs"
              @click="openPayment(q)"
            >
              {{ $t('condo.record_payment') }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Budget edit modal -->
    <div v-if="budgetModal" class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" @click.self="budgetModal = false">
      <div class="bg-white dark:bg-neutral-900 rounded-lg max-w-sm w-full p-6">
        <h3 class="text-lg font-bold text-neutral-900 dark:text-neutral-100 mb-4">{{ $t('condo.edit_budget') }}</h3>
        <div>
          <label class="text-xs text-neutral-500">{{ $t('condo.monthly_budget') }} (€)</label>
          <input v-model.number="budgetForm.amount" type="number" step="0.01" min="0" class="input w-full" />
          <p class="text-xs text-neutral-400 mt-1">{{ $t('condo.budget_hint') }}</p>
        </div>
        <UiAlert v-if="budgetError" variant="error" class="mt-3" dismissible @dismiss="budgetError = ''">
          {{ budgetError }}
        </UiAlert>
        <div class="flex justify-end gap-3 mt-4">
          <UiButton variant="outline" size="sm" @click="budgetModal = false">{{ $t('common.close') }}</UiButton>
          <UiButton variant="primary" size="sm" :loading="savingBudget" @click="submitBudget">{{ $t('condo.save_budget') }}</UiButton>
        </div>
      </div>
    </div>

    <!-- Payment modal -->
    <div v-if="paymentModal" class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" @click.self="paymentModal = null">
      <div class="bg-white dark:bg-neutral-900 rounded-lg max-w-sm w-full p-6">
        <h3 class="text-lg font-bold text-neutral-900 dark:text-neutral-100 mb-4">
          {{ $t('condo.record_payment') }} — {{ paymentModal.identifier }}
        </h3>
        <div v-if="paymentModal.resident_display_name" class="text-sm text-neutral-500 mb-3">
          {{ paymentModal.resident_display_name }}
        </div>
        <div class="space-y-3">
          <div>
            <label class="text-xs text-neutral-500">{{ $t('condo.payment_amount') }} (€)</label>
            <input v-model.number="paymentForm.amount" type="number" step="0.01" class="input w-full" />
          </div>
          <div>
            <label class="text-xs text-neutral-500">{{ $t('condo.payment_notes') }}</label>
            <input v-model="paymentForm.notes" type="text" :placeholder="$t('condo.payment_notes_placeholder')" class="input w-full" />
          </div>
        </div>
        <UiAlert v-if="paymentError" variant="error" class="mt-3" dismissible @dismiss="paymentError = ''">
          {{ paymentError }}
        </UiAlert>
        <div class="flex justify-end gap-3 mt-4">
          <UiButton variant="outline" size="sm" @click="paymentModal = null">{{ $t('common.close') }}</UiButton>
          <UiButton variant="primary" size="sm" :loading="savingPayment" @click="submitPayment">
            {{ $t('condo.record_payment') }}
          </UiButton>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ArrowLeft, Loader2, Grid3x3, Receipt, Vote, Pencil } from 'lucide-vue-next'

definePageMeta({
  middleware: 'auth',
})

const route = useRoute()
const { t } = useI18n()
const localePath = useLocalePath()
const authStore = useAuthStore()

const slug = route.params.slug as string
const month = ref(new Date().toISOString().substring(0, 7))
const condoName = ref('')

const { data: condoInfo } = await useAsyncData(`condo-info-${slug}`, () =>
  $fetch<any>(`/api/v1/geo/condominiums/${slug}/info/`).catch(() => null),
  { server: false }
)
watch(condoInfo, (v) => { if (v?.name) condoName.value = v.name }, { immediate: true })

useSeoMeta({
  title: () => condoName.value ? `${condoName.value} — ${t('condo.quotas_tab')}` : t('condo.meta_quotas_title'),
  ogTitle: () => condoName.value ? `${condoName.value} — ${t('condo.quotas_tab')}` : t('condo.meta_quotas_title'),
  description: () => t('condo.meta_quotas_desc'),
  ogDescription: () => t('condo.meta_quotas_desc'),
  ogImage: '/og-image.jpg',
  ogType: 'website',
  twitterCard: 'summary',
})

const condoTabs = computed(() => [
  { id: 'fractions', label: t('condo.fractions_tab'), icon: Grid3x3, to: localePath(`/condo/${slug}/fractions`) },
  { id: 'quotas', label: t('condo.quotas_tab'), icon: Receipt, to: localePath(`/condo/${slug}/quotas`) },
  { id: 'assembly', label: t('condo.assembly_tab'), icon: Vote, to: localePath(`/condo/${slug}/assembly`) },
])

const pageData = ref<any>(null)
const pending = ref(true)

const refresh = async () => {
  pending.value = true
  try {
    await authStore.ensureToken()
    pageData.value = await $fetch<any>(`/api/v1/geo/condominiums/${slug}/quotas/?month=${month.value}`, {
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.accessToken}` },
    })
  } catch (err) {
    console.error('Failed to fetch quotas:', err)
  } finally {
    pending.value = false
  }
}

onMounted(() => refresh())
watch(month, () => refresh())

const quotaItems = computed(() => pageData.value?.items || [])

const totalPaid = computed(() => {
  return quotaItems.value.filter((q: any) => q.paid).reduce((sum: number, q: any) => sum + Number(q.payment?.amount || 0), 0)
})

const totalExpected = computed(() => {
  return quotaItems.value.reduce((sum: number, q: any) => sum + Number(q.expected_quota || 0), 0)
})

// Payment modal
const paymentModal = ref<any>(null)
const savingPayment = ref(false)
const paymentError = ref('')
const paymentForm = reactive({ amount: 0, notes: '' })

const openPayment = (q: any) => {
  paymentModal.value = q
  paymentForm.amount = Number(q.expected_quota)
  paymentForm.notes = ''
  paymentError.value = ''
}

const submitPayment = async () => {
  savingPayment.value = true
  paymentError.value = ''
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/geo/condominiums/${slug}/quotas/`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.accessToken}` },
      body: {
        fraction_id: paymentModal.value.fraction_id,
        month: month.value,
        amount: paymentForm.amount,
        notes: paymentForm.notes,
      }
    })
    paymentModal.value = null
    await refresh()
  } catch (err: any) {
    paymentError.value = err?.data?.detail || err?.message || 'Error recording payment'
  } finally {
    savingPayment.value = false
  }
}

// Budget edit modal
const budgetModal = ref(false)
const savingBudget = ref(false)
const budgetError = ref('')
const budgetForm = reactive({ amount: 0 })

const openBudgetEdit = () => {
  budgetForm.amount = Number(pageData.value?.monthly_budget || 0)
  budgetError.value = ''
  budgetModal.value = true
}

const submitBudget = async () => {
  savingBudget.value = true
  budgetError.value = ''
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/geo/condominiums/${slug}/budget/`, {
      method: 'PUT',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.accessToken}` },
      body: { monthly_budget: budgetForm.amount }
    })
    budgetModal.value = false
    await refresh()
  } catch (err: any) {
    budgetError.value = err?.data?.detail || err?.message || 'Error saving budget'
  } finally {
    savingBudget.value = false
  }
}
</script>
