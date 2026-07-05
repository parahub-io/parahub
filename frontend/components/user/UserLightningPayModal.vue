<template>
  <Modal
    v-model="visible"
    :title="modalTitle"
    :icon="isSubscribe ? Heart : Zap"
    :icon-class="isSubscribe ? 'text-rose-500' : 'text-orange-600'"
    size="md"
  >
    <div class="space-y-4">
      <!-- No LN address -->
      <div v-if="sendStep === 'no_ln'" class="text-center py-4">
        <AlertTriangle class="w-12 h-12 text-amber-500 mx-auto mb-3" />
        <p class="text-sm text-neutral-700 dark:text-neutral-300">
          {{ t('user_profile.ln_no_address', { name: profile.display_name || profile.hna }) }}
        </p>
      </div>

      <!-- No wallet -->
      <div v-else-if="sendStep === 'no_wallet'" class="text-center py-4">
        <AlertTriangle class="w-12 h-12 text-amber-500 mx-auto mb-3" />
        <p class="text-sm text-neutral-700 dark:text-neutral-300 mb-4">
          {{ t('user_profile.ln_no_wallet') }}
        </p>
        <button
          @click="visible = false; navigateTo(localePath('/wallet'))"
          class="btn-primary"
        >
          {{ t('user_profile.ln_setup_wallet') }}
        </button>
      </div>

      <!-- Amount input -->
      <div v-else-if="sendStep === 'input'" class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
            {{ t('user_profile.amount_sats') }}
          </label>
          <input
            v-model="sendAmount"
            type="number"
            min="1"
            :placeholder="t('user_profile.enter_amount')"
            class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
            @keyup.enter="initSendLightning"
          />
          <p v-if="sendFiatEquivalent" class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
            {{ sendFiatEquivalent }}
          </p>
        </div>
        <div v-if="!profile.spark_address">
          <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
            {{ t('user_profile.payment_note_optional') }}
          </label>
          <input
            v-model="sendComment"
            type="text"
            :placeholder="t('user_profile.payment_note_placeholder')"
            class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
          />
        </div>
        <div class="bg-neutral-50 dark:bg-neutral-900/50 rounded-lg p-3 text-xs text-neutral-600 dark:text-neutral-400">
          <div class="flex items-center gap-1.5">
            <Zap class="w-3.5 h-3.5 text-amber-500 flex-shrink-0" />
            <span v-if="profile.spark_address">{{ t('user_profile.ln_sending_to') }}: <strong class="text-green-600 dark:text-green-400">Spark</strong></span>
            <span v-else>{{ t('user_profile.ln_sending_to') }}: <strong class="text-amber-600 dark:text-amber-400">{{ profile.ln_address }}</strong></span>
          </div>
        </div>
        <div v-if="isSubscribe" class="flex items-start gap-1.5 text-xs text-neutral-500 dark:text-neutral-400">
          <Info class="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
          <span>{{ t('subscriptions.monthly_hint') }}</span>
        </div>
      </div>

      <!-- Resolving/Preparing -->
      <div v-else-if="sendStep === 'resolving'" class="text-center py-8">
        <Loader2 class="w-8 h-8 animate-spin text-primary mx-auto mb-3" />
        <p class="text-sm text-neutral-600 dark:text-neutral-400">{{ t('user_profile.ln_preparing') }}</p>
      </div>

      <!-- Confirm -->
      <div v-else-if="sendStep === 'confirm'" class="space-y-3">
        <div class="bg-neutral-50 dark:bg-neutral-900/50 rounded-lg p-4 space-y-2">
          <div class="flex justify-between text-sm">
            <span class="text-neutral-600 dark:text-neutral-400">{{ t('user_profile.ln_recipient') }}</span>
            <span class="font-mono text-amber-600 dark:text-amber-400 text-right break-all max-w-[200px]">{{ sendViaSpark ? profile.spark_address : profile.ln_address }}</span>
          </div>
          <div v-if="sendViaSpark" class="flex justify-between text-sm">
            <span class="text-neutral-600 dark:text-neutral-400">{{ t('user_profile.ln_method') }}</span>
            <span class="text-green-600 dark:text-green-400 font-medium">Spark</span>
          </div>
          <div class="flex justify-between text-sm">
            <span class="text-neutral-600 dark:text-neutral-400">{{ t('user_profile.ln_amount') }}</span>
            <span class="font-medium">{{ lightning.formatSats(parseInt(sendAmount)) }} sats</span>
          </div>
          <div v-if="confirmFeeSats > 0" class="flex justify-between text-sm">
            <span class="text-neutral-600 dark:text-neutral-400">{{ t('user_profile.ln_fee') }}</span>
            <span class="text-neutral-600 dark:text-neutral-400">{{ lightning.formatSats(confirmFeeSats) }} sats</span>
          </div>
          <div class="border-t border-neutral-300 dark:border-neutral-600 pt-2 flex justify-between text-sm font-semibold">
            <span>{{ t('user_profile.ln_total') }}</span>
            <span>{{ lightning.formatSats(parseInt(sendAmount) + confirmFeeSats) }} sats</span>
          </div>
        </div>
        <p v-if="sendFiatEquivalent" class="text-xs text-center text-neutral-500 dark:text-neutral-400">
          {{ sendFiatEquivalent }}
        </p>
      </div>

      <!-- Executing -->
      <div v-else-if="sendStep === 'executing'" class="text-center py-8">
        <Loader2 class="w-8 h-8 animate-spin text-orange-500 mx-auto mb-3" />
        <p class="text-sm text-neutral-600 dark:text-neutral-400">{{ t('user_profile.ln_sending') }}</p>
      </div>

      <!-- Success -->
      <div v-else-if="sendStep === 'success'" class="text-center py-4">
        <component :is="isSubscribe ? Heart : CheckCircle" class="w-12 h-12 mx-auto mb-3" :class="isSubscribe ? 'text-rose-500' : 'text-green-500'" />
        <p class="text-lg font-semibold text-green-700 dark:text-green-300 mb-1">
          {{ isSubscribe ? t('subscriptions.success_title', { name: profile.display_name || profile.hna }) : t('user_profile.ln_sent_success') }}
        </p>
        <p class="text-sm text-neutral-600 dark:text-neutral-400">
          {{ lightning.formatSats(parseInt(sendAmount)) }} sats → {{ profile.display_name || profile.hna }}
        </p>
        <p v-if="isSubscribe" class="text-xs text-neutral-500 dark:text-neutral-400 mt-2">
          {{ t('subscriptions.success_hint') }}
        </p>
      </div>

      <!-- Error -->
      <div v-else-if="sendStep === 'error' || sendStep === 'sdk_error'" class="text-center py-4">
        <AlertTriangle class="w-12 h-12 text-red-500 mx-auto mb-3" />
        <p class="text-sm text-red-700 dark:text-red-300 mb-2">{{ t('user_profile.ln_error') }}</p>
        <p class="text-xs text-neutral-600 dark:text-neutral-400 font-mono">{{ sendError }}</p>
      </div>
    </div>

    <template #footer>
      <template v-if="sendStep === 'input'">
        <UiButton variant="outline" @click="visible = false">
          {{ t('user_profile.cancel') }}
        </UiButton>
        <UiButton
          :variant="isSubscribe ? 'primary' : 'warning'"
          :disabled="!sendAmount || parseInt(sendAmount) < 1"
          @click="initSendLightning"
        >
          {{ t('user_profile.ln_continue') }}
        </UiButton>
      </template>
      <template v-else-if="sendStep === 'confirm'">
        <UiButton variant="outline" @click="sendStep = 'input'">
          {{ t('common.back') }}
        </UiButton>
        <UiButton :variant="isSubscribe ? 'primary' : 'warning'" @click="executeSendLightning">
          {{ isSubscribe ? t('subscriptions.confirm_support') : t('user_profile.send_payment') }}
        </UiButton>
      </template>
      <template v-else-if="sendStep === 'success' || sendStep === 'error' || sendStep === 'sdk_error' || sendStep === 'no_ln' || sendStep === 'no_wallet'">
        <UiButton variant="primary" @click="visible = false">
          {{ t('user_profile.close') }}
        </UiButton>
      </template>
    </template>
  </Modal>
</template>

<script setup lang="ts">
const localePath = useLocalePath()
import { Zap, AlertTriangle, Loader2, CheckCircle, Heart, Info } from 'lucide-vue-next'

const props = withDefaults(defineProps<{
  profile: any
  modelValue: boolean
  mode?: 'tip' | 'subscribe'
  presetAmount?: number
}>(), { mode: 'tip', presetAmount: 0 })
const emit = defineEmits<{
  'update:modelValue': [boolean]
  // Fires once on a successful payment with the amount + best-effort LN hash, so a
  // parent can record a recurring subscription. Ignored by plain tip callers.
  'paid': [{ amountSats: number; paymentHash: string }]
}>()

const { t } = useI18n()
const lightning = useLightning()
const { satsToFiat, formatFiat, fetchBtcPrice } = useBtcPrice()

const isSubscribe = computed(() => props.mode === 'subscribe')
const modalTitle = computed(() => isSubscribe.value
  ? t('subscriptions.support_monthly', { name: props.profile.display_name || props.profile.hna })
  : t('user_profile.send_lightning_to', { name: props.profile.display_name || props.profile.hna }))

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v)
})

// State
type SendStep = 'input' | 'resolving' | 'confirm' | 'executing' | 'success' | 'no_ln' | 'no_wallet' | 'sdk_error' | 'error'
const sendStep = ref<SendStep>('input')
const sendAmount = ref('')
const sendComment = ref('')
const sendError = ref('')
const sendParsed = ref<any>(null)
const sendPrepared = ref<any>(null)
const sendResult = ref<any>(null)
const sendViaSpark = ref(false)

const sendFiatEquivalent = computed(() => {
  const sats = parseInt(sendAmount.value)
  if (!sats || isNaN(sats)) return ''
  const fiat = satsToFiat(sats)
  return fiat !== null ? `≈ ${formatFiat(fiat)}` : ''
})

const confirmFeeSats = computed(() => {
  if (!sendPrepared.value) return 0
  if (sendViaSpark.value) {
    const method = sendPrepared.value.paymentMethod
    if (method?.type === 'sparkAddress' || method?.type === 'sparkInvoice') {
      return Number(method.fee || 0)
    }
    return 0
  }
  return Number(sendPrepared.value.feesSats || 0)
})

const resetSendState = () => {
  sendStep.value = (props.profile?.ln_address || props.profile?.spark_address) ? 'input' : 'no_ln'
  sendAmount.value = props.presetAmount > 0 ? String(props.presetAmount) : ''
  sendComment.value = ''
  sendError.value = ''
  sendParsed.value = null
  sendPrepared.value = null
  sendResult.value = null
  sendViaSpark.value = false
}

const initSendLightning = async () => {
  if (!sendAmount.value || parseInt(sendAmount.value) < 1) return

  sendStep.value = 'resolving'
  sendError.value = ''
  sendViaSpark.value = false

  try {
    if (!lightning.hasSeed()) {
      sendStep.value = 'no_wallet'
      return
    }

    await lightning.initSdk()

    if (lightning.sdkState.value !== 'ready') {
      sendStep.value = 'sdk_error'
      sendError.value = lightning.sdkError.value || 'SDK initialization failed'
      return
    }

    const amountSats = parseInt(sendAmount.value)

    // Prefer Spark address for direct P2P (cheaper, no LNURL overhead)
    if (props.profile?.spark_address) {
      try {
        const prepared = await lightning.prepareSend(
          props.profile.spark_address,
          BigInt(amountSats)
        )
        sendPrepared.value = prepared
        sendViaSpark.value = true
        sendStep.value = 'confirm'
        return
      } catch (sparkErr: any) {
        console.warn('Spark send failed, falling back to LNURL:', sparkErr.message)
      }
    }

    // Fallback: LNURL-pay via ln_address
    if (!props.profile?.ln_address) {
      sendStep.value = 'error'
      sendError.value = 'No payment address available'
      return
    }

    const parsed = await lightning.parseInput(props.profile.ln_address)
    if (parsed.type !== 'lnUrlPay') {
      sendStep.value = 'error'
      sendError.value = 'Invalid Lightning address'
      return
    }

    sendParsed.value = parsed

    const prepared = await lightning.prepareLnurlPay(
      amountSats,
      parsed.lnurlPayRequestDetails,
      sendComment.value || undefined
    )

    sendPrepared.value = prepared
    sendStep.value = 'confirm'
  } catch (e: any) {
    console.error('Send Lightning error:', e)
    sendStep.value = 'error'
    sendError.value = e.message || 'Unknown error'
  }
}

const executeSendLightning = async () => {
  if (!sendPrepared.value) return

  sendStep.value = 'executing'
  sendError.value = ''

  try {
    let payment
    if (sendViaSpark.value) {
      payment = await lightning.executeSend(sendPrepared.value)
    } else {
      payment = await lightning.executeLnurlPay(sendPrepared.value)
    }
    sendResult.value = payment
    sendStep.value = 'success'
    // Best-effort payment hash for idempotent server-side recording (subscriptions).
    const hash = payment?.paymentHash || payment?.payment?.paymentHash
      || payment?.details?.paymentHash || ''
    emit('paid', { amountSats: parseInt(sendAmount.value), paymentHash: hash })
  } catch (e: any) {
    console.error('Execute payment error:', e)
    sendStep.value = 'error'
    sendError.value = e.message || 'Payment failed'
  }
}

watch(visible, (show) => {
  if (show) {
    resetSendState()
    fetchBtcPrice()
  }
})
</script>
