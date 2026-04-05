<template>
  <Teleport to="body">
    <Transition name="fade">
      <div
        v-if="ticket"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4"
        @click.self="$emit('close')"
      >
        <div class="bg-white dark:bg-neutral-900 rounded-2xl max-w-sm w-full overflow-hidden">
          <!-- QR code area — max brightness white bg -->
          <div class="bg-white p-8 flex flex-col items-center">
            <canvas ref="qrCanvas" class="w-56 h-56" role="img" :aria-label="$t('tickets.qr_aria_label', { code: ticket?.qr_token })" />
            <span class="sr-only">{{ $t('tickets.qr_token_text', { code: ticket?.qr_token }) }}</span>
          </div>

          <!-- Info -->
          <div class="p-4 space-y-2 border-t border-neutral-100 dark:border-neutral-800">
            <div class="font-semibold text-neutral-900 dark:text-white text-center">
              {{ ticket.ticket_type_name }}
            </div>
            <div class="text-sm text-neutral-500 dark:text-neutral-400 text-center">
              {{ ticket.category === 'EVENT' ? ticket.event_title : ticket.route_name }}
            </div>
            <div class="flex items-center justify-center gap-2 text-xs text-neutral-400">
              <UiBadge variant="success" type="soft" size="sm">{{ $t('tickets.status_active') }}</UiBadge>
              <span>{{ $t('tickets.price', { sats: ticket.amount_paid_sats || ticket.price_sats }) }}</span>
            </div>
          </div>

          <!-- Close -->
          <div class="p-3 border-t border-neutral-100 dark:border-neutral-800">
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
import { ref, watch, nextTick } from 'vue'
import QRCode from 'qrcode'

interface TicketData {
  id: string
  qr_token: string
  ticket_type_name: string
  category: string
  price_sats: number
  amount_paid_sats: number
  event_title?: string
  route_name?: string
}

const props = defineProps<{ ticket: TicketData | null }>()
defineEmits<{ (e: 'close'): void }>()

const qrCanvas = ref<HTMLCanvasElement | null>(null)

watch(() => props.ticket, async (t) => {
  if (!t) return
  await nextTick()
  if (qrCanvas.value) {
    QRCode.toCanvas(qrCanvas.value, t.qr_token, {
      width: 224,
      margin: 2,
      color: { dark: '#000000', light: '#ffffff' },
      errorCorrectionLevel: 'M',
    })
  }
}, { immediate: true })
</script>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity 0.2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
