<template>
  <div
    v-if="data && data.available"
    class="weather-hud flex items-center gap-1.5 h-11 select-none"
    :title="detailTitle"
  >
    <!-- Condition icon (also conveys the condition; the word is in the tooltip) -->
    <component :is="stateIcon" class="w-5 h-5 shrink-0" />

    <!-- Temperature near the map centre -->
    <span class="text-sm font-semibold leading-none tabular-nums">{{ tempLabel }}</span>

    <!-- Wind: arrow points where it blows TO, speed alongside -->
    <ArrowUp class="w-3.5 h-3.5 shrink-0 transition-transform" :style="windStyle" />
    <span class="text-xs leading-none tabular-nums">{{ windLabel }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ArrowUp } from 'lucide-vue-next'
import type { WeatherData } from '~/composables/useMapWeather'

const props = defineProps<{ data: WeatherData | null }>()

// All presentation (icon, labels, wind rotation, tooltip) is shared with the
// transit-stop chip via useWeatherDisplay — this component only adds the floaty
// over-map chrome.
const { stateIcon, tempLabel, windStyle, windLabel, detailTitle } =
  useWeatherDisplay(computed(() => props.data))
</script>

<style scoped>
/* Monochrome text floating over the map — no card, no backdrop chip. Sized
   (h-11) to sit level with the zoom/layer control strip. Colour + legibility
   follow the map's own label convention (dark glyph #111827 + white halo), NOT
   the app theme: this text lives on the imagery/tiles, which stay the same in
   dark mode (the white halo carries it over dark tiles too), so it must match
   the surrounding POI/street labels rather than flip with the chrome. */
.weather-hud {
  color: #111827;
  --halo: rgba(255, 255, 255, 0.95);
  /* 4-way hard outline + a soft pass to fill the diagonals */
  text-shadow:
    1px 0 0 var(--halo), -1px 0 0 var(--halo),
    0 1px 0 var(--halo), 0 -1px 0 var(--halo),
    0 0 2px var(--halo);
}
/* Icons are strokes, not text — halo them with stacked hard drop-shadows. */
.weather-hud :deep(svg) {
  filter:
    drop-shadow(1px 0 0 var(--halo)) drop-shadow(-1px 0 0 var(--halo))
    drop-shadow(0 1px 0 var(--halo)) drop-shadow(0 -1px 0 var(--halo));
}
</style>
