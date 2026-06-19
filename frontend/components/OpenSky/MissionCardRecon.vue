<template>
  <!-- Recon-instrument panel — identical shell for every status so processing /
       queued / failed cards align flush with published ones in the grid. -->
  <div
    class="group rounded-lg overflow-hidden bg-neutral-50 dark:bg-neutral-900 border transition-colors duration-300"
    :class="failed
      ? 'border-error/40 hover:border-error/60'
      : 'border-neutral-200 dark:border-neutral-800 hover:border-primary/60'"
  >
    <!-- Sensor viewport (serial + status live inside as a HUD overlay — no separate bezel row) -->
    <!-- Published imagery is clickable → jumps to the big map; non-published has no tiles yet. -->
    <div
      class="relative m-2 rounded-md overflow-hidden aspect-[5/4] bg-neutral-200 dark:bg-neutral-950 ring-1"
      :class="published ? 'ring-primary/20 cursor-pointer' : 'ring-neutral-300/50 dark:ring-neutral-700/50'"
      :title="published ? $t('opensky.view_on_map', 'View on Map') : undefined"
      @click="published && viewOnMap(mission)"
    >
      <div
        v-if="thumb"
        class="absolute inset-0 bg-cover bg-center transition-transform duration-[1200ms] ease-out group-hover:scale-105"
        :style="{ backgroundImage: `url(${thumb})` }"
      />
      <div v-else class="absolute inset-0 flex items-center justify-center">
        <component
          :is="placeholderIcon"
          class="w-10 h-10"
          :class="processing ? 'text-warning animate-pulse' : failed ? 'text-error/70' : 'text-neutral-500'"
        />
      </div>

      <!-- Processing: a quiet recon scan line sweeping the empty sensor -->
      <div v-if="processing" class="pointer-events-none absolute inset-x-0 left-0 h-px bg-primary/70 shadow-[0_0_8px_rgba(250,204,21,0.7)] animate-[scan_2.4s_ease-in-out_infinite]" />

      <!-- Top scrim so the HUD text stays legible over imagery -->
      <div class="absolute inset-x-0 top-0 h-9 bg-gradient-to-b from-black/55 to-transparent pointer-events-none" />

      <!-- Reticle corner brackets -->
      <span class="absolute top-1.5 left-1.5 w-3 h-3 border-t border-l border-primary/70" />
      <span class="absolute top-1.5 right-1.5 w-3 h-3 border-t border-r border-primary/70" />
      <span class="absolute bottom-1.5 left-1.5 w-3 h-3 border-b border-l border-primary/70" />
      <span class="absolute bottom-1.5 right-1.5 w-3 h-3 border-b border-r border-primary/70" />

      <!-- HUD: serial (left) + status (right), inset clear of the yellow corner brackets -->
      <span class="absolute top-2 left-6 font-mono text-[10px] uppercase tracking-wider text-white/70">{{ mission.id.slice(0, 8) }}</span>
      <span class="absolute top-2 right-6 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wider text-white/85">
        <span class="w-1.5 h-1.5 rounded-full" :class="statusDotClass" />
        {{ statusLabel }}
      </span>

      <!-- Center reticle (quiet — only on hover, published only) -->
      <span v-if="published" class="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-60 transition-opacity">
        <span class="block w-4 h-px bg-primary" />
        <span class="block w-px h-4 bg-primary absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2" />
      </span>

      <!-- Processing progress bar (weighted by pipeline step) -->
      <div v-if="processing" class="absolute inset-x-0 bottom-0 h-1 bg-warning/20">
        <div
          class="h-full bg-warning transition-all duration-1000 ease-in-out animate-[pulse-bar_2s_ease-in-out_infinite]"
          :style="{ width: stepProgress + '%' }"
        />
      </div>
    </div>

    <!-- Readouts -->
    <div class="px-3 pb-3">
      <!-- Place headline -->
      <div class="mb-2">
        <div class="flex items-center gap-1.5 text-neutral-900 dark:text-neutral-100" :title="place || mission.id">
          <MapPin class="w-3.5 h-3.5 shrink-0 text-neutral-400 dark:text-neutral-500" />
          <span class="text-[15px] font-mono font-semibold uppercase tracking-wide truncate">{{ place || '— — —' }}</span>
        </div>
        <div v-if="region" class="pl-5 text-[10px] font-mono uppercase tracking-wider text-neutral-400 dark:text-neutral-500 truncate">{{ region }}</div>
      </div>

      <div class="h-px bg-neutral-200 dark:bg-neutral-800" />

      <!-- Readout grid -->
      <div class="grid grid-cols-2 gap-x-3 gap-y-2 py-2.5">
        <div class="col-span-2">
          <div class="text-[9px] font-mono uppercase tracking-[0.18em] text-neutral-400 dark:text-neutral-600">{{ $t('opensky.r_coord', 'Coordinates') }}</div>
          <div class="text-[12px] font-mono tabular-nums text-neutral-800 dark:text-neutral-100">{{ coord || '—' }}</div>
        </div>

        <div>
          <div class="text-[9px] font-mono uppercase tracking-[0.18em] text-neutral-400 dark:text-neutral-600">{{ $t('opensky.r_area', 'Area') }}</div>
          <div class="text-[12px] font-mono tabular-nums text-neutral-800 dark:text-neutral-100">{{ area || '—' }}</div>
        </div>
        <div>
          <div class="text-[9px] font-mono uppercase tracking-[0.18em] text-neutral-400 dark:text-neutral-600">{{ $t('opensky.r_frames', 'Frames') }}</div>
          <div class="text-[12px] font-mono tabular-nums text-neutral-800 dark:text-neutral-100">{{ mission.source_photos_count }}</div>
        </div>

        <div>
          <div class="text-[9px] font-mono uppercase tracking-[0.18em] text-neutral-400 dark:text-neutral-600">{{ $t('opensky.r_survey', 'Survey') }}</div>
          <div class="text-[12px] font-mono tabular-nums text-neutral-800 dark:text-neutral-100">{{ surveyDate || '—' }}</div>
        </div>
        <div class="min-w-0">
          <div class="text-[9px] font-mono uppercase tracking-[0.18em] text-neutral-400 dark:text-neutral-600">{{ $t('opensky.r_pilot', 'Pilot') }}</div>
          <NuxtLink
            v-if="mission.pilot_name && mission.pilot_id"
            :to="`/u/${mission.pilot_id}`"
            class="block text-[12px] font-mono text-neutral-800 dark:text-neutral-100 truncate hover:text-secondary dark:hover:text-secondary-400 transition-colors"
          >{{ mission.pilot_name }}</NuxtLink>
          <div v-else class="text-[12px] font-mono text-neutral-800 dark:text-neutral-100 truncate">{{ mission.pilot_name || '—' }}</div>
        </div>
      </div>

      <div class="h-px bg-neutral-200 dark:bg-neutral-800" />

      <!-- Status footer — same band slot across all states keeps card rhythm aligned -->
      <div class="mt-3">
        <!-- Published: primary action -->
        <button
          v-if="published"
          class="w-full h-9 inline-flex items-center justify-center gap-1.5 rounded-md bg-primary text-neutral-900 text-[11px] font-mono font-semibold uppercase tracking-wider whitespace-nowrap hover:bg-primary-600 transition-colors"
          @click="viewOnMap(mission)"
        >
          <Map class="w-3.5 h-3.5" /> {{ $t('opensky.view_on_map', 'View on Map') }}
        </button>

        <!-- Processing: live elapsed + pipeline step -->
        <div
          v-else-if="processing"
          class="flex h-9 items-center gap-2 rounded-md border border-warning/40 bg-warning/10 px-2.5 text-warning"
        >
          <Loader2 class="w-3.5 h-3.5 shrink-0 animate-spin" />
          <span class="truncate font-mono text-[11px] uppercase tracking-wider">
            {{ elapsedTime || statusLabel }}<template v-if="stepLabel"> · {{ stepLabel }}</template>
          </span>
        </div>

        <!-- Queued: waiting in line -->
        <div
          v-else-if="queued"
          class="flex h-9 items-center gap-2 rounded-md border border-secondary/40 bg-secondary/10 px-2.5 text-secondary dark:text-secondary-400"
        >
          <Clock class="w-3.5 h-3.5 shrink-0" />
          <span class="truncate font-mono text-[11px] uppercase tracking-wider">{{ $t('opensky.waiting_in_queue', 'Waiting in queue') }}</span>
        </div>

        <!-- Failed: error readout (wraps; grid is items-start so height may vary) -->
        <div
          v-else-if="failed"
          class="flex items-start gap-2 rounded-md border border-error/30 bg-error/10 px-2.5 py-2 text-error"
        >
          <AlertTriangle class="w-3.5 h-3.5 shrink-0 mt-0.5" />
          <span class="font-mono text-[11px] leading-snug">{{ mission.error_message || $t('opensky.status_failed', 'Failed') }}</span>
        </div>
      </div>

      <!-- Diagnostics drawer — synced open state across all cards (3D / delete live inside) -->
      <details :open="detailsOpen" class="group/d mt-2 border-t border-neutral-200 dark:border-neutral-800">
        <summary
          class="pt-2 font-mono text-[10px] uppercase tracking-wider text-neutral-400 dark:text-neutral-500 cursor-pointer select-none flex items-center gap-1 hover:text-neutral-600 dark:hover:text-neutral-300"
          @click.prevent="detailsOpen = !detailsOpen"
        >
          <ChevronRight class="w-3 h-3 transition-transform group-open/d:rotate-90" />
          {{ $t('opensky.diagnostics', 'Details') }}
        </summary>
        <div class="pt-2">
          <OpenSkyMissionDetails
            :mission="mission"
            :can-delete="canDelete"
            @view-3d="$emit('view-3d', $event)"
            @delete="$emit('delete', $event)"
            @add-photos="$emit('add-photos', $event)"
            @download-3d="$emit('download-3d', $event)"
          />
        </div>
      </details>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Map, MapPin, Camera, ChevronRight, Loader2, Clock, AlertTriangle } from 'lucide-vue-next'
import type { OpenSkyMission } from '~/composables/useOpenSky'

const props = defineProps<{ mission: OpenSkyMission; canDelete?: boolean }>()
defineEmits<{ delete: [string]; 'view-3d': [string]; 'download-3d': [string]; 'add-photos': [string] }>()

const { t, locale } = useI18n()
const { viewOnMap } = useMissionActions()
const { lookup } = useReverseGeocode()

const published = computed(() => props.mission.status === 'PUBLISHED')
const processing = computed(() => props.mission.status === 'PROCESSING')
const queued = computed(() => props.mission.status === 'QUEUED')
const failed = computed(() => props.mission.status === 'FAILED')

const thumb = computed(() => missionThumbnailUrl(props.mission))
const area = computed(() => formatArea(props.mission.area_m2 ?? 0))
const coord = computed(() => formatCoord(props.mission.center_lat, props.mission.center_lng))
const surveyDate = computed(() => formatShortDate(props.mission.captured_at || props.mission.uploaded_at, locale.value))
const statusLabel = computed(() => t(`opensky.status_${props.mission.status.toLowerCase()}`, props.mission.status))
const placeholderIcon = computed(() => (failed.value ? AlertTriangle : Camera))

// Status indicator dot — emerald=live, amber=processing, secondary=queued, red=failed.
const statusDotClass = computed(() => {
  switch (props.mission.status) {
    case 'PUBLISHED': return 'bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.8)]'
    case 'PROCESSING': return 'bg-amber-400 shadow-[0_0_6px_rgba(251,191,36,0.85)] animate-pulse'
    case 'QUEUED': return 'bg-sky-400 shadow-[0_0_6px_rgba(56,189,248,0.75)]'
    case 'FAILED': return 'bg-red-400 shadow-[0_0_6px_rgba(248,113,113,0.85)]'
    default: return 'bg-neutral-400'
  }
})

// Shared across every recon card: open Details on one → all open, close → all close.
const detailsOpen = useState('opensky-details-open', () => false)

// Prefer the place resolved server-side at publish (stored, in SSR, zero requests).
// Fall back to a client reverse-geo lookup only for missions not yet backfilled.
const place = ref<string | null>(props.mission.place_label || null)
const region = ref<string | null>(props.mission.place_region || null)

onMounted(async () => {
  if (props.mission.status === 'PROCESSING') startTimer()
  if (place.value) return
  if (props.mission.center_lat != null && props.mission.center_lng != null) {
    const f = await lookup(props.mission.center_lat, props.mission.center_lng)
    place.value = placeName(f)
    region.value = placeRegion(f)
  }
})

onUnmounted(() => stopTimer())

// ===== Processing readout (elapsed ticker + weighted step progress) =====

const now = ref(Date.now())
let _timer: ReturnType<typeof setInterval> | null = null
const startTimer = () => { if (!_timer) _timer = setInterval(() => { now.value = Date.now() }, 30000) }
const stopTimer = () => { if (_timer) { clearInterval(_timer); _timer = null } }

watch(() => props.mission.status, (s) => {
  if (s === 'PROCESSING') startTimer()
  else stopTimer()
})

const STEP_KEYS: Record<string, string> = {
  odm: 'opensky.step_odm',
  reprojection: 'opensky.step_reprojection',
  alignment: 'opensky.step_alignment',
  tiling: 'opensky.step_tiling',
  mesh: 'opensky.step_mesh',
  finalizing: 'opensky.step_finalizing',
}
const STEP_ORDER = ['odm', 'reprojection', 'alignment', 'tiling', 'mesh', 'finalizing']
const STEP_WEIGHTS: Record<string, number> = {
  odm: 15, reprojection: 40, alignment: 55, tiling: 70, mesh: 85, finalizing: 95,
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
  const step = props.mission.processing_step
  if (!step || !STEP_KEYS[step]) return ''
  const stepNum = STEP_ORDER.indexOf(step) + 1
  return `${t(STEP_KEYS[step])} (${stepNum}/${STEP_ORDER.length})`
})
</script>

<style scoped>
@keyframes pulse-bar {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
@keyframes scan {
  0% { top: 0; opacity: 0; }
  15% { opacity: 0.9; }
  85% { opacity: 0.9; }
  100% { top: 100%; opacity: 0; }
}
</style>
