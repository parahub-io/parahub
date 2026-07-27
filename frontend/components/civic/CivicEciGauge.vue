<template>
  <div class="mt-3 rounded-lg border border-secondary/30 bg-secondary/5 dark:bg-secondary/10 p-3">
    <div class="flex flex-wrap items-center justify-between gap-x-2 gap-y-1 mb-1.5">
      <span class="text-xs font-semibold text-secondary dark:text-secondary-300 inline-flex items-center gap-1">
        <Sparkles class="w-3.5 h-3.5" aria-hidden="true" />
        {{ $t('civic.eci.title') }}
      </span>
      <span class="text-xs text-neutral-500 dark:text-neutral-400">
        {{ $t('civic.eci.countries', { n: countries, total: COUNTRIES_NEEDED }) }}
      </span>
    </div>
    <div
      class="h-2 rounded-full bg-neutral-200 dark:bg-neutral-700 overflow-hidden"
      role="progressbar" :aria-valuenow="supporters" :aria-valuemin="0" :aria-valuemax="THRESHOLD"
    >
      <div class="h-full bg-secondary rounded-full transition-all duration-500" :style="{ width: pct + '%' }"></div>
    </div>
    <div class="mt-1.5 flex flex-wrap items-center justify-between gap-x-2">
      <span class="text-xs text-neutral-600 dark:text-neutral-300">
        {{ $t('civic.eci.supporters', { n: fmt(supporters), total: fmt(THRESHOLD) }) }}
      </span>
      <span class="text-[10px] text-neutral-400 dark:text-neutral-500" :title="$t('civic.eci.disclaimerHint')">
        {{ $t('civic.eci.disclaimer') }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Sparkles } from 'lucide-vue-next'

const props = withDefaults(defineProps<{ supporters?: number; countries?: number }>(), {
  supporters: 0,
  countries: 0,
})

const { t: $t, locale } = useI18n()

// A full European Citizens' Initiative needs 1,000,000 supporters across >=7 states.
const THRESHOLD = 1_000_000
const COUNTRIES_NEEDED = 7

const pct = computed(() => {
  const raw = (props.supporters / THRESHOLD) * 100
  // Keep a visible sliver once anyone supports, so the bar reads as "started"
  return props.supporters > 0 ? Math.min(100, Math.max(0.75, raw)) : 0
})

function fmt(n: number): string {
  return new Intl.NumberFormat(locale.value).format(n)
}
</script>
