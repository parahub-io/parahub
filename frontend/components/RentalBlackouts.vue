<script setup lang="ts">
import { CalendarOff, Plus } from 'lucide-vue-next'

/**
 * Manager-only blackout editor for one bookable: list existing blocked day
 * ranges (AvailabilityException) and add/remove them. A blackout blocks new
 * bookings for those days (maintenance / holiday / personal use) but does NOT
 * cancel bookings already made — the API returns a conflict count we surface as
 * a warning. Self-loading by `bookableId`; emits `changed` after any mutation so
 * the parent refreshes its availability calendar.
 */
const props = defineProps<{ bookableId: string }>()
const emit = defineEmits<{ changed: [] }>()

const { t, locale } = useI18n()
const authStore = useAuthStore()
const toastStore = useToastStore()

const items = ref<any[]>([])
const loading = ref(false)
const adding = ref(false)

function localToday() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
const today = localToday()
const fromDate = ref(today)
const toDate = ref(today)
const reason = ref('')

// Keep the end on/after the start.
watch(fromDate, (v) => { if (toDate.value < v) toDate.value = v })

function authHeaders() {
  return { Authorization: `Bearer ${authStore.token}` }
}

function fmtDate(iso: string) {
  // Parse as local midnight so the displayed day never shifts by tz.
  return new Date(iso + 'T00:00:00').toLocaleDateString(locale.value, {
    day: 'numeric', month: 'short', year: 'numeric',
  })
}
function rangeLabel(ex: any) {
  return ex.start_date === ex.end_date
    ? fmtDate(ex.start_date)
    : `${fmtDate(ex.start_date)} – ${fmtDate(ex.end_date)}`
}

async function load() {
  if (!props.bookableId) { items.value = []; return }
  loading.value = true
  try {
    await authStore.ensureToken()
    items.value = await $fetch(`/api/v1/rental/bookables/${props.bookableId}/exceptions`, {
      credentials: 'include',
      headers: authHeaders(),
    })
  } catch (e: any) {
    toastStore.error(e?.data?.detail || t('booking.blackouts.error'))
  } finally {
    loading.value = false
  }
}

async function add() {
  if (!fromDate.value || !toDate.value) return
  adding.value = true
  try {
    await authStore.ensureToken()
    const res: any = await $fetch(`/api/v1/rental/bookables/${props.bookableId}/exceptions`, {
      method: 'POST',
      credentials: 'include',
      headers: authHeaders(),
      body: { start_date: fromDate.value, end_date: toDate.value, reason: reason.value.trim() },
    })
    if (res?.conflicts > 0) {
      toastStore.warning(t('booking.blackouts.conflict_warning', { count: res.conflicts }))
    } else {
      toastStore.success(t('booking.blackouts.added'))
    }
    reason.value = ''
    await load()
    emit('changed')
  } catch (e: any) {
    toastStore.error(e?.data?.detail || t('booking.blackouts.error'))
  } finally {
    adding.value = false
  }
}

// Two-tap delete (design-system: simple quick delete).
const confirmId = ref('')
let confirmTimer: any = null
async function remove(ex: any) {
  if (confirmId.value !== ex.id) {
    confirmId.value = ex.id
    clearTimeout(confirmTimer)
    confirmTimer = setTimeout(() => { confirmId.value = '' }, 3000)
    return
  }
  clearTimeout(confirmTimer)
  confirmId.value = ''
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/rental/bookables/${props.bookableId}/exceptions/${ex.id}`, {
      method: 'DELETE',
      credentials: 'include',
      headers: authHeaders(),
    })
    toastStore.success(t('booking.blackouts.removed'))
    await load()
    emit('changed')
  } catch (e: any) {
    toastStore.error(e?.data?.detail || t('booking.blackouts.error'))
  }
}

watch(() => props.bookableId, load)
onMounted(load)
</script>

<template>
  <div class="card p-4 mb-4">
    <h2 class="text-sm font-semibold mb-1 flex items-center gap-2">
      <CalendarOff class="w-4 h-4" /> {{ t('booking.blackouts.title') }}
    </h2>
    <p class="text-xs text-neutral-500 dark:text-neutral-400 mb-3">{{ t('booking.blackouts.hint') }}</p>

    <!-- Existing blackouts (flush list) -->
    <div v-if="items.length"
         class="border border-neutral-200 dark:border-neutral-700 rounded-lg divide-y divide-neutral-200 dark:divide-neutral-700 mb-3">
      <div v-for="ex in items" :key="ex.id" class="flex items-center justify-between gap-3 px-3 py-2">
        <div class="min-w-0">
          <div class="text-sm font-medium text-neutral-900 dark:text-neutral-100">{{ rangeLabel(ex) }}</div>
          <div v-if="ex.reason" class="text-xs text-neutral-500 dark:text-neutral-400 truncate">{{ ex.reason }}</div>
        </div>
        <UiButton :variant="confirmId === ex.id ? 'error' : 'outline-error'" size="sm" class="shrink-0" @click="remove(ex)">
          {{ confirmId === ex.id ? t('booking.blackouts.confirm_remove') : t('booking.blackouts.remove') }}
        </UiButton>
      </div>
    </div>
    <p v-else class="text-sm text-neutral-500 dark:text-neutral-400 mb-3">{{ t('booking.blackouts.empty') }}</p>

    <!-- Add a blackout -->
    <div class="flex flex-wrap items-end gap-2">
      <label class="flex flex-col gap-1">
        <span class="text-xs text-neutral-500 dark:text-neutral-400">{{ t('booking.blackouts.from') }}</span>
        <input v-model="fromDate" type="date" :min="today"
               class="h-10 px-3 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent" />
      </label>
      <label class="flex flex-col gap-1">
        <span class="text-xs text-neutral-500 dark:text-neutral-400">{{ t('booking.blackouts.to') }}</span>
        <input v-model="toDate" type="date" :min="fromDate || today"
               class="h-10 px-3 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent" />
      </label>
      <input v-model="reason" type="text" maxlength="255" :placeholder="t('booking.blackouts.reason_ph')"
             class="h-10 px-3 flex-1 min-w-[160px] border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent" />
      <UiButton variant="primary" :icon="Plus" :loading="adding" :disabled="adding || !fromDate || !toDate" @click="add">
        {{ adding ? t('booking.blackouts.adding') : t('booking.blackouts.add') }}
      </UiButton>
    </div>
  </div>
</template>
