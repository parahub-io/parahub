<template>
  <Modal
    v-model="visible"
    :title="t('user_profile.create_invoice')"
    :icon="FileText"
    icon-class="text-yellow-600"
    size="md"
  >
    <div class="space-y-4">
      <!-- Method selection -->
      <div v-if="invoiceStep === 'method_select'" class="space-y-3">
        <p class="text-sm text-neutral-600 dark:text-neutral-400">
          {{ t('user_profile.inv_choose_method') }}
        </p>
        <button
          @click="startInvoice('bolt11')"
          class="w-full flex items-center gap-3 px-4 py-3 bg-neutral-100 dark:bg-neutral-700 hover:bg-neutral-200 dark:hover:bg-neutral-600 rounded-lg transition-colors text-left"
        >
          <Zap class="w-5 h-5 text-amber-500 flex-shrink-0" />
          <div class="flex-1">
            <p class="font-medium text-neutral-900 dark:text-neutral-100">{{ t('user_profile.inv_bolt11_title') }}</p>
            <p class="text-xs text-neutral-600 dark:text-neutral-400">{{ t('user_profile.inv_bolt11_desc') }}</p>
          </div>
        </button>
        <button
          @click="startInvoice('spark')"
          class="w-full flex items-center gap-3 px-4 py-3 bg-neutral-100 dark:bg-neutral-700 hover:bg-neutral-200 dark:hover:bg-neutral-600 rounded-lg transition-colors text-left"
        >
          <Zap class="w-5 h-5 text-purple-500 flex-shrink-0" />
          <div class="flex-1">
            <p class="font-medium text-neutral-900 dark:text-neutral-100">{{ t('user_profile.inv_spark_title') }}</p>
            <p class="text-xs text-neutral-600 dark:text-neutral-400">{{ t('user_profile.inv_spark_desc') }}</p>
          </div>
        </button>
      </div>

      <!-- Bolt11 amount input -->
      <div v-else-if="invoiceStep === 'input'" class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
            {{ t('user_profile.amount_sats') }}
          </label>
          <input
            v-model="invoiceAmount"
            type="number"
            min="1"
            :placeholder="t('user_profile.enter_amount')"
            class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
            @keyup.enter="generateInvoice"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
            {{ t('user_profile.invoice_description') }}
          </label>
          <input
            v-model="invoiceDescription"
            type="text"
            :placeholder="t('user_profile.invoice_description_placeholder')"
            class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
          />
        </div>
      </div>

      <!-- Generating -->
      <div v-else-if="invoiceStep === 'generating'" class="text-center py-8">
        <Loader2 class="w-8 h-8 animate-spin text-primary mx-auto mb-3" />
        <p class="text-sm text-neutral-600 dark:text-neutral-400">{{ t('user_profile.inv_generating') }}</p>
      </div>

      <!-- Result: QR + copy -->
      <div v-else-if="invoiceStep === 'result' && invoiceResult" class="space-y-4">
        <div class="bg-white p-4 rounded-lg border border-neutral-300 dark:border-neutral-600 flex justify-center">
          <canvas ref="invoiceQrCanvas" role="img" :aria-label="$t('wallet.invoice_qr_aria_label')"></canvas>
        </div>
        <div class="relative">
          <div class="bg-neutral-100 dark:bg-neutral-700 rounded-lg p-3 pr-12 font-mono text-xs break-all max-h-24 overflow-y-auto">
            {{ invoiceResult.paymentRequest }}
          </div>
          <button
            @click="copyInvoice"
            class="absolute top-2 right-2 p-1.5 bg-white dark:bg-neutral-600 rounded border border-neutral-300 dark:border-neutral-500 hover:bg-neutral-50 dark:hover:bg-neutral-500"
          >
            <Copy v-if="!invoiceCopied" class="w-4 h-4 text-neutral-600 dark:text-neutral-400" />
            <Check v-else class="w-4 h-4 text-green-500" />
          </button>
        </div>
        <p class="text-xs text-center text-neutral-500 dark:text-neutral-400">
          {{ invoiceMethod === 'bolt11' ? t('user_profile.inv_bolt11_hint') : t('user_profile.inv_spark_hint') }}
        </p>
      </div>

      <!-- Error -->
      <div v-else-if="invoiceStep === 'error'" class="text-center py-4">
        <AlertTriangle class="w-12 h-12 text-red-500 mx-auto mb-3" />
        <p class="text-sm text-red-700 dark:text-red-300 mb-2">
          {{ invoiceError === 'no_wallet' ? t('user_profile.ln_no_wallet') : t('user_profile.ln_error') }}
        </p>
        <p v-if="invoiceError !== 'no_wallet'" class="text-xs text-neutral-600 dark:text-neutral-400 font-mono">{{ invoiceError }}</p>
        <button
          v-if="invoiceError === 'no_wallet'"
          @click="visible = false; navigateTo(localePath('/wallet'))"
          class="btn-primary mt-3"
        >
          {{ t('user_profile.ln_setup_wallet') }}
        </button>
      </div>
    </div>

    <template #footer>
      <template v-if="invoiceStep === 'method_select'">
        <button
          @click="visible = false"
          class="px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-700"
        >
          {{ t('user_profile.cancel') }}
        </button>
      </template>
      <template v-else-if="invoiceStep === 'input'">
        <button
          @click="invoiceStep = 'method_select'"
          class="px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-700"
        >
          {{ t('common.back') }}
        </button>
        <button
          @click="generateInvoice"
          :disabled="!invoiceAmount || parseInt(invoiceAmount) < 1"
          class="btn-primary btn-sm disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {{ t('user_profile.create_invoice_btn') }}
        </button>
      </template>
      <template v-else-if="invoiceStep === 'result'">
        <button
          @click="invoiceStep = 'method_select'"
          class="px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-700"
        >
          {{ t('user_profile.inv_new') }}
        </button>
        <button
          @click="visible = false"
          class="px-4 py-2 bg-primary text-black font-medium rounded-lg hover:bg-primary/90"
        >
          {{ t('user_profile.close') }}
        </button>
      </template>
      <template v-else-if="invoiceStep === 'error'">
        <button
          @click="visible = false"
          class="px-4 py-2 bg-primary text-black font-medium rounded-lg hover:bg-primary/90"
        >
          {{ t('user_profile.close') }}
        </button>
      </template>
    </template>
  </Modal>
</template>

<script setup lang="ts">
const localePath = useLocalePath()
import { Zap, FileText, Loader2, AlertTriangle, Copy, Check } from 'lucide-vue-next'
import QRCode from 'qrcode'

const props = defineProps<{ profile: any; modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [boolean] }>()

const { t } = useI18n()
const lightning = useLightning()
const toastStore = useToastStore()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v)
})

// State
type InvoiceStep = 'method_select' | 'input' | 'generating' | 'result' | 'error'
const invoiceStep = ref<InvoiceStep>('method_select')
const invoiceMethod = ref<'bolt11' | 'spark'>('bolt11')
const invoiceAmount = ref('')
const invoiceDescription = ref('')
const invoiceResult = ref<any>(null)
const invoiceError = ref('')
const invoiceCopied = ref(false)
const invoiceQrCanvas = ref<HTMLCanvasElement | null>(null)

const resetInvoiceState = () => {
  invoiceStep.value = 'method_select'
  invoiceMethod.value = 'bolt11'
  invoiceAmount.value = ''
  invoiceDescription.value = ''
  invoiceResult.value = null
  invoiceError.value = ''
  invoiceCopied.value = false
}

const startInvoice = async (method: 'bolt11' | 'spark') => {
  invoiceMethod.value = method
  invoiceError.value = ''
  invoiceResult.value = null
  invoiceCopied.value = false

  if (method === 'spark') {
    invoiceStep.value = 'generating'
    await generateInvoice()
  } else {
    invoiceStep.value = 'input'
    invoiceAmount.value = ''
    invoiceDescription.value = ''
  }
}

const generateInvoice = async () => {
  invoiceStep.value = 'generating'
  invoiceError.value = ''

  try {
    if (!lightning.hasSeed()) {
      invoiceStep.value = 'error'
      invoiceError.value = 'no_wallet'
      return
    }

    await lightning.initSdk()

    if (lightning.sdkState.value !== 'ready') {
      invoiceStep.value = 'error'
      invoiceError.value = lightning.sdkError.value || 'SDK initialization failed'
      return
    }

    let result: any
    if (invoiceMethod.value === 'bolt11') {
      const amount = parseInt(invoiceAmount.value)
      if (!amount || amount < 1) {
        invoiceStep.value = 'input'
        invoiceError.value = 'Invalid amount'
        return
      }
      result = await lightning.createInvoice(amount, invoiceDescription.value || undefined)
    } else {
      result = await lightning.getSparkAddress()
    }

    invoiceResult.value = result
    invoiceStep.value = 'result'

    await nextTick()
    generateInvoiceQR()
  } catch (e: any) {
    console.error('Create invoice error:', e)
    invoiceStep.value = 'error'
    invoiceError.value = e.message || 'Failed to create invoice'
  }
}

const generateInvoiceQR = async () => {
  await nextTick()
  setTimeout(async () => {
    if (invoiceQrCanvas.value && invoiceResult.value?.paymentRequest) {
      try {
        await QRCode.toCanvas(invoiceQrCanvas.value, invoiceResult.value.paymentRequest, {
          width: 256,
          margin: 2,
          color: { dark: '#000000', light: '#FFFFFF' }
        })
      } catch (err) {
        console.error('Failed to generate invoice QR:', err)
      }
    }
  }, 100)
}

const copyInvoice = async () => {
  if (!invoiceResult.value?.paymentRequest) return
  try {
    await navigator.clipboard.writeText(invoiceResult.value.paymentRequest)
    invoiceCopied.value = true
    toastStore.success(t('user_profile.invoice_copied'))
    setTimeout(() => { invoiceCopied.value = false }, 2000)
  } catch (err) {
    console.error('Failed to copy:', err)
  }
}

watch(visible, (show) => {
  if (show) {
    resetInvoiceState()
  }
})
</script>
