<template>
  <div class="py-6">
    <div class="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
      <!-- Loading -->
      <div v-if="loading" class="text-center py-12">
        <div class="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>

      <div v-else-if="shipment">
        <!-- Header -->
        <div class="mb-6">
          <div class="flex flex-wrap items-center gap-2 mb-2">
            <NuxtLink :to="localePath('/shipments')" class="text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 min-w-[44px] min-h-[44px] flex items-center justify-center -ml-2">
              <ArrowLeft class="w-5 h-5" />
            </NuxtLink>
            <span class="font-mono text-lg font-bold text-primary">{{ shipment.tracking_code }}</span>
            <span :class="statusClass(shipment.status)" class="px-2 py-0.5 text-xs font-medium rounded-full">
              {{ $t(`shipments.status.${shipment.status}`) }}
            </span>
          </div>
          <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100">{{ shipment.title }}</h1>
        </div>

        <!-- QR Code -->
        <div class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-5 mb-6 flex flex-col items-center">
          <canvas ref="qrCanvas" class="mb-2"></canvas>
          <div class="text-xs text-neutral-500 dark:text-neutral-400">{{ $t('shipments.qr_scan_hint') }}</div>
        </div>

        <!-- Info card -->
        <div class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-5 mb-6">
          <div class="grid grid-cols-2 gap-4 text-sm">
            <div class="min-w-0">
              <span class="text-neutral-500 dark:text-neutral-400">{{ $t('shipments.sent') }}</span>
              <div class="font-medium text-neutral-900 dark:text-neutral-100 truncate">{{ shipment.sender.display_name }}</div>
            </div>
            <div class="min-w-0">
              <span class="text-neutral-500 dark:text-neutral-400">{{ $t('shipments.received') }}</span>
              <div class="font-medium text-neutral-900 dark:text-neutral-100 truncate">{{ shipment.receiver.display_name }}</div>
            </div>
            <div class="min-w-0">
              <span class="text-neutral-500 dark:text-neutral-400">{{ $t('shipments.form.origin_hub') }}</span>
              <div class="font-medium text-neutral-900 dark:text-neutral-100 truncate">{{ shipment.origin_hub?.name }}</div>
            </div>
            <div class="min-w-0">
              <span class="text-neutral-500 dark:text-neutral-400">{{ $t('shipments.form.destination_hub') }}</span>
              <div class="font-medium text-neutral-900 dark:text-neutral-100 truncate">{{ shipment.destination_hub?.name }}</div>
            </div>
            <div>
              <span class="text-neutral-500 dark:text-neutral-400">{{ $t('shipments.form.size') }}</span>
              <div class="font-medium">{{ $t(`shipments.size.${shipment.size_category}`) }}</div>
            </div>
            <div v-if="shipment.delivery_fee">
              <span class="text-neutral-500 dark:text-neutral-400">{{ $t('shipments.delivery_fee') }}</span>
              <div class="font-medium">{{ shipment.delivery_fee }} sats</div>
            </div>
            <div v-if="shipment.expires_at">
              <span class="text-neutral-500 dark:text-neutral-400">{{ $t('shipments.expires_at') }}</span>
              <div class="font-medium">{{ new Date(shipment.expires_at).toLocaleDateString($i18n.locale) }}</div>
            </div>
          </div>

          <!-- Pickup code (receiver only) -->
          <div v-if="shipment.pickup_code && isReceiver" class="mt-4 p-4 bg-success/10 rounded-lg border border-success/30">
            <div class="text-xs text-success mb-1">{{ $t('shipments.pickup_code') }}</div>
            <div class="font-mono text-3xl font-bold text-success text-center">{{ shipment.pickup_code }}</div>
            <div class="text-xs text-success/70 mt-1 text-center">{{ $t('shipments.pickup_code_hint') }}</div>
          </div>
        </div>

        <!-- Actions -->
        <div v-if="showActions" class="mb-6 flex flex-col sm:flex-row gap-3">
          <UiButton v-if="shipment.status === 'CREATED' && isSender"
            variant="primary" size="sm" :disabled="acting"
            @click="handleDeposit">
            {{ $t('shipments.actions.deposit') }}
          </UiButton>
          <UiButton v-if="shipment.status === 'CREATED' && isSender"
            :variant="pendingCancel ? 'error' : 'ghost'" size="sm" :disabled="acting"
            :class="!pendingCancel ? 'text-error' : ''"
            @click="handleCancel">
            {{ pendingCancel ? $t('common.confirm') + '?' : $t('shipments.actions.cancel') }}
          </UiButton>
        </div>

        <!-- Carrier offers -->
        <div v-if="shipment.carrier_offers?.length" class="mb-6">
          <h2 class="text-lg font-bold text-neutral-900 dark:text-neutral-100 mb-3">
            {{ $t('shipments.carrier.offers') }}
          </h2>
          <div class="space-y-3">
            <div v-for="offer in shipment.carrier_offers" :key="offer.id"
              class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4">
              <div class="flex flex-wrap items-center gap-2">
                <span class="font-medium text-neutral-900 dark:text-neutral-100">{{ offer.carrier.display_name }}</span>
                <span v-if="offer.fee_sats" class="text-sm text-neutral-500">{{ offer.fee_sats }} sats</span>
                <span :class="offerStatusClass(offer.status)" class="px-2 py-0.5 text-xs rounded-full">{{ $t(`shipments.carrier.status_${offer.status.toLowerCase()}`, offer.status) }}</span>
              </div>
              <UiButton v-if="offer.status === 'OFFERED' && (isSender || isReceiver)"
                variant="primary" size="sm" class="mt-2 w-full sm:w-auto"
                :disabled="acting"
                @click="handleAcceptOffer(offer.id)">
                {{ $t('shipments.carrier.accept') }}
              </UiButton>
            </div>
          </div>
        </div>

        <!-- Timeline -->
        <div v-if="shipment.events?.length">
          <h2 class="text-lg font-bold text-neutral-900 dark:text-neutral-100 mb-3">{{ $t('shipments.timeline_title') }}</h2>
          <div class="relative pl-6 border-l-2 border-neutral-200 dark:border-neutral-700 space-y-4">
            <div v-for="event in shipment.events" :key="event.id" class="relative">
              <div class="absolute -left-[25px] w-3 h-3 rounded-full" :class="eventDotClass(event.event_type)"></div>
              <div class="text-sm">
                <span class="font-medium text-neutral-900 dark:text-neutral-100">
                  {{ $t(`shipments.timeline.${event.event_type.toLowerCase()}`, event.event_type) }}
                </span>
                <span v-if="event.hub" class="text-neutral-500 dark:text-neutral-400"> @ {{ event.hub.name }}</span>
                <span class="text-neutral-400 dark:text-neutral-500 ml-2 text-xs">
                  {{ new Date(event.created_at).toLocaleString($i18n.locale) }}
                </span>
              </div>
              <div v-if="event.note" class="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">{{ event.note }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Not found -->
      <div v-else class="text-center py-12">
        <p class="text-neutral-500">{{ $t('shipments.not_found') }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import { ArrowLeft } from 'lucide-vue-next'
import QRCode from 'qrcode'
import { useShipments, type Shipment } from '~/composables/useShipments'
import { useAuthStore } from '~/stores/auth'
import { useToastStore } from '~/stores/toast'

definePageMeta({ middleware: 'auth' })

const route = useRoute()
const localePath = useLocalePath()
const { t } = useI18n()
const authStore = useAuthStore()
const toast = useToastStore()
const { fetchShipment, depositShipment, cancelShipment, acceptCarrierOffer } = useShipments()

const loading = ref(true)
const acting = ref(false)
const shipment = ref<Shipment | null>(null)
const pendingCancel = ref(false)
let pendingCancelTimer: ReturnType<typeof setTimeout> | null = null
const qrCanvas = ref<HTMLCanvasElement | null>(null)

const isSender = computed(() => shipment.value?.sender?.id === authStore.activeProfile?.id)
const isReceiver = computed(() => shipment.value?.receiver?.id === authStore.activeProfile?.id)
const showActions = computed(() => shipment.value && (isSender.value || isReceiver.value))

function statusClass(status: string) {
  const map: Record<string, string> = {
    CREATED: 'bg-neutral-100 text-neutral-700 dark:bg-neutral-700 dark:text-neutral-300',
    AT_ORIGIN: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
    IN_TRANSIT: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
    AT_HUB: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
    READY: 'bg-success/10 text-success dark:bg-success/20',
    DELIVERED: 'bg-success/10 text-success dark:bg-success/20',
    EXPIRED: 'bg-error/10 text-error dark:bg-error/20',
    CANCELLED: 'bg-neutral-100 text-neutral-500 dark:bg-neutral-700 dark:text-neutral-400',
  }
  return map[status] || ''
}

function offerStatusClass(status: string) {
  const map: Record<string, string> = {
    OFFERED: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
    ACCEPTED: 'bg-success/10 text-success',
    COMPLETED: 'bg-success/10 text-success',
    CANCELLED: 'bg-neutral-100 text-neutral-500',
  }
  return map[status] || ''
}

function eventDotClass(type: string) {
  const map: Record<string, string> = {
    CREATED: 'bg-neutral-400',
    DEPOSITED: 'bg-blue-500',
    CARRIER_PICKUP: 'bg-amber-500',
    ARRIVED: 'bg-blue-500',
    READY: 'bg-success',
    DELIVERED: 'bg-success',
    EXPIRED: 'bg-error',
    CANCELLED: 'bg-neutral-400',
    NOTE: 'bg-neutral-400',
  }
  return map[type] || 'bg-neutral-400'
}

async function handleDeposit() {
  if (!shipment.value) return
  acting.value = true
  try {
    await depositShipment(shipment.value.id)
    toast.success(t('shipments.timeline.deposited'))
    await loadShipment()
  } catch (e: any) {
    toast.error(e.data?.detail || 'Error')
  } finally { acting.value = false }
}

async function handleCancel() {
  if (!shipment.value) return
  if (!pendingCancel.value) {
    pendingCancel.value = true
    if (pendingCancelTimer) clearTimeout(pendingCancelTimer)
    pendingCancelTimer = setTimeout(() => { pendingCancel.value = false }, 3000)
    return
  }
  pendingCancel.value = false
  if (pendingCancelTimer) clearTimeout(pendingCancelTimer)
  acting.value = true
  try {
    await cancelShipment(shipment.value.id)
    toast.success(t('shipments.timeline.cancelled'))
    await loadShipment()
  } catch (e: any) {
    toast.error(e.data?.detail || 'Error')
  } finally { acting.value = false }
}

async function handleAcceptOffer(offerId: string) {
  acting.value = true
  try {
    await acceptCarrierOffer(offerId)
    toast.success(t('shipments.carrier.accepted'))
    await loadShipment()
  } catch (e: any) {
    toast.error(e.data?.detail || 'Error')
  } finally { acting.value = false }
}

async function loadShipment() {
  loading.value = true
  try {
    await authStore.ensureToken()
    const code = route.params.code as string
    shipment.value = await fetchShipment(code)
    await nextTick()
    generateQR()
  } catch { shipment.value = null }
  finally { loading.value = false }
}

function generateQR() {
  if (!qrCanvas.value || !shipment.value) return
  QRCode.toCanvas(qrCanvas.value, shipment.value.tracking_code, {
    width: 180,
    margin: 1,
    color: { dark: '#000000', light: '#ffffff' },
  })
}

onMounted(loadShipment)
</script>
