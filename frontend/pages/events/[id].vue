<template>
  <div class="min-h-screen bg-neutral-50 dark:bg-neutral-900">
    <!-- Loading state -->
    <div v-if="loading" class="flex justify-center py-24" role="status" aria-live="polite">
      <div class="animate-spin rounded-full h-10 w-10 border-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-white" aria-hidden="true" />
      <span class="sr-only">{{ $t('common.loading') }}</span>
    </div>

    <!-- Error state -->
    <div v-else-if="error" class="max-w-2xl mx-auto px-4 py-24 text-center">
      <AlertCircle class="w-16 h-16 mx-auto text-red-500 mb-4" />
      <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100 mb-2">
        {{ $t('events.error_loading') }}
      </h1>
      <p class="text-neutral-600 dark:text-neutral-400 mb-6">{{ error }}</p>
      <NuxtLink :to="localePath('/events')" class="text-link">
        {{ $t('events.back_to_events') }}
      </NuxtLink>
    </div>

    <!-- Event content -->
    <div v-else-if="event" class="max-w-4xl mx-auto px-4 py-6">
      <!-- Back link -->
      <NuxtLink
        :to="localePath('/events')"
        class="text-link text-sm flex items-center gap-1 mb-4"
      >
        <ArrowLeft :size="16" />
        {{ $t('events.back_to_events') }}
      </NuxtLink>

      <!-- Cover image -->
      <div
        v-if="event.cover_image_url"
        class="h-64 md:h-80 rounded-xl bg-cover bg-center mb-6"
        :style="{ backgroundImage: `url(${event.cover_image_url})` }"
      />
      <div
        v-else
        class="h-48 md:h-64 rounded-xl bg-gradient-to-br from-neutral-200 to-neutral-300 dark:from-neutral-700 dark:to-neutral-800 flex items-center justify-center mb-6"
      >
        <Calendar class="w-20 h-20 text-neutral-400 dark:text-neutral-600" />
      </div>

      <!-- Status banner for cancelled events -->
      <UiAlert v-if="event.status === 'CANCELLED'" variant="error" class="mb-6">
        <span class="font-medium">{{ $t('events.cancelled') }}</span>
      </UiAlert>

      <!-- Header -->
      <div class="mb-6">
        <div class="flex items-start justify-between gap-4 mb-3">
          <h1 class="text-2xl md:text-3xl font-bold text-neutral-900 dark:text-neutral-100">
            {{ event.title }}
          </h1>
          <!-- Event type badge -->
          <div class="flex items-center gap-2 flex-shrink-0">
            <DemoBadge :is-demo="event.is_demo" />
            <span
              :class="eventTypeBadgeClass"
              class="px-3 py-1 rounded-full text-sm font-medium"
            >
              {{ eventTypeLabel }}
            </span>
          </div>
        </div>

        <!-- Category -->
        <div v-if="event.category_name" class="flex items-center gap-2 text-neutral-600 dark:text-neutral-400">
          <span v-if="event.category_icon" class="text-xl">{{ event.category_icon }}</span>
          <span>{{ event.category_name }}</span>
        </div>
      </div>

      <!-- Main content grid: flex on mobile (sidebar between key info and content), grid on lg -->
      <div class="flex flex-col lg:grid lg:grid-cols-3 gap-6">
        <!-- Key info: When, Where, Online link -->
        <div class="lg:col-span-2 space-y-6">
          <!-- Date & Time -->
          <div class="bg-white dark:bg-neutral-800 rounded-lg p-5 border border-neutral-200 dark:border-neutral-700">
            <h2 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-3 flex items-center gap-2">
              <CalendarDays :size="20" />
              {{ $t('events.when') }}
            </h2>
            <p class="text-lg text-neutral-900 dark:text-neutral-100">
              {{ formattedDateLong }}
            </p>
            <p v-if="event.ends_at" class="text-neutral-600 dark:text-neutral-400 mt-1">
              {{ $t('events.until') }} {{ formattedEndTime }}
            </p>
            <p v-if="showTimezone" class="text-sm text-neutral-500 mt-2">
              {{ event.timezone }}
            </p>
          </div>

          <!-- Location (offline/hybrid) -->
          <div
            v-if="event.event_type !== 'ONLINE'"
            class="bg-white dark:bg-neutral-800 rounded-lg p-5 border border-neutral-200 dark:border-neutral-700"
          >
            <h2 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-3 flex items-center gap-2">
              <MapPin :size="20" />
              {{ $t('events.where') }}
            </h2>
            <p v-if="event.world_object" class="text-neutral-900 dark:text-neutral-100">
              {{ event.world_object.full_address }}
            </p>
            <p v-else-if="event.location_name" class="text-neutral-900 dark:text-neutral-100">
              {{ event.location_name }}
            </p>
            <p v-else-if="event.location" class="text-neutral-600 dark:text-neutral-400">
              {{ event.location.lat.toFixed(6) }}, {{ event.location.lon.toFixed(6) }}
            </p>

            <!-- Map preview -->
            <StaticMapPreview
              v-if="eventCoords"
              :latitude="eventCoords.lat"
              :longitude="eventCoords.lon"
              :height="180"
              class="mt-3"
            />

            <!-- Show on map link -->
            <button
              v-if="event.location || event.world_object"
              @click="showOnMap"
              class="mt-3 text-link text-sm flex items-center gap-1"
            >
              <Map :size="14" />
              {{ $t('events.show_on_map') }}
            </button>
          </div>

          <!-- Online link (online/hybrid) -->
          <div
            v-if="event.event_type !== 'OFFLINE' && event.online_url"
            class="bg-white dark:bg-neutral-800 rounded-lg p-5 border border-neutral-200 dark:border-neutral-700"
          >
            <h2 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-3 flex items-center gap-2">
              <Video :size="20" />
              {{ $t('events.online_link') }}
            </h2>
            <a
              :href="event.online_url"
              target="_blank"
              rel="noopener noreferrer"
              class="text-link break-all"
            >
              {{ event.online_url }}
            </a>
          </div>
        </div>

        <!-- Sidebar: Organizer, Actions, Chat, Views — appears after key info on mobile -->
        <div class="space-y-4 lg:row-span-2">
          <!-- Organizer card -->
          <div class="bg-white dark:bg-neutral-800 rounded-lg p-5 border border-neutral-200 dark:border-neutral-700">
            <h3 class="text-sm text-neutral-500 mb-3">{{ $t('events.organizer') }}</h3>
            <NuxtLink
              :to="localePath(`/u/${event.organizer.hna?.split('@')[0] || event.organizer.id}`)"
              class="flex items-center gap-3 hover:bg-neutral-50 dark:hover:bg-neutral-700 -m-2 p-2 rounded-lg"
            >
              <img
                v-if="event.organizer.avatar_url"
                :src="event.organizer.avatar_url"
                :alt="event.organizer.hna"
                class="w-12 h-12 rounded-full"
              />
              <div v-else class="w-12 h-12 rounded-full bg-neutral-200 dark:bg-neutral-700 flex items-center justify-center">
                <User :size="24" class="text-neutral-500" />
              </div>
              <div>
                <p class="font-medium text-neutral-900 dark:text-neutral-100">
                  {{ event.organizer.display_name || event.organizer.hna }}
                </p>
              </div>
            </NuxtLink>
          </div>

          <!-- Join/Leave actions -->
          <div
            v-if="authStore.isAuthenticated && event.status === 'PUBLISHED'"
            class="bg-white dark:bg-neutral-800 rounded-lg p-5 border border-neutral-200 dark:border-neutral-700"
          >
            <!-- User is organizer -->
            <template v-if="event.is_organizer">
              <p class="text-sm text-neutral-500 mb-3">{{ $t('events.you_are_organizer') }}</p>
              <div class="space-y-2">
                <NuxtLink
                  :to="localePath(`/events/${event.id}/edit`)"
                  class="w-full flex items-center justify-center gap-2 px-4 py-2 bg-neutral-100 dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 rounded-lg font-medium hover:bg-neutral-200 dark:hover:bg-neutral-600"
                >
                  <Pencil :size="16" />
                  {{ $t('events.edit_event') }}
                </NuxtLink>
                <button
                  @click="showCancelEventConfirm = true"
                  :disabled="cancelling"
                  class="w-full flex items-center justify-center gap-2 px-4 py-2 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-300 rounded-lg font-medium hover:bg-red-200 dark:hover:bg-red-800"
                >
                  <XCircle :size="16" />
                  {{ $t('events.cancel_event') }}
                </button>
              </div>
            </template>

            <!-- User is participant -->
            <template v-else-if="event.my_participation_status && event.my_participation_status !== 'CANCELLED'">
              <p class="text-sm text-neutral-500 mb-3">
                {{ event.my_participation_status === 'GOING' ? $t('events.you_are_going') : $t('events.you_are_maybe') }}
              </p>
              <button
                @click="leaveEvent"
                :disabled="actionLoading"
                class="w-full flex items-center justify-center gap-2 px-4 py-2 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-300 rounded-lg font-medium hover:bg-red-200 dark:hover:bg-red-800"
              >
                <UserMinus :size="16" />
                {{ $t('events.leave_event') }}
              </button>
            </template>

            <!-- User can join -->
            <template v-else>
              <div class="space-y-2">
                <button
                  @click="joinEvent('GOING')"
                  :disabled="actionLoading || event.is_full"
                  :class="event.is_full ? 'opacity-50 cursor-not-allowed' : 'hover:bg-secondary-600'"
                  class="w-full flex items-center justify-center gap-2 px-4 py-2 bg-secondary text-white rounded-lg font-medium"
                >
                  <UserPlus :size="16" />
                  {{ event.is_full ? $t('events.full') : $t('events.join_going') }}
                </button>
                <button
                  @click="joinEvent('MAYBE')"
                  :disabled="actionLoading"
                  class="w-full flex items-center justify-center gap-2 px-4 py-2 border border-neutral-300 dark:border-neutral-600 text-neutral-900 dark:text-neutral-100 rounded-lg font-medium hover:bg-neutral-100 dark:hover:bg-neutral-700"
                >
                  <HelpCircle :size="16" />
                  {{ $t('events.join_maybe') }}
                </button>
              </div>
            </template>
          </div>

          <!-- Matrix chat link -->
          <div
            v-if="event.matrix_room_id && (event.is_organizer || event.my_participation_status === 'GOING')"
            class="bg-white dark:bg-neutral-800 rounded-lg p-5 border border-neutral-200 dark:border-neutral-700"
          >
            <NuxtLink
              :to="{ path: localePath('/chat'), query: { room_id: event.matrix_room_id } }"
              class="btn-secondary w-full flex items-center justify-center gap-2"
            >
              <MessageCircle :size="16" />
              {{ $t('events.open_chat') }}
            </NuxtLink>
          </div>

          <!-- Views counter -->
          <div class="text-center text-sm text-neutral-500">
            {{ $t('events.views', { count: event.views_count }) }}
          </div>
        </div>

        <!-- Content: Description, Participants — below sidebar on mobile -->
        <div class="lg:col-span-2 space-y-6">
          <!-- Description -->
          <div class="bg-white dark:bg-neutral-800 rounded-lg p-5 border border-neutral-200 dark:border-neutral-700">
            <h2 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-3 flex items-center gap-2">
              <FileText :size="20" />
              {{ $t('events.description') }}
            </h2>
            <div class="prose dark:prose-invert max-w-none text-neutral-700 dark:text-neutral-300 whitespace-pre-wrap">
              {{ event.description }}
            </div>
          </div>

          <!-- Tickets -->
          <div v-if="eventTicketTypes.length" class="bg-white dark:bg-neutral-800 rounded-lg p-5 border border-neutral-200 dark:border-neutral-700">
            <h2 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-3 flex items-center gap-2">
              <Ticket :size="20" />
              {{ $t('tickets.title') }}
            </h2>
            <TicketsTicketPurchaseCard :ticket-types="eventTicketTypes" :buying-id="buyingTicketId" @buy="startBuyTicket" />
          </div>

          <TicketsTicketBuyModal
            :ticket-type="buyingTicketType"
            @close="buyingTicketType = null; buyingTicketId = null"
            @purchased="loadEventTicketTypes"
            @show-qr="qrTicket = $event"
          />
          <TicketsTicketQRModal :ticket="qrTicket" @close="qrTicket = null" />

          <!-- Participants list -->
          <div class="bg-white dark:bg-neutral-800 rounded-lg p-5 border border-neutral-200 dark:border-neutral-700">
            <h2 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-3 flex items-center gap-2">
              <Users :size="20" />
              {{ $t('events.participants') }}
              <span class="text-neutral-500 font-normal">
                ({{ participants.length }}<template v-if="event.max_participants">/{{ event.max_participants }}</template>)
              </span>
            </h2>

            <div v-if="participants.length > 0" class="space-y-2">
              <div
                v-for="p in participants"
                :key="p.id"
                class="flex items-center gap-3 py-2"
              >
                <img
                  v-if="p.profile_avatar_url"
                  :src="p.profile_avatar_url"
                  :alt="p.profile_hna"
                  class="w-8 h-8 rounded-full"
                />
                <div v-else class="w-8 h-8 rounded-full bg-neutral-200 dark:bg-neutral-700 flex items-center justify-center">
                  <User :size="16" class="text-neutral-500" />
                </div>
                <div class="flex-1">
                  <NuxtLink
                    :to="localePath(`/u/${p.profile_hna?.split('@')[0] || p.profile_id}`)"
                    class="text-neutral-900 dark:text-neutral-100 hover:underline"
                  >
                    {{ p.profile_display_name || p.profile_hna || p.profile_id }}
                  </NuxtLink>
                </div>
                <span
                  v-if="p.status === 'MAYBE'"
                  class="text-xs px-2 py-0.5 bg-yellow-100 dark:bg-yellow-900 text-yellow-700 dark:text-yellow-300 rounded"
                >
                  {{ $t('events.maybe') }}
                </span>
              </div>
            </div>
            <p v-else class="text-neutral-500">
              {{ $t('events.no_participants_yet') }}
            </p>
          </div>
        </div>
      </div>
    </div>
  </div>

  <UiConfirmModal
    v-model="showCancelEventConfirm"
    :title="t('events.cancel_event')"
    :message="t('events.cancel_confirm')"
    :icon="XCircle"
    variant="error"
    :confirm-label="t('events.cancel_event')"
    @confirm="cancelEvent"
  />
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Calendar, CalendarDays, MapPin, Map, Video, Users, User, FileText, ArrowLeft,
  MessageCircle, AlertCircle, XCircle, Pencil, UserPlus, UserMinus, HelpCircle, Ticket
} from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'
import { useToastStore } from '~/stores/toast'
import StaticMapPreview from '~/components/IoT/StaticMapPreview.vue'

definePageMeta({
  keepalive: true
})

const route = useRoute()
const router = useRouter()
const localePath = useLocalePath()
const { t, locale } = useI18n()
const authStore = useAuthStore()
const toastStore = useToastStore()

// SSR-ready fetch (public data for SEO meta/JSON-LD)
const { data: event, pending: loading, error: fetchError } = await useAsyncData(
  `event-${route.params.id}`,
  () => $fetch(`/api/v1/geo/events/${route.params.id}/`)
)
const participants = ref([])
const error = computed(() => {
  if (!fetchError.value) return null
  const err = fetchError.value
  return err.data?.detail || err.message || 'Failed to load event'
})
const actionLoading = ref(false)
const cancelling = ref(false)
const showCancelEventConfirm = ref(false)

// Real-time updates
useObjectSubscription(event)

// SEO meta tags
useSeoMeta({
  title: () => event.value?.title ? `${event.value.title} - Parahub` : t('events.loading'),
  ogTitle: () => event.value?.title || t('events.page_title'),
  description: () => event.value?.description?.slice(0, 160) || t('events.meta_description'),
  ogDescription: () => event.value?.description?.slice(0, 160) || t('events.meta_description'),
  ogImage: () => event.value?.cover_image_url || '/og-image.jpg',
  ogType: 'website',
  twitterCard: 'summary_large_image',
})

// JSON-LD Event structured data
const _baseUrl = useRuntimeConfig().public.siteUrl || 'https://parahub.io'
useHead({
  script: computed(() => {
    if (!event.value) return []
    const baseUrl = _baseUrl

    const attendanceMap = {
      OFFLINE: 'https://schema.org/OfflineEventAttendanceMode',
      ONLINE: 'https://schema.org/OnlineEventAttendanceMode',
      HYBRID: 'https://schema.org/MixedEventAttendanceMode',
    }
    const statusMap = {
      PUBLISHED: 'https://schema.org/EventScheduled',
      CANCELLED: 'https://schema.org/EventCancelled',
    }

    const jsonLd = {
      '@context': 'https://schema.org',
      '@type': 'Event',
      'name': event.value.title,
      'url': `${baseUrl}/events/${event.value.id}`,
      'startDate': event.value.starts_at,
      'eventStatus': statusMap[event.value.status] || 'https://schema.org/EventScheduled',
      'eventAttendanceMode': attendanceMap[event.value.event_type] || attendanceMap.OFFLINE,
    }
    if (event.value.description) jsonLd.description = event.value.description
    if (event.value.ends_at) jsonLd.endDate = event.value.ends_at
    if (event.value.cover_image_url) jsonLd.image = event.value.cover_image_url

    // Location
    if (event.value.event_type !== 'ONLINE') {
      const loc = { '@type': 'Place' }
      if (event.value.world_object?.full_address) {
        loc.name = event.value.world_object.full_address
        loc.address = event.value.world_object.full_address
      } else if (event.value.location_name) {
        loc.name = event.value.location_name
      }
      const coords = event.value.location || event.value.world_object?.location
      if (coords) {
        loc.geo = {
          '@type': 'GeoCoordinates',
          'latitude': coords.lat,
          'longitude': coords.lon,
        }
      }
      jsonLd.location = loc
    }
    if (event.value.event_type !== 'OFFLINE' && event.value.online_url) {
      jsonLd.location = jsonLd.location || {}
      jsonLd.virtualLocation = {
        '@type': 'VirtualLocation',
        'url': event.value.online_url,
      }
    }

    // Organizer
    if (event.value.organizer) {
      jsonLd.organizer = {
        '@type': 'Person',
        'name': event.value.organizer.display_name || event.value.organizer.hna,
      }
    }

    return [{ type: 'application/ld+json', innerHTML: JSON.stringify(jsonLd) }]
  })
})

const eventTypeLabel = computed(() => {
  if (!event.value) return ''
  const labels = {
    OFFLINE: t('events.types.offline'),
    ONLINE: t('events.types.online'),
    HYBRID: t('events.types.hybrid')
  }
  return labels[event.value.event_type] || event.value.event_type
})

const eventTypeBadgeClass = computed(() => {
  if (!event.value) return ''
  const classes = {
    OFFLINE: 'bg-green-100 dark:bg-green-900/50 text-green-700 dark:text-green-400',
    ONLINE: 'bg-secondary-100 dark:bg-secondary-900/50 text-secondary-700 dark:text-secondary-400',
    HYBRID: 'bg-purple-100 dark:bg-purple-900/50 text-purple-700 dark:text-purple-400'
  }
  return classes[event.value.event_type] || 'bg-neutral-100 text-neutral-700'
})

const showTimezone = computed(() => {
  if (!event.value?.timezone) return false
  try {
    const localTz = Intl.DateTimeFormat().resolvedOptions().timeZone
    return event.value.timezone !== localTz
  } catch {
    return true
  }
})

const formattedDateLong = computed(() => {
  if (!event.value?.starts_at) return ''
  const date = new Date(event.value.starts_at)
  return date.toLocaleDateString(locale.value, {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
})

const formattedEndTime = computed(() => {
  if (!event.value?.ends_at) return ''
  const date = new Date(event.value.ends_at)
  return date.toLocaleTimeString(locale.value, {
    hour: '2-digit',
    minute: '2-digit'
  })
})

const eventCoords = computed(() => {
  if (!event.value) return null
  if (event.value.location) return event.value.location
  if (event.value.world_object?.location) return event.value.world_object.location
  return null
})

// Client-side re-fetch with auth (for is_organizer, my_participation_status, and after mutations)
const fetchEvent = async () => {
  try {
    const headers = {}
    if (authStore.isAuthenticated) {
      await authStore.ensureToken()
      if (authStore.token) {
        headers['Authorization'] = `Bearer ${authStore.token}`
      }
    }

    event.value = await $fetch(`/api/v1/geo/events/${route.params.id}/`, {
      credentials: 'include',
      headers
    })

    const participantsResponse = await $fetch(`/api/v1/geo/events/${route.params.id}/participants/`)
    participants.value = participantsResponse.items || []
  } catch (e) {
    console.error('Error fetching event:', e)
  }
}

const joinEvent = async (status) => {
  if (!authStore.isAuthenticated) {
    router.push(localePath('/login'))
    return
  }

  actionLoading.value = true
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/geo/events/${event.value.id}/join/`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
      body: { status }
    })

    toastStore.success(t('events.joined_successfully'))
    await fetchEvent()
  } catch (e) {
    console.error('Error joining event:', e)
    toastStore.error(e.data?.detail || t('events.join_failed'))
  } finally {
    actionLoading.value = false
  }
}

const leaveEvent = async () => {
  actionLoading.value = true
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/geo/events/${event.value.id}/leave/`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })

    toastStore.success(t('events.left_successfully'))
    await fetchEvent()
  } catch (e) {
    console.error('Error leaving event:', e)
    toastStore.error(e.data?.detail || t('events.leave_failed'))
  } finally {
    actionLoading.value = false
  }
}

const cancelEvent = async () => {
  showCancelEventConfirm.value = false
  cancelling.value = true
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/geo/events/${event.value.id}/cancel/`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })

    toastStore.success(t('events.cancelled_successfully'))
    await fetchEvent()
  } catch (e) {
    console.error('Error cancelling event:', e)
    toastStore.error(e.data?.detail || t('events.cancel_failed'))
  } finally {
    cancelling.value = false
  }
}

const showOnMap = () => {
  const location = event.value.location || (event.value.world_object ? {
    lat: event.value.world_object.location.lat,
    lon: event.value.world_object.location.lon
  } : null)

  if (location) {
    const query = {
      lat: location.lat.toFixed(6),
      lng: location.lon.toFixed(6),
      zoom: '16'
    }

    // Extract OSM way ID from xeno_id (format: "osm/<id>")
    const xenoId = event.value.world_object?.xeno_id
    if (xenoId) {
      const osmId = xenoId.split('/')[1]
      if (osmId) {
        query.layer = 'building'
        query.featureId = osmId
      }
    }

    router.push({ path: localePath('/map'), query })
  }
}

// ── Tickets ──
const eventTicketTypes = ref([])
const buyingTicketId = ref(null)
const buyingTicketType = ref(null)
const qrTicket = ref(null)

async function loadEventTicketTypes() {
  if (!event.value?.id) return
  try {
    const data = await $fetch(`/api/v1/tickets/types/`, {
      params: { event_id: event.value.id },
    })
    eventTicketTypes.value = data || []
  } catch {}
}

function startBuyTicket(tt) {
  if (!tt.operator_ln_address && !tt.operator_spark_address) {
    toastStore.error(t('tickets.error_no_ln_address'))
    return
  }
  buyingTicketId.value = tt.id
  buyingTicketType.value = tt
}

onMounted(() => {
  fetchEvent()
  loadEventTicketTypes()
})
</script>
