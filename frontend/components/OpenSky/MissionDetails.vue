<template>
  <div class="space-y-3 font-mono">
    <!-- Readouts: tiles + logged date -->
    <div class="grid grid-cols-2 gap-x-3 gap-y-2">
      <div v-if="mission.tiles_count">
        <div class="text-[9px] uppercase tracking-[0.18em] text-neutral-400 dark:text-neutral-600">{{ $t('opensky.r_tiles', 'Tiles') }}</div>
        <div class="text-[12px] tabular-nums text-neutral-700 dark:text-neutral-200">{{ formatTilesCount(mission.tiles_count) }}</div>
      </div>
      <div>
        <div class="text-[9px] uppercase tracking-[0.18em] text-neutral-400 dark:text-neutral-600">{{ $t('opensky.r_logged', 'Uploaded') }}</div>
        <div class="text-[12px] tabular-nums text-neutral-700 dark:text-neutral-200">{{ loggedDate || '—' }}</div>
      </div>
    </div>

    <!-- Coverage compass rose (per-direction frame counts) -->
    <div v-if="mission.direction_counts">
      <div class="text-[9px] uppercase tracking-[0.18em] text-neutral-400 dark:text-neutral-600 mb-1.5 text-center">{{ $t('opensky.r_coverage', 'Coverage') }}</div>
      <div class="grid grid-cols-3 gap-1 w-[6.5rem] mx-auto">
        <span />
        <span :class="cellClass(c.n)" :title="`N: ${c.n}`">N</span>
        <span />
        <span :class="cellClass(c.w)" :title="`W: ${c.w}`">W</span>
        <span :class="cellClass(c.nadir)" :title="`2D: ${c.nadir}`">2D</span>
        <span :class="cellClass(c.e)" :title="`E: ${c.e}`">E</span>
        <span />
        <span :class="cellClass(c.s)" :title="`S: ${c.s}`">S</span>
        <span v-if="c.unknown > 0" :class="cellClass(c.unknown)" :title="`?: ${c.unknown}`">?</span>
        <span v-else />
      </div>
    </div>

    <!-- Actions (owner only) — uniform grid so columns always line up -->
    <div v-if="canDelete" class="grid grid-cols-2 gap-2 pt-1">
      <UiButton
        v-if="mission.mesh_status === 'MESH_READY'"
        variant="outline" size="sm" :icon="Box" class="w-full text-xs"
        @click="$emit('view-3d', mission.id)"
      >
        {{ $t('opensky.view_3d', 'View 3D') }}
      </UiButton>
      <UiButton
        v-if="mission.mesh_status === 'MESH_READY'"
        variant="outline" size="sm" :icon="Download" class="w-full text-xs"
        @click="$emit('download-3d', mission.id)"
      >
        {{ $t('opensky.download_3d', 'Download 3D') }}
      </UiButton>
      <UiButton
        v-if="mission.status === 'PUBLISHED'"
        variant="outline" size="sm" :icon="Plus" class="w-full text-xs"
        @click="$emit('add-photos', mission.id)"
      >
        {{ $t('opensky.add_photos', 'Add photos') }}
      </UiButton>
      <UiButton
        variant="outline-error" size="sm" :icon="Trash2" class="w-full text-xs"
        :class="{ 'col-span-2': mission.status !== 'PUBLISHED' }"
        @click="$emit('delete', mission.id)"
      >
        {{ $t('opensky.delete', 'Delete') }}
      </UiButton>
    </div>

    <!-- Satellite alignment (staff only, published missions only) -->
    <div v-if="canDelete && authStore.user?.is_staff && mission.status === 'PUBLISHED'" class="pt-2 border-t border-neutral-200 dark:border-neutral-800">
      <div v-if="satAlignState === 'checking'" class="flex items-center gap-2 text-[11px] text-neutral-500 py-1">
        <Loader2 class="w-3.5 h-3.5 animate-spin" />
        {{ $t('opensky.satellite_checking', 'Checking alignment...') }}
      </div>
      <div v-else-if="satAlignState === 'result' && satAlignResult" class="p-2 bg-neutral-100 dark:bg-neutral-800 rounded text-[12px] space-y-2">
        <p v-if="satAlignResult.needs_correction">
          {{ $t('opensky.satellite_offset_detected', 'Detected offset:') }} <strong class="tabular-nums">{{ satAlignResult.offset }}m</strong>
        </p>
        <p v-else class="text-success">{{ $t('opensky.satellite_aligned', 'Already well-aligned') }}</p>
        <div v-if="satAlignResult.needs_correction" class="flex gap-2">
          <UiButton variant="primary" size="sm" class="flex-1" @click="doApplySatelliteAlign">
            {{ $t('opensky.satellite_apply', 'Apply correction') }}
          </UiButton>
          <UiButton variant="outline" size="sm" @click="satAlignState = 'idle'">
            {{ $t('opensky.cancel', 'Cancel') }}
          </UiButton>
        </div>
      </div>
      <div v-else-if="satAlignState === 'applying'" class="flex items-center gap-2 text-[11px] text-warning py-1">
        <Loader2 class="w-3.5 h-3.5 animate-spin" />
        {{ $t('opensky.satellite_aligning', 'Aligning & retiling...') }}
      </div>
      <UiButton
        v-else
        variant="outline" size="sm" :icon="Satellite" class="w-full text-xs"
        @click="doCheckSatelliteAlign"
      >
        {{ $t('opensky.satellite_align_btn', 'Check GPS Offset') }}
      </UiButton>
      <p v-if="satAlignError" class="text-[11px] text-error mt-1">{{ satAlignError }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Box, Download, Loader2, Plus, Satellite, Trash2 } from 'lucide-vue-next'
import type { OpenSkyMission } from '~/composables/useOpenSky'

const props = defineProps<{
  mission: OpenSkyMission
  canDelete?: boolean
}>()

defineEmits<{
  'add-photos': [missionId: string]
  'download-3d': [missionId: string]
  'view-3d': [missionId: string]
  'delete': [missionId: string]
}>()

const { locale } = useI18n()
const authStore = useAuthStore()

const COVERAGE_THRESHOLD = 50 // must match DIRECTION_COVERAGE_THRESHOLD in geo/endpoints/opensky.py

const c = computed(() => {
  const d = props.mission.direction_counts || {}
  return {
    nadir: d.nadir || 0, n: d.n || 0, e: d.e || 0, s: d.s || 0, w: d.w || 0, unknown: d.unknown || 0,
  }
})

const loggedDate = computed(() => formatShortDate(props.mission.uploaded_at, locale.value))

const cellClass = (count: number) => {
  const base = 'h-7 flex items-center justify-center rounded text-[10px] font-semibold tabular-nums '
  if (count >= COVERAGE_THRESHOLD) return base + 'bg-primary text-neutral-900'
  if (count > 0) return base + 'border border-primary/50 text-neutral-700 dark:text-neutral-200'
  return base + 'border border-neutral-300 dark:border-neutral-700 text-neutral-400 dark:text-neutral-600'
}

// Satellite alignment (staff)
const { checkSatelliteAlign, applySatelliteAlign } = useOpenSky()
const satAlignState = ref<'idle' | 'checking' | 'result' | 'applying'>('idle')
const satAlignResult = ref<{ offset: number; dx: number; dy: number; needs_correction: boolean } | null>(null)
const satAlignError = ref('')

const doCheckSatelliteAlign = async () => {
  satAlignState.value = 'checking'
  satAlignError.value = ''
  try {
    satAlignResult.value = await checkSatelliteAlign(props.mission.id)
    satAlignState.value = 'result'
  } catch (e: any) {
    satAlignError.value = e?.data?.detail || e?.message || 'Failed to check alignment'
    satAlignState.value = 'idle'
  }
}

const doApplySatelliteAlign = async () => {
  satAlignState.value = 'applying'
  satAlignError.value = ''
  try {
    await applySatelliteAlign(props.mission.id)
  } catch (e: any) {
    satAlignError.value = e?.data?.detail || e?.message || 'Failed to apply'
    satAlignState.value = 'idle'
  }
}
</script>
