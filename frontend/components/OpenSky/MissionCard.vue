<template>
  <div class="card overflow-hidden hover:border-primary transition-colors">
    <!-- Mission Preview (tile thumbnail or placeholder) -->
    <div
      class="aspect-video bg-neutral-200 dark:bg-neutral-700 relative bg-cover bg-center"
      :style="thumbnailStyle"
    >
      <div v-if="!hasThumbnail" class="absolute inset-0 flex items-center justify-center">
        <Camera class="w-12 h-12 text-neutral-400" />
      </div>

      <!-- Status Badge -->
      <div
        class="absolute top-2 right-2 px-2 py-1 rounded text-xs font-medium"
        :class="statusClass"
      >
        {{ $t(`opensky.status_${mission.status.toLowerCase()}`, mission.status) }}
      </div>

      <!-- Processing progress bar -->
      <div v-if="mission.status === 'PROCESSING'" class="absolute bottom-0 left-0 right-0 h-1 bg-warning/20">
        <div
          class="h-full bg-warning transition-all duration-1000 ease-in-out animate-[pulse-bar_2s_ease-in-out_infinite]"
          :style="{ width: stepProgress + '%' }"
        />
      </div>
    </div>

    <!-- Mission Info -->
    <div class="p-4">
      <h3 class="font-semibold text-lg truncate" :title="mission.name">
        {{ mission.name || `Mission ${mission.id.slice(0, 8)}` }}
      </h3>

      <div class="mt-2 space-y-1 text-sm text-neutral-600 dark:text-neutral-400">
        <!-- Pilot -->
        <div v-if="mission.pilot_name" class="flex items-center gap-2">
          <User class="w-4 h-4" />
          <NuxtLink
            v-if="mission.pilot_id"
            :to="`/u/${mission.pilot_id}`"
            class="hover:text-secondary hover:underline transition-colors"
          >
            {{ mission.pilot_name }}
          </NuxtLink>
          <span v-else>{{ mission.pilot_name }}</span>
        </div>

        <!-- Photos count -->
        <div class="flex items-center gap-2">
          <Image class="w-4 h-4" />
          <span>{{ mission.source_photos_count }} {{ $t('opensky.photos', 'photos') }}</span>
        </div>

        <!-- Tiles count (if published) -->
        <div v-if="mission.status === 'PUBLISHED' && mission.tiles_count" class="flex items-center gap-2">
          <Grid class="w-4 h-4" />
          <span>{{ formatTilesCount(mission.tiles_count) }} {{ $t('opensky.tiles', 'tiles') }}</span>
        </div>

        <!-- Tile -->
        <div v-if="mission.tile_z != null" class="flex items-center gap-2">
          <Grid class="w-4 h-4" />
          <span class="font-mono text-xs">Z{{ mission.tile_z }} {{ mission.tile_x }}/{{ mission.tile_y }}</span>
        </div>

        <!-- Date -->
        <div class="flex items-center gap-2">
          <Calendar class="w-4 h-4" />
          <span>{{ formatDate(mission.published_at || mission.uploaded_at) }}</span>
        </div>

        <!-- Processing progress (elapsed + step) -->
        <div v-if="(mission.status === 'PROCESSING' || mission.status === 'QUEUED') && mission.processing_started_at" class="flex items-center gap-2 text-warning">
          <Clock class="w-4 h-4 animate-pulse" />
          <span class="font-medium">{{ elapsedTime }}</span>
          <span v-if="mission.processing_step" class="text-neutral-500 dark:text-neutral-400">
            &mdash; {{ stepLabel }}
          </span>
        </div>
        <div v-else-if="mission.status === 'QUEUED'" class="flex items-center gap-2 text-secondary">
          <Clock class="w-4 h-4" />
          <span>{{ $t('opensky.waiting_in_queue', 'Waiting in queue') }}</span>
        </div>
      </div>

      <!-- Actions -->
      <div class="mt-4 flex items-center gap-2">
        <UiButton
          v-if="mission.status === 'PUBLISHED' && mission.center_lat && mission.center_lng"
          variant="primary"
          size="sm"
          :icon="Map"
          class="flex-1"
          @click="viewOnMap"
        >
          {{ $t('opensky.view_on_map', 'View on Map') }}
        </UiButton>

        <UiButton
          v-if="canDelete"
          variant="ghost"
          size="sm"
          :icon="Trash2"
          icon-only
          class="text-error"
          :title="$t('opensky.delete', 'Delete')"
          @click="$emit('delete', mission.id)"
        />
      </div>

      <!-- 3D Mesh Actions (visible only for own published missions with mesh ready) -->
      <div v-if="canDelete && mission.status === 'PUBLISHED' && mission.mesh_status === 'MESH_READY'" class="mt-2 flex items-center gap-2">
        <UiButton
          variant="outline"
          size="sm"
          :icon="Box"
          class="flex-1"
          @click="$emit('view-3d', mission.id)"
        >
          {{ $t('opensky.view_3d', 'View 3D') }}
        </UiButton>
        <UiButton
          variant="ghost"
          size="sm"
          :icon="Download"
          icon-only
          :title="$t('opensky.download_3d', 'Download 3D')"
          @click="$emit('download-3d', mission.id)"
        />
      </div>

      <!-- Satellite Alignment (staff only) -->
      <div v-if="canDelete && mission.status === 'PUBLISHED' && authStore.user?.is_staff" class="mt-2">
        <div v-if="satAlignState === 'checking'" class="flex items-center gap-2 text-sm text-neutral-500 py-2">
          <Loader2 class="w-4 h-4 animate-spin" />
          {{ $t('opensky.satellite_checking', 'Checking alignment...') }}
        </div>
        <div v-else-if="satAlignState === 'result' && satAlignResult" class="p-2 bg-neutral-100 dark:bg-neutral-700 rounded text-sm space-y-2">
          <p v-if="satAlignResult.needs_correction">
            {{ $t('opensky.satellite_offset_detected', 'Detected offset:') }} <strong>{{ satAlignResult.offset }}m</strong>
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
        <div v-else-if="satAlignState === 'applying'" class="flex items-center gap-2 text-sm text-warning py-2">
          <Loader2 class="w-4 h-4 animate-spin" />
          {{ $t('opensky.satellite_aligning', 'Aligning & retiling...') }}
        </div>
        <div v-else class="space-y-1">
          <UiButton
            variant="outline"
            size="sm"
            :icon="Satellite"
            class="w-full"
            :title="$t('opensky.satellite_align_tooltip', 'Check and correct GPS offset using satellite imagery')"
            @click="doCheckSatelliteAlign"
          >
            {{ $t('opensky.satellite_align_btn', 'Check GPS Offset') }}
          </UiButton>
          <p v-if="satAlignError" class="text-xs text-error px-1">{{ satAlignError }}</p>
        </div>
      </div>

      <!-- Oblique hint: show for own published missions with low photo count (likely nadir-only) -->
      <div
        v-if="canDelete && mission.status === 'PUBLISHED' && mission.source_photos_count <= 150"
        class="mt-2 p-2 bg-secondary-50 dark:bg-secondary-900/20 rounded text-xs text-secondary-700 dark:text-secondary-300"
      >
        <p>{{ $t('opensky.oblique_hint', 'Want richer 3D? Fly the oblique mission for this cell and add photos.') }}</p>
        <button
          @click="$emit('add-photos', mission.id)"
          class="mt-1 text-link"
        >
          {{ $t('opensky.add_photos', 'Add photos') }}
        </button>
      </div>

      <!-- Mesh error message -->
      <UiAlert v-if="mission.mesh_status === 'MESH_FAILED' && mission.mesh_error_message" variant="error" class="mt-2">
        {{ mission.mesh_error_message }}
      </UiAlert>

      <!-- Error message (if failed) -->
      <UiAlert v-if="mission.status === 'FAILED' && mission.error_message" variant="error" class="mt-3">
        {{ mission.error_message }}
      </UiAlert>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Camera, User, Image, Grid, Calendar, Map, Trash2, Box, Download, Loader2, Clock, Satellite } from 'lucide-vue-next'
import type { OpenSkyMission } from '~/composables/useOpenSky'

const props = defineProps<{
  mission: OpenSkyMission
  canDelete?: boolean
}>()

defineEmits<{
  delete: [missionId: string]
  'view-3d': [missionId: string]
  'download-3d': [missionId: string]
  'add-photos': [missionId: string]
}>()

const router = useRouter()
const localePath = useLocalePath()
const authStore = useAuthStore()

// Elapsed time ticker (updates every 30s while processing)
const now = ref(Date.now())
let _timer: ReturnType<typeof setInterval> | null = null

const _startTimer = () => {
  if (!_timer) _timer = setInterval(() => { now.value = Date.now() }, 30000)
}
const _stopTimer = () => {
  if (_timer) { clearInterval(_timer); _timer = null }
}

onMounted(() => {
  if (props.mission.status === 'PROCESSING') _startTimer()
})
onUnmounted(() => _stopTimer())

// Satellite alignment
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

watch(() => props.mission.status, (s) => {
  if (s === 'PROCESSING') _startTimer()
  else _stopTimer()
})

const STEP_LABELS: Record<string, string> = {
  odm: 'Photogrammetry',
  reprojection: 'Reprojecting',
  alignment: 'Aligning',
  tiling: 'Generating tiles',
  finalizing: 'Finalizing',
}

const STEP_WEIGHTS: Record<string, number> = {
  odm: 15,
  reprojection: 55,
  alignment: 70,
  tiling: 85,
  finalizing: 95,
}

const elapsedTime = computed(() => {
  if (!props.mission.processing_started_at) return ''
  const diffMs = now.value - new Date(props.mission.processing_started_at).getTime()
  const minutes = Math.floor(diffMs / 60000)
  if (minutes < 1) return '< 1 min'
  if (minutes < 60) return `${minutes} min`
  const hours = Math.floor(minutes / 60)
  return `${hours}h ${minutes % 60}m`
})

const stepProgress = computed(() => {
  const step = props.mission.processing_step
  if (!step) return 5
  return STEP_WEIGHTS[step] ?? 5
})

const stepLabel = computed(() => {
  return STEP_LABELS[props.mission.processing_step] || ''
})

const statusClass = computed(() => {
  switch (props.mission.status) {
    case 'PUBLISHED': return 'bg-success-50 text-success-700 dark:bg-success-900/50 dark:text-success-300'
    case 'PROCESSING': return 'bg-warning-50 text-warning-800 dark:bg-warning-900/50 dark:text-warning-200'
    case 'QUEUED': return 'bg-secondary-100 text-secondary-800 dark:bg-secondary-900/50 dark:text-secondary-300'
    case 'FAILED': return 'bg-error-50 text-error-700 dark:bg-error-900/50 dark:text-error-200'
    default: return 'bg-neutral-100 text-neutral-800 dark:bg-neutral-700 dark:text-neutral-300'
  }
})

// Calculate tile coordinates from lat/lng (with fractional position)
const latLngToTile = (lat: number, lng: number, zoom: number) => {
  const n = Math.pow(2, zoom)
  const xFloat = (lng + 180) / 360 * n
  const latRad = lat * Math.PI / 180
  const yFloat = (1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2 * n
  return {
    x: Math.floor(xFloat),
    y: Math.floor(yFloat),
    z: zoom,
    // Fractional position within tile (0-1)
    fracX: xFloat - Math.floor(xFloat),
    fracY: yFloat - Math.floor(yFloat)
  }
}

// Check if mission has a thumbnail (published with center coordinates)
const hasThumbnail = computed(() => {
  return props.mission.status === 'PUBLISHED' &&
    props.mission.center_lat != null &&
    props.mission.center_lng != null
})

// Generate thumbnail style - zoom 18 for good coverage
// Uses mission_id to show correct tiles for this specific mission
const thumbnailStyle = computed(() => {
  if (!hasThumbnail.value) return {}

  // Zoom 18: ~150m per tile, imagery fills most of tile
  const zoom = 18
  const tile = latLngToTile(props.mission.center_lat!, props.mission.center_lng!, zoom)
  const tileUrl = `/api/v1/geo/opensky/tiles/${zoom}/${tile.x}/${tile.y}.webp?mission_id=${props.mission.id}`

  return {
    backgroundImage: `url(${tileUrl})`,
    backgroundSize: 'cover',
    backgroundPosition: 'center'
  }
})

const formatTilesCount = (count: number) => {
  if (count >= 1000000) return `${(count / 1000000).toFixed(1)}M`
  if (count >= 1000) return `${(count / 1000).toFixed(1)}K`
  return count.toString()
}

const formatDate = (dateStr: string) => {
  const date = new Date(dateStr)
  return date.toISOString().slice(0, 10)  // 2025-09-27
}

const viewOnMap = () => {
  if (props.mission.center_lat && props.mission.center_lng) {
    router.push({
      path: localePath('/map'),
      query: {
        lat: props.mission.center_lat.toFixed(6),
        lng: props.mission.center_lng.toFixed(6),
        zoom: '17',
        opensky_mission: props.mission.id
      }
    })
  }
}
</script>

<style scoped>
@keyframes pulse-bar {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
</style>
