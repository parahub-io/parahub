<template>
  <div class="space-y-4 w-full">
    <div class="bg-white dark:bg-neutral-800 rounded-xl p-6 w-full min-h-[200px]">
      <div v-if="loadingHistory" class="text-center py-8">
        <div class="animate-spin w-8 h-8 border-4 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100 rounded-full mx-auto" role="status">
          <span class="sr-only">Loading...</span>
        </div>
      </div>

      <div v-else-if="payments.length === 0 && unclaimedDeposits.length === 0 && mempoolDeposits.length === 0" class="text-center py-8 text-neutral-500">
        <History class="w-12 h-12 mx-auto mb-3 opacity-30" />
        {{ $t('wallet.noTransactions') }}
      </div>

      <template v-else>
        <!-- Export button -->
        <div class="flex justify-end mb-2">
          <button
            type="button"
            class="inline-flex items-center gap-1 text-xs text-neutral-500 hover:text-secondary transition-colors"
            @click="exportCSV"
          >
            <FileDown class="w-3.5 h-3.5" />
            {{ $t('wallet.exportCsv') }}
          </button>
        </div>

        <!-- Unclaimed on-chain deposits (pending) -->
        <div
          v-for="deposit in unclaimedDeposits"
          :key="`deposit-${deposit.txid}:${deposit.vout}`"
          class="py-3 first:pt-0"
        >
          <div class="flex items-center gap-2 mb-1">
            <ArrowDownLeft class="w-4 h-4 text-success-500 flex-shrink-0" />
            <span class="font-semibold text-success-600 dark:text-success-500">
              +{{ deposit.amountSats.toLocaleString() }} sats
            </span>
            <span class="text-[10px] px-1.5 py-0.5 rounded bg-neutral-100 dark:bg-neutral-700 text-neutral-500">
              deposit
            </span>
            <span class="text-[10px] px-1.5 py-0.5 rounded bg-warning-100 dark:bg-warning-900/30 text-warning-700 dark:text-warning-400">
              {{ $t('wallet.status_pending') }}
            </span>
            <div class="ml-auto flex-shrink-0">
              <UiButton
                variant="primary"
                size="sm"
                :loading="claimingTxid === `${deposit.txid}:${deposit.vout}`"
                @click="handleClaimDeposit(deposit)"
              >
                {{ $t('wallet.claimDeposit') }}
              </UiButton>
            </div>
          </div>
          <div class="pl-6">
            <a
              :href="`https://mempool.space/tx/${deposit.txid}`"
              target="_blank"
              rel="noopener"
              class="inline-flex items-center gap-1 font-mono text-[10px] text-neutral-400 hover:text-secondary transition-colors"
              :title="deposit.txid"
            >
              {{ deposit.txid.slice(0, 16) }}...{{ deposit.txid.slice(-8) }}
              <ExternalLink class="w-2.5 h-2.5" />
            </a>
            <p v-if="deposit.claimError?.type === 'maxDepositClaimFeeExceeded'" class="text-xs text-warning-600 dark:text-warning-400 mt-1">
              {{ $t('wallet.claimFeeExceeded', { fee: deposit.claimError.requiredFeeSats }) }}
            </p>
          </div>
        </div>

        <!-- Claim result messages -->
        <div v-if="claimError" class="py-2 text-xs text-error dark:text-error-400">{{ claimError }}</div>
        <div v-if="claimSuccess" class="py-2 text-xs text-success-600 dark:text-success-400">{{ $t('wallet.depositClaimed') }}</div>

        <!-- On-chain deposits (mempool tracking) -->
        <div
          v-for="md in mempoolDeposits"
          :key="`mempool-${md.txid}`"
          class="py-3 first:pt-0"
        >
          <div class="flex items-center gap-2 mb-1">
            <ArrowDownLeft class="w-4 h-4 text-success-500 flex-shrink-0" />
            <span class="font-semibold text-success-600 dark:text-success-500">
              +{{ md.amount.toLocaleString() }} sats
            </span>
            <span class="text-[10px] px-1.5 py-0.5 rounded bg-neutral-100 dark:bg-neutral-700 text-neutral-500">
              on-chain
            </span>
            <span
              class="text-[10px] px-1.5 py-0.5 rounded font-medium"
              :class="{
                'bg-error-100 dark:bg-error-900/30 text-error-700 dark:text-error-400': md.confirmations === 0,
                'bg-warning-100 dark:bg-warning-900/30 text-warning-700 dark:text-warning-400': md.confirmations >= 1 && md.confirmations <= 3,
                'bg-success-100 dark:bg-success-900/30 text-success-700 dark:text-success-400': md.confirmations >= 4
              }"
            >
              {{ md.confirmations }}/6
            </span>
            <div class="text-right ml-auto">
              <p class="text-xs text-neutral-400 tabular-nums">{{ formatPaymentDate(md.timestamp) }}</p>
              <p class="text-xs text-neutral-400 tabular-nums">{{ formatPaymentTime(md.timestamp) }}</p>
            </div>
          </div>
          <div class="pl-6">
            <a
              :href="`https://mempool.space/tx/${md.txid}`"
              target="_blank"
              rel="noopener"
              class="inline-flex items-center gap-1 font-mono text-[10px] text-neutral-400 hover:text-secondary transition-colors"
              :title="md.txid"
            >
              {{ md.txid.slice(0, 16) }}...{{ md.txid.slice(-8) }}
              <ExternalLink class="w-2.5 h-2.5" />
            </a>
          </div>
        </div>

        <!-- Completed payments -->
        <div
          v-for="(payment, idx) in payments"
          :key="payment.id"
          class="py-3 first:pt-0 last:pb-0 px-2 -mx-2 rounded"
          :class="idx % 2 === 1 ? 'bg-neutral-50 dark:bg-neutral-700/30' : ''"
        >
          <div class="flex items-center gap-2 mb-1">
            <ArrowDownLeft v-if="payment.paymentType === 'receive'" class="w-4 h-4 text-success-500 flex-shrink-0" />
            <ArrowUpRight v-else class="w-4 h-4 text-error-500 flex-shrink-0" />

            <span
              class="font-semibold"
              :class="{
                'text-success-600 dark:text-success-500': payment.paymentType === 'receive',
                'text-error-600 dark:text-error-500': payment.paymentType === 'send'
              }"
            >
              {{ payment.paymentType === 'receive' ? '+' : '-' }}{{ Number(payment.amount) }} sats
            </span>

            <span class="text-[10px] px-1.5 py-0.5 rounded bg-neutral-100 dark:bg-neutral-700 text-neutral-500">
              {{ payment.method }}
            </span>

            <span
              v-if="payment.status !== 'completed'"
              class="text-[10px] px-1.5 py-0.5 rounded"
              :class="{
                'bg-warning-100 dark:bg-warning-900/30 text-warning-700 dark:text-warning-400': payment.status === 'pending',
                'bg-error-100 dark:bg-error-900/30 text-error-700 dark:text-error-400': payment.status === 'failed'
              }"
            >
              {{ $t(`wallet.status_${payment.status}`) }}
            </span>

            <div class="text-right ml-auto">
              <p class="text-xs text-neutral-400 tabular-nums">{{ formatPaymentDate(payment.timestamp) }}</p>
              <p class="text-xs text-neutral-400 tabular-nums">{{ formatPaymentTime(payment.timestamp) }}</p>
            </div>
          </div>

          <div v-if="getPaymentDescription(payment)" class="pl-6">
            <p class="text-xs text-neutral-500 dark:text-neutral-400 truncate">
              {{ getPaymentDescription(payment) }}
            </p>
          </div>

          <div v-if="getPaymentTxId(payment)" class="pl-6">
            <a
              :href="`https://mempool.space/tx/${getPaymentTxId(payment)}`"
              target="_blank"
              rel="noopener"
              class="inline-flex items-center gap-1 font-mono text-[10px] text-neutral-400 hover:text-secondary transition-colors"
              :title="getPaymentTxId(payment)"
            >
              {{ getPaymentTxId(payment)!.slice(0, 16) }}...{{ getPaymentTxId(payment)!.slice(-8) }}
              <ExternalLink class="w-2.5 h-2.5" />
            </a>
          </div>

          <div v-if="Number(payment.fees) > 0" class="pl-6">
            <p class="text-[10px] text-neutral-400">
              {{ $t('wallet.fee') }}: {{ Number(payment.fees) }} sats
            </p>
          </div>
        </div>

        <UiButton
          v-if="payments.length >= historyLimit"
          variant="ghost"
          class="w-full mt-4 text-secondary"
          @click="loadMoreHistory"
        >
          {{ $t('wallet.loadMore') }}
        </UiButton>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { History, ArrowDownLeft, ArrowUpRight, ExternalLink, FileDown } from 'lucide-vue-next'
import { useLightning } from '~/composables/useLightning'
import { useBtcPrice } from '~/composables/useBtcPrice'
import type { Payment, DepositInfo } from '@breeztech/breez-sdk-spark/web'

const { t } = useI18n()

const {
  sdkState,
  unclaimedDeposits,
  fetchUnclaimedDeposits,
  claimDeposit,
  listPayments,
  getDepositAddress,
  paymentEventVersion,
  formatSats,
} = useLightning()

const { satsToFiat, formatFiat, userCurrency } = useBtcPrice()

// ===== HISTORY =====
const payments = ref<Payment[]>([])
const loadingHistory = ref(false)
const historyLimit = ref(50)
const historyOffset = ref(0)

const loadHistory = async () => {
  if (sdkState.value !== 'ready') return
  loadingHistory.value = true
  try {
    payments.value = await listPayments(historyLimit.value, 0)
    historyOffset.value = payments.value.length
  } catch (e) {
    console.error('Failed to load history:', e)
  } finally {
    loadingHistory.value = false
  }
}

const loadMoreHistory = async () => {
  try {
    const more = await listPayments(historyLimit.value, historyOffset.value)
    payments.value.push(...more)
    historyOffset.value += more.length
  } catch (e) {
    console.error('Failed to load more history:', e)
  }
}

// ===== CLAIM DEPOSITS =====
const claimingTxid = ref('')
const claimError = ref('')
const claimSuccess = ref(false)

const handleClaimDeposit = async (deposit: DepositInfo) => {
  const key = `${deposit.txid}:${deposit.vout}`
  claimingTxid.value = key
  claimError.value = ''
  claimSuccess.value = false
  try {
    await claimDeposit(deposit.txid, deposit.vout)
    claimSuccess.value = true
    setTimeout(() => { claimSuccess.value = false }, 5000)
  } catch (e: any) {
    claimError.value = e.message || t('wallet.depositClaimFailed')
  } finally {
    claimingTxid.value = ''
  }
}

// ===== MEMPOOL DEPOSITS =====
interface MempoolDeposit {
  txid: string
  amount: number
  confirmations: number
  timestamp: number
  fee: number
}

const mempoolDeposits = ref<MempoolDeposit[]>([])
let mempoolPollingTimer: ReturnType<typeof setInterval> | null = null

const fetchMempoolDeposits = async () => {
  try {
    const addr = await getDepositAddress()
    if (!addr) return

    const [txs, tipHeight] = await Promise.all([
      $fetch<any[]>(`https://mempool.space/api/address/${addr}/txs`),
      $fetch<number>('https://mempool.space/api/blocks/tip/height')
    ])

    const knownTxids = new Set([
      ...unclaimedDeposits.value.map(d => d.txid),
      ...payments.value
        .filter(p => p.details?.type === 'deposit')
        .map(p => (p.details as any).txId)
        .filter(Boolean)
    ])

    const deposits: MempoolDeposit[] = []
    for (const tx of txs) {
      if (knownTxids.has(tx.txid)) continue

      let amount = 0
      for (const vout of tx.vout) {
        if (vout.scriptpubkey_address === addr) {
          amount += vout.value
        }
      }
      if (amount === 0) continue

      const confirmed = tx.status?.confirmed === true
      const confirmations = confirmed ? (tipHeight - tx.status.block_height + 1) : 0

      if (confirmations >= 6) continue

      deposits.push({
        txid: tx.txid,
        amount,
        confirmations,
        timestamp: confirmed ? tx.status.block_time : (tx.firstSeen || Math.floor(Date.now() / 1000)),
        fee: tx.fee || 0
      })
    }

    deposits.sort((a, b) => a.confirmations - b.confirmations)
    mempoolDeposits.value = deposits
  } catch (e) {
    console.error('Mempool fetch failed:', e)
  }
}

const startMempoolPolling = () => {
  stopMempoolPolling()
  fetchMempoolDeposits()
  mempoolPollingTimer = setInterval(fetchMempoolDeposits, 30_000)
}

const stopMempoolPolling = () => {
  if (mempoolPollingTimer) {
    clearInterval(mempoolPollingTimer)
    mempoolPollingTimer = null
  }
}

// ===== HELPERS =====
const formatPaymentDate = (timestamp: number): string => {
  const d = new Date(timestamp * 1000)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

const formatPaymentTime = (timestamp: number): string => {
  const d = new Date(timestamp * 1000)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`
}

const getPaymentDescription = (payment: Payment): string => {
  if (!payment.details) return ''
  if (payment.details.type === 'lightning') return payment.details.description || ''
  if (payment.details.type === 'spark') return payment.details.invoiceDetails?.description || ''
  return ''
}

const getPaymentTxId = (payment: Payment): string | null => {
  if (!payment.details) return null
  if (payment.details.type === 'deposit' || payment.details.type === 'withdraw') {
    return payment.details.txId || null
  }
  return null
}

// ===== CSV EXPORT =====
const exportCSV = () => {
  const header = 'Date,Time,Type,Amount (sats),Fee (sats),Method,Description,TxID'
  const rows = payments.value.map(p => {
    const desc = getPaymentDescription(p).replace(/"/g, '""')
    const txid = getPaymentTxId(p) || ''
    return [
      formatPaymentDate(p.timestamp),
      formatPaymentTime(p.timestamp),
      p.paymentType,
      Number(p.amount),
      Number(p.fees),
      p.method,
      `"${desc}"`,
      txid,
    ].join(',')
  })
  const csv = [header, ...rows].join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `parahub-wallet-${formatPaymentDate(Math.floor(Date.now() / 1000))}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

// ===== LIFECYCLE =====
watch(paymentEventVersion, () => {
  loadHistory()
})

onMounted(() => {
  if (sdkState.value === 'ready') {
    fetchUnclaimedDeposits()
    loadHistory()
    startMempoolPolling()
  }
})

// Watch for SDK becoming ready (if component mounts before SDK is initialized)
watch(sdkState, (newState) => {
  if (newState === 'ready') {
    fetchUnclaimedDeposits()
    loadHistory()
    startMempoolPolling()
  }
})

onUnmounted(() => {
  stopMempoolPolling()
})

defineExpose({ loadHistory })
</script>
