<template>
  <div class="space-y-3">
    <!-- Header with create button -->
    <div class="flex items-center justify-between">
      <p class="text-sm text-neutral-500 dark:text-neutral-400">
        {{ $t('debts.description') }}
      </p>
      <button
        @click="openCreateModal"
        class="btn-primary btn-sm gap-2"
      >
        <Plus class="w-4 h-4" />
        {{ $t('debts.create.button') }}
      </button>
    </div>

    <!-- Sub-tabs -->
    <UiTabs v-model="activeSubTab" :tabs="debtTabs" variant="pills" full-width />

    <!-- Loading -->
    <div v-if="loading" class="text-center py-8">
      <div class="animate-spin w-8 h-8 border-4 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100 rounded-full mx-auto" role="status"><span class="sr-only">Loading...</span></div>
    </div>

    <!-- Debts list -->
    <template v-else>
      <div
        v-for="debt in filteredDebts"
        :key="debt.id"
        class="bg-white dark:bg-neutral-800 rounded-xl border border-neutral-200 dark:border-neutral-700 p-4"
      >
        <div class="flex items-start justify-between">
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-3 mb-1">
              <span class="text-xl font-bold text-neutral-900 dark:text-neutral-100">
                {{ debt.remaining_amount }} {{ debt.currency }}
              </span>
              <span
                :class="[
                  'px-2 py-0.5 text-xs font-medium rounded-full',
                  debt.status === 'ACTIVE' ? 'bg-success/10 text-success dark:bg-success/20 dark:text-success-400' :
                  debt.status === 'PENDING_CONFIRMATION' ? 'bg-warning/10 text-warning dark:bg-warning/20 dark:text-warning' :
                  'bg-neutral-100 text-neutral-800 dark:bg-neutral-700 dark:text-neutral-200'
                ]"
              >
                {{ getStatusText(debt.status) }}
              </span>
            </div>
            <p class="text-sm text-neutral-600 dark:text-neutral-400 mb-1">
              <NuxtLink :to="localePath(`/u/${debt.debtor_hna?.split('@')[0] || debt.debtor_id}`)" class="font-medium text-secondary hover:underline">{{ debt.debtor_display_name }}</NuxtLink>{{ $t('debts.owes') }}<NuxtLink :to="localePath(`/u/${debt.creditor_hna?.split('@')[0] || debt.creditor_id}`)" class="font-medium text-secondary hover:underline">{{ debt.creditor_display_name }}</NuxtLink>
            </p>
            <p v-if="debt.description" class="text-xs text-neutral-500 dark:text-neutral-400 mb-2">
              {{ debt.description }}
            </p>
            <!-- Confirmation status for pending debts -->
            <div v-if="debt.status === 'PENDING_CONFIRMATION'" class="mt-2 text-xs text-neutral-600 dark:text-neutral-400">
              <span :class="debt.confirmed_by_creditor_at ? 'text-success dark:text-success-400' : 'text-warning dark:text-warning'">
                <NuxtLink :to="localePath(`/u/${debt.creditor_hna?.split('@')[0] || debt.creditor_id}`)" class="font-medium hover:underline">{{ debt.creditor_display_name }}</NuxtLink>: {{ debt.confirmed_by_creditor_at ? '✓ ' + $t('debts.confirmed') : $t('debts.waiting') }}
              </span>
              <span class="mx-2">|</span>
              <span :class="debt.confirmed_by_debtor_at ? 'text-success dark:text-success-400' : 'text-warning dark:text-warning'">
                <NuxtLink :to="localePath(`/u/${debt.debtor_hna?.split('@')[0] || debt.debtor_id}`)" class="font-medium hover:underline">{{ debt.debtor_display_name }}</NuxtLink>: {{ debt.confirmed_by_debtor_at ? '✓ ' + $t('debts.confirmed') : $t('debts.waiting') }}
              </span>
            </div>
            <div v-else class="mt-2 flex items-center gap-3 text-xs text-neutral-500 dark:text-neutral-400">
              <span>{{ $t('debts.item.settled', { percent: Math.round(debt.percent_settled) }) }}</span>
              <span>•</span>
              <span>
                {{ new Date(debt.created_at).toLocaleString($i18n.locale, {
                  year: 'numeric',
                  month: 'short',
                  day: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit'
                }) }}
              </span>
            </div>
            <!-- OTS Anchoring -->
            <div v-if="debt.timestamp_proof" class="mt-2 flex items-center gap-2 text-xs">
              <span class="text-neutral-400 dark:text-neutral-500 uppercase tracking-wider shrink-0">OTS:</span>
              <span v-if="debt.timestamp_proof.bitcoin_block" class="text-warning dark:text-warning font-medium">
                ₿ {{ $t('debts.ots.block') }} #{{ debt.timestamp_proof.bitcoin_block }}
              </span>
              <span v-else class="text-neutral-400 dark:text-neutral-500 animate-pulse">
                {{ $t('debts.ots.pending') }}
              </span>
            </div>
          </div>
          <div class="flex gap-2 shrink-0 ml-2">
            <button
              v-if="debt.status === 'PENDING_CONFIRMATION' && canConfirm(debt)"
              @click="confirmDebt(debt, true)"
              class="btn-success text-sm px-3 py-1"
            >
              {{ $t('debts.item.confirm') }}
            </button>
            <button
              v-if="(debt.status === 'ACTIVE' || debt.status === 'PARTIALLY_SETTLED') && debt.creditor_id === authStore.activeProfile?.id"
              @click="openRepayModal(debt)"
              class="btn-secondary text-sm px-3 py-1"
            >
              {{ $t('debts.item.record_payment') }}
            </button>
          </div>
        </div>
      </div>

      <div v-if="filteredDebts.length === 0" class="bg-white dark:bg-neutral-800 rounded-xl p-6 text-center">
        <img src="/images/para/celebrating.webp" alt="Para" class="mx-auto h-32 w-auto mb-4" />
        <h3 class="text-lg font-medium text-neutral-900 dark:text-neutral-100 mb-2">
          {{ $t('debts.empty') }}
        </h3>
        <p class="text-neutral-500 dark:text-neutral-400">
          {{ $t('debts.empty_subtitle') }}
        </p>
      </div>
    </template>

    <!-- Create Debt Modal -->
    <div v-if="showCreateModal" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50" @click="showCreateModal = false">
      <div class="bg-white dark:bg-neutral-800 rounded-lg p-6 max-w-md w-full mx-4" @click.stop>
        <h2 class="text-xl font-bold mb-4 text-neutral-900 dark:text-neutral-100">{{ $t('debts.create.title') }}</h2>
        <div class="space-y-4">
          <div>
            <label for="debt-role" class="block text-sm font-medium mb-1 text-neutral-700 dark:text-neutral-300">{{ $t('debts.create.my_role') }}</label>
            <select id="debt-role" v-model="newDebt.myRole" class="w-full px-3 py-2 border rounded dark:bg-neutral-700 dark:border-neutral-600 text-neutral-900 dark:text-neutral-100">
              <option value="debtor">{{ $t('debts.create.debtor') }}</option>
              <option value="creditor">{{ $t('debts.create.creditor') }}</option>
            </select>
          </div>
          <div>
            <label for="debt-partner" class="block text-sm font-medium mb-1 text-neutral-700 dark:text-neutral-300">{{ $t('debts.create.other_person') }}</label>
            <select id="debt-partner" v-model="newDebt.otherPersonId" class="w-full px-3 py-2 border rounded dark:bg-neutral-700 dark:border-neutral-600 text-neutral-900 dark:text-neutral-100">
              <option value="">-- {{ $t('debts.create.select_partner') }} --</option>
              <optgroup v-if="partners.length > 0" :label="$t('debts.create.your_partners')">
                <option v-for="partner in partners" :key="partner.id" :value="partner.id">
                  {{ partner.display_name || partner.hna }}
                </option>
              </optgroup>
              <optgroup v-if="temporaryPartners.length > 0" :label="$t('debts.create.other')">
                <option v-for="partner in temporaryPartners" :key="partner.id" :value="partner.id">
                  {{ partner.display_name || partner.hna }}
                </option>
              </optgroup>
            </select>
          </div>
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label for="debt-amount" class="block text-sm font-medium mb-1 text-neutral-700 dark:text-neutral-300">{{ $t('debts.create.amount') }}</label>
              <input id="debt-amount" v-model.number="newDebt.amount" type="number" step="0.01" min="0.01" required class="w-full px-3 py-2 border rounded dark:bg-neutral-700 dark:border-neutral-600 text-neutral-900 dark:text-neutral-100" />
            </div>
            <div>
              <label for="debt-currency" class="block text-sm font-medium mb-1 text-neutral-700 dark:text-neutral-300">{{ $t('debts.create.currency') }}</label>
              <select id="debt-currency" v-model="newDebt.currency" class="w-full px-3 py-2 border rounded dark:bg-neutral-700 dark:border-neutral-600 text-neutral-900 dark:text-neutral-100">
                <option v-for="curr in availableCurrencies" :key="curr" :value="curr">
                  {{ curr }}
                </option>
              </select>
            </div>
          </div>
          <div>
            <label for="debt-description" class="block text-sm font-medium mb-1 text-neutral-700 dark:text-neutral-300">{{ $t('debts.create.description') }}</label>
            <textarea id="debt-description" v-model="newDebt.description" rows="3" class="w-full px-3 py-2 border rounded dark:bg-neutral-700 dark:border-neutral-600 text-neutral-900 dark:text-neutral-100"></textarea>
          </div>
          <div class="flex gap-2">
            <UiButton variant="primary" class="flex-1" @click="createDebt">{{ $t('debts.create.submit') }}</UiButton>
            <UiButton variant="outline" @click="showCreateModal = false">{{ $t('debts.create.cancel') }}</UiButton>
          </div>
        </div>
      </div>
    </div>

    <!-- Repayment Modal -->
    <div v-if="showRepaymentModal" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50" @click="showRepaymentModal = false">
      <div class="bg-white dark:bg-neutral-800 rounded-lg p-6 max-w-md w-full mx-4" @click.stop>
        <h2 class="text-xl font-bold mb-4 text-neutral-900 dark:text-neutral-100">
          {{ $t('debts.repay.title') }}
        </h2>
        <div v-if="selectedDebt" class="space-y-4">
          <div class="bg-neutral-100 dark:bg-neutral-700 p-3 rounded">
            <p class="text-sm text-neutral-600 dark:text-neutral-400">
              {{ $t('debts.repay.debt_info') }}:
            </p>
            <p class="font-bold text-lg">
              <NuxtLink :to="localePath(`/u/${selectedDebt.debtor_hna?.split('@')[0] || selectedDebt.debtor_id}`)" class="text-secondary hover:underline">{{ selectedDebt.debtor_display_name }}</NuxtLink>{{ $t('debts.owes') }}<NuxtLink :to="localePath(`/u/${selectedDebt.creditor_hna?.split('@')[0] || selectedDebt.creditor_id}`)" class="text-secondary hover:underline">{{ selectedDebt.creditor_display_name }}</NuxtLink>
            </p>
            <p class="text-sm text-neutral-600 dark:text-neutral-400 mt-1">
              {{ $t('debts.repay.remaining') }}: {{ selectedDebt.remaining_amount }} {{ selectedDebt.currency }}
            </p>
          </div>
          <div>
            <label for="repayment-amount" class="block text-sm font-medium mb-1 text-neutral-700 dark:text-neutral-300">
              {{ $t('debts.repay.amount') }}:
            </label>
            <input
              id="repayment-amount"
              v-model.number="repayment.amount"
              type="number"
              step="0.01"
              min="0.01"
              :max="selectedDebt.remaining_amount"
              required
              class="w-full px-3 py-2 border rounded dark:bg-neutral-700 dark:border-neutral-600 text-neutral-900 dark:text-neutral-100"
            />
            <p class="text-xs text-neutral-500 mt-1">
              {{ $t('debts.repay.max') }}: {{ selectedDebt.remaining_amount }} {{ selectedDebt.currency }}
            </p>
          </div>
          <div>
            <label for="repayment-notes" class="block text-sm font-medium mb-1 text-neutral-700 dark:text-neutral-300">
              {{ $t('debts.repay.notes') }}:
            </label>
            <textarea id="repayment-notes" v-model="repayment.notes" rows="2" class="w-full px-3 py-2 border rounded dark:bg-neutral-700 dark:border-neutral-600 text-neutral-900 dark:text-neutral-100"></textarea>
          </div>
          <div class="flex gap-2">
            <UiButton variant="success" class="flex-1" @click="recordRepayment">
              {{ $t('debts.repay.submit') }}
            </UiButton>
            <UiButton variant="outline" @click="showRepaymentModal = false">
              {{ $t('debts.create.cancel') }}
            </UiButton>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { Plus, HandCoins } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'
import { useToastStore } from '~/stores/toast'
import { useWebSocket } from '~/composables/useWebSocket'
import { usePGP } from '~/composables/usePGP'

const authStore = useAuthStore()
const toastStore = useToastStore()
const { t: $t } = useI18n()
const localePath = useLocalePath()
const { loadKeys, signCanonicalPayload } = usePGP()

const debts = ref([])
const partners = ref([])
const temporaryPartners = ref([])
const loading = ref(false)
const activeSubTab = ref('owed_to_me')
const showCreateModal = ref(false)
const showRepaymentModal = ref(false)
const selectedDebt = ref(null)

const newDebt = ref({
  myRole: 'debtor',
  otherPersonId: '',
  amount: 0,
  currency: 'EUR',
  description: ''
})

const repayment = ref({
  amount: 0,
  notes: ''
})

const availableCurrencies = computed(() => {
  const prefs = authStore.activeProfile?.preferences
  if (prefs?.accepted_currencies && Array.isArray(prefs.accepted_currencies)) {
    return prefs.accepted_currencies
  }
  return ['EUR', 'USD', 'GBP', 'RUB', 'BRL', 'CNY', 'JPY']
})

const filteredDebts = computed(() => {
  if (!debts.value) return []
  const myId = authStore.activeProfile?.id

  if (activeSubTab.value === 'owed_to_me') {
    return debts.value.filter(d => d.creditor_id === myId && (d.status === 'ACTIVE' || d.status === 'PARTIALLY_SETTLED'))
  } else if (activeSubTab.value === 'i_owe') {
    return debts.value.filter(d => d.debtor_id === myId && (d.status === 'ACTIVE' || d.status === 'PARTIALLY_SETTLED'))
  } else {
    return debts.value.filter(d => d.status === 'PENDING_CONFIRMATION')
  }
})

const owedToMeCount = computed(() => {
  if (!debts.value) return 0
  const myId = authStore.activeProfile?.id
  return debts.value.filter(d => d.creditor_id === myId && (d.status === 'ACTIVE' || d.status === 'PARTIALLY_SETTLED')).length
})

const iOweCount = computed(() => {
  if (!debts.value) return 0
  const myId = authStore.activeProfile?.id
  return debts.value.filter(d => d.debtor_id === myId && (d.status === 'ACTIVE' || d.status === 'PARTIALLY_SETTLED')).length
})

const pendingCount = computed(() => {
  if (!debts.value) return 0
  return debts.value.filter(d => d.status === 'PENDING_CONFIRMATION').length
})

const debtTabs = computed(() => [
  { id: 'owed_to_me', label: $t('debts.tabs.owed_to_me'), badge: owedToMeCount.value > 0 ? owedToMeCount.value : undefined },
  { id: 'i_owe', label: $t('debts.tabs.i_owe'), badge: iOweCount.value > 0 ? iOweCount.value : undefined },
  { id: 'pending', label: $t('debts.tabs.pending'), badge: pendingCount.value > 0 ? pendingCount.value : undefined },
])

const canConfirm = (debt) => {
  const myId = authStore.activeProfile?.id
  return debt.debtor_id === myId && !debt.confirmed_by_debtor_at
}

function getStatusText(status) {
  const key = `debts.status.${status.toLowerCase()}`
  return $t(key)
}

async function fetchDebts() {
  loading.value = true
  try {
    await authStore.ensureToken()
    const response = await $fetch('/api/v1/debts/', {
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
      params: { mine_only: true }
    })
    debts.value = response
  } catch (err) {
    console.error('Failed to fetch debts:', err)
  } finally {
    loading.value = false
  }
}

async function fetchPartners() {
  try {
    await authStore.ensureToken()
    const response = await $fetch('/api/v1/partners/list/', {
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` }
    })
    partners.value = response.items || response
  } catch (err) {
    console.error('Failed to fetch partners:', err)
  }
}

async function openCreateModal() {
  showCreateModal.value = true
  if (partners.value.length === 0) {
    await fetchPartners()
  }
}

async function createDebt() {
  if (!newDebt.value.otherPersonId) {
    alert($t('debts.create.select_partner'))
    return
  }

  if (newDebt.value.amount <= 0) {
    alert($t('debts.repay.error_amount'))
    return
  }

  try {
    await authStore.ensureToken()
    const creditorId = newDebt.value.myRole === 'creditor' ? authStore.activeProfile.id : newDebt.value.otherPersonId
    const debtorId = newDebt.value.myRole === 'debtor' ? authStore.activeProfile.id : newDebt.value.otherPersonId
    const amountStr = String(Number(newDebt.value.amount).toFixed(2))

    const timestamp = new Date().toISOString()
    const pgpSignature = await signCanonicalPayload({
      action: 'create_debt',
      amount: amountStr,
      creditor_id: creditorId,
      currency: newDebt.value.currency,
      debtor_id: debtorId,
      timestamp,
    })

    const payload = {
      creditor_id: creditorId,
      debtor_id: debtorId,
      amount: newDebt.value.amount,
      currency: newDebt.value.currency,
      description: newDebt.value.description,
      pgp_signature: pgpSignature,
      signed_timestamp: timestamp,
    }

    await $fetch('/api/v1/debts/', {
      method: 'POST',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
      body: payload
    })

    showCreateModal.value = false
    newDebt.value = { myRole: 'debtor', otherPersonId: '', amount: 0, currency: 'EUR', description: '' }
    await fetchDebts()
  } catch (err) {
    console.error('Failed to create debt:', err)
    alert('Failed to create debt: ' + (err.data?.message || err.message))
  }
}

async function confirmDebt(debt, confirmed) {
  try {
    await authStore.ensureToken()

    const timestamp = new Date().toISOString()
    const pgpSignature = await signCanonicalPayload({
      action: 'confirm_debt',
      confirmed,
      debt_id: debt.id,
      timestamp,
    })

    await $fetch(`/api/v1/debts/${debt.id}/confirm/`, {
      method: 'POST',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
      body: {
        confirmed,
        pgp_signature: pgpSignature,
        signed_timestamp: timestamp,
      }
    })
    await fetchDebts()
  } catch (err) {
    console.error('Failed to confirm debt:', err)
    alert('Failed to confirm debt: ' + (err.data?.message || err.message))
  }
}

function openRepayModal(debt) {
  selectedDebt.value = debt
  repayment.value = {
    amount: debt.remaining_amount,
    notes: ''
  }
  showRepaymentModal.value = true
}

async function recordRepayment() {
  if (!selectedDebt.value) return

  if (repayment.value.amount <= 0) {
    alert($t('debts.repay.error_amount'))
    return
  }

  if (repayment.value.amount > selectedDebt.value.remaining_amount) {
    alert($t('debts.repay.error_exceeds'))
    return
  }

  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/debts/${selectedDebt.value.id}/repay/`, {
      method: 'POST',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
      body: {
        amount: repayment.value.amount,
        notes: repayment.value.notes
      }
    })

    showRepaymentModal.value = false
    selectedDebt.value = null
    await fetchDebts()
  } catch (err) {
    console.error('Failed to record repayment:', err)
    alert('Failed to record repayment: ' + (err.data?.message || err.message))
  }
}

// WebSocket for real-time updates
const { connect: connectWS, disconnect: disconnectWS } = useWebSocket({
  path: '/ws/v1/realtime/',
  onMessage: (data) => {
    if (data.type === 'debt.created' || data.type === 'debt.updated') {
      handleDebtUpdate(data.debt)
    }
  },
  onOpen: () => {},
  autoReconnect: true
})

function handleDebtUpdate(debtData) {
  const myId = authStore.activeProfile?.id
  const index = debts.value.findIndex(d => d.id === debtData.id)
  const isCreditor = debtData.creditor_id === myId
  const isDebtor = debtData.debtor_id === myId

  if (index === -1 && (isCreditor || isDebtor)) {
    const otherPerson = isCreditor ? debtData.debtor_display_name : debtData.creditor_display_name
    if (debtData.status === 'PENDING_CONFIRMATION') {
      toastStore.info(
        $t('debts.toast.new_pending', { person: otherPerson, amount: debtData.amount, currency: debtData.currency })
      )
    } else {
      toastStore.success(
        $t('debts.toast.new_active', { person: otherPerson, amount: debtData.amount, currency: debtData.currency })
      )
    }
    debts.value.unshift(debtData)
  } else if (index !== -1) {
    const oldDebt = debts.value[index]

    if (oldDebt.status !== debtData.status && debtData.status === 'ACTIVE') {
      toastStore.success($t('debts.toast.confirmed'))
    }

    if (oldDebt.remaining_amount !== debtData.remaining_amount) {
      const paidAmount = oldDebt.remaining_amount - debtData.remaining_amount
      if (debtData.status === 'FULLY_SETTLED') {
        toastStore.success(
          $t('debts.toast.fully_settled', { amount: paidAmount, currency: debtData.currency })
        )
      } else {
        toastStore.info(
          $t('debts.toast.partial_payment', { amount: paidAmount, currency: debtData.currency, remaining: debtData.remaining_amount })
        )
      }
    }

    debts.value[index] = { ...debts.value[index], ...debtData }
  }

  if (debtData.status === 'FULLY_SETTLED') {
    setTimeout(() => {
      debts.value = debts.value.filter(d => d.id !== debtData.id)
    }, 2000)
  }
}

// Handle query param partner pre-selection (from /wallet/debts?partner=ULID)
async function handlePartnerQuery() {
  const route = useRoute()
  const router = useRouter()

  if (route.query.partner) {
    const partnerId = String(route.query.partner)

    try {
      await authStore.ensureToken()
      const partnerProfile = await $fetch(`/api/v1/profiles/${partnerId}/`, {
        credentials: 'include',
        headers: authStore.token ? {
          'Authorization': `Bearer ${authStore.token}`
        } : {}
      })

      await fetchPartners()

      const isInPartners = partners.value.some(p => p.id === partnerId)

      if (!isInPartners) {
        temporaryPartners.value = [{
          id: partnerProfile.id,
          hna: partnerProfile.hna,
          display_name: partnerProfile.display_name,
          _temporary: true
        }]
      }

      newDebt.value.otherPersonId = partnerId
      newDebt.value.myRole = 'debtor'
      showCreateModal.value = true

      router.replace({ query: {} })
    } catch (error) {
      console.error('Failed to load partner from query:', error)
      toastStore.error($t('debts.toast.partner_load_failed'))
    }
  }
}

// Expose load function for parent to call
const loadDebts = async () => {
  loadKeys()
  await fetchDebts()
  await authStore.ensureToken()
  connectWS()
  await handlePartnerQuery()
}

defineExpose({ loadDebts })

onMounted(() => {
  loadDebts()
})

onUnmounted(() => {
  disconnectWS()
})
</script>
