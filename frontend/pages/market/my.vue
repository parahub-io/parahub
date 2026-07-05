<template>
  <div class="py-6">
    <div class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
      <!-- Header -->
      <div class="mb-6">
        <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div>
            <h1 class="text-3xl font-bold text-neutral-900 dark:text-neutral-100">{{ $t('market.my_items.title') }}</h1>
            <p class="text-neutral-600 dark:text-neutral-400 mt-1">{{ $t('market.my_items.subtitle') }}</p>
          </div>

          <UiButton v-if="mode === 'listings'" size="sm" :icon="Plus" :to="localePath('/market/create')">
            {{ $t('market.create_listing') }}
          </UiButton>
        </div>

        <!-- Primary tabs: listings · booking requests (owner) · my bookings (renter) -->
        <div class="mt-4">
          <UiTabs
            :model-value="mode"
            :tabs="modeTabs"
            @update:model-value="mode = $event"
          />
        </div>
      </div>

      <!-- ===== Listings (own marketplace items) ===== -->
      <template v-if="mode === 'listings'">
      <!-- Status filter -->
      <div class="mb-4">
        <UiTabs
          :model-value="filterStatus"
          :tabs="statusTabs"
          variant="pills"
          @update:model-value="filterStatus = $event; fetchMyItems()"
        />
      </div>

      <!-- Loading state -->
      <div v-if="loading" class="py-12 text-center" role="status" aria-live="polite">
        <div class="h-12 w-12 mx-auto border-4 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100 rounded-full animate-spin" aria-hidden="true"></div>
        <span class="sr-only">{{ $t('common.loading') }}</span>
      </div>

      <!-- Items grid -->
      <div v-else-if="items.length > 0" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <div
          v-for="item in items"
          :key="item.id"
          class="card overflow-hidden relative flex flex-col"
        >
          <!-- Status badge -->
          <div class="absolute top-2 right-2 z-10">
            <UiBadge :variant="item.is_active ? 'success' : 'neutral'" type="solid" size="sm">
              {{ $t(item.is_active ? 'market.my_items.status_active' : 'market.my_items.status_hidden') }}
            </UiBadge>
          </div>

          <!-- Item image (links to the public listing page) -->
          <NuxtLink :to="localePath(`/market/${item.slug || item.id}`)" class="block">
            <div v-if="item.images && item.images.length > 0" class="w-full aspect-video bg-neutral-200 dark:bg-neutral-700">
              <img :src="item.images[0].url" :alt="item.title" class="w-full h-full object-cover">
            </div>
            <div v-else class="w-full aspect-video bg-neutral-200 dark:bg-neutral-700 flex items-center justify-center">
              <Package class="w-12 h-12 text-neutral-400" />
            </div>
          </NuxtLink>

          <!-- Item content -->
          <div class="p-4 flex flex-col flex-1">
            <!-- Type badge -->
            <div class="mb-2">
              <MarketListingType :item-type="item.item_type" size="sm" />
            </div>

            <!-- Title -->
            <NuxtLink :to="localePath(`/market/${item.slug || item.id}`)" class="block">
              <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 hover:text-secondary dark:hover:text-secondary-400 mb-1 line-clamp-2">
                {{ item.title }}
              </h3>
            </NuxtLink>

            <!-- Description -->
            <p class="text-sm text-neutral-600 dark:text-neutral-400 line-clamp-2 mb-3">
              {{ item.description || $t('market.item.no_description') }}
            </p>

            <!-- Price -->
            <div class="mb-3">
              <div v-if="item.pricing_options && item.pricing_options.length > 0" class="text-sm">
                <div
                  v-for="(opt, idx) in item.pricing_options.slice(0, 2)"
                  :key="idx"
                  class="font-semibold text-neutral-900 dark:text-neutral-100"
                >
                  {{ formatPricingOption(opt, { withNote: false }) }}
                </div>
              </div>
              <div v-else class="font-semibold text-success dark:text-success-400">
                {{ $t('market.pricing.free') }}
              </div>
            </div>

            <!-- Actions — wrap (never clip) so every label stays readable at any card width -->
            <div class="flex flex-wrap gap-2 mt-auto pt-3 border-t border-neutral-200 dark:border-neutral-700">
              <UiButton
                variant="outline"
                size="sm"
                :icon="Edit"
                class="flex-1 min-w-[7.5rem]"
                :to="localePath(`/market/create?edit=${item.slug || item.id}`)"
              >
                {{ $t('market.actions.edit') }}
              </UiButton>
              <UiButton
                :variant="item.is_active ? 'outline-warning' : 'success'"
                size="sm"
                class="flex-1 min-w-[7.5rem]"
                :icon="item.is_active ? EyeOff : Eye"
                @click="toggleActive(item)"
              >
                {{ $t(item.is_active ? 'market.actions.hide' : 'market.actions.activate') }}
              </UiButton>
              <UiButton variant="outline-error" size="sm" class="flex-1 min-w-[7.5rem]" :icon="Trash2" @click="confirmDelete(item)">
                {{ $t('market.actions.delete') }}
              </UiButton>
            </div>

            <div class="mt-2 text-xs text-neutral-500">
              {{ formatDate(item.created_at) }}
            </div>
          </div>
        </div>
      </div>

      <!-- Empty state -->
      <div v-else class="text-center py-12">
        <img src="/images/para/pointing.webp" alt="Para" class="mx-auto h-32 w-auto mb-6" />
        <h3 class="text-xl font-semibold text-neutral-700 dark:text-neutral-300 mb-2">
          {{ $t('market.my_items.empty_title') }}
        </h3>
        <p class="text-neutral-600 dark:text-neutral-400 mb-6">
          {{ $t('market.my_items.empty_description') }}
        </p>
        <UiButton :to="localePath('/market/create')">
          {{ $t('market.create_listing') }}
        </UiButton>
      </div>
      </template>

      <!-- ===== Barter matches (chains + diagnosis over my listings) ===== -->
      <template v-else-if="mode === 'barter'">
        <MarketBarterPanel />
      </template>

      <!-- ===== Booking requests (owner / item manager) ===== -->
      <template v-else-if="mode === 'requests'">
        <div v-if="bookingLoading" class="py-12 text-center" role="status" aria-live="polite">
          <div class="h-12 w-12 mx-auto border-4 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100 rounded-full animate-spin" aria-hidden="true"></div>
          <span class="sr-only">{{ $t('booking.loading') }}</span>
        </div>
        <div v-else-if="!incoming.length" class="py-12 text-center">
          <Inbox class="w-12 h-12 text-neutral-300 dark:text-neutral-600 mx-auto mb-4" />
          <h3 class="text-neutral-500">{{ $t('booking.manage.empty') }}</h3>
        </div>
        <ul v-else class="space-y-3">
          <li v-for="b in incoming" :key="b.id" class="card p-4 flex items-center justify-between gap-3">
            <NuxtLink :to="localePath(`/rental/${b.item_id}`)" class="min-w-0 flex-1">
              <div class="font-medium truncate flex items-center gap-2">
                <CalendarClock class="w-4 h-4 shrink-0" /> {{ b.item_title || b.item_id }}
              </div>
              <div class="text-sm text-neutral-500 flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
                <span v-if="b.renter_name" class="font-medium text-neutral-600 dark:text-neutral-300">{{ b.renter_name }}</span>
                <UiBadge v-if="b.is_walk_in" variant="secondary" type="soft" size="sm">{{ $t('booking.walk_in.tag') }}</UiBadge>
                <span v-if="b.client_phone" class="inline-flex items-center gap-1"><Phone class="w-3 h-3 shrink-0" /> {{ b.client_phone }}</span>
                <span>{{ fmtBooking(b.start) }} → {{ fmtBooking(b.end) }}</span>
                <Repeat v-if="b.recurrence_group" class="w-3.5 h-3.5 text-secondary shrink-0"
                        :title="$t('booking.series')" :aria-label="$t('booking.series')" />
              </div>
              <div v-if="b.price_total != null" class="text-sm">{{ b.price_total }} {{ b.currency }}</div>
            </NuxtLink>
            <div class="flex flex-wrap items-center justify-end gap-2 shrink-0">
              <UiBadge :variant="statusVariant[b.status] || 'neutral'" type="soft">{{ $t('booking.status.' + b.status) }}</UiBadge>
              <UiButton v-if="b.status === 'REQUESTED'" variant="primary" size="sm" :icon="Check"
                        :loading="acting === b.id" @click="transition(b, 'confirm')">
                {{ $t('booking.manage.confirm') }}
              </UiButton>
              <UiButton v-if="b.status === 'CONFIRMED'" variant="outline" size="sm" :icon="CheckCheck"
                        :loading="acting === b.id" @click="transition(b, 'complete')">
                {{ $t('booking.manage.complete') }}
              </UiButton>
              <!-- Formalize → PGP-signed rental contract (platform renters only, not already formalized) -->
              <UiButton v-if="b.status === 'CONFIRMED' && b.renter_id && !b.contract_id"
                        :to="localePath(`/contracts?partner=${b.renter_id}&item=${b.item_id}&kind=rental&booking=${b.id}`)"
                        variant="primary" size="sm" :icon="FileSignature">
                {{ $t('booking.manage.formalize') }}
              </UiButton>
              <UiButton v-if="['REQUESTED', 'CONFIRMED'].includes(b.status)"
                        variant="outline-error" size="sm" :icon="X" @click="askCancel(b)">
                {{ $t('booking.cancel') }}
              </UiButton>
            </div>
          </li>
        </ul>
      </template>

      <!-- ===== My bookings (as renter) ===== -->
      <template v-else-if="mode === 'bookings'">
        <div v-if="bookingLoading" class="py-12 text-center" role="status" aria-live="polite">
          <div class="h-12 w-12 mx-auto border-4 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100 rounded-full animate-spin" aria-hidden="true"></div>
          <span class="sr-only">{{ $t('booking.loading') }}</span>
        </div>
        <div v-else-if="!bookings.length" class="py-12 text-center">
          <CalendarX2 class="w-12 h-12 text-neutral-300 dark:text-neutral-600 mx-auto mb-4" />
          <h3 class="text-neutral-500">{{ $t('booking.empty') }}</h3>
        </div>
        <ul v-else class="space-y-3">
          <li v-for="b in bookings" :key="b.id" class="card p-4 flex items-center justify-between gap-3">
            <NuxtLink :to="localePath(`/rental/${b.item_id}`)" class="min-w-0 flex-1">
              <div class="font-medium truncate flex items-center gap-2">
                <CalendarClock class="w-4 h-4 shrink-0" /> {{ b.item_title || b.item_id }}
              </div>
              <div class="text-sm text-neutral-500">
                {{ fmtBooking(b.start) }} → {{ fmtBooking(b.end) }}
                <Repeat v-if="b.recurrence_group" class="inline w-3.5 h-3.5 ml-1 text-secondary align-text-bottom"
                        :title="$t('booking.series')" :aria-label="$t('booking.series')" />
              </div>
              <div v-if="b.price_total != null" class="text-sm">{{ b.price_total }} {{ b.currency }}</div>
              <div v-if="b.status === 'CANCELLED' && b.cancel_note" class="text-xs text-neutral-500 italic mt-0.5">
                {{ $t('booking.cancel_reason') }}: {{ b.cancel_note }}
              </div>
            </NuxtLink>
            <div class="flex flex-wrap items-center justify-end gap-2 shrink-0">
              <UiBadge :variant="statusVariant[b.status] || 'neutral'" type="soft">{{ $t('booking.status.' + b.status) }}</UiBadge>
              <UiButton v-if="['REQUESTED', 'CONFIRMED'].includes(b.status)"
                        variant="outline-error" size="sm" :icon="X" @click="askCancel(b)">
                {{ $t('booking.cancel') }}
              </UiButton>
            </div>
          </li>
        </ul>
      </template>
    </div>

    <!-- Delete Confirmation Modal -->
    <UiConfirmModal
      :model-value="!!deletingItem"
      @update:model-value="!$event && (deletingItem = null)"
      :title="$t('market.delete_modal.title')"
      :message="deletingItem ? $t('market.delete_modal.confirm_message', { title: deletingItem.title }) : ''"
      :icon="Trash2"
      variant="error"
      :confirm-label="$t('market.delete_modal.delete')"
      :cancel-label="$t('market.delete_modal.cancel')"
      :loading="deleting"
      @confirm="deleteItem"
    />

    <!-- Booking cancel confirmation (requests + my-bookings tabs) -->
    <UiConfirmModal
      v-model="showCancel"
      :title="$t('booking.cancel_confirm')"
      :icon="CalendarOff"
      variant="warning"
      :confirm-label="$t('booking.cancel_yes')"
      :cancel-label="$t('booking.keep')"
      :loading="cancelling"
      @confirm="doCancel"
    >
      <p class="text-sm text-neutral-500 dark:text-neutral-400 mb-3">{{ $t('booking.cancel_confirm_msg') }}</p>
      <label v-if="cancelTarget && cancelTarget.recurrence_group" class="flex items-center gap-2 mb-3 text-sm">
        <input v-model="cancelSeries" type="checkbox"
               class="rounded border-neutral-300 dark:border-neutral-600 text-secondary focus:ring-secondary" />
        <span>{{ $t('booking.cancel_series') }}</span>
      </label>
      <label class="block">
        <span class="text-sm font-medium">{{ $t('booking.cancel_note') }}</span>
        <textarea v-model="cancelNote" rows="2" maxlength="255" :placeholder="$t('booking.cancel_note_ph')"
                  class="mt-1 w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"></textarea>
      </label>
    </UiConfirmModal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useAuthStore } from '~/stores/auth'
import { useNotification } from '~/composables/useNotification'
import { useRentalInbox } from '~/composables/useRentalInbox'
import { Plus, Package, Edit, Trash2, Eye, EyeOff, X, Inbox, CalendarClock, Check, CheckCheck, CalendarOff, CalendarX2, Repeat, Phone, RefreshCw, FileSignature } from 'lucide-vue-next'

definePageMeta({
  middleware: 'auth'
})

const { t: $t, locale } = useI18n()

const authStore = useAuthStore()
const localePath = useLocalePath()
const { showSuccess, showError } = useNotification()
const { apiErrorMessage } = useApiError()
const { formatPricingOption } = usePricingFormat()
const { pendingCount, loadPendingCount } = useRentalInbox()

// Primary view: own listings · barter matches · incoming booking requests (owner) · my bookings (renter).
// ?tab= drives this (deep-linked from booking push notifications and the market barter banner).
const mode = useTabSync(['listings', 'barter', 'requests', 'bookings'])
const modeTabs = computed(() => [
  { id: 'listings', label: $t('market.my_items.tab_listings'), icon: Package },
  { id: 'barter', label: $t('market.my_items.tab_barter'), icon: RefreshCw },
  {
    id: 'requests', label: $t('booking.manage.inbox'), icon: Inbox,
    ...(pendingCount.value > 0 ? { badge: pendingCount.value } : {}),
  },
  { id: 'bookings', label: $t('booking.my_bookings'), icon: CalendarClock },
])

// State
const items = ref([])
const loading = ref(false)
// Sub-filter within the Listings tab — bookmarkable via ?status= (independent of ?tab=)
const filterStatus = useTabSync(['all', 'active', 'inactive'], 'all', 'status')
const statusTabs = computed(() => [
  { id: 'all', label: $t('market.my_items.filter_all') },
  { id: 'active', label: $t('market.my_items.filter_active') },
  { id: 'inactive', label: $t('market.my_items.filter_inactive') },
])

// Booking state (requests + my-bookings tabs)
const bookings = ref([])        // mine (as renter)
const incoming = ref([])        // managed items (as owner)
const bookingLoading = ref(false)
const bookingsLoaded = ref(false)
const acting = ref(null)
const showCancel = ref(false)
const cancelTarget = ref(null)
const cancelNote = ref('')
const cancelSeries = ref(false)
const cancelling = ref(false)

const statusVariant = {
  REQUESTED: 'warning', CONFIRMED: 'success', CANCELLED: 'neutral',
  COMPLETED: 'info', NO_SHOW: 'error',
}

const fmtBooking = (iso) => new Date(iso).toLocaleString(locale.value, {
  day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
})

const loadBookings = async () => {
  bookingLoading.value = true
  try {
    await authStore.ensureToken()
    const headers = { Authorization: `Bearer ${authStore.accessToken}` }
    const [mine, inc] = await Promise.all([
      $fetch('/api/v1/rental/bookings/mine', { credentials: 'include', headers }),
      $fetch('/api/v1/rental/bookings/incoming', { credentials: 'include', headers }),
    ])
    bookings.value = Array.isArray(mine) ? mine : []
    incoming.value = Array.isArray(inc) ? inc : []
    bookingsLoaded.value = true
    loadPendingCount()
  } catch (error) {
    showError($t('booking.error'))
  } finally {
    bookingLoading.value = false
  }
}

const transition = async (b, action) => {
  acting.value = b.id
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/rental/bookings/${b.id}/${action}`, {
      method: 'POST',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.accessToken}` },
    })
    showSuccess($t('booking.manage.updated'))
    await loadBookings()
  } catch (error) {
    showError(error?.data?.detail || $t('booking.error'))
  } finally {
    acting.value = null
  }
}

const askCancel = (b) => { cancelTarget.value = b; cancelNote.value = ''; cancelSeries.value = false; showCancel.value = true }

const doCancel = async () => {
  if (!cancelTarget.value) return
  cancelling.value = true
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/rental/bookings/${cancelTarget.value.id}/cancel`, {
      method: 'POST',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.accessToken}` },
      body: { note: cancelNote.value.trim(), series: cancelSeries.value },
    })
    showSuccess($t('booking.cancelled'))
    await loadBookings()
  } catch (error) {
    showError(error?.data?.detail || $t('booking.error'))
  } finally {
    cancelling.value = false
    showCancel.value = false
  }
}
const deletingItem = ref(null)
const deleting = ref(false)

// Fetch user's items
const fetchMyItems = async () => {
  loading.value = true
  try {
    await authStore.ensureToken()

    if (!authStore.accessToken) {
      showError($t('market.notifications.login_required_action'))
      return
    }

    // Get current user's ID
    const profile = await $fetch('/api/v1/profiles/me/', {
      headers: { Authorization: `Bearer ${authStore.accessToken}` },
      credentials: 'include'
    })

    const params = new URLSearchParams({
      owner_id: profile.id
    })

    // Add status filter
    if (filterStatus.value === 'active') {
      params.append('is_active', 'true')
    } else if (filterStatus.value === 'inactive') {
      params.append('is_active', 'false')
    }

    const response = await $fetch(`/api/v1/items/?${params}`, {
      headers: { Authorization: `Bearer ${authStore.accessToken}` },
      credentials: 'include'
    })

    items.value = Array.isArray(response) ? response : (response.items || response.results || [])
  } catch (error) {
    console.error('Failed to fetch items:', error)
    showError($t('market.notifications.load_error'))
  } finally {
    loading.value = false
  }
}

// Toggle active status
const toggleActive = async (item) => {
  try {
    await authStore.ensureToken()

    if (!authStore.accessToken) {
      showError($t('market.notifications.login_required_action'))
      return
    }

    if (item.is_active) {
      // Deactivate
      await $fetch(`/api/v1/items/${item.id}/deactivate/`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${authStore.accessToken}`
        },
        credentials: 'include'
      })
      showSuccess($t('market.notifications.hidden'))
    } else {
      // Activate (update with is_active: true)
      await $fetch(`/api/v1/items/${item.id}/`, {
        method: 'PUT',
        headers: {
          Authorization: `Bearer ${authStore.accessToken}`,
          'Content-Type': 'application/json'
        },
        credentials: 'include',
        body: { is_active: true, expected_version: item.version }
      })
      showSuccess($t('market.notifications.activated'))
    }

    await fetchMyItems()
  } catch (error) {
    console.error('Failed to toggle item status:', error)
    showError(apiErrorMessage(error, 'market.error_codes', $t('market.notifications.status_error')))
  }
}

// Confirm delete
const confirmDelete = (item) => {
  deletingItem.value = item
}

// Delete item
const deleteItem = async () => {
  deleting.value = true
  try {
    await authStore.ensureToken()

    if (!authStore.accessToken) {
      showError($t('market.notifications.login_required_action'))
      return
    }

    await $fetch(`/api/v1/items/${deletingItem.value.id}/`, {
      method: 'DELETE',
      headers: {
        Authorization: `Bearer ${authStore.accessToken}`
      },
      credentials: 'include'
    })

    showSuccess($t('market.notifications.deleted'))
    useState('marketDirty', () => false).value = true
    deletingItem.value = null
    await fetchMyItems()
  } catch (error) {
    console.error('Failed to delete item:', error)
    showError(apiErrorMessage(error, 'market.error_codes', $t('market.notifications.delete_error')))
  } finally {
    deleting.value = false
  }
}

// Format date
const formatDate = (dateString) => {
  const date = new Date(dateString)
  const now = new Date()
  const diff = Math.floor((now - date) / 1000)

  if (diff < 60) return $t('market.time.just_now')
  if (diff < 3600) return $t('market.time.minutes_ago', { n: Math.floor(diff / 60) })
  if (diff < 86400) return $t('market.time.hours_ago', { n: Math.floor(diff / 3600) })
  if (diff < 604800) return $t('market.time.days_ago', { n: Math.floor(diff / 86400) })

  return date.toLocaleDateString(locale.value, { day: 'numeric', month: 'short', year: 'numeric' })
}

// Lazy-load bookings the first time the user opens a booking tab (or on deep-link).
watch(mode, (m) => {
  if ((m === 'requests' || m === 'bookings') && !bookingsLoaded.value) loadBookings()
})

onMounted(() => {
  fetchMyItems()
  loadPendingCount()          // hydrate the Requests-tab badge
  if (mode.value !== 'listings') loadBookings()
})
</script>

