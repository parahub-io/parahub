<script setup lang="ts">
import { Check, Clock, CalendarRange, Repeat, LogIn, ChevronLeft, ChevronRight, UserPlus } from 'lucide-vue-next'

/**
 * The renter booking surface for a single bookable item: price header, the
 * RANGE date pickers or SLOTS day-grouped grid (with per-day occupancy badges),
 * a message field, the recurrence selector, live total, and the confirm button.
 *
 * Data is passed in (the parent owns loading + realtime); on a successful
 * booking the component emits `booked` so the parent can refresh availability.
 * Shared by the per-item page (`pages/rental/[id].vue`) and the owner rental
 * board (`pages/rental/[type]/[id].vue`, org | person) — DRY, one booking flow.
 */
const props = defineProps<{
  itemId: string       // resolved ULID used for the POST
  bookable: any        // { booking_mode, rent_amount, currency, unit }
  slots?: any[]        // SLOTS-mode availability (start/end/busy)
  canManage?: boolean  // owner/manager → unlocks the walk-in (book-for-a-client) path
}>()
const emit = defineEmits<{ booked: []; range: [{ frm: string; to: string }] }>()

const { t, locale } = useI18n()
const { priceAmount, pricingPeriod } = usePricingFormat()
const authStore = useAuthStore()
const toastStore = useToastStore()
const route = useRoute()
const localePath = useLocalePath()

// Every rent tier the owner listed (hour / half-day / weekend …) so the booking
// page shows the same variants as the market listing — not just the primary one.
// The live total still bills the primary tier (rent_amount/unit); the extra tiers
// are the owner's published rates. Falls back to the single snapshot fields if an
// older API response carries no `rent_options`.
const rentTiers = computed<any[]>(() => {
  const opts = props.bookable?.rent_options
  if (opts?.length) return opts
  if (props.bookable?.rent_amount != null) {
    return [{ type: 'rent', amount: props.bookable.rent_amount, currency: props.bookable.currency, unit: props.bookable.unit }]
  }
  return []
})

// Anonymous visitors land here from a shared link — they can browse availability
// but must sign in to actually book. Return them to this exact page afterwards.
const loginLink = computed(() => localePath(`/login?redirect=${encodeURIComponent(route.fullPath)}`))

const startLocal = ref('')
const endLocal = ref('')
const msg = ref('')
const selectedSlot = ref<any>(null)
const recurrence = ref<'NONE' | 'WEEKLY' | 'MONTHLY'>('NONE')
const repeatCount = ref(4)
const creating = ref(false)

// Walk-in / manual booking (owner-only): block a slot for an offline client who
// isn't a platform user. The backend takes renter=None + the client's name/phone.
const walkIn = ref(false)
const clientName = ref('')
const clientPhone = ref('')
const isWalkIn = computed(() => !!props.canManage && walkIn.value)

const isSlots = computed(() => props.bookable?.booking_mode === 'SLOTS')

// Live clock: a slot whose start has already passed is unbookable (backend
// rejects `start < now`, see rental.py:437), so grey it out in real time —
// re-evaluated each second, in sync with the RentalClock readout above.
// SSR-safe: `now` starts at 0 (nothing past) and is set on mount, so the
// server render and the hydration render agree.
const now = ref(0)
let clockTimer: ReturnType<typeof setInterval> | undefined
onMounted(() => {
  now.value = Date.now()
  clockTimer = setInterval(() => { now.value = Date.now() }, 1000)
})
onBeforeUnmount(() => { if (clockTimer) clearInterval(clockTimer) })
const isPast = (s: any) => now.value > 0 && new Date(s.start).getTime() <= now.value

// ---- SLOTS week-pager: page the visible window across the whole booking
// horizon (the grid otherwise only ever showed the first fortnight). The
// surface owns the offset; the parent re-fetches on @range. ----
const PAGE_DAYS = 14
const DAY_MS = 86400000
const periodOffset = ref(0)              // 0 = current fortnight
const pageBase = ref(0)                  // midnight today (ms), set on mount
const advanceDays = computed(() => props.bookable?.advance_window_days || 90)
const canPrev = computed(() => periodOffset.value > 0)
const canNext = computed(() => (periodOffset.value + 1) * PAGE_DAYS < advanceDays.value)
const periodLabel = computed(() => {
  if (!pageBase.value) return ''
  const startMs = pageBase.value + periodOffset.value * PAGE_DAYS * DAY_MS
  const endMs = startMs + (PAGE_DAYS - 1) * DAY_MS
  const fmt = (ms: number) => new Date(ms).toLocaleDateString(locale.value, { day: 'numeric', month: 'short' })
  return `${fmt(startMs)} – ${fmt(endMs)}`
})
function emitRange() {
  if (!pageBase.value) return
  const startMs = pageBase.value + periodOffset.value * PAGE_DAYS * DAY_MS
  // Offset 0 starts "now" (never offer already-past slots); later pages at midnight.
  const frm = periodOffset.value === 0 ? new Date() : new Date(startMs)
  const to = new Date(startMs + PAGE_DAYS * DAY_MS)
  emit('range', { frm: frm.toISOString(), to: to.toISOString() })
}
function goPrev() { if (canPrev.value) { periodOffset.value--; emitRange() } }
function goNext() { if (canNext.value) { periodOffset.value++; emitRange() } }
onMounted(() => { const d = new Date(); d.setHours(0, 0, 0, 0); pageBase.value = d.getTime() })

// ---- Live highlight: flash slots whose busy-state flipped under us (someone
// else booked/cancelled the same window). Diff against the previous slot set;
// only flash slots that already existed, so paging to a new week never flashes.
const flashing = ref<Set<string>>(new Set())
let prevAll: Set<string> | null = null
let prevBusy: Set<string> | null = null
const flashTimers = new Set<ReturnType<typeof setTimeout>>()
function flash(start: string) {
  flashing.value = new Set(flashing.value).add(start)
  const tid = setTimeout(() => {
    const s = new Set(flashing.value); s.delete(start); flashing.value = s; flashTimers.delete(tid)
  }, 1600)
  flashTimers.add(tid)
}
onBeforeUnmount(() => { flashTimers.forEach(clearTimeout) })

// A reload (new slots) invalidates any prior selection + drives the flash diff.
watch(() => props.slots, (slots) => {
  selectedSlot.value = null
  const list: any[] = slots || []
  const busyNow = new Set<string>(list.filter(s => s.busy).map(s => s.start))
  const allNow = new Set<string>(list.map(s => s.start))
  if (prevAll !== null && prevBusy !== null) {
    for (const st of busyNow) if (prevAll.has(st) && !prevBusy.has(st)) flash(st)  // free → busy
    for (const st of prevBusy) if (allNow.has(st) && !busyNow.has(st)) flash(st)   // busy → free
  }
  prevAll = allNow; prevBusy = busyNow
})
// Clock crossing the selected slot's start drops the (now-past) selection so
// the confirm button can't submit a booking the backend would reject.
watch(now, () => { if (selectedSlot.value && isPast(selectedSlot.value)) selectedSlot.value = null })

function isoFromLocal(s: string): string | null {
  if (!s) return null
  const d = new Date(s)
  return isNaN(d.getTime()) ? null : d.toISOString()
}

// Floor for the native datetime-local pickers — blocks picking the past at the
// browser level (also catches the 12 AM/PM trap: "12:04 AM" = 00:04 < now).
// Set on mount (client-only) to avoid an SSR hydration mismatch on `new Date()`.
function toLocalInput(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}
const minLocal = ref('')
onMounted(() => { minLocal.value = toLocalInput(new Date()) })
// Return can't precede pickup (nor the past); falls back to `now` until pickup is set.
const endMin = computed(() => startLocal.value || minLocal.value)

function billableUnits(startISO: string, endISO: string, unit: string): number {
  const sec = (new Date(endISO).getTime() - new Date(startISO).getTime()) / 1000
  if (sec <= 0) return 0
  let u: number
  if (unit === 'hour') u = sec / 3600
  else if (unit === 'month') u = sec / (3600 * 24 * 30)
  else if (unit === 'week') u = sec / (3600 * 24 * 7)
  else u = sec / (3600 * 24)
  return Math.max(1, Math.ceil(u - 1e-9))
}

const previewTotal = computed(() => {
  const b = props.bookable
  if (!b || b.rent_amount == null) return null
  let s: string | null = null, e: string | null = null
  if (isSlots.value) {
    if (!selectedSlot.value) return null
    s = selectedSlot.value.start; e = selectedSlot.value.end
  } else {
    s = isoFromLocal(startLocal.value); e = isoFromLocal(endLocal.value)
  }
  if (!s || !e) return null
  const units = billableUnits(s, e, b.unit)
  if (!units) return null
  return { amount: (Number(b.rent_amount) * units), currency: b.currency, units }
})

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString(locale.value, { weekday: 'short', day: 'numeric', month: 'short' })
}

// Group free/busy slots by day for the SLOTS grid (+ per-day occupancy badge).
const slotsByDay = computed(() => {
  const groups: Record<string, any[]> = {}
  for (const s of (props.slots || [])) {
    const key = new Date(s.start).toDateString()
    ;(groups[key] ||= []).push(s)
  }
  return Object.entries(groups).map(([k, slots]) => ({
    key: k, label: fmtDate(slots[0].start), slots,
    free: slots.filter((s: any) => !s.busy && !isPast(s)).length,
    total: slots.length,
  }))
})

// Confirm is enabled once a window is chosen — and, for a walk-in, once the
// client's name is filled in (the only extra required field).
const canSubmit = computed(() => {
  if (creating.value) return false
  if (isWalkIn.value && !clientName.value.trim()) return false
  return isSlots.value ? !!selectedSlot.value : !!(startLocal.value && endLocal.value)
})

function authHeaders() {
  return { Authorization: `Bearer ${authStore.token}` }
}

async function submit() {
  const b = props.bookable
  if (!b) return
  let s: string | null, e: string | null
  if (isSlots.value) {
    if (!selectedSlot.value) return
    s = selectedSlot.value.start; e = selectedSlot.value.end
  } else {
    s = isoFromLocal(startLocal.value); e = isoFromLocal(endLocal.value)
    if (!s || !e) { toastStore.warning(t('booking.pick_dates')); return }
  }
  if (isWalkIn.value && !clientName.value.trim()) { toastStore.warning(t('booking.walk_in.need_name')); return }
  creating.value = true
  try {
    await authStore.ensureToken()
    const isSeries = recurrence.value !== 'NONE' && repeatCount.value > 1
    const res: any = await $fetch('/api/v1/rental/bookings', {
      method: 'POST',
      credentials: 'include',
      headers: authHeaders(),
      body: {
        item_id: props.itemId, start: s, end: e, msg: msg.value,
        recurrence: recurrence.value,
        repeat: isSeries ? repeatCount.value : 1,
        external_renter_name: isWalkIn.value ? clientName.value.trim() : '',
        external_renter_phone: isWalkIn.value ? clientPhone.value.trim() : '',
      },
    })
    const made = res.bookings || []
    const skipped = res.skipped || []
    if (made.length > 1 || skipped.length) {
      let m = t('booking.series_made', { n: made.length })
      if (skipped.length) m += ' · ' + t('booking.series_skipped', { n: skipped.length })
      toastStore.success(m)
    } else if (isWalkIn.value) {
      toastStore.success(t('booking.walk_in.added'))
    } else {
      const primary = made[0]
      toastStore.success(primary?.status === 'CONFIRMED' ? t('booking.success') : t('booking.requested_success'))
    }
    selectedSlot.value = null; startLocal.value = ''; endLocal.value = ''; msg.value = ''
    recurrence.value = 'NONE'
    walkIn.value = false; clientName.value = ''; clientPhone.value = ''
    emit('booked')
  } catch (e: any) {
    toastStore.error(e?.data?.detail || t('booking.error'))
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <div>
    <!-- Price header: a single rate keeps the hero price; a multi-tier listing
         (hour / half-day / weekend …) lists every tier as an aligned table,
         mirroring the market page so the renter sees the same options. -->
    <div v-if="rentTiers.length" class="card p-4 mb-4">
      <template v-if="rentTiers.length > 1">
        <div class="text-xs font-semibold uppercase tracking-wide text-neutral-500 mb-2">{{ t('booking.rate_options') }}</div>
        <ul class="divide-y divide-neutral-100 dark:divide-neutral-800">
          <li v-for="(tier, i) in rentTiers" :key="i" class="flex items-center justify-between gap-4 py-1.5">
            <span class="text-sm text-neutral-600 dark:text-neutral-300">{{ pricingPeriod(tier) }}</span>
            <span class="text-sm font-semibold tabular-nums">{{ priceAmount(tier) }}</span>
          </li>
        </ul>
      </template>
      <div v-else class="text-lg font-semibold">
        {{ priceAmount(rentTiers[0]) }}
        <span class="text-sm font-normal text-neutral-500">{{ t('booking.per_unit', { unit: pricingPeriod(rentTiers[0]) }) }}</span>
      </div>
    </div>

    <!-- RANGE: date pickers -->
    <div v-if="!isSlots" class="card p-4 mb-4 space-y-4">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <h2 class="text-sm font-semibold flex items-center gap-2">
          <CalendarRange class="w-4 h-4" /> {{ t('booking.choose_period') }}
        </h2>
        <RentalClock />
      </div>
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <label class="block">
          <span class="text-sm font-medium">{{ t('booking.checkin') }}</span>
          <input v-model="startLocal" type="datetime-local" :min="minLocal"
                 class="mt-1 w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent" />
        </label>
        <label class="block">
          <span class="text-sm font-medium">{{ t('booking.checkout') }}</span>
          <input v-model="endLocal" type="datetime-local" :min="endMin"
                 class="mt-1 w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent" />
        </label>
      </div>
    </div>

    <!-- SLOTS: grid grouped by day -->
    <div v-else class="card p-4 mb-4 space-y-4">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <h2 class="text-sm font-semibold flex items-center gap-2">
          <Clock class="w-4 h-4" /> {{ t('booking.select_slot') }}
        </h2>
        <RentalClock />
      </div>

      <!-- Week pager: reach the whole booking horizon, not just the first fortnight -->
      <div class="flex items-center justify-between gap-2">
        <UiButton variant="ghost" size="sm" :disabled="!canPrev" @click="goPrev">
          <ChevronLeft class="w-4 h-4" /> {{ t('booking.period_prev') }}
        </UiButton>
        <span class="text-sm font-medium text-neutral-600 dark:text-neutral-300">{{ periodLabel }}</span>
        <UiButton variant="ghost" size="sm" :disabled="!canNext" @click="goNext">
          {{ t('booking.period_next') }} <ChevronRight class="w-4 h-4" />
        </UiButton>
      </div>

      <div v-if="!slotsByDay.length" class="text-sm text-neutral-500 py-4 text-center">{{ t('booking.no_free_slots') }}</div>
      <div v-for="day in slotsByDay" :key="day.key">
        <div class="flex items-center justify-between mb-2 gap-2">
          <span class="text-sm font-semibold capitalize">{{ day.label }}</span>
          <UiBadge :variant="day.free ? 'success' : 'neutral'" type="soft" size="sm">
            {{ day.free ? t('booking.n_free', { n: day.free }) : t('booking.all_busy') }}
          </UiBadge>
        </div>
        <div class="flex flex-wrap gap-2">
          <button
            v-for="(s, i) in day.slots" :key="i"
            type="button"
            :disabled="s.busy || isPast(s)"
            @click="selectedSlot = s"
            class="px-3 py-1.5 rounded-lg text-sm border transition"
            :class="[
              (s.busy || isPast(s))
                ? 'border-neutral-200 dark:border-neutral-700 text-neutral-400 line-through cursor-not-allowed'
                : (selectedSlot && selectedSlot.start === s.start
                    ? 'border-success bg-success text-white'
                    : 'border-neutral-300 dark:border-neutral-600 hover:border-success'),
              flashing.has(s.start) ? 'ring-2 ring-secondary' : '',
            ]"
          >
            {{ new Date(s.start).toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' }) }}
          </button>
        </div>
      </div>
    </div>

    <!-- Message + recurrence + total + confirm -->
    <div class="card p-4 mb-4 space-y-4">
      <!-- Walk-in (owner/manager only): block a slot for an offline / phone-in client -->
      <div v-if="canManage" class="rounded-lg border border-neutral-200 dark:border-neutral-700 p-3">
        <label class="flex items-center gap-2 text-sm font-medium cursor-pointer">
          <input v-model="walkIn" type="checkbox"
                 class="rounded border-neutral-300 dark:border-neutral-600 text-secondary focus:ring-secondary" />
          <UserPlus class="w-4 h-4 text-secondary" /> {{ t('booking.walk_in.toggle') }}
        </label>
        <div v-if="walkIn" class="mt-3 space-y-3">
          <p class="text-xs text-neutral-500">{{ t('booking.walk_in.hint') }}</p>
          <label class="block">
            <span class="text-sm font-medium">{{ t('booking.walk_in.name') }}</span>
            <input v-model="clientName" type="text" maxlength="120" :placeholder="t('booking.walk_in.name_ph')"
                   class="mt-1 w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent" />
          </label>
          <label class="block">
            <span class="text-sm font-medium">{{ t('booking.walk_in.phone') }}</span>
            <input v-model="clientPhone" type="tel" maxlength="40" :placeholder="t('booking.walk_in.phone_ph')"
                   class="mt-1 w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent" />
          </label>
        </div>
      </div>

      <label v-if="authStore.isAuthenticated" class="block">
        <span class="text-sm font-medium">{{ t('booking.message') }}</span>
        <input v-model="msg" type="text" :placeholder="t('booking.message_ph')" maxlength="255"
               class="mt-1 w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent" />
      </label>

      <!-- Recurrence: repeat the chosen window weekly/monthly -->
      <div v-if="authStore.isAuthenticated" class="flex flex-wrap items-end gap-3">
        <label class="block flex-1 min-w-[150px]">
          <span class="text-sm font-medium flex items-center gap-1.5"><Repeat class="w-3.5 h-3.5" /> {{ t('booking.repeat') }}</span>
          <select v-model="recurrence"
                  class="mt-1 w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent">
            <option value="NONE">{{ t('booking.repeat_none') }}</option>
            <option value="WEEKLY">{{ t('booking.repeat_weekly') }}</option>
            <option value="MONTHLY">{{ t('booking.repeat_monthly') }}</option>
          </select>
        </label>
        <label v-if="recurrence !== 'NONE'" class="block w-28">
          <span class="text-sm font-medium">{{ t('booking.repeat_count') }}</span>
          <input v-model.number="repeatCount" type="number" min="2" max="52"
                 class="mt-1 w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent" />
        </label>
      </div>

      <div v-if="previewTotal" class="flex items-center justify-between text-lg">
        <span class="text-neutral-500">{{ t('booking.total') }}</span>
        <span class="font-bold">{{ previewTotal.amount }} {{ previewTotal.currency }}</span>
      </div>
      <p v-if="recurrence !== 'NONE'" class="text-xs text-neutral-500">{{ t('booking.repeat_hint', { n: repeatCount }) }}</p>

      <UiButton v-if="authStore.isAuthenticated" variant="success" :icon="isWalkIn ? UserPlus : Check" class="w-full" :loading="creating"
                :disabled="!canSubmit"
                @click="submit">
        {{ creating ? t('booking.confirming') : (isWalkIn ? t('booking.walk_in.submit') : t('booking.confirm')) }}
      </UiButton>
      <UiButton v-else variant="primary" :icon="LogIn" class="w-full" :to="loginLink">
        {{ t('booking.login_to_book') }}
      </UiButton>
    </div>
  </div>
</template>
