<template>
  <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
    <div class="stat-card">
      <Map class="w-8 h-8 text-primary" />
      <div class="text-2xl font-bold">{{ stats?.total_coverage_km2?.toFixed(1) || '0' }}</div>
      <div class="text-sm text-neutral-500">{{ $t('opensky.coverage_km2', 'km\u00B2 covered') }}</div>
    </div>
    <div class="stat-card">
      <Camera class="w-8 h-8 text-success" />
      <div class="text-2xl font-bold">{{ stats?.published_missions || 0 }}</div>
      <div class="text-sm text-neutral-500">{{ $t('opensky.missions', 'missions') }}</div>
    </div>
    <div class="stat-card">
      <Users class="w-8 h-8 text-secondary" />
      <div class="text-2xl font-bold">{{ stats?.total_pilots || 0 }}</div>
      <div class="text-sm text-neutral-500">{{ $t('opensky.pilots', 'pilots') }}</div>
    </div>
    <div class="stat-card">
      <component
        :is="processingIcon"
        class="w-8 h-8"
        :class="stats?.processing_missions || stats?.queued_missions ? 'text-warning animate-spin' : 'text-neutral-400'"
      />
      <div class="text-2xl font-bold">{{ (stats?.processing_missions || 0) + (stats?.queued_missions || 0) }}</div>
      <div class="text-sm text-neutral-500">{{ $t('opensky.processing', 'processing') }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Map, Camera, Users, Loader2, CheckCircle } from 'lucide-vue-next'
import type { OpenSkyStats } from '~/composables/useOpenSky'

const props = defineProps<{
  stats: OpenSkyStats | null
}>()

const processingIcon = computed(() => {
  if (props.stats?.processing_missions || props.stats?.queued_missions) {
    return Loader2
  }
  return CheckCircle
})
</script>

<style scoped>
.stat-card {
  @apply p-4 rounded-lg flex flex-col items-center justify-center text-center gap-2 bg-neutral-100 dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-700;
}
</style>
