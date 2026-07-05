<script setup lang="ts">
import { Inbox, CalendarOff, Repeat, User, Phone, FileSignature } from 'lucide-vue-next'

/**
 * Manager-only booking inbox for a single bookable item: every booking (all
 * statuses, newest first) with confirm / complete / cancel actions and a
 * cancel-with-reason modal. Self-loading by `itemId`; bump `reloadKey` to force
 * a refresh after a realtime event. Emits `changed` after any successful
 * transition so the parent can refresh its availability view.
 *
 * Shared by the per-item page (`pages/rental/[id].vue`) and the owner rental
 * board (`pages/rental/[type]/[id].vue`, org | person) — DRY, one management surface.
 */
const props = defineProps<{
  itemId: string
  reloadKey?: number | string   // bump to re-fetch (realtime / external booking)
}>()
const emit = defineEmits<{ changed: [] }>()

const { t, locale } = useI18n()
const authStore = useAuthStore()
const toastStore = useToastStore()
const localePath = useLocalePath()

const inbox = ref<any[]>([])
const loading = ref(false)

// Cancel-with-reason modal
const showCancel = ref(false)
const cancelPending = ref<any>(null)
const cancelNote = ref('')
const cancelSeries = ref(false)
const cancelling = ref(false)

function authHeaders() {
  return { Authorization: `Bearer ${authStore.token}` }
}

function fmtDateTime(iso: string) {
  return new Date(iso).toLocaleString(locale.value, {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
  })
}

async function loadInbox() {
  if (!props.itemId) { inbox.value = []; return }
  loading.value = true
  try {
    await authStore.ensureToken()
    inbox.value = await $fetch('/api/v1/rental/bookings/inbox', {
      credentials: 'include',
      headers: authHeaders(),
      query: { item_id: props.itemId },
    })
  } catch (e: any) {
    toastStore.error(e?.data?.detail || t('booking.error'))
  } finally {
    loading.value = false
  }
}

async function transition(bookingId: string, action: 'confirm' | 'cancel' | 'complete', note = '', series = false) {
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/rental/bookings/${bookingId}/${action}`, {
      method: 'POST',
      credentials: 'include',
      headers: authHeaders(),
      ...(action === 'cancel' ? { body: { note: note.trim(), series } } : {}),
    })
    toastStore.success(t('booking.manage.updated'))
    await loadInbox()
    emit('changed')   // let the parent refresh the calendar / occupancy
  } catch (e: any) {
    toastStore.error(e?.data?.detail || t('booking.error'))
  }
}

function askCancel(b: any) { cancelPending.value = b; cancelNote.value = ''; cancelSeries.value = false; showCancel.value = true }

async function doCancel() {
  if (!cancelPending.value) return
  cancelling.value = true
  try {
    await transition(cancelPending.value.id, 'cancel', cancelNote.value, cancelSeries.value)
  } finally {
    cancelling.value = false
    showCancel.value = false
  }
}

// Reload when the active item changes (board tab switch) or on a realtime bump.
watch(() => props.itemId, loadInbox)
watch(() => props.reloadKey, loadInbox)
onMounted(loadInbox)
</script>

<template>
  <div class="card p-4 mb-4">
    <h2 class="text-sm font-semibold mb-3 flex items-center gap-2">
      <Inbox class="w-4 h-4" /> {{ t('booking.manage.inbox') }}
    </h2>
    <div v-if="!inbox.length" class="text-sm text-neutral-500">{{ t('booking.manage.empty') }}</div>
    <ul v-else class="space-y-2 text-sm">
      <li v-for="b in inbox" :key="b.id" class="flex flex-wrap items-center justify-between gap-2 border-b border-neutral-100 dark:border-neutral-800 pb-2 last:border-0">
        <div class="min-w-0">
          <div>
            {{ fmtDateTime(b.start) }} → {{ fmtDateTime(b.end) }}
            <Repeat v-if="b.recurrence_group" class="inline w-3.5 h-3.5 ml-1 text-secondary align-text-bottom"
                    :title="t('booking.series')" :aria-label="t('booking.series')" />
          </div>
          <!-- Who booked — for a walk-in, the client name + a click-to-call phone -->
          <div v-if="b.renter_name" class="text-xs text-neutral-600 dark:text-neutral-300 flex items-center flex-wrap gap-x-2 gap-y-0.5 mt-0.5">
            <span class="inline-flex items-center gap-1"><User class="w-3 h-3 shrink-0" /> {{ b.renter_name }}</span>
            <UiBadge v-if="b.is_walk_in" variant="secondary" type="soft" size="sm">{{ t('booking.walk_in.tag') }}</UiBadge>
            <a v-if="b.client_phone" :href="`tel:${b.client_phone}`" class="inline-flex items-center gap-1 text-secondary hover:underline">
              <Phone class="w-3 h-3 shrink-0" /> {{ b.client_phone }}
            </a>
          </div>
          <div class="text-xs text-neutral-500" v-if="b.price_total != null">{{ b.price_total }} {{ b.currency }}<span v-if="b.msg"> · {{ b.msg }}</span></div>
          <div v-if="b.status === 'CANCELLED' && b.cancel_note" class="text-xs text-neutral-500 italic mt-0.5">
            {{ t('booking.cancel_reason') }}: {{ b.cancel_note }}
          </div>
        </div>
        <div class="flex items-center gap-2">
          <UiBadge :variant="b.status === 'CONFIRMED' ? 'success' : (b.status === 'REQUESTED' ? 'warning' : 'neutral')" type="soft" size="sm">
            {{ t('booking.status.' + b.status) }}
          </UiBadge>
          <UiButton v-if="b.status === 'REQUESTED'" size="sm" variant="success" @click="transition(b.id, 'confirm')">{{ t('booking.manage.confirm') }}</UiButton>
          <UiButton v-if="b.status === 'CONFIRMED'" size="sm" variant="secondary" @click="transition(b.id, 'complete')">{{ t('booking.manage.complete') }}</UiButton>
          <!-- Formalize a confirmed booking into a PGP-signed rental contract.
               Only for platform renters (walk-ins can't sign) not already formalized. -->
          <UiButton v-if="b.status === 'CONFIRMED' && b.renter_id && !b.contract_id"
                    :to="localePath(`/contracts?partner=${b.renter_id}&item=${b.item_id}&kind=rental&booking=${b.id}`)"
                    size="sm" variant="primary" :icon="FileSignature">{{ t('booking.manage.formalize') }}</UiButton>
          <UiButton v-if="b.status === 'REQUESTED' || b.status === 'CONFIRMED'" size="sm" variant="ghost" @click="askCancel(b)">{{ t('booking.cancel') }}</UiButton>
        </div>
      </li>
    </ul>

    <UiConfirmModal
      v-model="showCancel"
      :title="t('booking.cancel_confirm')"
      :icon="CalendarOff"
      variant="warning"
      :confirm-label="t('booking.cancel_yes')"
      :cancel-label="t('booking.keep')"
      :loading="cancelling"
      @confirm="doCancel"
    >
      <p class="text-sm text-neutral-500 dark:text-neutral-400 mb-3">{{ t('booking.cancel_confirm_msg') }}</p>
      <label v-if="cancelPending && cancelPending.recurrence_group" class="flex items-center gap-2 mb-3 text-sm">
        <input v-model="cancelSeries" type="checkbox"
               class="rounded border-neutral-300 dark:border-neutral-600 text-secondary focus:ring-secondary" />
        <span>{{ t('booking.cancel_series') }}</span>
      </label>
      <label class="block">
        <span class="text-sm font-medium">{{ t('booking.cancel_note') }}</span>
        <textarea v-model="cancelNote" rows="2" maxlength="255" :placeholder="t('booking.cancel_note_ph')"
                  class="mt-1 w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"></textarea>
      </label>
    </UiConfirmModal>
  </div>
</template>
