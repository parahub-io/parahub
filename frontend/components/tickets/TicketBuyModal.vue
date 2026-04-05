<template>
  <Teleport to="body">
    <Transition name="fade">
      <div
        v-if="ticketType"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4"
        @click.self="canClose && $emit('close')"
      >
        <div class="bg-white dark:bg-neutral-900 rounded-2xl max-w-sm w-full overflow-hidden">
          <!-- Header -->
          <div class="p-5 border-b border-neutral-100 dark:border-neutral-800">
            <div class="font-semibold text-neutral-900 dark:text-white">
              {{ ticketType.name }}
            </div>
            <div v-if="ticketType.description" class="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
              {{ ticketType.description }}
            </div>
            <div class="mt-2 text-lg font-bold text-secondary dark:text-secondary-400">
              {{ $t('tickets.price', { sats: ticketType.price_sats.toLocaleString() }) }}
            </div>
          </div>

          <!-- Step: Wallet not ready -->
          <div v-if="step === 'no-wallet'" class="p-5 text-center space-y-3">
            <WalletMinimal class="w-10 h-10 mx-auto text-neutral-400" />
            <p class="text-sm text-neutral-600 dark:text-neutral-400">
              {{ $t('tickets.error_no_wallet') }}
            </p>
            <UiButton variant="primary" class="w-full" @click="goToWallet">
              {{ $t('wallet.title') }}
            </UiButton>
          </div>

          <!-- Step: Ready to pay -->
          <div v-else-if="step === 'ready'" class="p-5 space-y-3">
            <div class="text-sm text-neutral-600 dark:text-neutral-400">
              {{ $t('tickets.pay_to_operator', { name: ticketType.operator_name }) }}
            </div>
            <div class="flex items-center gap-2 text-xs text-neutral-400">
              <Zap class="w-3.5 h-3.5" />
              <span class="truncate">{{ payAddress }}</span>
            </div>
            <UiButton
              variant="primary"
              class="w-full"
              :loading="paying"
              @click="pay"
            >
              <Zap class="w-4 h-4 mr-1.5" />
              {{ $t('tickets.pay_lightning', { sats: ticketType.price_sats.toLocaleString() }) }}
            </UiButton>
          </div>

          <!-- Step: Paying -->
          <div v-else-if="step === 'paying'" class="p-5 text-center space-y-3">
            <div class="animate-spin w-8 h-8 border-4 border-secondary border-t-transparent rounded-full mx-auto" />
            <p class="text-sm text-neutral-600 dark:text-neutral-400">{{ stepLabel }}</p>
          </div>

          <!-- Step: Success -->
          <div v-else-if="step === 'success'" class="p-5 text-center space-y-3">
            <div class="w-12 h-12 mx-auto rounded-full bg-emerald-100 dark:bg-emerald-900/50 flex items-center justify-center">
              <Check class="w-6 h-6 text-emerald-600 dark:text-emerald-400" />
            </div>
            <p class="font-semibold text-neutral-900 dark:text-white">
              {{ $t('tickets.purchase_success') }}
            </p>
            <UiButton
              v-if="purchasedTicket && !purchasedTicket.pgp_signature"
              variant="outline"
              size="sm"
              class="w-full"
              :loading="signing"
              @click="signTicket"
            >
              <ShieldCheck class="w-4 h-4 mr-1.5" />
              {{ $t('tickets.pgp_sign') }}
            </UiButton>
            <div v-if="purchasedTicket?.pgp_signature" class="text-xs text-emerald-600 dark:text-emerald-400 flex items-center justify-center gap-1">
              <ShieldCheck class="w-3.5 h-3.5" />
              {{ $t('tickets.pgp_signed') }}
            </div>
            <UiButton variant="primary" class="w-full" @click="showQR">
              <QrCode class="w-4 h-4 mr-1.5" />
              {{ $t('tickets.show_qr') }}
            </UiButton>
          </div>

          <!-- Step: Error -->
          <div v-else-if="step === 'error'" class="p-5 text-center space-y-3">
            <div class="w-12 h-12 mx-auto rounded-full bg-red-100 dark:bg-red-900/50 flex items-center justify-center">
              <AlertCircle class="w-6 h-6 text-red-600 dark:text-red-400" />
            </div>
            <p class="text-sm text-red-600 dark:text-red-400">{{ errorMsg }}</p>
            <UiButton variant="primary" class="w-full" @click="retry">
              {{ $t('common.retry') }}
            </UiButton>
          </div>

          <!-- Close button (only when not in middle of payment) -->
          <div v-if="canClose" class="p-3 border-t border-neutral-100 dark:border-neutral-800">
            <UiButton variant="ghost" class="w-full" @click="$emit('close')">
              {{ $t('common.close') }}
            </UiButton>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Zap, Check, AlertCircle, QrCode, ShieldCheck, WalletMinimal } from 'lucide-vue-next'

interface TicketType {
  id: string
  name: string
  description: string
  price_sats: number
  operator_name: string
  operator_ln_address: string
  operator_spark_address: string
}

const props = defineProps<{
  ticketType: TicketType | null
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'purchased', ticket: any): void
  (e: 'show-qr', ticket: any): void
}>()

const { t } = useI18n()
const localePath = useLocalePath()
const authStore = useAuthStore()
const {
  sdkState, initSdk, parseInput, prepareSend, executeSend,
  prepareLnurlPay, executeLnurlPay, hasSeed
} = useLightning()

const step = ref<'ready' | 'no-wallet' | 'paying' | 'success' | 'error'>('ready')
const stepLabel = ref('')
const paying = ref(false)
const signing = ref(false)
const errorMsg = ref('')
const purchasedTicket = ref<any>(null)

const payAddress = computed(() => {
  if (!props.ticketType) return ''
  return props.ticketType.operator_spark_address || props.ticketType.operator_ln_address
})

const canClose = computed(() => step.value !== 'paying')

// Reset when ticket type changes
watch(() => props.ticketType, async (tt) => {
  if (!tt) return
  step.value = 'ready'
  errorMsg.value = ''
  purchasedTicket.value = null

  // Check wallet availability
  if (!hasSeed.value) {
    step.value = 'no-wallet'
    return
  }

  if (sdkState.value !== 'ready') {
    try {
      await initSdk()
    } catch {
      step.value = 'no-wallet'
    }
  }
})

async function pay() {
  if (!props.ticketType) return
  paying.value = true
  step.value = 'paying'

  try {
    // 1. Create PENDING ticket
    stepLabel.value = t('tickets.payment_pending')
    await authStore.ensureToken()
    const ticket = await $fetch<any>('/api/v1/tickets/purchase/', {
      method: 'POST',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
      body: { ticket_type_id: props.ticketType.id },
    })

    // 2. Pay via Lightning
    stepLabel.value = t('tickets.paying_lightning')
    const address = props.ticketType.operator_spark_address || props.ticketType.operator_ln_address
    if (!address) throw new Error(t('tickets.error_no_ln_address'))

    let paymentHash = ''
    let preimage = ''

    const parsed = await parseInput(address)

    if (parsed.type === 'sparkAddress') {
      // Spark address: prepareSend + executeSend
      const amount = BigInt(props.ticketType.price_sats)
      const prep = await prepareSend(address, amount)
      const payment = await executeSend(prep)
      paymentHash = payment.details?.htlcDetails?.paymentHash || payment.id || ''
      preimage = payment.details?.htlcDetails?.preimage || ''
    } else if (parsed.type === 'lnurlPay' || parsed.type === 'lightningAddress') {
      // LN address: prepareLnurlPay + executeLnurlPay
      const payReq = parsed.type === 'lnurlPay' ? parsed : (parsed as any).payRequest
      const prep = await prepareLnurlPay(props.ticketType.price_sats, payReq)
      const payment = await executeLnurlPay(prep)
      paymentHash = payment.details?.htlcDetails?.paymentHash || payment.id || ''
      preimage = payment.details?.htlcDetails?.preimage || ''
    } else {
      throw new Error('Unsupported address type')
    }

    if (!paymentHash || !preimage) {
      throw new Error('Payment succeeded but missing proof data')
    }

    // 3. Confirm payment
    stepLabel.value = t('tickets.payment_confirm')
    const confirmed = await $fetch<any>('/api/v1/tickets/confirm/', {
      method: 'POST',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
      body: {
        ticket_id: ticket.id,
        ln_payment_hash: paymentHash,
        ln_preimage: preimage,
      },
    })

    purchasedTicket.value = confirmed
    step.value = 'success'
    emit('purchased', confirmed)
  } catch (e: any) {
    errorMsg.value = e?.data?.detail || e?.message || t('tickets.error_purchase')
    step.value = 'error'
  } finally {
    paying.value = false
  }
}

async function signTicket() {
  if (!purchasedTicket.value) return
  signing.value = true
  try {
    const { signMessage } = usePGP()
    const signature = await signMessage(purchasedTicket.value.qr_token)
    await authStore.ensureToken()
    const updated = await $fetch<any>(`/api/v1/tickets/${purchasedTicket.value.id}/sign/`, {
      method: 'PATCH',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
      body: { pgp_signature: signature },
    })
    purchasedTicket.value = updated
  } catch (e: any) {
    console.error('PGP sign failed:', e)
  } finally {
    signing.value = false
  }
}

function showQR() {
  if (purchasedTicket.value) {
    emit('show-qr', purchasedTicket.value)
    emit('close')
  }
}

function goToWallet() {
  emit('close')
  navigateTo(localePath('/wallet'))
}

function retry() {
  step.value = 'ready'
  errorMsg.value = ''
}
</script>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity 0.2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
