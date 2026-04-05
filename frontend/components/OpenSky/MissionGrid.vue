<template>
  <div>
    <!-- Loading -->
    <div v-if="loading" class="py-12 text-center">
      <div class="inline-block animate-spin rounded-full h-12 w-12 border-4 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100" role="status"><span class="sr-only">Loading...</span></div>
    </div>

    <!-- Empty state -->
    <div v-else-if="missions.length === 0" class="text-center py-12 text-neutral-500">
      <Camera class="w-12 h-12 mx-auto mb-4 opacity-50" />
      <h3 class="text-lg font-medium">{{ $t('opensky.no_missions', 'No missions yet') }}</h3>
      <p class="text-sm mt-1">{{ $t('opensky.be_first', 'Be the first to contribute aerial imagery!') }}</p>
    </div>

    <!-- Grid -->
    <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
      <OpenSkyMissionCard
        v-for="mission in missions"
        :key="mission.id"
        :mission="mission"
        :can-delete="canDelete || (myProfileId != null && mission.pilot_id === myProfileId)"
        @delete="$emit('delete', $event)"
        @view-3d="$emit('view-3d', $event)"
        @download-3d="$emit('download-3d', $event)"
        @add-photos="$emit('add-photos', $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { Camera } from 'lucide-vue-next'
import type { OpenSkyMission } from '~/composables/useOpenSky'

defineProps<{
  missions: OpenSkyMission[]
  loading?: boolean
  canDelete?: boolean
  myProfileId?: string
}>()

defineEmits<{
  delete: [missionId: string]
  'view-3d': [missionId: string]
  'download-3d': [missionId: string]
  'add-photos': [missionId: string]
}>()
</script>
