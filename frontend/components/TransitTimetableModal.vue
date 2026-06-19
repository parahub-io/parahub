<template>
  <Teleport to="body">
    <div class="fixed inset-0 z-50 flex items-end sm:items-center justify-center">
      <div class="fixed inset-0 bg-black/50" @click="$emit('close')"></div>
      <div class="relative bg-white dark:bg-neutral-900 w-full sm:max-w-2xl sm:rounded-xl rounded-t-xl max-h-[85vh] overflow-y-auto shadow-xl">
        <div class="sticky top-0 z-10 bg-white dark:bg-neutral-900 border-b border-neutral-200 dark:border-neutral-700 px-4 pt-3 pb-2">
          <div class="flex items-center justify-between gap-2">
            <div class="flex items-center gap-2 min-w-0">
              <span class="flex-shrink-0 inline-block px-2 py-0.5 rounded font-bold text-sm" :style="routeBadgeStyle(routeData)">{{ routeData.short_name }}</span>
              <h3 class="font-bold text-sm text-neutral-900 dark:text-neutral-100 truncate">{{ $t('transit.schedule') }}</h3>
            </div>
            <button ref="closeBtn" @click="$emit('close')" :aria-label="$t('common.close')" class="btn-ghost btn-icon btn-sm flex-shrink-0"><X class="w-4 h-4" /></button>
          </div>
          <!-- Next 7 concrete dates, not abstract weekdays — GTFS calendars are
               date-based (summer/school-period services differ between same weekdays). -->
          <div class="flex gap-1 mt-2 overflow-x-auto pb-1">
            <button
              v-for="d in dayChips"
              :key="d.iso"
              @click="$emit('update:date', d.iso)"
              class="flex flex-col items-center min-w-[3rem] px-2 py-1 rounded-lg border text-xs transition-colors flex-shrink-0"
              :class="d.iso === selectedDate
                ? 'border-secondary bg-secondary text-white'
                : 'border-neutral-200 dark:border-neutral-700 text-neutral-700 dark:text-neutral-300 hover:bg-primary-100 dark:hover:bg-primary-900/40'"
            >
              <span class="font-semibold uppercase">{{ d.weekday }}</span>
              <span :class="d.iso === selectedDate ? 'text-white/80' : 'text-neutral-400 dark:text-neutral-500'">{{ d.dayNum }}</span>
            </button>
          </div>
        </div>

        <div v-if="pending" class="flex justify-center py-12" role="status">
          <div class="animate-spin rounded-full h-6 w-6 border-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100"></div>
          <span class="sr-only">{{ $t('common.loading') }}</span>
        </div>

        <div v-else-if="!day?.directions?.length" class="py-12 px-4 text-center">
          <CalendarOff class="w-12 h-12 mx-auto text-neutral-300 dark:text-neutral-600 mb-3" />
          <h3 class="text-sm font-medium text-neutral-600 dark:text-neutral-400">{{ $t('transit.timetable_no_service') }}</h3>
        </div>

        <template v-else>
          <div class="px-4 py-4 grid grid-cols-1 gap-6" :class="{ 'sm:grid-cols-2': day.directions.length > 1 }">
            <div v-for="dir in day.directions" :key="dir.direction_id">
              <!-- Direction-specific arrow (→ outbound / ← inbound) + label: real
                   headsign when the feed provides one, else a localized there/back
                   word (Carris Lisboa ships empty trip_headsign feed-wide). -->
              <h4 class="text-sm font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                <component :is="dir.direction_id === 1 ? ArrowLeft : ArrowRight" class="w-4 h-4 flex-shrink-0" />
                <span class="truncate">{{ dir.headsign || $t(dir.direction_id === 1 ? 'transit.direction_inbound' : 'transit.direction_outbound') }}</span>
              </h4>
              <div class="space-y-1">
                <div v-for="row in hourRows(dir)" :key="row.hour" class="flex gap-3 text-sm leading-6">
                  <span class="w-6 flex-shrink-0 text-right font-bold tabular-nums text-neutral-900 dark:text-neutral-100">{{ row.hour }}</span>
                  <span class="flex flex-wrap gap-x-2.5 gap-y-0.5 min-w-0">
                    <span
                      v-for="(dep, i) in row.deps"
                      :key="i"
                      class="tabular-nums"
                      :class="isPast(dep.t) ? 'text-neutral-400 dark:text-neutral-600' : 'text-neutral-900 dark:text-neutral-100'"
                    >{{ dep.t.slice(3) }}<sup v-if="dep.v > 0" class="font-bold text-secondary dark:text-secondary-400">{{ dep.v }}</sup></span>
                  </span>
                </div>
              </div>
            </div>
          </div>
          <div v-if="legendVariants.length" class="px-4 pb-4 pt-3 mx-4 mb-0 border-t border-neutral-200 dark:border-neutral-700 space-y-1 -mt-1">
            <div v-for="lv in legendVariants" :key="lv.index" class="text-xs text-neutral-600 dark:text-neutral-400">
              <sup class="font-bold text-secondary dark:text-secondary-400">{{ lv.index }}</sup>
              <NuxtLink :to="localePath(`/transit/route/${lv.place_slug || city}/${lv.slug}`)" class="ml-1 text-link" @click="$emit('close')">{{ lv.long_name }}</NuxtLink>
            </div>
          </div>
        </template>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { X, ArrowRight, ArrowLeft, CalendarOff } from 'lucide-vue-next'

const props = defineProps<{
  routeData: any
  city: string
  slug: string
  selectedDate: string // ISO YYYY-MM-DD
}>()
const emit = defineEmits<{ close: []; 'update:date': [date: string] }>()

const { locale } = useI18n()
const localePath = useLocalePath()
const { routeBadgeStyle } = useTransitHelpers()

// One request for the whole 7-day window — switching days is pure client-side
// state, no refetch/flicker.
const data = ref<any>(null)
const pending = ref(true)

async function load() {
  pending.value = true
  try {
    data.value = await $fetch(
      `/api/v1/geo/transit/routes/${props.city}/${props.slug}/timetable/`
    )
  } catch {
    data.value = null
  }
  pending.value = false
}
load()

const day = computed(() =>
  data.value?.days?.find((d: any) => d.date === props.selectedDate) ?? null
)

// "Today" and "now" in the agency's timezone — a viewer in another zone must
// see the operator's clock, consistent with the rest of the transit pages.
function agencyParts(): { iso: string; hm: string } {
  const tz = props.routeData?.agency_timezone
  const now = new Date()
  try {
    return {
      iso: new Intl.DateTimeFormat('en-CA', { timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit' }).format(now),
      hm: new Intl.DateTimeFormat('en-GB', { timeZone: tz, hour: '2-digit', minute: '2-digit', hour12: false }).format(now),
    }
  } catch {
    return { iso: now.toISOString().slice(0, 10), hm: `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}` }
  }
}

const dayChips = computed(() => {
  const start = new Date(`${agencyParts().iso}T12:00:00`)
  const fmt = new Intl.DateTimeFormat(locale.value, { weekday: 'short' })
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(start.getTime() + i * 86400000)
    const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    return { iso, weekday: fmt.format(d).replace('.', ''), dayNum: d.getDate() }
  })
})

function hourRows(dir: any) {
  const rows: Record<string, { hour: string; deps: any[] }> = {}
  for (const dep of dir.departures) {
    const h = dep.t.slice(0, 2)
    ;(rows[h] ??= { hour: h, deps: [] }).deps.push(dep)
  }
  return Object.values(rows).sort((a, b) => a.hour.localeCompare(b.hour))
}

const nowHm = ref(agencyParts().hm)
function isPast(t: string): boolean {
  return !!day.value?.is_today && t < nowHm.value
}

// Non-canonical variants present in the shown day's departures; index = sup marker
const legendVariants = computed(() => {
  if (!day.value?.directions?.length) return []
  const used = new Set<number>()
  for (const dir of day.value.directions) for (const dep of dir.departures) used.add(dep.v)
  return (data.value?.variants ?? [])
    .map((v: any, index: number) => ({ ...v, index }))
    .filter((v: any) => v.index > 0 && used.has(v.index))
})

const closeBtn = ref<HTMLElement | null>(null)
function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
}
onMounted(() => {
  document.addEventListener('keydown', onKey)
  nowHm.value = agencyParts().hm
  closeBtn.value?.focus()
})
onUnmounted(() => document.removeEventListener('keydown', onKey))
</script>
