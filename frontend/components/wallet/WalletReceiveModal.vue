<template>
  <Modal v-model="visible" :title="$t('wallet.receive')" size="lg">
    <!-- Receive method selector -->
    <div class="space-y-3">
      <UiTabs v-model="receiveMethod" :tabs="receiveMethods" variant="pills" full-width @update:model-value="switchReceiveMethod" />

      <!-- Stable-height region for ALL generation states (input form / spinner / QR)
           so switching payment type never resizes the modal body — that resize is
           what makes the centered modal jump vertically between methods. -->
      <div class="min-h-[400px] flex flex-col justify-center">
        <!-- Lightning Invoice (with amount input) -->
        <div v-if="receiveMethod === 'lightningInvoice' && !receivePaymentRequest">
          <div class="mb-4">
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
              {{ $t('wallet.amount') }} (sats)
            </label>
            <input
              v-model="invoiceAmount"
              type="text"
              inputmode="numeric"
              placeholder="1000"
              class="w-full px-4 py-3 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-700 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent font-mono"
            />
            <p v-if="userCurrency !== 'BTC'" class="mt-1 text-sm text-neutral-500 font-mono">
              ≈ {{ formatFiat((invoiceAmount && parseInt(invoiceAmount) > 0 ? satsToFiat(parseInt(invoiceAmount)) : null) ?? 0) }}
            </p>
          </div>
          <div class="mb-4">
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
              {{ $t('wallet.description') }}
            </label>
            <input
              v-model="invoiceDescription"
              type="text"
              :placeholder="$t('wallet.invoiceDescPlaceholder')"
              class="w-full px-4 py-3 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-700 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
            />
          </div>
          <UiButton
            variant="primary"
            class="w-full"
            :disabled="!invoiceAmount || parseInt(invoiceAmount) <= 0"
            :loading="generatingReceive"
            @click="generateLightningInvoice"
          >
            {{ $t('wallet.generateInvoice') }}
          </UiButton>
        </div>

        <!-- Loading spinner for Spark/Bitcoin address generation -->
        <div v-if="receiveMethod !== 'lightningInvoice' && generatingReceive" class="text-center">
          <div class="animate-spin w-8 h-8 border-4 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100 rounded-full mx-auto" role="status">
            <span class="sr-only">Loading...</span>
          </div>
          <p class="mt-4 text-neutral-500">{{ $t('wallet.generating') }}</p>
        </div>

        <!-- QR + Address display (shared for all methods after generation) -->
        <div v-if="receivePaymentRequest && !generatingReceive" class="text-center">
          <!-- Fee info -->
          <div v-if="receiveFee > 0n" class="mb-2 text-sm text-neutral-500">
            {{ $t('wallet.fee') }}: {{ Number(receiveFee) }} sats
            <span v-if="satsToFiat(Number(receiveFee)) !== null && userCurrency !== 'BTC'" class="text-neutral-400 font-mono">(≈ {{ formatFiat(satsToFiat(Number(receiveFee))!) }})</span>
          </div>

          <!-- QR Code -->
          <div class="bg-white p-2 rounded-lg inline-block mb-2">
            <img
              v-if="qrCodeDataUrl"
              :src="qrCodeDataUrl"
              :alt="$t('wallet.invoice_qr_aria_label')"
              class="w-64 h-64"
            />
          </div>

          <!-- Payment request string -->
          <div class="bg-neutral-100 dark:bg-neutral-700 rounded-lg p-2 mb-2">
            <p class="font-mono text-xs break-all">{{ receivePaymentRequest }}</p>
          </div>

          <!-- Copy button -->
          <UiButton
            variant="primary"
            :icon="Copy"
            class="w-full"
            @click="copyPaymentRequest"
          >
            {{ addressCopied ? $t('common.copied') : $t('wallet.copyAddress') }}
          </UiButton>
        </div>
      </div>
    </div>
  </Modal>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Copy } from 'lucide-vue-next'
import QRCode from 'qrcode'
import { useLightning } from '~/composables/useLightning'
import { useBtcPrice } from '~/composables/useBtcPrice'

const props = defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v)
})

const { t } = useI18n()

const {
  createInvoice,
  getSparkAddress,
  getBitcoinAddress,
} = useLightning()

const { userCurrency, satsToFiat, formatFiat } = useBtcPrice()

// ===== RECEIVE STATE =====
const receiveMethods = computed(() => [
  { id: 'sparkAddress', label: t('wallet.sparkAddress') },
  { id: 'lightningInvoice', label: t('wallet.lightningInvoice') },
  { id: 'bitcoinAddress', label: t('wallet.bitcoinAddress') },
])
const receiveMethod = ref<string>('sparkAddress')
const invoiceAmount = ref('')
const invoiceDescription = ref('')
const generatingReceive = ref(false)
const receivePaymentRequest = ref('')
const receiveFee = ref(0n)
const qrCodeDataUrl = ref('')
const addressCopied = ref(false)

const switchReceiveMethod = async (method: string) => {
  receiveMethod.value = method
  receivePaymentRequest.value = ''
  qrCodeDataUrl.value = ''
  receiveFee.value = 0n

  if (method === 'sparkAddress') {
    await generateSparkAddress()
  } else if (method === 'bitcoinAddress') {
    await generateBitcoinAddress()
  }
}

const generateLightningInvoice = async () => {
  generatingReceive.value = true
  try {
    const amount = parseInt(invoiceAmount.value)
    if (isNaN(amount) || amount <= 0) return
    const result = await createInvoice(amount, invoiceDescription.value || undefined)
    receivePaymentRequest.value = result.paymentRequest
    receiveFee.value = result.fee
    await generateQRCode(result.paymentRequest)
  } catch (e: any) {
    console.error('Failed to create invoice:', e)
  } finally {
    generatingReceive.value = false
  }
}

const generateSparkAddress = async () => {
  generatingReceive.value = true
  try {
    const result = await getSparkAddress()
    receivePaymentRequest.value = result.paymentRequest
    receiveFee.value = result.fee
    await generateQRCode(result.paymentRequest)
  } catch (e: any) {
    console.error('Failed to get spark address:', e)
  } finally {
    generatingReceive.value = false
  }
}

const generateBitcoinAddress = async () => {
  generatingReceive.value = true
  try {
    const result = await getBitcoinAddress()
    receivePaymentRequest.value = result.paymentRequest
    receiveFee.value = result.fee
    await generateQRCode(`bitcoin:${result.paymentRequest}`)
  } catch (e: any) {
    console.error('Failed to get bitcoin address:', e)
  } finally {
    generatingReceive.value = false
  }
}

const generateQRCode = async (data: string) => {
  try {
    qrCodeDataUrl.value = await QRCode.toDataURL(data, {
      width: 320,
      margin: 2,
      color: { dark: '#000000', light: '#ffffff' }
    })
  } catch (e) {
    console.error('Failed to generate QR:', e)
  }
}

const copyPaymentRequest = async () => {
  try {
    await navigator.clipboard.writeText(receivePaymentRequest.value)
    addressCopied.value = true
    setTimeout(() => { addressCopied.value = false }, 2000)
  } catch (e) {
    console.error('Failed to copy:', e)
  }
}

const resetAll = () => {
  receivePaymentRequest.value = ''
  qrCodeDataUrl.value = ''
  receiveFee.value = 0n
  invoiceAmount.value = ''
  invoiceDescription.value = ''
  addressCopied.value = false
  receiveMethod.value = 'sparkAddress'
}

// Auto-generate on open
watch(visible, (isOpen) => {
  if (isOpen) {
    switchReceiveMethod(receiveMethod.value)
  } else {
    resetAll()
  }
})
</script>
