<template>
  <div>
    <!-- Loading → skeleton cards in the real grid layout (no spinner, no layout jump) -->
    <div v-if="loading" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5 items-start">
      <OpenSkyMissionCardSkeleton v-for="n in skeletonCount" :key="n" />
    </div>

    <!-- Empty state -->
    <div v-else-if="missions.length === 0" class="text-center py-12 text-neutral-500">
      <component :is="emptyIcon || Camera" class="w-12 h-12 mx-auto mb-4 opacity-50" />
      <h3 class="text-lg font-medium">{{ emptyTitle || $t('opensky.no_missions', 'No missions yet') }}</h3>
      <p class="text-sm mt-1">{{ emptyText || $t('opensky.be_first', 'Be the first to contribute aerial imagery!') }}</p>
    </div>

    <!-- Grid -->
    <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5 items-start">
      <OpenSkyMissionCardRecon
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
import type { Component } from 'vue'
import { Camera } from 'lucide-vue-next'
import type { OpenSkyMission } from '~/composables/useOpenSky'

withDefaults(defineProps<{
  missions: OpenSkyMission[]
  loading?: boolean
  canDelete?: boolean
  myProfileId?: string
  skeletonCount?: number
  emptyIcon?: Component
  emptyTitle?: string
  emptyText?: string
}>(), {
  skeletonCount: 4,
})

defineEmits<{
  delete: [missionId: string]
  'view-3d': [missionId: string]
  'download-3d': [missionId: string]
  'add-photos': [missionId: string]
}>()
</script>
