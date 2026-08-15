<template>
  <div class="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
    <NuxtLink :to="localePath('/tips')" class="text-sm text-neutral-500 dark:text-neutral-400 hover:text-secondary dark:hover:text-secondary-400">
      ← {{ $t('tips.title') }}
    </NuxtLink>
    <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100 mt-2 mb-6">
      {{ $t('tips.new.title') }}
    </h1>

    <img src="/images/tips/mint.webp" alt="" class="mx-auto h-24 sm:h-28 w-auto object-contain mb-6" />

    <!-- Funding in progress: one note at a time, so a failure is isolated -->
    <div v-if="funding" class="card p-6 text-center">
      <div class="mx-auto h-12 w-12 animate-spin rounded-full border-4 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100" role="status">
        <span class="sr-only">{{ $t('tips.new.funding', { n: fundedCount + 1, total: form.count }) }}</span>
      </div>
      <p class="mt-4 font-semibold text-neutral-900 dark:text-neutral-100">
        {{ $t('tips.new.funding', { n: Math.min(fundedCount + 1, form.count), total: form.count }) }}
      </p>

      <!-- Each note is a separate on-network transfer that takes seconds, so the
           wait is measured, not just spun: elapsed always, ETA once one note has
           landed and there is a real per-note average to extrapolate from. -->
      <div class="mt-4 h-1.5 w-full overflow-hidden rounded-full bg-neutral-200 dark:bg-neutral-700">
        <div
          class="h-full rounded-full bg-neutral-900 transition-all duration-500 dark:bg-neutral-100"
          :style="{ width: `${(fundedCount / form.count) * 100}%` }"
        />
      </div>
      <p class="mt-2 text-sm tabular-nums text-neutral-600 dark:text-neutral-300">
        {{ $t('tips.new.elapsed', { time: formatDuration(elapsedMs) }) }}
        <span v-if="remainingMs">· {{ $t('tips.new.remaining', { time: formatDuration(remainingMs) }) }}</span>
      </p>

      <p class="mt-2 text-sm text-neutral-500 dark:text-neutral-400">{{ $t('tips.new.fundingHint') }}</p>
    </div>

    <form v-else class="space-y-6" @submit.prevent="submit">
      <div class="card p-4 space-y-4">
        <div>
          <label class="block text-sm font-medium mb-1" for="tip-sats">{{ $t('tips.new.amount') }}</label>
          <input
            id="tip-sats" v-model.number="form.sats" type="number" min="100" step="100" required
            class="w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 px-3 py-2 focus:ring-2 focus:ring-primary focus:border-transparent"
          >
          <p class="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
            {{ $t('tips.new.amountHint', { fiat: formatFiat(satsToFiat(form.sats)) }) }}
          </p>
        </div>

        <div>
          <label class="block text-sm font-medium mb-1" for="tip-count">{{ $t('tips.new.count') }}</label>
          <input
            id="tip-count" v-model.number="form.count" type="number" min="1" max="45" required
            class="w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 px-3 py-2 focus:ring-2 focus:ring-primary focus:border-transparent"
          >
          <p class="mt-1 text-xs text-neutral-500 dark:text-neutral-400">{{ $t('tips.new.countHint') }}</p>
        </div>

        <div>
          <label class="block text-sm font-medium mb-1" for="tip-expiry">{{ $t('tips.new.expiry') }}</label>
          <select
            id="tip-expiry" v-model.number="form.expiryDays"
            class="w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 px-3 py-2 focus:ring-2 focus:ring-primary focus:border-transparent"
          >
            <option v-for="d in [7, 14, 30, 90]" :key="d" :value="d">{{ $t('tips.new.days', { n: d }) }}</option>
          </select>
          <p class="mt-1 text-xs text-neutral-500 dark:text-neutral-400">{{ $t('tips.new.expiryHint') }}</p>
        </div>

        <div>
          <label class="block text-sm font-medium mb-1" for="tip-message">{{ $t('tips.new.message') }}</label>
          <input
            id="tip-message" v-model="form.message" type="text" maxlength="60"
            :placeholder="$t('tips.new.messagePlaceholder')"
            class="w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 px-3 py-2 focus:ring-2 focus:ring-primary focus:border-transparent"
          >
        </div>
      </div>

      <UiAlert variant="info" :title="$t('tips.new.total', { sats: total.toLocaleString(), fiat: formatFiat(satsToFiat(total)) })">
        {{ $t('tips.new.totalHint') }}
      </UiAlert>

      <UiAlert v-if="error" variant="error">{{ error }}</UiAlert>

      <UiButton type="submit" class="w-full" :loading="preparing" :disabled="!canSubmit">
        {{ $t('tips.new.submit') }}
      </UiButton>
    </form>
  </div>
</template>

<script setup lang="ts">
definePageMeta({ middleware: 'auth' })

const localePath = useLocalePath()
const router = useRouter()
const { t } = useI18n()
const { satsToFiat, formatFiat, btcPrice, userCurrency, fetchBtcPrice } = useBtcPrice()
const { initSdk, sdkState, balanceSats, prepareSend, executeSendHtlc } = useLightning()
const { save } = useTipBatches()

const form = reactive({ sats: 2500, count: 9, expiryDays: 30, message: '' })
const preparing = ref(false)
const funding = ref(false)
const fundedCount = ref(0)
const error = ref('')

const total = computed(() => (form.sats || 0) * (form.count || 0))
const canSubmit = computed(() => total.value > 0 && !preparing.value)

// Funding clock. Every note costs a full round of network work, so a nine-note
// batch legitimately runs tens of seconds — without a moving number that reads
// as a hang. ETA extrapolates the average of the notes already funded.
const startedAt = ref(0)
const clockNow = ref(0)
let ticker: ReturnType<typeof setInterval> | null = null

const elapsedMs = computed(() => (startedAt.value ? Math.max(0, clockNow.value - startedAt.value) : 0))
const remainingMs = computed(() => {
  const left = form.count - fundedCount.value
  if (!fundedCount.value || left <= 0) return 0
  return Math.round((elapsedMs.value / fundedCount.value) * left)
})

const formatDuration = (ms: number) => {
  const secs = Math.max(0, Math.round(ms / 1000))
  return `${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, '0')}`
}

const stopClock = () => {
  if (ticker) clearInterval(ticker)
  ticker = null
}

const startClock = () => {
  stopClock()
  startedAt.value = Date.now()
  clockNow.value = startedAt.value
  ticker = setInterval(() => { clockNow.value = Date.now() }, 1000)
}

onUnmounted(stopClock)

onMounted(() => {
  fetchBtcPrice()
  initSdk()
})

const submit = async () => {
  error.value = ''
  preparing.value = true
  try {
    await initSdk()
    if (sdkState.value !== 'ready') {
      error.value = t('tips.new.walletNeeded')
      return
    }
    if (balanceSats.value < total.value) {
      error.value = t('tips.new.insufficient', { sats: total.value.toLocaleString() })
      return
    }

    const { mintTipNote } = await import('~/utils/tips')
    const expirySecs = form.expiryDays * 86400
    const batch = {
      id: crypto.randomUUID(),
      createdAt: Date.now(),
      sats: form.sats,
      expirySecs,
      message: form.message,
      fiat: formatFiat(satsToFiat(form.sats)),
      rate: btcPrice.value ? `1 BTC = ${formatFiat(btcPrice.value)}` : '',
      notes: [] as { code: string, paymentId?: string, error?: string }[],
    }

    funding.value = true
    startClock()
    for (let i = 0; i < form.count; i++) {
      const note = await mintTipNote()
      try {
        const prep = await prepareSend(note.address, BigInt(form.sats))
        const payment = await executeSendHtlc(prep, note.paymentHash, expirySecs)
        batch.notes.push({ code: note.code, paymentId: payment.id })
      } catch (e: any) {
        // Keep the code: the transfer may still have gone out, and the note is
        // worthless to us but claimable if it did. Never silently drop a secret.
        batch.notes.push({ code: note.code, error: String(e?.message || e) })
      }
      fundedCount.value = i + 1
      // Persist after every note so a closed tab can't lose funded secrets.
      save(batch)
    }

    await router.push(localePath(`/tips/${batch.id}`))
  } catch (e: any) {
    error.value = String(e?.message || e)
  } finally {
    stopClock()
    preparing.value = false
    funding.value = false
  }
}

useHead({ title: t('tips.new.title') })
</script>
