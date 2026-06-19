<template>
  <div class="py-6">
    <div class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
      <PageHeader
        :title="$t('shipments.title')"
        :subtitle="$t('shipments.subtitle')"
        :create-label="$t('shipments.create')"
        @create="showCreateModal = true"
      />

      <!-- Tabs -->
      <UiTabs v-model="activeTab" :tabs="tabs" class="mb-6">

      <!-- Loading -->
      <div v-if="loading" class="text-center py-12" role="status" aria-live="polite">
        <div class="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-primary" aria-hidden="true"></div>
        <span class="sr-only">{{ $t('common.loading') }}</span>
      </div>

      <!-- Empty state -->
      <div v-else-if="filteredShipments.length === 0" class="text-center py-12">
        <img src="/images/para/shrug.png" alt="Para" class="mx-auto h-32 w-auto mb-4" />
        <h3 class="text-lg font-medium text-neutral-900 dark:text-neutral-100 mb-2">
          {{ $t('shipments.no_shipments') }}
        </h3>
        <p class="text-neutral-500 dark:text-neutral-400 mb-6">
          {{ $t('shipments.no_shipments_subtitle') }}
        </p>
        <UiButton variant="primary" size="sm" @click="showCreateModal = true">
          {{ $t('shipments.create') }}
        </UiButton>
      </div>

      <!-- Shipments list -->
      <div v-else class="space-y-4">
        <NuxtLink
          v-for="s in filteredShipments"
          :key="s.id"
          :to="localePath(`/shipments/${s.tracking_code.replace('PH-', '')}`)"
          class="block bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-5 hover:border-primary/50 transition-colors"
        >
          <div>
            <div class="flex flex-wrap items-center gap-2 mb-2">
              <span class="font-mono text-sm font-bold text-primary">{{ s.tracking_code }}</span>
              <span :class="statusClass(s.status)" class="px-2 py-0.5 text-xs font-medium rounded-full">
                {{ $t(`shipments.status.${s.status}`) }}
              </span>
              <span class="px-2 py-0.5 text-xs rounded bg-neutral-100 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-300">
                {{ $t(`shipments.size.${s.size_category}`) }}
              </span>
            </div>
            <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 truncate">{{ s.title }}</h3>
            <div class="mt-2 text-sm text-neutral-500 dark:text-neutral-400 flex flex-wrap items-center gap-2">
              <MapPin class="w-3.5 h-3.5 flex-shrink-0" />
              <span class="truncate max-w-[120px] sm:max-w-none">{{ s.origin_hub?.name }}</span>
              <ArrowRight class="w-3.5 h-3.5 flex-shrink-0" />
              <span class="truncate max-w-[120px] sm:max-w-none">{{ s.destination_hub?.name }}</span>
            </div>
            <div class="mt-1 text-xs text-neutral-400 dark:text-neutral-500">
              {{ s.role === 'carrier' ? $t('shipments.carrying') : s.role === 'sender' ? $t('shipments.sent') : $t('shipments.received') }}
              &middot;
              {{ new Date(s.created_at).toLocaleDateString($i18n.locale) }}
            </div>

            <!-- Pickup code for receiver when READY -->
            <div v-if="s.role === 'receiver' && s.status === 'READY' && s.pickup_code" class="mt-3 p-2 bg-success/10 rounded-lg text-center">
              <div class="text-xs text-success">{{ $t('shipments.pickup_code') }}</div>
              <div class="font-mono text-2xl font-bold text-success">{{ s.pickup_code }}</div>
            </div>

            <!-- Offer to carry (available tab) -->
            <div v-if="activeTab === 'available'" class="mt-3" @click.prevent.stop>
              <div v-if="offeringId === s.id" class="flex items-center gap-2">
                <input v-model.number="offerFee" type="number" min="0" :placeholder="$t('shipments.carrier.fee')"
                  class="w-32 px-3 py-1.5 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 text-sm" />
                <UiButton variant="primary" size="sm" @click="handleOffer(s.id)">
                  {{ $t('shipments.form.submit') }}
                </UiButton>
                <UiButton variant="ghost" size="sm" @click="offeringId = null">
                  {{ $t('common.cancel') }}
                </UiButton>
              </div>
              <UiButton v-else variant="secondary" size="sm" :icon="Truck" @click="offeringId = s.id; offerFee = 0">
                {{ $t('shipments.carrier.offer') }}
              </UiButton>
            </div>
          </div>
        </NuxtLink>
      </div>
      </UiTabs>

      <!-- Create modal -->
      <Teleport to="body">
        <div v-if="showCreateModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50" @click.self="showCreateModal = false">
          <div class="bg-white dark:bg-neutral-800 rounded-xl shadow-xl max-w-lg w-full mx-4 p-6 max-h-[90vh] overflow-y-auto">
            <h2 class="text-xl font-bold text-neutral-900 dark:text-neutral-100 mb-4">{{ $t('shipments.create') }}</h2>

            <div class="space-y-4">
              <!-- Title -->
              <div>
                <label class="block text-sm font-medium mb-1 text-neutral-700 dark:text-neutral-300">{{ $t('shipments.form.title') }}</label>
                <input v-model="form.title" type="text" :placeholder="$t('shipments.form.title_placeholder')"
                  class="w-full px-3 py-2 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100" />
              </div>

              <!-- Size -->
              <div>
                <label class="block text-sm font-medium mb-1 text-neutral-700 dark:text-neutral-300">{{ $t('shipments.form.size') }}</label>
                <div class="flex gap-2">
                  <button v-for="size in ['S', 'M', 'L', 'XL']" :key="size"
                    @click="form.size_category = size"
                    :class="[
                      'px-4 py-2 rounded-lg border text-sm font-medium transition-colors',
                      form.size_category === size
                        ? 'border-primary bg-primary/10 text-primary'
                        : 'border-neutral-300 dark:border-neutral-600 text-neutral-600 dark:text-neutral-400'
                    ]">
                    {{ size }}
                  </button>
                </div>
              </div>

              <!-- Receiver -->
              <div>
                <label class="block text-sm font-medium mb-1 text-neutral-700 dark:text-neutral-300">{{ $t('shipments.form.receiver') }}</label>
                <input v-model="receiverSearch" type="text" :placeholder="$t('shipments.form.receiver_placeholder')"
                  class="w-full px-3 py-2 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100"
                  @input="searchReceivers" />
                <div v-if="receiverResults.length" class="mt-1 border border-neutral-200 dark:border-neutral-600 rounded-lg divide-y divide-neutral-200 dark:divide-neutral-600">
                  <button v-for="p in receiverResults" :key="p.id" @click="selectReceiver(p)"
                    class="w-full px-3 py-2 text-left text-sm hover:bg-neutral-50 dark:hover:bg-neutral-700">
                    {{ p.display_name }} <span v-if="p.hna" class="text-neutral-400">{{ p.hna }}</span>
                  </button>
                </div>
                <div v-if="selectedReceiver" class="mt-1 text-sm text-success">
                  {{ selectedReceiver.display_name }}
                </div>
              </div>

              <!-- Origin Hub -->
              <div>
                <label class="block text-sm font-medium mb-1 text-neutral-700 dark:text-neutral-300">{{ $t('shipments.form.origin_hub') }}</label>
                <select v-model="form.origin_hub_id"
                  class="w-full px-3 py-2 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100">
                  <option value="">--</option>
                  <option v-for="h in hubs" :key="h.id" :value="h.id">
                    {{ h.name }} {{ h.distance_m != null ? `(${(h.distance_m / 1000).toFixed(1)} km)` : '' }}
                  </option>
                </select>
              </div>

              <!-- Destination Hub -->
              <div>
                <label class="block text-sm font-medium mb-1 text-neutral-700 dark:text-neutral-300">{{ $t('shipments.form.destination_hub') }}</label>
                <select v-model="form.destination_hub_id"
                  class="w-full px-3 py-2 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100">
                  <option value="">--</option>
                  <option v-for="h in hubs" :key="h.id" :value="h.id">
                    {{ h.name }} {{ h.distance_m != null ? `(${(h.distance_m / 1000).toFixed(1)} km)` : '' }}
                  </option>
                </select>
              </div>

              <!-- Delivery Fee -->
              <div>
                <label class="block text-sm font-medium mb-1 text-neutral-700 dark:text-neutral-300">{{ $t('shipments.form.delivery_fee') }}</label>
                <input v-model.number="form.delivery_fee" type="number" min="0"
                  class="w-full px-3 py-2 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100" />
              </div>

              <!-- Error -->
              <div v-if="createError" class="text-sm text-error">{{ createError }}</div>

              <!-- Actions -->
              <div class="flex flex-col-reverse sm:flex-row gap-3 sm:justify-end pt-2">
                <UiButton variant="ghost" size="sm" @click="showCreateModal = false">{{ $t('common.cancel') }}</UiButton>
                <UiButton variant="primary" size="sm" :loading="creating" @click="handleCreate">
                  {{ $t('shipments.form.submit') }}
                </UiButton>
              </div>
            </div>
          </div>
        </div>
      </Teleport>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Plus, PackageCheck, MapPin, ArrowRight, Truck } from 'lucide-vue-next'
import { useShipments, type Shipment } from '~/composables/useShipments'
import { useAuthStore } from '~/stores/auth'
import { useToastStore } from '~/stores/toast'

definePageMeta({ middleware: 'auth' })

const { t } = useI18n()
const localePath = useLocalePath()
const authStore = useAuthStore()
const toast = useToastStore()
const { fetchMyShipments, fetchAvailableShipments, fetchHubs, createShipment, createCarrierOffer } = useShipments()

const loading = ref(true)
const shipments = ref<Shipment[]>([])
const availableShipments = ref<Shipment[]>([])
const hubs = ref<any[]>([])
const activeTab = useTabSync(['all', 'sent', 'received', 'carrying', 'available'])
const offeringId = ref<string | null>(null)
const offerFee = ref(0)

const tabs = computed(() => [
  { id: 'all', label: t('shipments.my_shipments') },
  { id: 'sent', label: t('shipments.sent') },
  { id: 'received', label: t('shipments.received') },
  { id: 'carrying', label: t('shipments.carrying') },
  { id: 'available', label: t('shipments.carrier.available') },
])

const filteredShipments = computed(() => {
  if (activeTab.value === 'sent') return shipments.value.filter(s => s.role === 'sender')
  if (activeTab.value === 'received') return shipments.value.filter(s => s.role === 'receiver')
  if (activeTab.value === 'carrying') return shipments.value.filter(s => s.role === 'carrier')
  if (activeTab.value === 'available') return availableShipments.value
  return shipments.value
})

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

// Create modal
const showCreateModal = ref(false)
const creating = ref(false)
const createError = ref('')
const form = ref({
  title: '',
  size_category: 'M',
  origin_hub_id: '',
  destination_hub_id: '',
  delivery_fee: 0,
})
const receiverSearch = ref('')
const receiverResults = ref<any[]>([])
const selectedReceiver = ref<any>(null)

let searchTimeout: ReturnType<typeof setTimeout> | null = null
function searchReceivers() {
  selectedReceiver.value = null
  if (searchTimeout) clearTimeout(searchTimeout)
  if (receiverSearch.value.length < 2) { receiverResults.value = []; return }
  searchTimeout = setTimeout(async () => {
    try {
      await authStore.ensureToken()
      const res = await $fetch(`/api/v1/profiles/search/?q=${encodeURIComponent(receiverSearch.value)}&limit=5`, {
        credentials: 'include',
        headers: { Authorization: `Bearer ${authStore.token}` },
      })
      receiverResults.value = (res as any).items || res || []
    } catch { receiverResults.value = [] }
  }, 300)
}

function selectReceiver(p: any) {
  selectedReceiver.value = p
  receiverSearch.value = p.display_name
  receiverResults.value = []
}

async function handleCreate() {
  if (!form.value.title || !selectedReceiver.value || !form.value.origin_hub_id || !form.value.destination_hub_id) {
    createError.value = t('shipments.form.required_fields')
    return
  }
  creating.value = true
  createError.value = ''
  try {
    await createShipment({
      title: form.value.title,
      size_category: form.value.size_category,
      receiver_id: selectedReceiver.value.id,
      origin_hub_id: form.value.origin_hub_id,
      destination_hub_id: form.value.destination_hub_id,
      delivery_fee: form.value.delivery_fee,
    })
    showCreateModal.value = false
    toast.success(t('shipments.created_success'))
    await loadData()
  } catch (e: any) {
    createError.value = e.data?.detail || e.message || 'Error'
  } finally {
    creating.value = false
  }
}

async function handleOffer(shipmentId: string) {
  try {
    await createCarrierOffer(shipmentId, offerFee.value)
    toast.success(t('shipments.carrier.offer_sent'))
    offeringId.value = null
    await loadData()
  } catch (e: any) {
    toast.error(e.data?.detail || 'Error')
  }
}

async function loadData() {
  loading.value = true
  try {
    await authStore.ensureToken()
    const [shipmentsRes, hubsRes, availableRes] = await Promise.all([
      fetchMyShipments(),
      fetchHubs(),
      fetchAvailableShipments().catch(() => ({ items: [], count: 0 })),
    ])
    shipments.value = shipmentsRes.items
    hubs.value = hubsRes.items
    availableShipments.value = availableRes.items
  } catch (e) {
    console.error('Failed to load shipments:', e)
  } finally {
    loading.value = false
  }
}

onMounted(loadData)
</script>
