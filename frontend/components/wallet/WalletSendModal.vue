<template>
  <Modal v-model="visible" :title="$t('wallet.send')" size="lg">
    <!-- Step 1: Input -->
    <div v-if="!sendPrepared && !sendSuccess" class="space-y-4">
      <!-- Partners: the people you deal with, above the addresses you happened to
           use last. Only the top few — the long tail is reached through their
           profile, which is where paying someone properly starts. -->
      <div v-if="partners.length > 0 && !sendInput" class="space-y-1.5">
        <p class="text-xs font-medium text-neutral-500 dark:text-neutral-400">{{ $t('wallet.partners') }}</p>
        <div class="flex flex-wrap gap-2">
          <button
            v-for="partner in partners"
            :key="partner.id"
            type="button"
            class="flex items-center gap-1.5 pl-1 pr-3 py-1 rounded-full bg-neutral-100 dark:bg-neutral-700 text-sm transition-colors"
            :class="partnerAddress(partner)
              ? 'hover:bg-primary-100 dark:hover:bg-primary-900/40'
              : 'opacity-50 cursor-not-allowed'"
            :disabled="!partnerAddress(partner)"
            :title="partnerAddress(partner) || $t('wallet.partner_no_address')"
            @click="selectPartner(partner)"
          >
            <img
              v-if="partner.avatar_url"
              :src="partner.avatar_url"
              :alt="partnerLabel(partner)"
              class="w-6 h-6 rounded-full object-cover"
            />
            <span
              v-else
              class="w-6 h-6 rounded-full bg-gradient-to-br from-primary to-secondary flex items-center justify-center text-[10px] font-bold text-black"
            >{{ partnerInitials(partner) }}</span>
            <span class="text-xs truncate max-w-[160px]">{{ partnerLabel(partner) }}</span>
          </button>
        </div>
      </div>

      <!-- Recent contacts -->
      <div v-if="recentContacts.length > 0 && !sendInput" class="space-y-1.5">
        <p class="text-xs font-medium text-neutral-500 dark:text-neutral-400">{{ $t('wallet.recentRecipients') }}</p>
        <div class="flex flex-wrap gap-2">
          <button
            v-for="contact in recentContacts"
            :key="contact.address"
            type="button"
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-neutral-100 dark:bg-neutral-700 hover:bg-primary-100 dark:hover:bg-primary-900/40 text-sm transition-colors"
            :title="contact.address"
            @click="selectContact(contact)"
          >
            <!-- A recent address that belongs to a partner is shown as that person:
                 the raw string stays in the tooltip -->
            <template v-if="partnerForAddress(contact.address)">
              <img
                v-if="partnerForAddress(contact.address)!.avatar_url"
                :src="partnerForAddress(contact.address)!.avatar_url!"
                :alt="partnerLabel(partnerForAddress(contact.address)!)"
                class="w-5 h-5 rounded-full object-cover"
              />
              <span
                v-else
                class="w-5 h-5 rounded-full bg-gradient-to-br from-primary to-secondary flex items-center justify-center text-[9px] font-bold text-black"
              >{{ partnerInitials(partnerForAddress(contact.address)!) }}</span>
              <span class="text-xs truncate max-w-[160px]">{{ partnerLabel(partnerForAddress(contact.address)!) }}</span>
            </template>
            <template v-else>
              <Clock class="w-3 h-3 text-neutral-400" />
              <span class="font-mono text-xs truncate max-w-[160px]">{{ contact.label || contact.address }}</span>
            </template>
          </button>
        </div>
      </div>

      <!-- QR Scan button -->
      <button
        type="button"
        class="w-full flex items-center justify-center gap-2 px-4 py-3 bg-primary hover:bg-primary/90 text-neutral-900 font-medium rounded-xl transition-colors"
        @click="openScanner"
      >
        <ScanLine class="w-5 h-5" />
        {{ $t('wallet.scanQr') }}
      </button>

      <div>
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
          {{ $t('wallet.recipientAddress') }}
        </label>
        <div class="relative">
          <input
            v-model="sendInput"
            type="text"
            :placeholder="$t('wallet.enterAddress')"
            class="w-full px-4 py-3 pr-12 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-700 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent font-mono text-sm"
          />
          <button
            type="button"
            class="absolute right-2 top-1/2 -translate-y-1/2 p-2 text-neutral-400 hover:text-secondary transition-colors"
            :title="$t('wallet.scanQr')"
            @click="openScanner"
          >
            <ScanLine class="w-5 h-5" />
          </button>
        </div>
        <p v-if="sendParseInfo" class="mt-2 text-xs text-neutral-500">
          {{ sendParseInfo }}
        </p>
      </div>

      <!-- Amount (if needed) -->
      <WalletAmountInput
        v-if="sendNeedsAmount"
        v-model:sats="sendAmountSats"
        :max-sats="balanceSats"
        @submit="handlePrepareSend"
      />

      <UiButton
        variant="primary"
        class="w-full"
        :disabled="!sendInput"
        :loading="preparingSend"
        @click="handlePrepareSend"
      >
        {{ $t('wallet.next') }}
      </UiButton>

      <p v-if="sendError" class="text-sm text-error dark:text-error-400">
        {{ sendError }}
      </p>
    </div>

    <!-- Step 2: Confirm -->
    <div v-if="sendPrepared && !sendSuccess" class="space-y-4">
      <h3 class="font-medium text-lg">{{ $t('wallet.confirmPayment') }}</h3>

      <div class="space-y-2 text-sm">
        <div class="flex justify-between">
          <span class="text-neutral-500">{{ $t('wallet.amount') }}</span>
          <div class="text-right">
            <span class="font-mono font-medium">{{ Number(sendPrepareResponse!.amount) }} sats</span>
            <span v-if="satsToFiat(Number(sendPrepareResponse!.amount)) !== null && userCurrency !== 'BTC'" class="text-neutral-400 ml-2 font-mono">≈ {{ formatFiat(satsToFiat(Number(sendPrepareResponse!.amount))!) }}</span>
          </div>
        </div>
        <div class="flex justify-between">
          <span class="text-neutral-500">{{ $t('wallet.fee') }}</span>
          <div class="text-right">
            <span class="font-mono">{{ sendFeeDisplay }} sats</span>
            <span v-if="satsToFiat(parseInt(sendFeeDisplay || '0')) !== null && userCurrency !== 'BTC' && parseInt(sendFeeDisplay || '0') > 0" class="text-neutral-400 ml-2 font-mono">≈ {{ formatFiat(satsToFiat(parseInt(sendFeeDisplay || '0'))!) }}</span>
          </div>
        </div>
        <div class="border-t border-neutral-200 dark:border-neutral-700 pt-2 flex justify-between font-medium">
          <span>{{ $t('wallet.total') }}</span>
          <div class="text-right">
            <span class="font-mono">{{ sendTotalDisplay }} sats</span>
            <span v-if="satsToFiat(parseInt(sendTotalDisplay || '0')) !== null && userCurrency !== 'BTC'" class="text-neutral-400 ml-2 font-mono">≈ {{ formatFiat(satsToFiat(parseInt(sendTotalDisplay || '0'))!) }}</span>
          </div>
        </div>
      </div>

      <!-- Association donation prompt -->
      <DonationPrompt :source-amount-sats="Number(sendPrepareResponse!.amount)" />

      <div class="flex gap-3">
        <UiButton variant="outline" class="flex-1" @click="cancelSend">
          {{ $t('common.cancel') }}
        </UiButton>
        <UiButton variant="primary" class="flex-1" :loading="executingSend" @click="handleExecuteSend">
          {{ $t('wallet.send') }}
        </UiButton>
      </div>

      <p v-if="sendError" class="text-sm text-error dark:text-error-400">
        {{ sendError }}
      </p>
    </div>

    <!-- Step 3: Success -->
    <div v-if="sendSuccess" class="text-center py-4">
      <UiAlert variant="success">{{ $t('wallet.paymentSuccessful') }}</UiAlert>
    </div>
  </Modal>

  <!-- QR Scanner fullscreen overlay -->
  <Teleport to="body">
    <div v-if="scannerActive" class="fixed inset-0 z-[60] bg-black flex flex-col">
      <div class="flex items-center justify-between p-4">
        <h2 class="text-white font-medium">{{ $t('wallet.scanQr') }}</h2>
        <button
          type="button"
          class="p-2 text-white hover:text-neutral-300 transition-colors"
          @click="closeScanner"
        >
          <X class="w-6 h-6" />
        </button>
      </div>
      <div class="flex-1 flex items-center justify-center relative overflow-hidden">
        <video ref="scannerVideo" class="w-full h-full object-cover" />
      </div>
      <div v-if="scannerError" class="absolute bottom-0 left-0 right-0 p-4 bg-error-900/80">
        <div class="flex items-center gap-2 text-white text-sm">
          <AlertTriangle class="w-5 h-5 flex-shrink-0" />
          <span>{{ scannerError }}</span>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onUnmounted } from 'vue'
import { ScanLine, X, AlertTriangle, Clock } from 'lucide-vue-next'
import { useLightning } from '~/composables/useLightning'
import { useBtcPrice } from '~/composables/useBtcPrice'
import type { QuickPartner } from '~/composables/usePartnersQuickList'

import type {
  PrepareSendPaymentResponse,
  PrepareLnurlPayResponse,
  InputType,
  LnurlPayRequestDetails,
} from '@breeztech/breez-sdk-spark/web'

const props = defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'success': []
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v)
})

const { t } = useI18n()

const {
  balanceSats,
  parseInput,
  prepareSend,
  executeSend,
  prepareLnurlPay,
  executeLnurlPay,
} = useLightning()

const { userCurrency, satsToFiat, formatFiat } = useBtcPrice()

const donation = useDonation()

// ===== RECENT CONTACTS =====
interface RecentContact {
  address: string
  label: string
  lastUsed: number
}

const CONTACTS_KEY = 'parahub_recent_recipients'
const MAX_CONTACTS = 5

const loadContacts = (): RecentContact[] => {
  if (!import.meta.client) return []
  try {
    return JSON.parse(localStorage.getItem(CONTACTS_KEY) || '[]')
  } catch { return [] }
}

const saveContact = (address: string) => {
  if (!import.meta.client) return
  const contacts = loadContacts()
  // Derive label: lightning address or shortened address
  const label = address.includes('@') ? address : `${address.slice(0, 10)}...${address.slice(-6)}`
  const existing = contacts.findIndex(c => c.address === address)
  if (existing >= 0) contacts.splice(existing, 1)
  contacts.unshift({ address, label, lastUsed: Date.now() })
  if (contacts.length > MAX_CONTACTS) contacts.length = MAX_CONTACTS
  localStorage.setItem(CONTACTS_KEY, JSON.stringify(contacts))
}

const recentContacts = ref<RecentContact[]>(loadContacts())

const selectContact = (contact: RecentContact) => {
  sendInput.value = contact.address
}

// ===== PARTNERS =====
// Same cached list the site-menu strip uses. A partner without a payment
// address stays in the row, greyed out with the reason in its tooltip —
// silently dropping them reads as "my partner is missing".
const { items: partners, fetch: fetchPartners } = usePartnersQuickList()

const partnerLabel = (partner: QuickPartner) => partner.display_name || partner.hna
const partnerInitials = (partner: QuickPartner) => {
  const name = partnerLabel(partner)
  const parts = name.split(' ')
  if (parts.length >= 2) return (parts[0].charAt(0) + parts[1].charAt(0)).toUpperCase()
  return name.substring(0, 2).toUpperCase()
}

// Spark first — the same preference TicketBuyModal applies (direct P2P, no LN hop)
const partnerAddress = (partner: QuickPartner) => partner.spark_address || partner.ln_address || ''

const selectPartner = (partner: QuickPartner) => {
  const address = partnerAddress(partner)
  if (address) sendInput.value = address
}

// Address → partner, so a recent chip can name the person behind the string
const partnersByAddress = computed(() => {
  const map = new Map<string, QuickPartner>()
  for (const partner of partners.value) {
    if (partner.spark_address) map.set(partner.spark_address.toLowerCase(), partner)
    if (partner.ln_address) map.set(partner.ln_address.toLowerCase(), partner)
  }
  return map
})
const partnerForAddress = (address: string) => partnersByAddress.value.get(address.trim().toLowerCase()) || null

// Amount entered via WalletAmountInput (always sats)
const sendAmountSats = ref(0)

// ===== SEND STATE =====
const sendInputRaw = ref('')
const normalizedSendInput = computed(() => {
  const v = sendInputRaw.value.trim()
  const lower = v.toLowerCase()
  if (lower.startsWith('bitcoin:')) return v.slice(8).split('?')[0]
  if (lower.startsWith('lightning:')) return v.slice(10)
  return v
})
const sendInput = computed({
  get: () => normalizedSendInput.value,
  set: (v: string) => { sendInputRaw.value = v }
})
const sendNeedsAmount = ref(false)
const sendParseInfo = ref('')
const sendError = ref('')
const sendSuccess = ref(false)
const preparingSend = ref(false)
const executingSend = ref(false)
const sendPrepared = ref(false)
const sendPrepareResponse = ref<PrepareSendPaymentResponse | null>(null)
const sendLnurlPrepareResponse = ref<PrepareLnurlPayResponse | null>(null)
const sendIsLnurl = ref(false)
const parsedInput = ref<InputType | null>(null)

const sendFeeDisplay = computed(() => {
  if (sendIsLnurl.value && sendLnurlPrepareResponse.value) {
    return sendLnurlPrepareResponse.value.feeSats.toString()
  }
  if (sendPrepareResponse.value) {
    const method = sendPrepareResponse.value.paymentMethod
    if (method.type === 'bolt11Invoice') return method.lightningFeeSats.toString()
    if (method.type === 'sparkAddress' || method.type === 'sparkInvoice') return method.fee
    if (method.type === 'bitcoinAddress') return method.feeQuote.speedMedium.userFeeSat.toString()
  }
  return '0'
})

const sendTotalDisplay = computed(() => {
  if (sendPrepareResponse.value) {
    return (Number(sendPrepareResponse.value.amount) + parseInt(sendFeeDisplay.value || '0')).toString()
  }
  return '0'
})

const handlePrepareSend = async () => {
  sendError.value = ''
  sendSuccess.value = false
  preparingSend.value = true

  try {
    const input = normalizedSendInput.value
    const parsed = await parseInput(input)
    parsedInput.value = parsed

    if (parsed.type === 'lnurlPay' || parsed.type === 'lightningAddress') {
      sendIsLnurl.value = true
      const payReq = parsed.type === 'lnurlPay' ? parsed as any : (parsed as any).payRequest

      if (sendAmountSats.value <= 0) {
        sendNeedsAmount.value = true
        sendParseInfo.value = t('wallet.lnurlDetected')
        preparingSend.value = false
        return
      }

      const prepResponse = await prepareLnurlPay(
        sendAmountSats.value,
        payReq as LnurlPayRequestDetails
      )
      sendLnurlPrepareResponse.value = prepResponse
      sendPrepareResponse.value = {
        paymentMethod: { type: 'bolt11Invoice' as any, lightningFeeSats: prepResponse.feeSats } as any,
        amount: BigInt(prepResponse.amountSats)
      } as PrepareSendPaymentResponse
      sendPrepared.value = true
    } else {
      sendIsLnurl.value = false

      const needsAmount = (parsed.type === 'bolt11Invoice' && !parsed.amountMsat)
        || parsed.type === 'sparkAddress'
        || parsed.type === 'bitcoinAddress'
      if (needsAmount && sendAmountSats.value <= 0) {
        sendNeedsAmount.value = true
        if (parsed.type === 'bolt11Invoice') {
          sendParseInfo.value = t('wallet.amountlessInvoice')
        }
        preparingSend.value = false
        return
      }

      const amount = sendAmountSats.value > 0 ? BigInt(sendAmountSats.value) : undefined
      const prepResponse = await prepareSend(input, amount)
      sendPrepareResponse.value = prepResponse
      sendPrepared.value = true
    }
  } catch (e: any) {
    sendError.value = mapSendError(e)
  } finally {
    preparingSend.value = false
  }
}

const handleExecuteSend = async () => {
  executingSend.value = true
  sendError.value = ''

  const sourceAmountSats = sendPrepareResponse.value ? Number(sendPrepareResponse.value.amount) : 0

  try {
    if (sendIsLnurl.value && sendLnurlPrepareResponse.value) {
      await executeLnurlPay(sendLnurlPrepareResponse.value)
    } else if (sendPrepareResponse.value) {
      await executeSend(sendPrepareResponse.value)
    }

    // Save to recent contacts
    saveContact(normalizedSendInput.value)
    recentContacts.value = loadContacts()

    // Association donation rides along (records SKIPPED at 0%)
    await donation.executeDonation({
      source: 'WALLET_SEND',
      sourceAmountSats,
    })

    sendSuccess.value = true
    emit('success')

    // Auto-close after showing success
    setTimeout(() => {
      visible.value = false
    }, 1500)
  } catch (e: any) {
    sendError.value = mapSendError(e)
  } finally {
    executingSend.value = false
  }
}

const cancelSend = () => {
  sendPrepared.value = false
  sendPrepareResponse.value = null
  sendLnurlPrepareResponse.value = null
  sendIsLnurl.value = false
  parsedInput.value = null
}

const resetAll = () => {
  cancelSend()
  sendInputRaw.value = ''
  sendAmountSats.value = 0
  sendNeedsAmount.value = false
  sendParseInfo.value = ''
  sendError.value = ''
  sendSuccess.value = false
}

const mapSendError = (e: any): string => {
  const msg = e.message || e.toString()
  if (msg.includes('InsufficientFunds') || msg.includes('insufficient')) {
    return t('wallet.insufficientFunds')
  }
  if (msg.includes('Invalid') || msg.includes('parse')) {
    return t('wallet.invalidInput')
  }
  return msg
}

// Reset on close; partners load with the open (cached for 60s across opens)
watch(visible, (isOpen) => {
  if (isOpen) fetchPartners()
  else resetAll()
})

// ===== QR SCANNER =====
const scannerActive = ref(false)
const scannerError = ref('')
const scannerVideo = ref<HTMLVideoElement | null>(null)
let qrScanner: any = null

const openScanner = async () => {
  scannerError.value = ''
  try {
    // qr-scanner swallows getUserMedia DOMExceptions and rethrows a bare
    // "Camera not found." string, so probe the camera directly to learn the
    // real failure reason (and to trigger the native permission dialog).
    const probe = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })
    probe.getTracks().forEach((track) => track.stop())
  } catch (e: any) {
    if (e?.name === 'NotAllowedError' || e?.name === 'SecurityError') {
      scannerError.value = t('wallet.cameraPermissionDenied')
    } else if (e?.name === 'NotFoundError' || e?.name === 'OverconstrainedError') {
      scannerError.value = t('wallet.noCameraAvailable')
    } else {
      scannerError.value = t('wallet.scannerUnavailable')
    }
    scannerActive.value = true
    return
  }
  try {
    const QrScanner = (await import('qr-scanner')).default
    scannerActive.value = true
    await nextTick()
    if (!scannerVideo.value) return
    qrScanner = new QrScanner(
      scannerVideo.value,
      (result: any) => {
        sendInput.value = result.data?.trim() || ''
        closeScanner()
      },
      {
        preferredCamera: 'environment',
        highlightScanRegion: true,
        highlightCodeOutline: true
      }
    )
    await qrScanner.start()
  } catch {
    scannerError.value = t('wallet.scannerUnavailable')
    if (!scannerActive.value) scannerActive.value = true
  }
}

const closeScanner = () => {
  if (qrScanner) {
    qrScanner.destroy()
    qrScanner = null
  }
  scannerActive.value = false
  scannerError.value = ''
}

onUnmounted(() => {
  closeScanner()
})
</script>
