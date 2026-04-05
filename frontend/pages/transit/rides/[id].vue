<template>
  <div class="max-w-2xl mx-auto px-4 py-6">
    <!-- Back -->
    <NuxtLink :to="localePath('/transit/rides')" class="inline-flex items-center gap-1 text-sm text-link mb-4">
      <ArrowLeft class="w-4 h-4" />
      {{ $t('rides.back') }}
    </NuxtLink>

    <!-- Loading -->
    <div v-if="loading" class="text-center py-12">
      <div class="w-8 h-8 border-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100 rounded-full animate-spin mx-auto"></div>
    </div>

    <!-- Not found -->
    <div v-else-if="!rideRequest" class="text-center py-12 text-neutral-500">
      {{ $t('rides.not_found') }}
    </div>

    <template v-else>
      <!-- Request Info Card -->
      <div class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-5 mb-6">
        <div class="flex items-start justify-between mb-4">
          <div>
            <h1 class="text-xl font-bold text-neutral-900 dark:text-neutral-100">
              {{ rideRequest.origin_stop?.name }} → {{ rideRequest.destination_stop?.name }}
            </h1>
            <p class="text-sm text-neutral-500 mt-1">{{ timeAgo(rideRequest.created_at) }}</p>
          </div>
          <div class="text-right">
            <div class="text-xl font-bold text-amber-600 dark:text-amber-400">{{ rideRequest.price_sats }} sats</div>
            <div class="text-xs text-neutral-500">{{ rideRequest.passengers_count }} {{ $t('rides.passengers_label', rideRequest.passengers_count) }}</div>
          </div>
        </div>

        <!-- Passenger info -->
        <div class="flex items-center gap-3 py-3 border-t border-neutral-200 dark:border-neutral-700">
          <div class="w-10 h-10 rounded-full bg-neutral-200 dark:bg-neutral-700 flex items-center justify-center text-sm font-bold text-neutral-600 dark:text-neutral-300">
            {{ rideRequest.passenger?.display_name?.charAt(0) || '?' }}
          </div>
          <div>
            <div class="font-medium text-neutral-900 dark:text-neutral-100">{{ rideRequest.passenger?.display_name }}</div>
            <div v-if="rideRequest.passenger?.ride_rating" class="text-sm text-neutral-500">
              {{ rideRequest.passenger.ride_rating }} / 5 ({{ rideRequest.passenger.ride_count }} {{ $t('rides.reviews') }})
            </div>
          </div>
        </div>

        <p v-if="rideRequest.note" class="mt-3 text-sm text-neutral-600 dark:text-neutral-400 italic">{{ rideRequest.note }}</p>

        <!-- Status badges -->
        <div class="mt-3 flex items-center gap-2">
          <span v-if="rideRequest.is_active" class="px-2 py-0.5 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 text-xs font-medium rounded">
            {{ $t('rides.status.active') }}
          </span>
          <span v-else class="px-2 py-0.5 bg-neutral-100 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-400 text-xs font-medium rounded">
            {{ $t('rides.status.closed') }}
          </span>
        </div>

        <!-- Cancel button (own request, still active) -->
        <button
          v-if="isOwner && rideRequest.is_active"
          @click="showCancelConfirm = true"
          class="mt-4 w-full py-2 border border-red-300 dark:border-red-700 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg text-sm font-medium transition-colors"
        >
          {{ $t('rides.cancel_request') }}
        </button>
      </div>

      <!-- Driver: Offer to Drive -->
      <div v-if="!isOwner && rideRequest.is_active && !myOffer" class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-5 mb-6">
        <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4">{{ $t('rides.offer.title') }}</h2>
        <div class="space-y-3">
          <div>
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ $t('rides.offer.vehicle_note') }}</label>
            <input
              v-model="offerForm.driverNote"
              type="text"
              :placeholder="$t('rides.offer.vehicle_note_placeholder')"
              maxlength="500"
              class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ $t('rides.offer.seats') }}</label>
            <input
              v-model.number="offerForm.availableSeats"
              type="number"
              min="1"
              max="20"
              class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100"
            />
          </div>
          <button
            @click="submitOffer"
            :disabled="submittingOffer"
            class="btn-success w-full transition-colors"
          >
            {{ submittingOffer ? $t('rides.offer.submitting') : $t('rides.offer.submit') }}
          </button>
          <p v-if="offerError" class="text-sm text-red-500">{{ offerError }}</p>
        </div>
      </div>

      <!-- My existing offer status -->
      <div v-if="myOffer" class="bg-secondary-50 dark:bg-secondary-900/20 rounded-lg border border-secondary-200 dark:border-secondary-800 p-4 mb-6">
        <p class="text-sm font-medium text-secondary-700 dark:text-secondary-300">
          {{ $t('rides.offer.your_offer') }}: {{ $t(`rides.booking_status.${myOffer.status}`) }}
        </p>
        <p v-if="myOffer.matrix_room_id" class="mt-2">
          <NuxtLink :to="localePath('/chat')" class="text-link text-sm">{{ $t('rides.open_chat') }}</NuxtLink>
        </p>
      </div>

      <!-- Driver Offers (for request owner) -->
      <div v-if="isOwner && rideRequest.bookings?.length > 0" class="mb-6">
        <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-3">{{ $t('rides.offers_title') }}</h2>
        <div class="space-y-3">
          <div
            v-for="booking in rideRequest.bookings"
            :key="booking.id"
            class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4"
          >
            <div class="flex items-center justify-between mb-2">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-full bg-neutral-200 dark:bg-neutral-700 flex items-center justify-center text-sm font-bold text-neutral-600 dark:text-neutral-300">
                  {{ booking.driver?.display_name?.charAt(0) || '?' }}
                </div>
                <div>
                  <div class="font-medium text-neutral-900 dark:text-neutral-100">{{ booking.driver?.display_name }}</div>
                  <div v-if="booking.driver?.ride_rating" class="text-sm text-neutral-500">
                    {{ booking.driver.ride_rating }} / 5 ({{ booking.driver.ride_count }} {{ $t('rides.reviews') }})
                  </div>
                </div>
              </div>
              <span
                class="px-2 py-0.5 text-xs font-medium rounded"
                :class="statusClass(booking.status)"
              >
                {{ $t(`rides.booking_status.${booking.status}`) }}
              </span>
            </div>

            <p v-if="booking.driver_note" class="text-sm text-neutral-600 dark:text-neutral-400 mb-2">{{ booking.driver_note }}</p>
            <p class="text-xs text-neutral-500">{{ $t('rides.offer.seats') }}: {{ booking.available_seats }}</p>

            <!-- Accept button -->
            <button
              v-if="booking.status === 'OFFERED' && rideRequest.is_active"
              @click="acceptOffer(booking.id)"
              :disabled="accepting"
              class="btn-success btn-sm mt-3 w-full transition-colors"
            >
              {{ $t('rides.accept') }}
            </button>

            <!-- Chat link for confirmed -->
            <NuxtLink
              v-if="booking.status === 'CONFIRMED' && booking.matrix_room_id"
              :to="localePath('/chat')"
              class="mt-3 inline-flex items-center gap-1 text-sm text-link"
            >
              <MessageCircle class="w-4 h-4" />
              {{ $t('rides.open_chat') }}
            </NuxtLink>
          </div>
        </div>
      </div>

      <!-- Confirmed Booking Actions -->
      <div v-if="confirmedBooking" class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-5 mb-6">
        <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-3">{{ $t('rides.booking_actions') }}</h2>

        <div v-if="confirmedBooking.status === 'CONFIRMED'" class="flex gap-3">
          <button
            @click="updateBooking(confirmedBooking.id, 'COMPLETED')"
            class="btn-success btn-sm flex-1 transition-colors"
          >
            {{ $t('rides.complete') }}
          </button>
          <button
            @click="updateBooking(confirmedBooking.id, 'CANCELLED')"
            class="flex-1 py-2 border border-red-300 dark:border-red-700 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg text-sm font-medium transition-colors"
          >
            {{ $t('rides.cancel') }}
          </button>
        </div>

        <!-- Review form (after completion) -->
        <div v-if="confirmedBooking.status === 'COMPLETED' && !hasReviewed">
          <h3 class="text-base font-medium text-neutral-900 dark:text-neutral-100 mb-3 mt-4">{{ $t('rides.review.title') }}</h3>
          <div class="space-y-3">
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ $t('rides.review.rating') }}</label>
              <div class="flex gap-1">
                <button
                  v-for="star in 5"
                  :key="star"
                  @click="reviewForm.rating = star"
                  class="text-2xl transition-colors"
                  :class="star <= reviewForm.rating ? 'text-amber-400' : 'text-neutral-300 dark:text-neutral-600'"
                >
                  &#9733;
                </button>
              </div>
            </div>
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ $t('rides.review.comment') }}</label>
              <textarea
                v-model="reviewForm.comment"
                rows="2"
                maxlength="1000"
                class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100"
              ></textarea>
            </div>
            <button
              @click="submitReview"
              :disabled="reviewForm.rating === 0 || submittingReview"
              class="btn-secondary btn-sm w-full transition-colors"
            >
              {{ $t('rides.review.submit') }}
            </button>
          </div>
        </div>
      </div>
    </template>
  </div>

  <UiConfirmModal
    v-model="showCancelConfirm"
    :title="t('rides.cancel_request')"
    :message="t('rides.confirm_cancel')"
    :icon="XCircle"
    variant="error"
    :confirm-label="t('rides.cancel_request')"
    @confirm="cancelRequest"
  />
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ArrowLeft, MessageCircle, XCircle } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'

const { t } = useI18n()
const route = useRoute()
const localePath = useLocalePath()
const authStore = useAuthStore()

const rideRequest = ref<any>(null)
const loading = ref(true)
const showCancelConfirm = ref(false)

useSeoMeta({
  title: () => rideRequest.value ? `${rideRequest.value.origin_stop?.name} → ${rideRequest.value.destination_stop?.name} — Parahub` : t('rides.title'),
  ogTitle: () => rideRequest.value ? `${rideRequest.value.origin_stop?.name} → ${rideRequest.value.destination_stop?.name}` : t('rides.title'),
  description: () => rideRequest.value ? t('rides.ride_meta', { origin: rideRequest.value.origin_stop?.name, destination: rideRequest.value.destination_stop?.name }) : t('rides.landing_meta'),
  ogDescription: () => rideRequest.value ? t('rides.ride_meta', { origin: rideRequest.value.origin_stop?.name, destination: rideRequest.value.destination_stop?.name }) : t('rides.landing_meta'),
  ogImage: '/og-image.jpg',
  ogType: 'website',
  twitterCard: 'summary_large_image',
})

const isOwner = computed(() => {
  return authStore.isAuthenticated && rideRequest.value?.passenger?.id === authStore.activeProfile?.id
})

const myOffer = computed(() => {
  if (!authStore.isAuthenticated || !rideRequest.value?.bookings) return null
  return rideRequest.value.bookings.find((b: any) => b.driver?.id === authStore.activeProfile?.id)
})

const confirmedBooking = computed(() => {
  if (!rideRequest.value?.bookings) return null
  return rideRequest.value.bookings.find((b: any) =>
    b.status === 'CONFIRMED' || b.status === 'COMPLETED'
  )
})

const justReviewed = ref(false)
const hasReviewed = computed(() => {
  if (justReviewed.value) return true
  return rideRequest.value?.viewer_has_reviewed === true
})
const accepting = ref(false)

// Offer form
const offerForm = ref({ driverNote: '', availableSeats: 3 })
const submittingOffer = ref(false)
const offerError = ref('')

// Review form
const reviewForm = ref({ rating: 0, comment: '' })
const submittingReview = ref(false)

async function loadRequest() {
  loading.value = true
  try {
    await authStore.ensureToken()
    rideRequest.value = await $fetch<any>(`/api/v1/rides/requests/${route.params.id}/`, {
      credentials: 'include',
      headers: authStore.token ? { 'Authorization': `Bearer ${authStore.token}` } : {},
    })
  } catch {
    rideRequest.value = null
  } finally {
    loading.value = false
  }
}

async function cancelRequest() {
  showCancelConfirm.value = false
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/rides/requests/${route.params.id}/`, {
      method: 'DELETE',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
    })
    await loadRequest()
  } catch (err) {
    console.error('Cancel failed:', err)
  }
}

async function acceptOffer(bookingId: string) {
  accepting.value = true
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/rides/requests/${route.params.id}/accept/`, {
      method: 'PATCH',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
      body: { booking_id: bookingId },
    })
    await loadRequest()
  } catch (err) {
    console.error('Accept failed:', err)
  } finally {
    accepting.value = false
  }
}

async function submitOffer() {
  submittingOffer.value = true
  offerError.value = ''
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/rides/requests/${route.params.id}/offer/`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
      body: {
        driver_note: offerForm.value.driverNote,
        available_seats: offerForm.value.availableSeats,
      },
    })
    await loadRequest()
  } catch (err: any) {
    offerError.value = err?.data?.message || err?.data?.detail || t('rides.offer.error')
  } finally {
    submittingOffer.value = false
  }
}

async function updateBooking(bookingId: string, status: string) {
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/rides/bookings/${bookingId}/`, {
      method: 'PATCH',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
      body: { status },
    })
    await loadRequest()
  } catch (err) {
    console.error('Update booking failed:', err)
  }
}

async function submitReview() {
  if (!confirmedBooking.value) return
  submittingReview.value = true
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/rides/bookings/${confirmedBooking.value.id}/review/`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
      body: {
        rating: reviewForm.value.rating,
        comment: reviewForm.value.comment,
      },
    })
    justReviewed.value = true
  } catch (err) {
    console.error('Review failed:', err)
  } finally {
    submittingReview.value = false
  }
}

function statusClass(status: string): string {
  switch (status) {
    case 'OFFERED': return 'bg-secondary-100 dark:bg-secondary-900/30 text-secondary-700 dark:text-secondary-400'
    case 'CONFIRMED': return 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400'
    case 'COMPLETED': return 'bg-neutral-100 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-400'
    case 'CANCELLED': return 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400'
    default: return 'bg-neutral-100 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-400'
  }
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return t('rides.time.now')
  if (mins < 60) return t('rides.time.minutes_ago', { n: mins })
  return t('rides.time.hours_ago', { n: Math.floor(mins / 60) })
}

onMounted(() => {
  loadRequest()
})
</script>
