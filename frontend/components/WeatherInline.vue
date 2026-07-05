<template>
  <!-- Compact weather readout for normal-UI surfaces (transit stop header, …).
       Same icon + temp + wind-arrow + speed as the map HUD, but styled to sit on
       a solid page background instead of floating over the map. -->
  <div
    v-if="data && data.available"
    class="inline-flex items-center gap-1.5 select-none"
    :title="detailTitle"
  >
    <component :is="stateIcon" class="w-5 h-5 shrink-0 text-amber-500 dark:text-amber-300" />
    <span class="text-sm font-semibold tabular-nums text-neutral-900 dark:text-neutral-100">{{ tempLabel }}</span>
    <ArrowUp class="w-3.5 h-3.5 shrink-0 text-sky-600 dark:text-sky-300" :style="windStyle" />
    <span class="text-xs tabular-nums text-neutral-500 dark:text-neutral-400">{{ windLabel }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ArrowUp } from 'lucide-vue-next'
import type { WeatherData } from '~/composables/useMapWeather'

const props = defineProps<{ data: WeatherData | null }>()

const { stateIcon, tempLabel, windStyle, windLabel, detailTitle } =
  useWeatherDisplay(computed(() => props.data))
</script>
