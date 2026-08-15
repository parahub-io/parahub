<template>
  <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
    <NuxtLink :to="localePath('/tips')" class="text-sm text-neutral-500 dark:text-neutral-400 hover:text-secondary dark:hover:text-secondary-400">
      ← {{ $t('tips.title') }}
    </NuxtLink>

    <div v-if="!batch" class="py-12 text-center">
      <img src="/images/para/searching.webp" alt="Para" class="mx-auto h-32 w-auto mb-4" />
      <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100">{{ $t('tips.batch.missing') }}</h3>
      <p class="mt-2 text-sm text-neutral-500 dark:text-neutral-400 max-w-md mx-auto">{{ $t('tips.batch.missingHint') }}</p>
      <!-- The likely cause is device-locality — surface the opt-in sync toggle / a key mismatch. -->
      <p v-if="syncError === 'key-mismatch'" class="mt-2 text-sm text-amber-600 dark:text-amber-400 max-w-md mx-auto">
        {{ $t('tips.sync.keyMismatch') }}
      </p>
      <p v-else-if="syncError === 'no-seed'" class="mt-2 text-sm text-amber-600 dark:text-amber-400 max-w-md mx-auto">
        {{ $t('profile.preferences.wallet_sync_needs_wallet') }}
      </p>
      <p v-else-if="syncEnabled === false" class="mt-2 text-sm text-neutral-500 dark:text-neutral-400 max-w-md mx-auto">
        {{ $t('tips.sync.offHint') }}
        <NuxtLink :to="localePath('/profile') + '#wallet-sync'" class="text-link">
          {{ $t('tips.sync.settingsLink') }}
        </NuxtLink>
      </p>
    </div>

    <template v-else>
      <div class="flex flex-wrap items-start justify-between gap-3 mt-2 mb-4">
        <div>
          <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100">
            {{ $t("tips.batch.notes", { count: batch.notes.length }, batch.notes.length) }} · {{ batch.sats.toLocaleString() }} sats
          </h1>
          <p class="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            {{ batch.message || $t('tips.batch.noMessage') }}
          </p>
        </div>
        <div class="flex gap-2">
          <UiButton :icon="Links" @click="copyAll">{{ $t('tips.batch.copyAll') }}</UiButton>
          <UiButton variant="outline" :to="localePath(`/tips/${batch.id}/print`)" :icon="Printer">
            {{ $t('tips.batch.print') }}
          </UiButton>
        </div>
      </div>

      <!-- Face value was frozen at mint; bitcoin moved since. Show both, don't pretend. -->
      <p class="text-xs text-neutral-500 dark:text-neutral-400 mb-4">
        {{ $t('tips.batch.rateAtIssue', { fiat: batch.fiat, rate: batch.rate }) }}
        <template v-if="fiatNow"> · {{ $t('tips.batch.rateNow', { fiat: fiatNow }) }}</template>
      </p>

      <div class="flex items-center gap-4 mb-6">
        <div class="flex-1 min-w-0 space-y-3">
          <UiAlert variant="info" :title="$t('tips.batch.linkTitle')">
            {{ $t('tips.batch.linkText') }}
          </UiAlert>

          <UiAlert variant="warning" :title="$t('tips.batch.reprintTitle')">
            {{ $t('tips.batch.reprintText') }}
          </UiAlert>
        </div>
        <img src="/images/tips/link.webp" alt="" class="hidden sm:block h-32 w-auto object-contain flex-shrink-0" loading="lazy" />
      </div>

      <div class="border border-neutral-300 dark:border-neutral-600 rounded-lg overflow-hidden divide-y divide-neutral-300 dark:divide-neutral-600">
        <div v-for="(note, i) in batch.notes" :key="note.code" class="p-3 flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3">
          <span class="text-xs text-neutral-400 w-8 shrink-0 hidden sm:block">{{ String(i + 1).padStart(3, '0') }}</span>

          <div class="min-w-0 flex-1">
            <!-- Which note went to whom: the sender's own bookkeeping, kept local -->
            <input
              v-model="note.label"
              type="text"
              :placeholder="$t('tips.batch.labelPlaceholder')"
              class="w-full bg-transparent text-sm font-medium text-neutral-900 dark:text-neutral-100 placeholder:text-neutral-400 placeholder:font-normal border-0 border-b border-transparent hover:border-neutral-300 focus:border-primary focus:outline-none py-0.5"
              @change="persist"
            >
            <code class="block text-xs text-neutral-500 dark:text-neutral-400 truncate mt-0.5">{{ formatTipCode(note.code) }}</code>
          </div>

          <div class="flex items-center gap-2 shrink-0">
            <span class="text-xs text-neutral-500 dark:text-neutral-400 tabular-nums">{{ fiatNow || '' }}</span>
            <UiBadge :variant="statusVariant(note)" type="soft" size="sm">
              {{ $t(`tips.status.${statusOf(note)}`) }}
            </UiBadge>
            <!-- A note that never got funded has a dead link; don't offer to send it -->
            <UiButton
              v-if="!note.error"
              variant="ghost" size="sm" icon-only :icon="copied === note.code ? Check : Copy"
              :title="$t('tips.batch.copyLink')" :aria-label="$t('tips.batch.copyLink')"
              @click="copyLink(note)"
            />
            <UiButton
              v-if="canShare && !note.error"
              variant="ghost" size="sm" icon-only :icon="Share2"
              :title="$t('tips.batch.share')" :aria-label="$t('tips.batch.share')"
              @click="shareLink(note)"
            />
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { Printer, Copy, Check, Share2, Link2 as Links } from 'lucide-vue-next'
import { formatTipCode, tipClaimUrl } from '~/utils/tips'
import type { TipBatch, TipBatchNote } from '~/composables/useTipBatches'

definePageMeta({ middleware: 'auth' })

const localePath = useLocalePath()
const route = useRoute()
const { t } = useI18n()
const { get, save } = useTipBatches()
const { enabled: syncEnabled, lastError: syncError, pull } = useWalletSync()
const { initSdk, sdkState, getPayment, syncAndRefresh } = useLightning()
const { satsToFiat, formatFiat, fetchBtcPrice } = useBtcPrice()
const toastStore = useToastStore()

const batch = ref<TipBatch | undefined>()
/** paymentId → HTLC status, read from the wallet rather than from our own notes. */
const htlcStatus = ref<Record<string, string>>({})
const copied = ref('')
const canShare = ref(false)

const fiatNow = computed(() => batch.value ? formatFiat(satsToFiat(batch.value.sats)) : '')

const statusOf = (note: TipBatchNote): string => {
  if (note.error) return 'failed'
  const s = note.paymentId ? htlcStatus.value[note.paymentId] : undefined
  if (s === 'preimageShared') return 'claimed'
  if (s === 'returned') return 'returned'
  if (s === 'waitingForPreimage') return 'waiting'
  return 'unknown'
}

const statusVariant = (note: TipBatchNote) => ({
  claimed: 'success', returned: 'neutral', waiting: 'info', failed: 'error', unknown: 'neutral',
}[statusOf(note)] as 'success' | 'neutral' | 'info' | 'error')

const persist = () => { if (batch.value) save(batch.value) }

const copyLink = async (note: TipBatchNote) => {
  try {
    await navigator.clipboard.writeText(tipClaimUrl(note.code, window.location.origin))
    copied.value = note.code
    toastStore.success(t('tips.batch.linkCopied'))
    setTimeout(() => { if (copied.value === note.code) copied.value = '' }, 2000)
  } catch {
    toastStore.error(t('tips.batch.copyFailed'))
  }
}

const shareLink = async (note: TipBatchNote) => {
  try {
    await navigator.share({
      title: t('tips.title'),
      text: batch.value?.message || t('tips.print.defaultMessage'),
      url: tipClaimUrl(note.code, window.location.origin),
    })
  } catch { /* the user dismissing the share sheet is not an error */ }
}

const copyAll = async () => {
  if (!batch.value) return
  // One line per note, labelled where the sender labelled it — paste into a doc and work through it.
  const lines = batch.value.notes
    .map((n, i) => ({ n, i }))
    .filter(({ n }) => !n.error)
    .map(({ n, i }) => {
      const url = tipClaimUrl(n.code, window.location.origin)
      return n.label ? `${n.label}\t${url}` : `${String(i + 1).padStart(3, '0')}\t${url}`
    })
  try {
    await navigator.clipboard.writeText(lines.join('\n'))
    toastStore.success(t('tips.batch.allCopied', { count: lines.length }))
  } catch {
    toastStore.error(t('tips.batch.copyFailed'))
  }
}

const refreshStatuses = async () => {
  if (!batch.value || sdkState.value !== 'ready') return
  // getPayment reads local state, so a note claimed on someone else's phone
  // still looks "waiting" until we pull the wallet forward first.
  try { await syncAndRefresh() } catch { /* stale statuses beat no page */ }
  for (const note of batch.value.notes) {
    if (!note.paymentId) continue
    try {
      const payment = await getPayment(note.paymentId)
      const details = payment.details as { htlcDetails?: { status?: string } } | undefined
      if (details?.htlcDetails?.status) {
        htlcStatus.value = { ...htlcStatus.value, [note.paymentId]: details.htlcDetails.status }
      }
    } catch { /* a note whose payment the wallet can't see stays "unknown" */ }
  }
}

onMounted(async () => {
  batch.value = get(String(route.params.id))
  canShare.value = typeof navigator !== 'undefined' && !!navigator.share
  // Opt-in cross-device sync: a batch minted on another device (or a label
  // edited there) arrives via the merged blob — re-read after the pull.
  pull().then(() => {
    const fresh = get(String(route.params.id))
    if (fresh) batch.value = fresh
  })
  fetchBtcPrice()
  await initSdk()
  await refreshStatuses()
})

watch(sdkState, (s) => { if (s === 'ready') refreshStatuses() })

useHead({ title: t('tips.title') })
</script>
