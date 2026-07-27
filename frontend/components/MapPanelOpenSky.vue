<template>
  <div class="px-4 pt-2 space-y-4">
    <p class="text-sm text-neutral-600 dark:text-neutral-400">{{ t('map.opensky.panel_about') }}</p>

    <!-- Flight budget for the hovered tile (was the top-center hint bar) -->
    <div class="rounded-lg border border-neutral-200 dark:border-neutral-700 p-3">
      <template v-if="generating">
        <div class="flex items-center gap-2 text-sm text-neutral-600 dark:text-neutral-400" role="status">
          <Loader2 class="w-4 h-4 animate-spin" />
          <span>{{ t('map.opensky.generating') }}</span>
        </div>
      </template>
      <template v-else-if="budget">
        <div class="font-mono text-sm font-bold text-secondary dark:text-secondary-400 mb-2">Z17/{{ budget.x }}/{{ budget.y }}</div>
        <div class="space-y-1.5">
          <div v-for="row in budgetRows" :key="row.desc" class="flex items-center justify-between text-sm">
            <span class="text-neutral-500 dark:text-neutral-400">{{ row.desc }}</span>
            <span class="font-mono text-neutral-900 dark:text-neutral-100">{{ row.label }}</span>
          </div>
        </div>
        <p class="text-xs text-neutral-500 dark:text-neutral-400 italic mt-2">{{ t('map.opensky.click_to_download') }}</p>
      </template>
      <template v-else>
        <p class="text-sm text-neutral-500 dark:text-neutral-400 italic">{{ t('map.opensky.hover_hint') }}</p>
      </template>
    </div>

    <!-- Covered-tiles legend (yellow fill on the grid) -->
    <div class="flex items-start gap-2 text-xs text-neutral-500 dark:text-neutral-400">
      <span class="mt-0.5 w-3 h-3 rounded-sm flex-shrink-0 bg-yellow-400/40 border border-yellow-500" aria-hidden="true" />
      <span>{{ t('map.opensky.covered_legend') }}</span>
    </div>

    <UiAlert v-if="!authStore.isAuthenticated" variant="info">{{ t('map.opensky.login_note') }}</UiAlert>

    <UiButton variant="primary" :to="localePath('/opensky')" :icon="Plane" class="w-full">
      {{ t('map.opensky.dashboard_cta') }}
    </UiButton>
  </div>
</template>

<script setup lang="ts">
/**
 * Side-panel content for OpenSky mission planning mode (the tile-grid tool in
 * the map Tools matrix): what the grid is, live flight-budget readout for the
 * hovered Z17 tile, and the entry point to the OpenSky dashboard.
 */
import { computed } from 'vue'
import { Loader2, Plane } from 'lucide-vue-next'

const { t } = useI18n()
const localePath = useLocalePath()
const authStore = useAuthStore()

const props = defineProps<{
  budget: { battery1: number; battery3: number; battery5: number; x: number; y: number } | null
  generating: boolean
}>()

const budgetRows = computed(() => {
  const b = props.budget
  if (!b) return []
  return [
    { desc: t('map.opensky.ortho'), label: t('map.opensky.battery_level', { level: 1, min: b.battery1 }) },
    { desc: t('map.opensky.baseline_3d'), label: t('map.opensky.battery_level', { level: 3, min: b.battery3 }) },
    { desc: t('map.opensky.ultra_3d'), label: t('map.opensky.battery_level', { level: 5, min: b.battery5 }) },
  ]
})
</script>
