<template>
  <div>
    <!-- Loading state -->
    <div v-if="loading" class="py-12 text-center" role="status" aria-live="polite">
      <div class="animate-spin rounded-full h-12 w-12 mx-auto border-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-white" aria-hidden="true" />
      <span class="sr-only">{{ $t('common.loading') }}</span>
    </div>

    <!-- Error state -->
    <div v-else-if="error" class="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-12 text-center">
      <div class="w-16 h-16 mx-auto rounded-full bg-error-100 dark:bg-error-900/30 flex items-center justify-center mb-4">
        <AlertCircle class="w-8 h-8 text-error" aria-hidden="true" />
      </div>
      <h1 class="text-xl font-semibold text-neutral-800 dark:text-neutral-200 mb-2">
        {{ $t('events.error_loading') }}
      </h1>
      <p class="text-neutral-600 dark:text-neutral-400 mb-6">{{ error }}</p>
      <UiButton variant="primary" :to="localePath('/events')">
        {{ $t('events.back_to_events') }}
      </UiButton>
    </div>

    <!-- Event content -->
    <div v-else-if="event" class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
      <!-- Back link -->
      <NuxtLink
        :to="localePath('/events')"
        class="inline-flex items-center gap-1 text-sm text-neutral-500 dark:text-neutral-400 hover:text-secondary dark:hover:text-secondary-400 transition-colors mb-4"
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
        <!-- One wrapping row, not justify-between: a long title must push the
             badges to their own line instead of shoving them past the edge -->
        <div class="flex flex-wrap items-start gap-x-4 gap-y-2 mb-3">
          <h1 class="text-2xl md:text-3xl font-bold text-neutral-900 dark:text-neutral-100 min-w-0">
            {{ event.title }}
          </h1>
          <!-- Event type badge -->
          <div class="flex items-center gap-2 flex-shrink-0 ml-auto mt-1">
            <DemoBadge :is-demo="event.is_demo" />
            <UiBadge :variant="eventTypeBadgeVariant" type="soft" size="lg" class="gap-1.5">
              <component :is="eventTypeIcon" :size="14" aria-hidden="true" />
              {{ eventTypeLabel }}
            </UiBadge>
          </div>
        </div>

        <!-- Category -->
        <div v-if="event.category_name" class="flex items-center gap-2 text-neutral-600 dark:text-neutral-400">
          <span v-if="event.category_icon" class="text-xl">{{ event.category_icon }}</span>
          <span>{{ categoryLabel }}</span>
        </div>
      </div>

      <!-- Main content grid: flex on mobile (sidebar between key info and content), grid on lg -->
      <div class="flex flex-col lg:grid lg:grid-cols-3 gap-6">
        <!-- Key info: When, Where, Online link -->
        <div class="lg:col-span-2 space-y-6">
          <!-- Date & Time -->
          <div class="card p-5">
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
            class="card p-5"
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

            <!-- Map preview — the venue wears the same static-place square it
                 gets on /map and in the create picker (§ Map Markers) -->
            <div v-if="eventCoords" class="relative mt-3">
              <StaticMapPreview
                :latitude="eventCoords.lat"
                :longitude="eventCoords.lon"
                :height="180"
                hide-marker
              />
              <IoTSnapshotMarker
                shape="square"
                :size="PLACE_SQUARE_SIZE"
                fill="#4E4EC8"
                :glyph="CALENDAR_GLYPH"
              />
            </div>

            <!-- Show on map link -->
            <UiButton
              v-if="event.location || event.world_object"
              variant="ghost"
              size="sm"
              :icon="Map"
              class="mt-3 -ml-2"
              @click="showOnMap"
            >
              {{ $t('events.show_on_map') }}
            </UiButton>
          </div>

          <!-- Online link (online/hybrid) -->
          <div
            v-if="event.event_type !== 'OFFLINE' && event.online_url"
            class="card p-5"
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
          <div class="card p-5">
            <h3 class="text-sm text-neutral-500 mb-3">{{ $t('events.organizer') }}</h3>
            <div class="flex items-center gap-3">
              <NuxtLink :to="organizerPath" class="flex-shrink-0">
                <img
                  v-if="event.organizer.avatar_url"
                  :src="event.organizer.avatar_url"
                  :alt="event.organizer.hna"
                  class="w-12 h-12 rounded-full"
                />
                <div v-else class="w-12 h-12 rounded-full bg-neutral-200 dark:bg-neutral-700 flex items-center justify-center">
                  <User :size="24" class="text-neutral-500" />
                </div>
              </NuxtLink>
              <div class="min-w-0">
                <!-- Act-as: the establishment is credited on top, the person who
                     organizes it stays underneath — same order as market listings -->
                <NuxtLink
                  v-if="event.establishment_id"
                  :to="localePath(`/org/${event.establishment_slug || event.establishment_id}`)"
                  class="block font-medium text-neutral-900 dark:text-neutral-100 truncate hover:text-secondary dark:hover:text-secondary-400 transition-colors"
                >
                  {{ event.establishment_name }}
                </NuxtLink>
                <NuxtLink
                  :to="organizerPath"
                  class="block truncate hover:text-secondary dark:hover:text-secondary-400 transition-colors"
                  :class="event.establishment_id
                    ? 'text-sm text-neutral-500 dark:text-neutral-400'
                    : 'font-medium text-neutral-900 dark:text-neutral-100'"
                >
                  {{ event.organizer.display_name || event.organizer.hna }}
                </NuxtLink>
              </div>
            </div>
          </div>

          <!-- Join/Leave actions -->
          <div
            v-if="authStore.isAuthenticated && event.status === 'PUBLISHED'"
            class="card p-5"
          >
            <!-- User is organizer -->
            <template v-if="event.is_organizer">
              <p class="text-sm text-neutral-500 mb-3">{{ $t('events.you_are_organizer') }}</p>
              <div class="space-y-2">
                <UiButton
                  variant="outline"
                  :icon="Pencil"
                  :to="localePath(`/events/${event.id}/edit`)"
                  class="w-full !whitespace-normal min-w-0 text-center"
                >
                  {{ $t('events.edit_event') }}
                </UiButton>
                <UiButton
                  variant="outline-error"
                  :icon="XCircle"
                  :loading="cancelling"
                  class="w-full !whitespace-normal min-w-0 text-center"
                  @click="showCancelEventConfirm = true"
                >
                  {{ $t('events.cancel_event') }}
                </UiButton>
              </div>
            </template>

            <!-- User is participant -->
            <template v-else-if="event.my_participation_status && event.my_participation_status !== 'CANCELLED'">
              <p class="text-sm text-neutral-500 mb-3">
                {{ event.my_participation_status === 'GOING' ? $t('events.you_are_going') : $t('events.you_are_maybe') }}
              </p>
              <UiButton
                variant="outline-error"
                :icon="UserMinus"
                :loading="actionLoading"
                class="w-full !whitespace-normal min-w-0 text-center"
                @click="leaveEvent"
              >
                {{ $t('events.leave_event') }}
              </UiButton>
            </template>

            <!-- User can join -->
            <template v-else>
              <div class="space-y-2">
                <UiButton
                  variant="secondary"
                  :icon="UserPlus"
                  :disabled="event.is_full || actionLoading"
                  :loading="pendingJoinStatus === 'GOING'"
                  class="w-full !whitespace-normal min-w-0 text-center"
                  @click="joinEvent('GOING')"
                >
                  {{ event.is_full ? $t('events.full') : $t('events.join_going') }}
                </UiButton>
                <UiButton
                  variant="outline"
                  :icon="HelpCircle"
                  :disabled="actionLoading"
                  :loading="pendingJoinStatus === 'MAYBE'"
                  class="w-full !whitespace-normal min-w-0 text-center"
                  @click="joinEvent('MAYBE')"
                >
                  {{ $t('events.join_maybe') }}
                </UiButton>
              </div>
            </template>
          </div>

          <!-- Matrix chat link -->
          <div
            v-if="event.matrix_room_id && (event.is_organizer || event.my_participation_status === 'GOING')"
            class="card p-5"
          >
            <UiButton
              variant="secondary"
              :icon="MessageCircle"
              :to="localePath(`/chat?room_id=${event.matrix_room_id}`)"
              class="w-full !whitespace-normal min-w-0 text-center"
            >
              {{ $t('events.open_chat') }}
            </UiButton>
          </div>

          <!-- Views counter -->
          <div class="text-center text-sm text-neutral-500">
            {{ $t('events.views', { count: event.views_count }) }}
          </div>
        </div>

        <!-- Content: Description, Participants — below sidebar on mobile -->
        <div class="lg:col-span-2 space-y-6">
          <!-- Description -->
          <div class="card p-5">
            <h2 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-3 flex items-center gap-2">
              <FileText :size="20" />
              {{ $t('events.description') }}
            </h2>
            <div class="prose dark:prose-invert max-w-none text-neutral-700 dark:text-neutral-300 whitespace-pre-wrap">
              {{ event.description }}
            </div>
          </div>

          <!-- Tickets -->
          <div v-if="eventTicketTypes.length" class="card p-5">
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
          <div class="card p-5">
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
                    :to="localePath(`/@${p.profile_hna?.split('@')[0] || p.profile_id}`)"
                    class="text-neutral-900 dark:text-neutral-100 hover:underline"
                  >
                    {{ p.profile_display_name || p.profile_hna || p.profile_id }}
                  </NuxtLink>
                </div>
                <UiBadge v-if="p.status === 'MAYBE'" variant="warning" type="soft" size="sm">
                  {{ $t('events.maybe') }}
                </UiBadge>
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
  Calendar, CalendarDays, MapPin, Map, Video, Layers, Users, User, FileText, ArrowLeft,
  MessageCircle, AlertCircle, XCircle, Pencil, UserPlus, UserMinus, HelpCircle, Ticket
} from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'
import { useToastStore } from '~/stores/toast'
import StaticMapPreview from '~/components/IoT/StaticMapPreview.vue'
import { PLACE_SQUARE_SIZE, CALENDAR_GLYPH } from '~/composables/useMapToggleableLayer'

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
// Which join button is in flight — so only the pressed one spins
const pendingJoinStatus = ref(null)
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

// The API returns reference data in English (category_name); translate by slug
// via the localized category tree, falling back to the English name.
const { fetchCategory } = useCategories()
const categoryLabel = ref('')
watch([event, locale], async () => {
  const e = event.value
  const fallback = e?.category_name || ''
  if (!e?.category_slug) { categoryLabel.value = fallback; return }
  try { categoryLabel.value = (await fetchCategory(e.category_slug))?.name || fallback }
  catch { categoryLabel.value = fallback }
}, { immediate: true })

const organizerPath = computed(() => {
  const org = event.value?.organizer
  return org ? localePath(`/@${org.hna?.split('@')[0] || org.id}`) : ''
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

// Event type reads by glyph first, colour second — the <UiBadge> tokens are
// categorical, not semantic. Violet stays reserved for the market axis and
// yellow soft is sub-AA as label text, so HYBRID (= both) takes neutral.
const eventTypeBadgeVariant = computed(() => {
  const variants = { OFFLINE: 'success', ONLINE: 'info', HYBRID: 'neutral' }
  return variants[event.value?.event_type] || 'neutral'
})

const eventTypeIcon = computed(() => {
  const icons = { OFFLINE: MapPin, ONLINE: Video, HYBRID: Layers }
  return icons[event.value?.event_type] || Calendar
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
  pendingJoinStatus.value = status
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
    pendingJoinStatus.value = null
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
