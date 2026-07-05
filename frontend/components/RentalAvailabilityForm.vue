<script setup lang="ts">
// Shared availability fields for the rental owner — used both by the initial
// setup form and the owner edit panel on pages/rental/[id].vue.
//
// `windows` is a list of open envelopes: each carries its own weekdays + hours
// (+ slot length for SLOTS). Multiple windows express split shifts / lunch
// breaks (e.g. 09:00–13:00 and 14:00–18:00) and different hours per day — the
// backend stores one Availability row per window (set-semantics).
import { Plus, Trash2, Clock } from 'lucide-vue-next'

interface AvailWindow {
  weekdays: number[]
  start: string
  stop: string
  slotMinutes: number
}

const mode = defineModel<'RANGE' | 'SLOTS'>('mode', { required: true })
const confirmation = defineModel<'AUTO' | 'REQUEST'>('confirmation', { required: true })
const timezone = defineModel<string>('timezone', { required: true })
const windows = defineModel<AvailWindow[]>('windows', { required: true })

const { t, locale } = useI18n()

// Localized Mon..Sun short labels (2024-01-01 is a Monday)
const weekdayLabels = computed(() =>
  Array.from({ length: 7 }, (_, i) => {
    const d = new Date(Date.UTC(2024, 0, 1 + i))
    return new Intl.DateTimeFormat(locale.value, { weekday: 'short', timeZone: 'UTC' }).format(d)
  }))

function toggleWeekday(wi: number, day: number) {
  windows.value = windows.value.map((w, i) => {
    if (i !== wi) return w
    const weekdays = w.weekdays.includes(day)
      ? w.weekdays.filter(d => d !== day)
      : [...w.weekdays, day]
    return { ...w, weekdays }
  })
}

function addWindow() {
  windows.value = [...windows.value, { weekdays: [0, 1, 2, 3, 4, 5, 6], start: '09:00', stop: '18:00', slotMinutes: 60 }]
}

function removeWindow(wi: number) {
  if (windows.value.length <= 1) return
  windows.value = windows.value.filter((_, i) => i !== wi)
}
</script>

<template>
  <div class="space-y-5">
    <!-- Mode -->
    <div>
      <span class="text-sm font-medium block mb-2">{{ t('booking.setup.mode') }}</span>
      <div class="flex gap-2">
        <button v-for="m in (['RANGE','SLOTS'] as const)" :key="m" type="button"
                @click="mode = m"
                class="px-3 py-2 rounded-lg text-sm border transition flex-1"
                :class="mode === m
                  ? 'border-green-600 bg-green-600 text-white'
                  : 'border-neutral-300 dark:border-neutral-600 hover:border-green-600'">
          {{ t('booking.setup.mode_' + m.toLowerCase()) }}
        </button>
      </div>
      <p class="text-xs text-neutral-500 mt-1">{{ t('booking.setup.mode_hint_' + mode.toLowerCase()) }}</p>
    </div>

    <!-- Confirmation -->
    <div>
      <span class="text-sm font-medium block mb-2">{{ t('booking.setup.confirmation') }}</span>
      <div class="flex gap-2">
        <button v-for="c in (['AUTO','REQUEST'] as const)" :key="c" type="button"
                @click="confirmation = c"
                class="px-3 py-2 rounded-lg text-sm border transition flex-1"
                :class="confirmation === c
                  ? 'border-green-600 bg-green-600 text-white'
                  : 'border-neutral-300 dark:border-neutral-600 hover:border-green-600'">
          {{ t('booking.setup.confirm_' + c.toLowerCase()) }}
        </button>
      </div>
    </div>

    <!-- Windows: one open envelope per row (split shifts / per-day hours) -->
    <div>
      <span class="text-sm font-medium block mb-2">{{ t('booking.setup.windows') }}</span>
      <div class="space-y-3">
        <div v-for="(win, wi) in windows" :key="wi"
             class="rounded-lg border border-neutral-200 dark:border-neutral-700 p-3 space-y-3">
          <div class="flex items-center justify-between gap-2">
            <span class="text-xs font-medium text-neutral-500 flex items-center gap-1.5">
              <Clock class="w-3.5 h-3.5" /> {{ t('booking.setup.window_n', { n: wi + 1 }) }}
            </span>
            <UiButton v-if="windows.length > 1" variant="ghost" size="sm" :icon="Trash2"
                      @click="removeWindow(wi)">
              {{ t('booking.setup.remove_window') }}
            </UiButton>
          </div>

          <!-- Weekdays for this window -->
          <div class="flex flex-wrap gap-2">
            <button v-for="(lbl, i) in weekdayLabels" :key="i" type="button"
                    @click="toggleWeekday(wi, i)"
                    class="px-3 py-1.5 rounded-lg text-sm border capitalize transition"
                    :class="win.weekdays.includes(i)
                      ? 'border-green-600 bg-green-600 text-white'
                      : 'border-neutral-300 dark:border-neutral-600 hover:border-green-600'">
              {{ lbl }}
            </button>
          </div>

          <!-- Hours (+ slot length for SLOTS) -->
          <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <label class="block">
              <span class="text-sm font-medium">{{ t('booking.setup.open_from') }}</span>
              <input v-model="win.start" type="time"
                     class="mt-1 w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 px-3 py-2" />
            </label>
            <label class="block">
              <span class="text-sm font-medium">{{ t('booking.setup.open_to') }}</span>
              <input v-model="win.stop" type="time"
                     class="mt-1 w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 px-3 py-2" />
            </label>
            <label v-if="mode === 'SLOTS'" class="block">
              <span class="text-sm font-medium">{{ t('booking.setup.slot_minutes') }}</span>
              <input v-model.number="win.slotMinutes" type="number" min="5" step="5"
                     class="mt-1 w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 px-3 py-2" />
            </label>
          </div>
        </div>
      </div>

      <UiButton variant="ghost" size="sm" :icon="Plus" class="mt-3" @click="addWindow">
        {{ t('booking.setup.add_window') }}
      </UiButton>
    </div>

    <!-- Timezone -->
    <label class="block">
      <span class="text-sm font-medium">{{ t('booking.setup.timezone') }}</span>
      <input v-model="timezone" type="text" placeholder="Europe/Lisbon"
             class="mt-1 w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 px-3 py-2" />
    </label>
  </div>
</template>
