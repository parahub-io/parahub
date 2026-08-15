<template>
  <div>
    <div class="flex items-center justify-between mb-2">
      <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
        {{ $t('wallet.amount') }} ({{ amountInFiat ? userCurrency : 'sats' }})
      </label>
      <button
        v-if="fiatAvailable"
        type="button"
        class="text-xs px-2 py-0.5 rounded bg-neutral-100 dark:bg-neutral-700 hover:bg-neutral-200 dark:hover:bg-neutral-600 text-neutral-600 dark:text-neutral-300 transition-colors"
        @click="toggleAmountMode"
      >
        {{ amountInFiat ? 'sats' : userCurrency }}
      </button>
    </div>
    <div class="relative">
      <input
        v-model="amountDisplay"
        type="text"
        inputmode="decimal"
        placeholder="0"
        class="w-full px-4 py-3 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-700 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent font-mono"
        :class="maxSats != null ? 'pr-16' : ''"
        @keyup.enter="emit('submit')"
      />
      <button
        v-if="maxSats != null"
        type="button"
        class="absolute right-2 top-1/2 -translate-y-1/2 px-2.5 py-1 text-xs font-medium bg-neutral-200 dark:bg-neutral-600 hover:bg-neutral-300 dark:hover:bg-neutral-500 text-neutral-700 dark:text-neutral-200 rounded transition-colors"
        @click="setMaxAmount"
      >
        MAX
      </button>
    </div>
    <p class="mt-1 text-sm text-neutral-500 font-mono">
      <template v-if="amountInFiat">
        ≈ {{ sats > 0 ? `${sats.toLocaleString()} sats` : '0 sats' }}
      </template>
      <template v-else-if="fiatAvailable">
        ≈ {{ formatFiat((sats > 0 ? satsToFiat(sats) : null) ?? 0) }}
      </template>
    </p>
  </div>
</template>

<script setup lang="ts">
/**
 * Amount input with a sats ↔ fiat (preferred currency) toggle.
 * v-model:sats is the single source of truth for the parent — always sats.
 * External writes (preset, reset) switch the field to sats mode so the exact
 * sat amount is preserved (fiat round-trips can drift by a sat).
 */
import { ref, computed, watch, onMounted } from 'vue'
import { useBtcPrice } from '~/composables/useBtcPrice'

const props = defineProps<{
  /** When set, a MAX button fills the input with this amount */
  maxSats?: number
}>()

const emit = defineEmits<{
  /** Enter pressed in the input */
  'submit': []
}>()

const sats = defineModel<number>('sats', { default: 0 })

const { userCurrency, satsToFiat, fiatToSats, formatFiat, fetchBtcPrice } = useBtcPrice()

const amountInFiat = ref(false)
const amountDisplay = ref('')

const fiatAvailable = computed(() => userCurrency.value !== 'BTC')

const internalSats = computed(() => {
  const raw = amountDisplay.value.replace(',', '.')
  const num = parseFloat(raw)
  if (isNaN(num) || num <= 0) return 0
  if (amountInFiat.value) {
    return fiatToSats(num) ?? 0
  }
  return Math.floor(num)
})

watch(internalSats, (v) => { sats.value = v })

// External write (preset amount, reset): reflect it in the field verbatim.
watch(sats, (v) => {
  if (v === internalSats.value) return
  amountInFiat.value = false
  amountDisplay.value = v > 0 ? String(v) : ''
}, { immediate: true })

const toggleAmountMode = () => {
  const currentSats = internalSats.value
  amountInFiat.value = !amountInFiat.value
  if (amountInFiat.value && currentSats > 0) {
    const fiat = satsToFiat(currentSats)
    amountDisplay.value = fiat !== null ? fiat.toFixed(2) : ''
  } else if (!amountInFiat.value && currentSats > 0) {
    amountDisplay.value = String(currentSats)
  } else {
    amountDisplay.value = ''
  }
}

const setMaxAmount = () => {
  const max = props.maxSats ?? 0
  if (amountInFiat.value) {
    const fiat = satsToFiat(max)
    amountDisplay.value = fiat !== null ? fiat.toFixed(2) : String(max)
    if (fiat === null) amountInFiat.value = false
  } else {
    amountDisplay.value = String(max)
  }
}

onMounted(() => {
  fetchBtcPrice()
})
</script>
