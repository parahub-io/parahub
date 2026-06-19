<template>
  <!-- Compact instrument strip: one thin row instead of four tall cards -->
  <div class="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-lg border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-900 px-4 py-2.5">
    <div class="flex items-center gap-1.5">
      <Map class="w-4 h-4 shrink-0 text-primary" />
      <span class="text-lg font-bold tabular-nums leading-none">{{ stats?.total_coverage_km2?.toFixed(1) || '0' }}</span>
      <span class="text-xs text-neutral-500 dark:text-neutral-400">{{ $t('opensky.coverage_km2', 'km² covered') }}</span>
    </div>

    <div class="flex items-center gap-1.5">
      <Camera class="w-4 h-4 shrink-0 text-success" />
      <span class="text-lg font-bold tabular-nums leading-none">{{ stats?.published_missions || 0 }}</span>
      <span class="text-xs text-neutral-500 dark:text-neutral-400">{{ $t('opensky.missions', 'missions') }}</span>
    </div>

    <div class="flex items-center gap-1.5">
      <Users class="w-4 h-4 shrink-0 text-secondary" />
      <span class="text-lg font-bold tabular-nums leading-none">{{ stats?.total_pilots || 0 }}</span>
      <span class="text-xs text-neutral-500 dark:text-neutral-400">{{ $t('opensky.pilots', 'pilots') }}</span>
    </div>

    <!-- Processing: only surfaced while something is actually in flight -->
    <div v-if="processingCount > 0" class="flex items-center gap-1.5">
      <Loader2 class="w-4 h-4 shrink-0 text-warning animate-spin" />
      <span class="text-lg font-bold tabular-nums leading-none">{{ processingCount }}</span>
      <span class="text-xs text-neutral-500 dark:text-neutral-400">{{ $t('opensky.processing', 'processing') }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Map, Camera, Users, Loader2 } from 'lucide-vue-next'
import type { OpenSkyStats } from '~/composables/useOpenSky'

const props = defineProps<{
  stats: OpenSkyStats | null
}>()

const processingCount = computed(
  () => (props.stats?.processing_missions || 0) + (props.stats?.queued_missions || 0),
)
</script>
