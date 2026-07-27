<template>
  <UiAlert variant="success" :title="$t('tips.claim.receiptTitle')">
    <dl class="mt-2 space-y-1.5 text-sm">
      <div class="flex justify-between gap-3">
        <dt class="shrink-0 opacity-70">{{ $t('tips.claim.receiptAmount') }}</dt>
        <dd class="text-right font-medium">
          {{ sats.toLocaleString() }} sats<span v-if="fiat" class="font-normal opacity-70"> · {{ fiat }}</span>
        </dd>
      </div>

      <div v-if="fee > 0" class="flex justify-between gap-3">
        <dt class="shrink-0 opacity-70">{{ $t('tips.claim.receiptFee') }}</dt>
        <dd class="text-right">{{ fee.toLocaleString() }} sats</dd>
      </div>

      <div v-if="destination" class="flex justify-between gap-3">
        <dt class="shrink-0 opacity-70">{{ $t('tips.claim.receiptTo') }}</dt>
        <dd class="text-right font-mono text-xs break-all">{{ shorten(destination) }}</dd>
      </div>

      <div v-if="reference" class="flex justify-between gap-3">
        <dt class="shrink-0 opacity-70">{{ txUrl ? $t('tips.claim.receiptTx') : $t('tips.claim.receiptRef') }}</dt>
        <dd class="text-right">
          <!-- On-chain has a public explorer; Lightning and Spark only have the hash itself -->
          <a
            v-if="txUrl" :href="txUrl" target="_blank" rel="noopener"
            class="inline-flex items-center gap-1 font-mono text-xs underline break-all"
          >
            {{ shorten(reference) }}<ExternalLink class="w-3 h-3 shrink-0" />
          </a>
          <button
            v-else type="button" class="inline-flex items-center gap-1 font-mono text-xs break-all"
            :title="$t('tips.claim.receiptCopy')" @click="copyRef"
          >
            {{ shorten(reference) }}
            <component :is="copied ? Check : Copy" class="w-3 h-3 shrink-0" />
          </button>
        </dd>
      </div>

      <div class="flex justify-between gap-3">
        <dt class="shrink-0 opacity-70">{{ $t('tips.claim.receiptWhen') }}</dt>
        <dd class="text-right">{{ when }}</dd>
      </div>
    </dl>
  </UiAlert>
</template>

<script setup lang="ts">
import { ExternalLink, Copy, Check } from 'lucide-vue-next'
import type { Payment } from '@breeztech/breez-sdk-spark/web'

const props = defineProps<{
  payment: Payment
  /** What the holder typed, kept as-is: the SDK does not echo it back. */
  destination?: string
}>()

const { t, locale } = useI18n()
const { satsToFiat, formatFiat } = useBtcPrice()
const toastStore = useToastStore()

const copied = ref(false)

const sats = computed(() => Number(props.payment.amount))
const fee = computed(() => Number(props.payment.fees))
const fiat = computed(() => formatFiat(satsToFiat(sats.value)))
const when = computed(() => new Date(props.payment.timestamp * 1000).toLocaleString(locale.value))

/** An on-chain send is the only kind with a transaction anyone can look up. */
const txId = computed(() => {
  const d = props.payment.details
  return d && (d.type === 'withdraw' || d.type === 'deposit') ? d.txId : ''
})
const txUrl = computed(() => (txId.value ? `https://mempool.space/tx/${txId.value}` : ''))
const reference = computed(() => {
  if (txId.value) return txId.value
  const d = props.payment.details
  if (d?.type === 'lightning') return d.htlcDetails?.paymentHash || props.payment.id
  return props.payment.id
})

const shorten = (s: string) => (s.length > 28 ? `${s.slice(0, 14)}…${s.slice(-10)}` : s)

const copyRef = async () => {
  try {
    await navigator.clipboard.writeText(reference.value)
    copied.value = true
    toastStore.success(t('tips.claim.receiptCopied'))
    setTimeout(() => { copied.value = false }, 2000)
  } catch { /* the hash is on screen anyway */ }
}
</script>
