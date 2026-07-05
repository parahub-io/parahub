<template>
  <div class="bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700 px-4 sm:px-6 py-4">
    <!-- Header -->
    <div class="flex items-center justify-between mb-3">
      <h2 class="text-sm font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
        <Package class="w-4 h-4 text-neutral-400" />
        {{ $t('shipments.hub.operator_panel') }}
        <span v-if="shipments.length" class="px-1.5 py-0.5 bg-primary/10 text-primary-800 dark:text-primary-200 text-xs rounded-full font-medium">
          {{ shipments.length }}
        </span>
      </h2>
      <button
        @click="loadShipments"
        :disabled="loading"
        class="text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300"
        :aria-label="$t('common.refresh')"
      >
        <RefreshCw :class="['w-4 h-4', loading && 'animate-spin']" />
      </button>
    </div>

    <!-- Loading -->
    <div v-if="loading && !shipments.length" class="flex items-center justify-center py-6">
      <Loader2 class="w-5 h-5 animate-spin text-neutral-400" />
    </div>

    <!-- Empty state -->
    <div v-else-if="!shipments.length" class="text-center py-6">
      <PackageOpen class="w-8 h-8 text-neutral-300 dark:text-neutral-600 mx-auto mb-2" />
      <p class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('shipments.hub.no_parcels_at_hub') }}</p>
    </div>

    <!-- Shipment list -->
    <div v-else class="space-y-3">
      <div
        v-for="s in shipments"
        :key="s.id"
        class="border border-neutral-200 dark:border-neutral-700 rounded-lg p-3"
      >
        <!-- Top row: tracking code + status -->
        <div class="flex items-center justify-between gap-2 mb-2">
          <NuxtLink
            :to="localePath(`/shipments/${s.tracking_code.replace('PH-', '')}`)"
            class="font-mono text-xs text-link"
          >
            {{ s.tracking_code }}
          </NuxtLink>
          <span :class="statusClass(s.status)">
            {{ $t(`shipments.status.${s.status}`) }}
          </span>
        </div>

        <!-- Title -->
        <p class="text-sm font-medium text-neutral-900 dark:text-neutral-100 truncate">{{ s.title }}</p>

        <!-- Meta row: size + expires -->
        <div class="flex items-center gap-3 mt-1.5 text-xs text-neutral-500 dark:text-neutral-400">
          <span class="px-1.5 py-0.5 bg-neutral-100 dark:bg-neutral-800 rounded">
            {{ $t(`shipments.size.${s.size_category}`) }}
          </span>
          <span v-if="s.expires_at" class="flex items-center gap-1">
            <Clock class="w-3 h-3" />
            {{ formatDate(s.expires_at) }}
          </span>
        </div>

        <!-- Sender / Receiver -->
        <div class="flex items-center gap-3 mt-1.5 text-xs text-neutral-500 dark:text-neutral-400">
          <span>{{ s.sender.display_name }} → {{ s.receiver.display_name }}</span>
        </div>

        <!-- Action buttons -->
        <div class="flex flex-wrap gap-2 mt-3">
          <!-- Confirm Arrival: only for IN_TRANSIT (but backend also filters, so hub list won't have these often) -->
          <!-- AT_ORIGIN / AT_HUB: Mark Ready -->
          <button
            v-if="s.status === 'AT_ORIGIN' || s.status === 'AT_HUB'"
            @click="handleMarkReady(s)"
            :disabled="actionLoading === s.id"
            class="btn-primary btn-sm text-xs"
          >
            <Loader2 v-if="actionLoading === s.id && actionType === 'ready'" class="w-3 h-3 animate-spin mr-1 inline" />
            {{ $t('shipments.hub.mark_ready') }}
          </button>

          <!-- READY: Pickup code verification -->
          <template v-if="s.status === 'READY'">
            <div class="flex items-center gap-2 w-full">
              <input
                v-model="pickupCodes[s.id]"
                type="text"
                maxlength="6"
                inputmode="numeric"
                pattern="[0-9]*"
                :placeholder="$t('shipments.hub.enter_pickup_code')"
                class="flex-1 text-sm border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-1.5 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 font-mono tracking-wider"
                @keyup.enter="handleVerifyPickup(s)"
              />
              <button
                @click="handleVerifyPickup(s)"
                :disabled="!pickupCodes[s.id]?.trim() || actionLoading === s.id"
                class="btn-primary btn-sm text-xs whitespace-nowrap"
              >
                <Loader2 v-if="actionLoading === s.id && actionType === 'verify'" class="w-3 h-3 animate-spin mr-1 inline" />
                {{ $t('shipments.hub.verify_pickup') }}
              </button>
            </div>
            <p v-if="pickupError === s.id" class="text-xs text-red-500 mt-1">
              {{ $t('shipments.hub.invalid_code') }}
            </p>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Package, RefreshCw, Loader2, Clock, PackageOpen } from 'lucide-vue-next'
import { useShipments, type Shipment } from '~/composables/useShipments'

const props = defineProps<{
  establishmentId: string
}>()

const { t } = useI18n()
const localePath = useLocalePath()
const { fetchHubShipments, markReady, verifyPickup } = useShipments()

const shipments = ref<Shipment[]>([])
const loading = ref(false)
const actionLoading = ref<string | null>(null)
const actionType = ref<'ready' | 'verify' | null>(null)
const pickupCodes = ref<Record<string, string>>({})
const pickupError = ref<string | null>(null)

const loadShipments = async () => {
  loading.value = true
  try {
    const data = await fetchHubShipments(props.establishmentId)
    shipments.value = data.items
  } catch (err: any) {
    console.error('Failed to load hub shipments:', err)
  } finally {
    loading.value = false
  }
}

const handleMarkReady = async (s: Shipment) => {
  actionLoading.value = s.id
  actionType.value = 'ready'
  try {
    await markReady(props.establishmentId, s.id)
    await loadShipments()
  } catch (err: any) {
    console.error('Failed to mark ready:', err)
  } finally {
    actionLoading.value = null
    actionType.value = null
  }
}

const handleVerifyPickup = async (s: Shipment) => {
  const code = pickupCodes.value[s.id]?.trim()
  if (!code) return

  pickupError.value = null
  actionLoading.value = s.id
  actionType.value = 'verify'
  try {
    await verifyPickup(props.establishmentId, s.id, code)
    delete pickupCodes.value[s.id]
    await loadShipments()
  } catch (err: any) {
    if (err?.statusCode === 400 || err?.data?.detail?.includes?.('Invalid')) {
      pickupError.value = s.id
    }
    console.error('Failed to verify pickup:', err)
  } finally {
    actionLoading.value = null
    actionType.value = null
  }
}

const statusClass = (status: string) => {
  const base = 'px-1.5 py-0.5 text-[10px] font-medium rounded-full'
  switch (status) {
    case 'AT_ORIGIN':
    case 'AT_HUB':
      return `${base} bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400`
    case 'READY':
      return `${base} bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400`
    default:
      return `${base} bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400`
  }
}

const formatDate = (iso: string) => {
  try {
    return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  } catch {
    return iso
  }
}

// Load on mount
onMounted(() => {
  loadShipments()
})
</script>
