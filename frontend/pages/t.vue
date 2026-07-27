<template>
  <div class="max-w-md mx-auto px-4 sm:px-6 py-10">
    <!-- No code at all: someone opened /t by hand -->
    <div v-if="state === 'invalid'" class="py-12 text-center">
      <div class="mx-auto w-16 h-16 rounded-full bg-warning-100 dark:bg-warning-900 flex items-center justify-center">
        <HelpCircle class="w-8 h-8 text-warning" />
      </div>
      <h2 class="mt-4 text-xl font-bold text-neutral-900 dark:text-neutral-100">{{ $t('tips.claim.invalid') }}</h2>
      <p class="mt-2 text-sm text-neutral-500 dark:text-neutral-400">{{ $t('tips.claim.invalidHint') }}</p>
    </div>

    <div v-else-if="state === 'loading'" class="py-12 text-center">
      <div class="mx-auto h-12 w-12 animate-spin rounded-full border-4 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100" role="status">
        <span class="sr-only">{{ $t('tips.claim.checking') }}</span>
      </div>
      <p class="mt-4 text-sm text-neutral-500 dark:text-neutral-400">{{ $t('tips.claim.checking') }}</p>
    </div>

    <!-- Cashed out. Must not fall through to "nothing here", which reads as a loss. -->
    <div v-else-if="state === 'sent'">
      <div class="py-8 text-center">
        <div class="mx-auto w-16 h-16 rounded-full bg-success-100 dark:bg-success-900 flex items-center justify-center">
          <Check class="w-8 h-8 text-success" />
        </div>
        <h2 class="mt-4 text-xl font-bold text-neutral-900 dark:text-neutral-100">{{ $t('tips.claim.sent') }}</h2>
        <p class="mt-2 text-sm text-neutral-500 dark:text-neutral-400">{{ $t('tips.claim.sentHint') }}</p>
      </div>
      <TipsReceipt v-if="receipt" :payment="receipt" :destination="sentTo" />
    </div>

    <div v-else-if="state === 'empty'" class="py-12 text-center">
      <div class="mx-auto w-16 h-16 rounded-full bg-neutral-100 dark:bg-neutral-800 flex items-center justify-center">
        <Clock class="w-8 h-8 text-neutral-400" />
      </div>
      <h2 class="mt-4 text-xl font-bold text-neutral-900 dark:text-neutral-100">{{ $t('tips.claim.empty') }}</h2>
      <p class="mt-2 text-sm text-neutral-500 dark:text-neutral-400">{{ $t('tips.claim.emptyHint') }}</p>
    </div>

    <template v-else>
      <div class="text-center">
        <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100">{{ $t('tips.claim.title') }}</h1>
        <div class="mt-6 text-4xl font-black text-neutral-900 dark:text-neutral-100">
          {{ shownSats.toLocaleString() }}<span class="text-lg font-bold text-neutral-500 ml-2">sats</span>
        </div>
        <div v-if="fiat" class="mt-1 text-lg font-bold text-secondary dark:text-secondary-400">≈ {{ fiat }}</div>
      </div>

      <!-- Locked: unlock it into this note's own wallet first -->
      <div v-if="state === 'unclaimed'" class="mt-8">
        <UiButton class="w-full" size="lg" :loading="busy" @click="doClaim">{{ $t('tips.claim.claim') }}</UiButton>
        <p class="mt-3 text-xs text-center text-neutral-500 dark:text-neutral-400">{{ $t('tips.claim.claimHint') }}</p>
      </div>

      <!-- Unlocked: it is already the holder's; moving it out is optional -->
      <div v-else class="mt-8 space-y-4">
        <UiAlert variant="success" :title="$t('tips.claim.claimed')">{{ $t('tips.claim.keepIt') }}</UiAlert>

        <TipsReceipt v-if="receipt" :payment="receipt" :destination="sentTo" />

        <div class="card p-4 space-y-3">
          <h2 class="font-semibold text-neutral-900 dark:text-neutral-100">{{ $t('tips.claim.cashout') }}</h2>

          <template v-if="!quoted">
            <input
              v-model="destination" type="text" :placeholder="$t('tips.claim.destinationPlaceholder')"
              class="w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 px-3 py-2 text-sm focus:ring-2 focus:ring-primary focus:border-transparent"
              @input="remembered = false"
            >
            <!-- Say where a pre-filled address came from: a shared browser must not send money silently -->
            <p v-if="remembered" class="text-xs text-neutral-500 dark:text-neutral-400">
              {{ $t('tips.claim.remembered') }}
              <button type="button" class="underline hover:text-primary" @click="forgetPayout">{{ $t('tips.claim.forget') }}</button>
            </p>
            <p v-else class="text-xs text-neutral-500 dark:text-neutral-400">{{ $t('tips.claim.destinationHint') }}</p>
          </template>

          <!-- Confirm step: name the destination before a send nobody can undo -->
          <dl v-else class="space-y-1.5 text-sm text-neutral-700 dark:text-neutral-300">
            <div class="flex justify-between gap-3">
              <dt class="shrink-0 text-neutral-500 dark:text-neutral-400">{{ $t('tips.claim.receiptTo') }}</dt>
              <dd class="text-right font-mono text-xs break-all">{{ destination.trim() }}</dd>
            </div>
            <div class="flex justify-between gap-3">
              <dt class="shrink-0 text-neutral-500 dark:text-neutral-400">{{ $t('tips.claim.receiptAmount') }}</dt>
              <dd class="text-right font-medium">{{ Number(quoted.amount).toLocaleString() }} sats</dd>
            </div>
            <div class="flex justify-between gap-3">
              <dt class="shrink-0 text-neutral-500 dark:text-neutral-400">{{ $t('tips.claim.receiptFee') }}</dt>
              <dd class="text-right">{{ quotedFee.toLocaleString() }} sats</dd>
            </div>
          </dl>

          <UiAlert v-if="error" variant="error">{{ error }}</UiAlert>

          <div class="flex gap-2">
            <UiButton v-if="quoted" variant="outline" :disabled="busy" @click="quoted = null; lnurlQuote = null">
              {{ $t('common.cancel') }}
            </UiButton>
            <UiButton
              class="flex-1" :loading="busy" :disabled="!destination.trim()"
              @click="quoted ? doSend() : doQuote()"
            >
              {{ quoted ? $t('tips.claim.confirmSend') : $t('tips.claim.getQuote') }}
            </UiButton>
          </div>
        </div>
      </div>

      <!-- A link can reach someone who has never held bitcoin. Say what this is. -->
      <div class="mt-8 p-4 bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg">
        <h2 class="font-semibold text-neutral-900 dark:text-neutral-100">{{ $t('tips.claim.aboutTitle') }}</h2>
        <p class="mt-1 text-sm text-neutral-600 dark:text-neutral-400">{{ $t('tips.claim.aboutText') }}</p>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { HelpCircle, Clock, Check } from 'lucide-vue-next'
import type { Payment } from '@breeztech/breez-sdk-spark/web'

// Public on purpose: whoever holds the paper claims it, account or not.
definePageMeta({ layout: 'default' })

/** Where the last cash-out went, so a stack of notes is not a stack of retyping. */
const PAYOUT_KEY = 'parahub_tip_payout'
/**
 * Only destinations that survive being used twice. A bolt11 invoice or a Spark
 * invoice is one-shot — remembering one would offer the holder a dead address.
 */
const REUSABLE_DESTINATIONS = new Set([
  'lightningAddress', 'sparkAddress', 'bitcoinAddress', 'lnurlPay', 'bolt12Offer', 'silentPaymentAddress',
])

const { t } = useI18n()
const { satsToFiat, formatFiat, fetchBtcPrice } = useBtcPrice()
const wallet = useTipWallet()

const state = ref<'loading' | 'invalid' | 'unclaimed' | 'claimed' | 'sent' | 'empty'>('loading')
const busy = ref(false)
const error = ref('')
const destination = ref('')
const destinationType = ref('')
const remembered = ref(false)
const quoted = ref<any>(null)
/** Set only when the destination went down the LNURL route, which pays differently. */
const lnurlQuote = ref<any>(null)
const preimage = ref('')
const receipt = ref<Payment | null>(null)
const sentTo = ref('')

const shownSats = computed(() => wallet.balanceSats.value || wallet.pendingSats.value)
const fiat = computed(() => formatFiat(satsToFiat(shownSats.value)))
const quotedFee = computed(() => {
  const m = quoted.value?.paymentMethod
  return Number(m?.lightningFeeSats ?? m?.fee ?? 0)
})

const settle = () => {
  if (wallet.balanceSats.value > 0) state.value = 'claimed'
  else if (wallet.pendingSats.value > 0) state.value = 'unclaimed'
  else state.value = 'empty'
}

const doClaim = async () => {
  busy.value = true
  error.value = ''
  try {
    await wallet.claim(preimage.value)
    settle()
  } catch (e: any) {
    error.value = String(e?.message || e)
    state.value = 'empty'
  } finally {
    busy.value = false
  }
}

const forgetPayout = () => {
  try { localStorage.removeItem(PAYOUT_KEY) } catch { /* nothing was stored either */ }
  destination.value = ''
  remembered.value = false
}

const doQuote = async () => {
  busy.value = true
  error.value = ''
  try {
    const parsed = await wallet.sdk.value.parse(destination.value.trim())
    destinationType.value = parsed.type

    if (parsed.type === 'lightningAddress' || parsed.type === 'lnurlPay') {
      const payRequest = parsed.type === 'lnurlPay' ? parsed : parsed.payRequest
      // The LNURL fee is charged on top, so "send it all" has to leave room for it.
      let amount = wallet.balanceSats.value
      let prep = await wallet.quoteLnurl(payRequest, amount)
      if (prep.feeSats > 0) {
        amount = wallet.balanceSats.value - prep.feeSats
        if (amount <= 0) throw new Error(t('tips.claim.tooSmall'))
        prep = await wallet.quoteLnurl(payRequest, amount)
      }
      lnurlQuote.value = prep
      // The confirm step and the fee line read one shape, whichever route we took.
      quoted.value = { amount: BigInt(prep.amountSats), paymentMethod: { lightningFeeSats: prep.feeSats } }
    } else {
      lnurlQuote.value = null
      // No amount for an invoice that already carries one; otherwise send it all.
      const carriesAmount = parsed.type === 'bolt11Invoice' && parsed.amountMsat
      quoted.value = await wallet.quote(destination.value, carriesAmount ? undefined : wallet.balanceSats.value)
    }
  } catch (e: any) {
    error.value = String(e?.message || e)
  } finally {
    busy.value = false
  }
}

const doSend = async () => {
  busy.value = true
  error.value = ''
  try {
    const payment = lnurlQuote.value
      ? await wallet.sendLnurl(lnurlQuote.value)
      : await wallet.send(quoted.value)
    sentTo.value = destination.value.trim()
    receipt.value = payment
    if (REUSABLE_DESTINATIONS.has(destinationType.value)) {
      try { localStorage.setItem(PAYOUT_KEY, sentTo.value) } catch { /* private mode: just do not remember */ }
    }
    quoted.value = null
    lnurlQuote.value = null
    destination.value = ''
    remembered.value = false
    // A drained note is not an empty one — say it went out, not that it is gone.
    state.value = wallet.balanceSats.value > 0 ? 'claimed' : 'sent'
  } catch (e: any) {
    error.value = String(e?.message || e)
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  fetchBtcPrice()
  try {
    const saved = localStorage.getItem(PAYOUT_KEY)
    if (saved) { destination.value = saved; remembered.value = true }
  } catch { /* private mode, or storage blocked: the field just starts empty */ }

  // The secret rides in the fragment, which browsers never send to the server.
  const code = window.location.hash.replace(/^#/, '').trim()
  if (!code) { state.value = 'invalid'; return }

  try {
    const { tipNoteFromCode } = await import('~/utils/tips')
    const note = await tipNoteFromCode(code)
    preimage.value = note.preimage
    await wallet.connect(note.mnemonic, note.code)
    settle()
  } catch {
    state.value = 'invalid'
  }
})

onBeforeUnmount(() => { wallet.disconnect() })

useHead({
  title: t('tips.claim.title'),
  meta: [{ name: 'robots', content: 'noindex, nofollow' }],
})
</script>
