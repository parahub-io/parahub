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
          class="py-3 first:pt-0 flex items-start gap-3"
        >
          <WalletTxChip kind="onchain" />
          <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2 mb-1">
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
          <div>
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
        </div>

        <!-- Claim result messages -->
        <div v-if="claimError" class="py-2 text-xs text-error dark:text-error-400">{{ claimError }}</div>
        <div v-if="claimSuccess" class="py-2 text-xs text-success-600 dark:text-success-400">{{ $t('wallet.depositClaimed') }}</div>

        <!-- On-chain deposits (mempool tracking) -->
        <div
          v-for="md in mempoolDeposits"
          :key="`mempool-${md.txid}`"
          class="py-3 first:pt-0 flex items-start gap-3"
        >
          <WalletTxChip kind="onchain" />
          <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2 mb-1">
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
          <div>
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
        </div>

        <!-- Completed payments, related sends collapsed into one row -->
        <template v-for="(row, idx) in rows" :key="row.key">
          <!-- Group: a batch of tip notes or ad rewards -->
          <div
            v-if="row.type === 'group'"
            class="py-3 first:pt-0 last:pb-0 px-2 -mx-2 rounded flex items-start gap-3"
            :class="idx % 2 === 1 ? 'bg-neutral-50 dark:bg-neutral-700/30' : ''"
          >
            <WalletTxChip :kind="row.kind" />
            <div class="flex-1 min-w-0">
            <button type="button" class="w-full text-left" @click="toggleGroup(row.key)">
              <div class="flex items-center gap-2 mb-1">
                <span class="font-semibold text-error-600 dark:text-error-500">
                  -{{ row.totalSats.toLocaleString() }} sats
                </span>
                <span class="text-[10px] px-1.5 py-0.5 rounded bg-neutral-100 dark:bg-neutral-700 text-neutral-500">
                  {{ row.kind === 'ad'
                    ? $t('wallet.txAdRewards', { count: row.items.length }, row.items.length)
                    : $t('wallet.txTipNotes', { count: row.items.length }, row.items.length) }}
                </span>
                <div class="text-right ml-auto">
                  <p class="text-xs text-neutral-400 tabular-nums">{{ formatPaymentDate(row.newestTs) }}</p>
                  <p class="text-xs text-neutral-400 tabular-nums">{{ formatPaymentTime(row.newestTs) }}</p>
                </div>
                <ChevronDown
                  class="w-4 h-4 text-neutral-400 flex-shrink-0 transition-transform"
                  :class="expandedGroups.has(row.key) ? 'rotate-180' : ''"
                />
              </div>
            </button>
            <div class="flex items-center gap-2 min-w-0 flex-wrap">
              <span v-if="row.name" class="text-xs text-neutral-500 dark:text-neutral-400 truncate">{{ row.name }}</span>
              <span v-if="groupStatusSummary(row)" class="text-xs text-neutral-400">{{ groupStatusSummary(row) }}</span>
              <NuxtLink
                v-if="row.batchId"
                :to="localePath(`/tips/${row.batchId}`)"
                class="text-xs text-link flex-shrink-0"
              >
                {{ $t('wallet.txViewBatch') }}
              </NuxtLink>
            </div>
            <div v-if="expandedGroups.has(row.key)" class="mt-2 space-y-1.5">
              <div v-for="e in row.items" :key="e.p.id" class="flex items-center gap-2 min-w-0">
                <span class="text-xs text-neutral-400 tabular-nums flex-shrink-0">{{ formatPaymentTime(e.p.timestamp) }}</span>
                <span
                  class="text-xs tabular-nums"
                  :class="isReturnedNote(e) ? 'text-neutral-400 line-through' : 'text-neutral-600 dark:text-neutral-300'"
                >
                  -{{ Number(e.p.amount).toLocaleString() }} sats
                </span>
                <span v-if="e.ctx.noteLabel" class="text-xs text-neutral-500 truncate">{{ e.ctx.noteLabel }}</span>
                <span
                  v-if="statusBadge(e)"
                  class="text-[10px] px-1.5 py-0.5 rounded flex-shrink-0"
                  :class="statusBadge(e)!.cls"
                >
                  {{ statusBadge(e)!.text }}
                </span>
              </div>
            </div>
            </div>
          </div>

          <!-- Single payment -->
          <div
            v-else
            class="py-3 first:pt-0 last:pb-0 px-2 -mx-2 rounded flex items-start gap-3"
            :class="idx % 2 === 1 ? 'bg-neutral-50 dark:bg-neutral-700/30' : ''"
          >
            <WalletTxChip :kind="kindFor(row.e)" />
            <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 mb-1">
              <span
                class="font-semibold"
                :class="isReturnedNote(row.e)
                  ? 'text-neutral-400 line-through'
                  : row.e.p.paymentType === 'receive'
                    ? 'text-success-600 dark:text-success-500'
                    : 'text-error-600 dark:text-error-500'"
              >
                {{ row.e.p.paymentType === 'receive' ? '+' : '-' }}{{ Number(row.e.p.amount) }} sats
              </span>

              <span class="text-[10px] px-1.5 py-0.5 rounded bg-neutral-100 dark:bg-neutral-700 text-neutral-500">
                {{ row.e.p.method }}
              </span>

              <span
                v-if="statusBadge(row.e)"
                class="text-[10px] px-1.5 py-0.5 rounded"
                :class="statusBadge(row.e)!.cls"
              >
                {{ statusBadge(row.e)!.text }}
              </span>

              <div class="text-right ml-auto">
                <p class="text-xs text-neutral-400 tabular-nums">{{ formatPaymentDate(row.e.p.timestamp) }}</p>
                <p class="text-xs text-neutral-400 tabular-nums">{{ formatPaymentTime(row.e.p.timestamp) }}</p>
              </div>
            </div>

            <div v-if="contextText(row.e)" class="flex items-center gap-2 min-w-0">
              <NuxtLink
                v-if="row.e.ctx.slug"
                :to="localePath(`/@${row.e.ctx.slug}`)"
                class="text-xs text-link truncate"
              >
                {{ contextText(row.e) }}
              </NuxtLink>
              <span v-else class="text-xs text-neutral-500 dark:text-neutral-400 truncate">{{ contextText(row.e) }}</span>
              <NuxtLink
                v-if="row.e.ctx.batchId"
                :to="localePath(`/tips/${row.e.ctx.batchId}`)"
                class="text-xs text-link flex-shrink-0"
              >
                {{ $t('wallet.txViewBatch') }}
              </NuxtLink>
            </div>
            <div v-else-if="getPaymentDescription(row.e.p)">
              <p class="text-xs text-neutral-500 dark:text-neutral-400 truncate">
                {{ getPaymentDescription(row.e.p) }}
              </p>
            </div>

            <div v-if="receiveComment(row.e.p)">
              <p class="text-xs italic text-neutral-500 dark:text-neutral-400 truncate">“{{ receiveComment(row.e.p) }}”</p>
            </div>

            <div v-if="getPaymentTxId(row.e.p)">
              <a
                :href="`https://mempool.space/tx/${getPaymentTxId(row.e.p)}`"
                target="_blank"
                rel="noopener"
                class="inline-flex items-center gap-1 font-mono text-[10px] text-neutral-400 hover:text-secondary transition-colors"
                :title="getPaymentTxId(row.e.p)"
              >
                {{ getPaymentTxId(row.e.p)!.slice(0, 16) }}...{{ getPaymentTxId(row.e.p)!.slice(-8) }}
                <ExternalLink class="w-2.5 h-2.5" />
              </a>
            </div>

            <div v-if="Number(row.e.p.fees) > 0">
              <p class="text-[10px] text-neutral-400">
                {{ $t('wallet.fee') }}: {{ Number(row.e.p.fees) }} sats
              </p>
            </div>
            </div>
          </div>
        </template>

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
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { History, ExternalLink, FileDown, ChevronDown } from 'lucide-vue-next'
import { useLightning } from '~/composables/useLightning'
import { useBtcPrice } from '~/composables/useBtcPrice'
import { useTipBatches } from '~/composables/useTipBatches'
import { readTxAnnotations, type TxAnnotation } from '~/composables/useTxAnnotations'
import { saveText } from '~/utils/download'
import type { Payment, DepositInfo } from '@breeztech/breez-sdk-spark/web'

const { t } = useI18n()
const localePath = useLocalePath()

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

// ===== PAYMENT CONTEXT =====
// A Spark transfer carries no counterparty, so context comes from what this
// browser recorded at send time: tip batches (per-note payment ids) and the
// send-flow annotations (profile / donation / ad / ticket).
const annotations = ref<Record<string, TxAnnotation>>({})
const tipBatchesStore = useTipBatches()
const expandedGroups = ref<Set<string>>(new Set())

interface TxContext {
  kind: TxAnnotation['kind'] | 'tip' | null
  name?: string
  slug?: string
  batchId?: string
  noteLabel?: string
  groupKey?: string
}

interface EnrichedPayment { p: Payment; ctx: TxContext }

type HistoryRow =
  | { type: 'single'; key: string; e: EnrichedPayment }
  | {
      type: 'group'; key: string; kind: 'tip' | 'ad'; items: EnrichedPayment[]
      totalSats: number; batchId?: string; name?: string
      claimed: number; returned: number; waiting: number; newestTs: number
    }

const tipIndex = computed(() => {
  const map = new Map<string, { batchId: string; message: string; noteLabel?: string }>()
  for (const b of tipBatchesStore.batches.value) {
    for (const n of b.notes) {
      if (n.paymentId) map.set(n.paymentId, { batchId: b.id, message: b.message, noteLabel: n.label })
    }
  }
  return map
})

const contextFor = (p: Payment): TxContext => {
  const tip = tipIndex.value.get(p.id)
  if (tip) {
    return {
      kind: 'tip', name: tip.message, batchId: tip.batchId,
      noteLabel: tip.noteLabel, groupKey: `tip:${tip.batchId}`,
    }
  }
  const ann = annotations.value[p.id]
  if (ann) {
    return {
      kind: ann.kind, name: ann.name, slug: ann.slug,
      groupKey: ann.kind === 'ad' ? `ad:${ann.name || ''}` : undefined,
    }
  }
  // Bearer-note funding from a browser that lost (or never had) the batch:
  // an HTLC-locked outgoing spark transfer is a tip note by construction.
  if (p.paymentType === 'send' && p.details?.type === 'spark' && p.details.htlcDetails) {
    return { kind: 'tip', groupKey: `tiph:${Number(p.amount)}` }
  }
  return { kind: null }
}

const htlcStatusOf = (p: Payment): string | null => {
  const d = p.details
  if (d && (d.type === 'spark' || d.type === 'lightning') && d.htlcDetails) return d.htlcDetails.status
  return null
}

const isReturnedNote = (e: EnrichedPayment): boolean =>
  e.ctx.kind === 'tip' && htlcStatusOf(e.p) === 'returned'

// Operation kind for the row chip (WalletTxChip: tinted circle + lucide glyph).
// The chip encodes the operation kind; direction stays on the signed amount.
const kindFor = (e: EnrichedPayment): string => {
  if (e.ctx.kind) return e.ctx.kind
  const t = e.p.details?.type
  if (t === 'deposit' || t === 'withdraw') return 'onchain'
  return e.p.paymentType === 'receive' ? 'receive' : 'send'
}

// Consecutive same-batch (or same-campaign) sends collapse into one row.
// The gap cap keeps unrelated fundings of the same batch weeks apart separate.
const GROUP_GAP_SECS = 30 * 60

const rows = computed<HistoryRow[]>(() => {
  const out: HistoryRow[] = []
  let bucket: EnrichedPayment[] = []
  let bucketKey = ''

  const flush = () => {
    if (!bucket.length) return
    if (bucket.length === 1) {
      out.push({ type: 'single', key: bucket[0].p.id, e: bucket[0] })
    } else {
      const first = bucket[0]
      let claimed = 0, returned = 0, waiting = 0, totalSats = 0
      for (const e of bucket) {
        totalSats += Number(e.p.amount)
        const s = htlcStatusOf(e.p)
        if (s === 'preimageShared') claimed++
        else if (s === 'returned') returned++
        else if (s === 'waitingForPreimage') waiting++
      }
      out.push({
        type: 'group', key: `g:${bucketKey}:${first.p.id}`,
        kind: first.ctx.kind === 'ad' ? 'ad' : 'tip',
        items: bucket, totalSats,
        batchId: first.ctx.batchId, name: first.ctx.name,
        claimed, returned, waiting, newestTs: first.p.timestamp,
      })
    }
    bucket = []
    bucketKey = ''
  }

  for (const p of payments.value) {
    const ctx = contextFor(p)
    if (ctx.groupKey) {
      const prev = bucket[bucket.length - 1]
      if (prev && ctx.groupKey === bucketKey && (prev.p.timestamp - p.timestamp) <= GROUP_GAP_SECS) {
        bucket.push({ p, ctx })
        continue
      }
      flush()
      bucket = [{ p, ctx }]
      bucketKey = ctx.groupKey
      continue
    }
    flush()
    out.push({ type: 'single', key: p.id, e: { p, ctx } })
  }
  flush()
  return out
})

const toggleGroup = (key: string) => {
  const next = new Set(expandedGroups.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  expandedGroups.value = next
}

const contextText = (e: EnrichedPayment): string => {
  const { ctx, p } = e
  switch (ctx.kind) {
    case 'profile': return t('wallet.txTo', { name: ctx.name || '' })
    case 'subscription': return t('wallet.txSupport', { name: ctx.name || '' })
    case 'donation': return t('wallet.txDonation')
    case 'ad': return t('wallet.txAdReward', { name: ctx.name || '' })
    case 'ticket': return t('wallet.txTicket', { name: ctx.name || '' })
    case 'tip': {
      const extra = ctx.noteLabel || ctx.name
      return extra ? `${t('wallet.txTipNote')} · ${extra}` : t('wallet.txTipNote')
    }
  }
  // Retroactive context: sends to a Lightning address keep the address
  const d = p.details
  if (d?.type === 'lightning' && p.paymentType === 'send' && d.lnurlPayInfo?.lnAddress) {
    return t('wallet.txTo', { name: d.lnurlPayInfo.lnAddress })
  }
  return ''
}

const receiveComment = (p: Payment): string => {
  const d = p.details
  if (d?.type !== 'lightning' || p.paymentType !== 'receive') return ''
  return d.lnurlReceiveMetadata?.senderComment || ''
}

const statusBadge = (e: EnrichedPayment): { text: string; cls: string } | null => {
  const NEUTRAL = 'bg-neutral-100 dark:bg-neutral-700 text-neutral-500'
  const SUCCESS = 'bg-success-100 dark:bg-success-900/30 text-success-700 dark:text-success-400'
  const WARNING = 'bg-warning-100 dark:bg-warning-900/30 text-warning-700 dark:text-warning-400'
  const ERROR = 'bg-error-100 dark:bg-error-900/30 text-error-700 dark:text-error-400'
  const htlc = e.ctx.kind === 'tip' ? htlcStatusOf(e.p) : null
  // A returned note is the HTLC expiry working as designed, not a failure
  if (htlc === 'returned') return { text: t('wallet.status_returned'), cls: NEUTRAL }
  if (e.p.status === 'pending') return { text: t('wallet.status_pending'), cls: WARNING }
  if (e.p.status === 'failed') return { text: t('wallet.status_failed'), cls: ERROR }
  if (htlc === 'preimageShared') return { text: t('wallet.status_claimed'), cls: SUCCESS }
  if (htlc === 'waitingForPreimage') return { text: t('wallet.status_unclaimed'), cls: NEUTRAL }
  return null
}

const groupStatusSummary = (row: Extract<HistoryRow, { type: 'group' }>): string => {
  if (row.kind !== 'tip') return ''
  const parts: string[] = []
  if (row.claimed) parts.push(t('wallet.txClaimedCount', { count: row.claimed }, row.claimed))
  if (row.returned) parts.push(t('wallet.txReturnedCount', { count: row.returned }, row.returned))
  if (row.waiting) parts.push(t('wallet.txWaitingCount', { count: row.waiting }, row.waiting))
  return parts.join(' · ')
}

const loadHistory = async () => {
  if (sdkState.value !== 'ready') return
  // Spinner only on the first load. Background refreshes (fired by the `synced`
  // event) keep the list mounted and patch rows in place via stable :key, so
  // the user's scroll position survives instead of jumping to the top.
  const isInitial = payments.value.length === 0
  if (isInitial) loadingHistory.value = true
  annotations.value = readTxAnnotations()
  tipBatchesStore.load()
  try {
    // Never shrink below what's already shown (e.g. after "load more").
    const count = Math.max(historyLimit.value, payments.value.length)
    const fresh = await listPayments(count, 0)
    payments.value = fresh
    historyOffset.value = fresh.length
  } catch (e) {
    console.error('Failed to load history:', e)
  } finally {
    if (isInitial) loadingHistory.value = false
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
const csvContext = (p: Payment, ctx: TxContext): string => {
  if (ctx.noteLabel) return ctx.noteLabel
  if (ctx.name) return ctx.name
  const d = p.details
  if (d?.type === 'lightning') {
    if (p.paymentType === 'send' && d.lnurlPayInfo?.lnAddress) return d.lnurlPayInfo.lnAddress
    if (p.paymentType === 'receive' && d.lnurlReceiveMetadata?.senderComment) {
      return d.lnurlReceiveMetadata.senderComment
    }
  }
  return ''
}

const exportCSV = () => {
  const header = 'Date,Time,Type,Amount (sats),Fee (sats),Method,Category,Context,Description,TxID'
  const csvRows = payments.value.map(p => {
    const ctx = contextFor(p)
    const context = csvContext(p, ctx).replace(/"/g, '""')
    const desc = getPaymentDescription(p).replace(/"/g, '""')
    const txid = getPaymentTxId(p) || ''
    return [
      formatPaymentDate(p.timestamp),
      formatPaymentTime(p.timestamp),
      p.paymentType,
      Number(p.amount),
      Number(p.fees),
      p.method,
      ctx.kind || '',
      `"${context}"`,
      `"${desc}"`,
      txid,
    ].join(',')
  })
  const csv = [header, ...csvRows].join('\n')
  saveText(
    csv,
    `parahub-wallet-${formatPaymentDate(Math.floor(Date.now() / 1000))}.csv`,
    'text/csv;charset=utf-8;'
  )
}

// ===== LIFECYCLE =====
watch(paymentEventVersion, () => {
  loadHistory()
})

onMounted(() => {
  // Cross-device context: merge the synced blob (opt-in), then re-read the
  // stores it may have grown so labels minted elsewhere appear.
  useWalletSync().pull().then(() => {
    annotations.value = readTxAnnotations()
    tipBatchesStore.load()
  })
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
