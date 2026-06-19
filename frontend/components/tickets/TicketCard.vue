<template>
  <div
    class="border rounded-xl overflow-hidden"
    :class="statusBorderClass"
  >
    <!-- Color strip -->
    <div class="h-1" :class="statusBgClass" />

    <div class="p-4 space-y-3">
      <!-- Header -->
      <div class="flex items-center justify-between">
        <div>
          <div class="font-medium text-neutral-900 dark:text-white">{{ ticket.ticket_type_name }}</div>
          <div class="text-xs text-neutral-500 dark:text-neutral-400">
            {{ ticket.category === 'EVENT' ? ticket.event_title : (ticket.route_name || ticket.agency_name) }}
          </div>
        </div>
        <UiBadge :variant="statusVariant" type="soft" size="sm">
          {{ statusLabel }}
        </UiBadge>
      </div>

      <!-- Details -->
      <div class="flex items-center gap-4 text-xs text-neutral-500 dark:text-neutral-400">
        <span v-if="ticket.price_eur != null">
          {{ $t('tickets.price_eur', { eur: formatEur(ticket.price_eur) }) }}
          · {{ $t('tickets.price', { sats: ticket.amount_paid_sats || ticket.price_sats }) }}
        </span>
        <span v-else>{{ $t('tickets.price', { sats: ticket.amount_paid_sats || ticket.price_sats }) }}</span>
        <span>{{ formatDate(ticket.created_at) }}</span>
        <span v-if="inWindow" class="text-emerald-500 font-medium">
          {{ $t('tickets.valid_until_short', { time: formatTime(ticket.valid_until!) }) }}
        </span>
        <span v-if="ticket.pgp_signature" class="text-emerald-500">
          <ShieldCheck class="w-3 h-3 inline" /> {{ $t('tickets.pgp_signed') }}
        </span>
      </div>

      <!-- QR button (active, or activated windowed ticket still in window) -->
      <UiButton
        v-if="tk.status === 'ACTIVE' || inWindow"
        variant="outline"
        size="sm"
        class="w-full"
        @click="$emit('show-qr', ticket)"
      >
        <QrCode class="w-4 h-4 mr-1.5" />
        {{ $t('tickets.show_qr') }}
      </UiButton>

      <!-- Refund: request (unused tickets) -->
      <template v-if="tk.status === 'ACTIVE'">
        <UiButton
          v-if="!refundFormOpen"
          variant="ghost"
          size="sm"
          class="w-full"
          @click="refundFormOpen = true"
        >
          <Undo2 class="w-4 h-4 mr-1.5" />
          {{ $t('tickets.refund_request') }}
        </UiButton>
        <div v-else class="space-y-2">
          <textarea
            v-model="refundReason"
            :placeholder="$t('tickets.refund_reason_placeholder')"
            rows="2"
            class="w-full text-sm rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 p-2 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
          />
          <div class="flex gap-2">
            <UiButton variant="primary" size="sm" class="flex-1" :loading="refundBusy" @click="submitRefundRequest">
              {{ $t('tickets.refund_submit') }}
            </UiButton>
            <UiButton variant="ghost" size="sm" @click="refundFormOpen = false">
              {{ $t('common.cancel') }}
            </UiButton>
          </div>
        </div>
      </template>

      <!-- Refund: pending -->
      <div v-else-if="tk.status === 'REFUND_REQUESTED'" class="space-y-2">
        <p v-if="tk.refund_reason" class="text-xs text-neutral-500 dark:text-neutral-400">
          {{ tk.refund_reason }}
        </p>
        <UiButton variant="ghost" size="sm" class="w-full" :loading="refundBusy" @click="cancelRefundRequest">
          {{ $t('tickets.refund_withdraw') }}
        </UiButton>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { QrCode, ShieldCheck, Undo2 } from 'lucide-vue-next'

interface TicketData {
  id: string
  status: string
  qr_token: string
  pgp_signature: string
  ticket_type_name: string
  category: string
  price_sats: number
  price_eur?: number | null
  amount_paid_sats: number
  valid_until?: string | null
  refund_reason?: string
  event_title?: string
  route_name?: string
  agency_name?: string | null
  created_at: string
}

const props = defineProps<{ ticket: TicketData }>()
const emit = defineEmits<{
  (e: 'show-qr', t: TicketData): void
  (e: 'updated', t: TicketData): void
}>()

const { t } = useI18n()
const authStore = useAuthStore()

// Optimistic local state after refund API calls (props stay immutable)
const localOverride = ref<Partial<TicketData>>({})
const tk = computed(() => ({ ...props.ticket, ...localOverride.value }))

const refundFormOpen = ref(false)
const refundReason = ref('')
const refundBusy = ref(false)

async function refundCall(path: string, body?: Record<string, any>) {
  refundBusy.value = true
  try {
    await authStore.ensureToken()
    const updated = await $fetch<TicketData>(`/api/v1/tickets/${props.ticket.id}/${path}/`, {
      method: 'POST',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
      body,
    })
    localOverride.value = { status: updated.status, refund_reason: updated.refund_reason }
    emit('updated', updated)
  } finally {
    refundBusy.value = false
  }
}

async function submitRefundRequest() {
  await refundCall('refund-request', { reason: refundReason.value })
  refundFormOpen.value = false
}

async function cancelRefundRequest() {
  await refundCall('refund-cancel')
}

// VALIDATED ticket whose usage window is still open
const inWindow = computed(() =>
  tk.value.status === 'VALIDATED'
  && !!tk.value.valid_until
  && new Date(tk.value.valid_until) > new Date()
)

// Expired-window VALIDATED tickets read as "Used"
const effectiveStatus = computed(() =>
  tk.value.status === 'VALIDATED' && !inWindow.value ? 'USED' : tk.value.status
)

const statusLabel = computed(() => t(`tickets.status_${effectiveStatus.value.toLowerCase()}`))

const statusVariant = computed(() => {
  const map: Record<string, string> = {
    ACTIVE: 'success',
    VALIDATED: 'success',
    USED: 'primary',
    PENDING_PAYMENT: 'warning',
    REFUND_REQUESTED: 'warning',
    CANCELLED: 'error',
    EXPIRED: 'error',
  }
  return map[effectiveStatus.value] || 'primary'
})

const statusBorderClass = computed(() => {
  const map: Record<string, string> = {
    ACTIVE: 'border-emerald-200 dark:border-emerald-800/50',
    VALIDATED: 'border-emerald-200 dark:border-emerald-800/50',
    USED: 'border-neutral-200 dark:border-neutral-700',
    PENDING_PAYMENT: 'border-amber-200 dark:border-amber-800/50',
    REFUND_REQUESTED: 'border-amber-200 dark:border-amber-800/50',
    CANCELLED: 'border-red-200 dark:border-red-800/50',
    EXPIRED: 'border-red-200 dark:border-red-800/50',
  }
  return map[effectiveStatus.value] || 'border-neutral-200 dark:border-neutral-700'
})

const statusBgClass = computed(() => {
  const map: Record<string, string> = {
    ACTIVE: 'bg-emerald-500',
    VALIDATED: 'bg-emerald-500',
    USED: 'bg-neutral-400',
    PENDING_PAYMENT: 'bg-amber-500',
    REFUND_REQUESTED: 'bg-amber-500',
    CANCELLED: 'bg-red-500',
    EXPIRED: 'bg-red-500',
  }
  return map[effectiveStatus.value] || 'bg-neutral-400'
})

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function formatEur(v: number) {
  return v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}
</script>
