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
            {{ ticket.category === 'EVENT' ? ticket.event_title : ticket.route_name }}
          </div>
        </div>
        <UiBadge :variant="statusVariant" type="soft" size="sm">
          {{ $t(`tickets.status_${ticket.status.toLowerCase()}`) }}
        </UiBadge>
      </div>

      <!-- Details -->
      <div class="flex items-center gap-4 text-xs text-neutral-500 dark:text-neutral-400">
        <span>{{ $t('tickets.price', { sats: ticket.amount_paid_sats || ticket.price_sats }) }}</span>
        <span>{{ formatDate(ticket.created_at) }}</span>
        <span v-if="ticket.pgp_signature" class="text-emerald-500">
          <ShieldCheck class="w-3 h-3 inline" /> {{ $t('tickets.pgp_signed') }}
        </span>
      </div>

      <!-- QR button -->
      <UiButton
        v-if="ticket.status === 'ACTIVE'"
        variant="outline"
        size="sm"
        class="w-full"
        @click="$emit('show-qr', ticket)"
      >
        <QrCode class="w-4 h-4 mr-1.5" />
        {{ $t('tickets.show_qr') }}
      </UiButton>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { QrCode, ShieldCheck } from 'lucide-vue-next'

interface TicketData {
  id: string
  status: string
  qr_token: string
  pgp_signature: string
  ticket_type_name: string
  category: string
  price_sats: number
  amount_paid_sats: number
  event_title?: string
  route_name?: string
  created_at: string
}

const props = defineProps<{ ticket: TicketData }>()
defineEmits<{ (e: 'show-qr', t: TicketData): void }>()

const statusVariant = computed(() => {
  const map: Record<string, string> = {
    ACTIVE: 'success',
    USED: 'primary',
    PENDING_PAYMENT: 'warning',
    CANCELLED: 'error',
    EXPIRED: 'error',
  }
  return map[props.ticket.status] || 'primary'
})

const statusBorderClass = computed(() => {
  const map: Record<string, string> = {
    ACTIVE: 'border-emerald-200 dark:border-emerald-800/50',
    USED: 'border-neutral-200 dark:border-neutral-700',
    PENDING_PAYMENT: 'border-amber-200 dark:border-amber-800/50',
    CANCELLED: 'border-red-200 dark:border-red-800/50',
    EXPIRED: 'border-red-200 dark:border-red-800/50',
  }
  return map[props.ticket.status] || 'border-neutral-200 dark:border-neutral-700'
})

const statusBgClass = computed(() => {
  const map: Record<string, string> = {
    ACTIVE: 'bg-emerald-500',
    USED: 'bg-neutral-400',
    PENDING_PAYMENT: 'bg-amber-500',
    CANCELLED: 'bg-red-500',
    EXPIRED: 'bg-red-500',
  }
  return map[props.ticket.status] || 'bg-neutral-400'
})

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}
</script>
