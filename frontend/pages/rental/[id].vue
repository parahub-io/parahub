<script setup lang="ts">
import { ArrowLeft, CalendarClock, Check, CalendarX2, ListChecks, Settings2 } from 'lucide-vue-next'

definePageMeta({ middleware: 'auth' })

const { t, locale } = useI18n()
const route = useRoute()
const localePath = useLocalePath()
const authStore = useAuthStore()
const toastStore = useToastStore()

const slugOrId = computed(() => route.params.id as string)

const loading = ref(true)
const notBookable = ref(false)
const notFound = ref(false)
const ctx = ref<any>(null)         // RentalContextResponse
const data = ref<any>(null)        // AvailabilityWindowResponse
// Bumped on any booking event so the manager inbox (RentalManagerInbox) re-fetches.
const bookingVersion = ref(0)

// The canonical item ULID (URL may carry the slug) — used for API + realtime.
const resolvedId = computed(() => ctx.value?.item_id || slugOrId.value)

const bookable = computed(() => data.value?.bookable)
const showSetup = computed(() =>
  ctx.value && !ctx.value.is_bookable && ctx.value.can_manage && ctx.value.has_rent_option)
const canManage = computed(() => !!ctx.value?.can_manage)

// ---- Setup / edit form (owner configures the bookable; shared fields live in
// <RentalAvailabilityForm>, reused by the initial setup and the edit panel) ----
interface AvailWindow { weekdays: number[]; start: string; stop: string; slotMinutes: number }
const defaultWindow = (): AvailWindow => ({ weekdays: [0, 1, 2, 3, 4, 5, 6], start: '09:00', stop: '18:00', slotMinutes: 60 })
const setupMode = ref<'RANGE' | 'SLOTS'>('RANGE')
const setupConfirmation = ref<'AUTO' | 'REQUEST'>('AUTO')
const setupTimezone = ref('Europe/Lisbon')
// One or more open envelopes (split shifts / per-day hours). Each → an Availability row.
const setupWindows = ref<AvailWindow[]>([defaultWindow()])
const saving = ref(false)

// Map the editable windows to the API availability payload (drop empty-weekday rows).
function availabilityPayload() {
  return setupWindows.value
    .filter(w => w.weekdays.length)
    .map(w => ({
      start: w.start, stop: w.stop, slot_minutes: w.slotMinutes,
      weekdays: [...w.weekdays].sort((a, b) => a - b),
    }))
}

// Owner edit panel (item already bookable)
const showSettings = ref(false)
const savingSettings = ref(false)

function fmtDateTime(iso: string) {
  return new Date(iso).toLocaleString(locale.value, {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
  })
}

// A booking was made via <RentalBookingSurface> → refresh the calendar + inbox.
async function onBooked() {
  await loadAvailability()
  bookingVersion.value++   // refresh the manager inbox
}

function authHeaders() {
  return { Authorization: `Bearer ${authStore.token}` }
}

async function loadContext() {
  ctx.value = await $fetch(`/api/v1/rental/items/${slugOrId.value}/context`, {
    credentials: 'include',
    headers: authHeaders(),
  })
  // Suggest a sensible default mode from the rent unit (hour → slots).
  setupMode.value = ctx.value?.unit === 'hour' ? 'SLOTS' : 'RANGE'
}

// The window the SLOTS grid currently shows — set by the surface's week-pager.
// Stored (not passed per-call) so every refresh (booking, realtime, inbox
// action) re-fetches the *visible* week, not a reset to "now".
const availRange = ref<{ frm?: string; to?: string }>({})
async function loadAvailability() {
  const now = new Date()
  const f = availRange.value.frm || now.toISOString()
  const tt = availRange.value.to || new Date(now.getTime() + 14 * 24 * 3600 * 1000).toISOString()
  data.value = await $fetch(`/api/v1/rental/items/${resolvedId.value}/availability`, {
    credentials: 'include',
    headers: authHeaders(),
    query: { frm: f, to: tt },
  })
}
// The booking surface drives which period the SLOTS grid shows.
function onRange(r: { frm: string; to: string }) { availRange.value = r; loadAvailability() }

async function load() {
  loading.value = true
  notBookable.value = false
  notFound.value = false
  try {
    await authStore.ensureToken()
    await loadContext()
    if (ctx.value.is_bookable) {
      await loadAvailability()
      if (ctx.value.can_manage) {
        prefillSettings()
      }
    } else if (!showSetup.value) {
      notBookable.value = true
    }
  } catch (e: any) {
    if (e?.response?.status === 404 || e?.status === 404) notFound.value = true
    else toastStore.error(e?.data?.detail || t('booking.error'))
  } finally {
    loading.value = false
  }
}

async function createBookable() {
  const availability = availabilityPayload()
  if (!availability.length) { toastStore.warning(t('booking.setup.pick_days')); return }
  saving.value = true
  try {
    await authStore.ensureToken()
    await $fetch('/api/v1/rental/bookables', {
      method: 'POST',
      credentials: 'include',
      headers: authHeaders(),
      body: {
        item_id: resolvedId.value,
        booking_mode: setupMode.value,
        timezone: setupTimezone.value,
        confirmation: setupConfirmation.value,
        availability,
      },
    })
    toastStore.success(t('booking.setup.created'))
    await load()
  } catch (e: any) {
    toastStore.error(e?.data?.detail || t('booking.setup.error'))
  } finally {
    saving.value = false
  }
}

// Pre-fill the edit panel from the live bookable + its open hours. The API
// returns open_hours flattened per weekday; regroup by (start, stop, slot) so
// each distinct envelope becomes one editable window again.
function prefillSettings() {
  const b = bookable.value
  if (!b) return
  setupMode.value = b.booking_mode
  setupConfirmation.value = b.confirmation
  setupTimezone.value = b.timezone
  const oh = data.value?.open_hours || []
  if (oh.length) {
    const byKey = new Map<string, AvailWindow>()
    for (const h of oh) {
      const start = String(h.start).slice(0, 5)
      const stop = String(h.stop).slice(0, 5)
      const slotMinutes = h.slot_minutes ?? 60
      const key = `${start}|${stop}|${slotMinutes}`
      if (!byKey.has(key)) byKey.set(key, { weekdays: [], start, stop, slotMinutes })
      byKey.get(key)!.weekdays.push(h.weekday)
    }
    setupWindows.value = [...byKey.values()].map(w => ({
      ...w, weekdays: [...new Set(w.weekdays)].sort((a, b) => a - b),
    }))
  } else {
    setupWindows.value = [defaultWindow()]
  }
}

async function saveSettings() {
  const b = bookable.value
  if (!b) return
  const availability = availabilityPayload()
  if (!availability.length) { toastStore.warning(t('booking.setup.pick_days')); return }
  savingSettings.value = true
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/rental/bookables/${b.id}`, {
      method: 'PATCH',
      credentials: 'include',
      headers: authHeaders(),
      body: {
        booking_mode: setupMode.value,
        confirmation: setupConfirmation.value,
        timezone: setupTimezone.value,
      },
    })
    await $fetch(`/api/v1/rental/bookables/${b.id}/availability`, {
      method: 'POST',
      credentials: 'include',
      headers: authHeaders(),
      body: availability,
    })
    toastStore.success(t('booking.settings.saved'))
    showSettings.value = false
    await load()
  } catch (e: any) {
    toastStore.error(e?.data?.detail || t('booking.settings.error'))
  } finally {
    savingSettings.value = false
  }
}

// Live calendar: refresh when anyone books/cancels this item (reuses the
// existing object:{ulid} realtime channel — backend publishes 'rental.booking')
const realtimeStore = useRealtimeStore()
const chime = useChime()
function onBookingEvent(ev: any) {
  if (ev?.item_id === resolvedId.value) {
    // Audible cue for the manager when a fresh booking lands (not on cancel/confirm).
    if (ev.event === 'created' && canManage.value) chime.play()
    loadAvailability()
    bookingVersion.value++   // refresh the manager inbox
  }
}
onMounted(async () => {
  await load()
  if (authStore.isAuthenticated && ctx.value?.item_id) {
    realtimeStore.connect()
    realtimeStore.on('rental.booking', onBookingEvent)
    realtimeStore.subscribe([ctx.value.item_id])
  }
})
onUnmounted(() => {
  realtimeStore.off('rental.booking', onBookingEvent)
  if (ctx.value?.item_id) realtimeStore.unsubscribe([ctx.value.item_id])
})
</script>

<template>
  <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
    <NuxtLink :to="localePath(`/market/${slugOrId}`)" class="inline-flex items-center gap-1 text-sm text-neutral-500 hover:text-neutral-900 dark:hover:text-neutral-100 mb-4">
      <ArrowLeft class="w-4 h-4" /> {{ t('booking.back_to_item') }}
    </NuxtLink>

    <div class="flex items-start justify-between gap-3 mb-6">
      <div class="min-w-0">
        <div class="flex items-center gap-1.5 text-sm font-medium text-neutral-500 mb-0.5">
          <CalendarClock class="w-4 h-4 shrink-0" />
          {{ showSetup ? t('booking.setup.title') : t('booking.title') }}
        </div>
        <h1 class="text-2xl font-bold truncate">
          <NuxtLink v-if="ctx?.item_title" :to="localePath(`/market/${ctx.slug || slugOrId}`)"
                    class="hover:text-secondary dark:hover:text-secondary-400 transition-colors">
            {{ ctx.item_title }}
          </NuxtLink>
          <template v-else>{{ t('booking.title') }}</template>
        </h1>
      </div>
      <div class="flex items-center gap-2 shrink-0">
        <UiButton v-if="canManage && bookable" variant="ghost" :icon="Settings2"
                  @click="showSettings = !showSettings">
          {{ t('booking.settings.button') }}
        </UiButton>
        <UiButton variant="ghost" :icon="ListChecks" :to="localePath({ path: '/market/my', query: { tab: 'bookings' } })">
          {{ t('booking.my_bookings_link') }}
        </UiButton>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="py-12 text-center" role="status" aria-live="polite">
      <div class="h-12 w-12 mx-auto border-4 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100 rounded-full animate-spin"></div>
      <span class="sr-only">{{ t('booking.loading') }}</span>
    </div>

    <!-- Item not found -->
    <UiAlert v-else-if="notFound" variant="warning" :icon="CalendarX2" :title="t('booking.not_found')" />

    <!-- Not bookable (and viewer can't set it up) -->
    <UiAlert v-else-if="notBookable" variant="info" :icon="CalendarX2"
             :title="ctx && !ctx.has_rent_option ? t('booking.not_for_rent') : t('booking.not_bookable')" />

    <!-- Owner setup: make this item bookable -->
    <template v-else-if="showSetup">
      <UiAlert variant="info" :icon="Settings2" :title="t('booking.setup.intro')" class="mb-4" />
      <div class="card p-4 space-y-5">
        <RentalAvailabilityForm
          v-model:mode="setupMode"
          v-model:confirmation="setupConfirmation"
          v-model:windows="setupWindows"
          v-model:timezone="setupTimezone" />

        <UiButton variant="success" :icon="Check" class="w-full" :loading="saving"
                  :disabled="saving" @click="createBookable">
          {{ saving ? t('booking.setup.saving') : t('booking.setup.submit') }}
        </UiButton>
      </div>
    </template>

    <!-- Booking surface -->
    <template v-else-if="bookable">
      <!-- Owner edit panel: change hours / days / mode after setup -->
      <div v-if="canManage && showSettings" class="card p-4 mb-4 space-y-5">
        <h2 class="text-sm font-semibold flex items-center gap-2">
          <Settings2 class="w-4 h-4" /> {{ t('booking.settings.title') }}
        </h2>
        <RentalAvailabilityForm
          v-model:mode="setupMode"
          v-model:confirmation="setupConfirmation"
          v-model:windows="setupWindows"
          v-model:timezone="setupTimezone" />
        <div class="flex gap-2">
          <UiButton variant="ghost" class="flex-1" :disabled="savingSettings" @click="showSettings = false">
            {{ t('booking.settings.cancel') }}
          </UiButton>
          <UiButton variant="success" :icon="Check" class="flex-1" :loading="savingSettings"
                    :disabled="savingSettings" @click="saveSettings">
            {{ savingSettings ? t('booking.settings.saving') : t('booking.settings.save') }}
          </UiButton>
        </div>
      </div>

      <!-- Renter booking surface (price + slot/range picker + recurrence + confirm);
           managers also get the walk-in path (book for an offline client) -->
      <RentalBookingSurface :item-id="resolvedId" :bookable="bookable" :slots="data.slots"
                            :can-manage="canManage" @booked="onBooked" @range="onRange" />

      <!-- Manager inbox -->
      <RentalManagerInbox v-if="canManage" :item-id="resolvedId" :reload-key="bookingVersion"
                          @changed="loadAvailability" />

      <!-- Blackout dates (block days for maintenance / holiday / personal use) -->
      <RentalBlackouts v-if="canManage && bookable" :bookable-id="bookable.id"
                       @changed="loadAvailability" />

      <!-- Occupied periods -->
      <div class="card p-4">
        <h2 class="text-sm font-semibold mb-3 flex items-center gap-2">
          <CalendarX2 class="w-4 h-4" /> {{ t('booking.occupied') }}
        </h2>
        <div v-if="!data.occupied.length" class="text-sm text-neutral-500">{{ t('booking.none_occupied') }}</div>
        <ul v-else class="space-y-1 text-sm">
          <li v-for="(o, i) in data.occupied" :key="i" class="flex items-center justify-between">
            <span>{{ fmtDateTime(o.start) }} → {{ fmtDateTime(o.end) }}</span>
            <UiBadge :variant="o.status === 'BLACKOUT' ? 'neutral' : 'warning'" type="soft" size="sm">
              {{ o.status === 'BLACKOUT' ? '—' : t('booking.status.' + o.status) }}
            </UiBadge>
          </li>
        </ul>
      </div>
    </template>
  </div>
</template>
