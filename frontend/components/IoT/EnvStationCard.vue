<template>
  <div class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 flex flex-col">
    <!-- Map viewport — every station has coordinates (location is required).
         Source + AQI live on the map as a HUD overlay, same language as device cards. -->
    <div class="relative shrink-0 m-1 mb-0 aspect-[1.618/1] rounded overflow-hidden bg-neutral-200 dark:bg-neutral-700">
      <img v-if="snapshotUrl" :src="snapshotUrl" :alt="station.name" class="w-full h-full object-cover" loading="lazy" />
      <div v-else class="w-full h-full animate-pulse" />
      <IoTSnapshotMarker :fill="dotColor" :glyph="latest.aqi != null ? LEAF_GLYPH : WIND_GLYPH" :stale="isStale" />
      <!-- Top scrim keeps the HUD legible over map tiles -->
      <div class="absolute inset-x-0 top-0 h-9 bg-gradient-to-b from-black/55 to-transparent pointer-events-none" />
      <span class="absolute top-2 left-3 font-mono text-[10px] uppercase tracking-wider text-white/75">
        {{ sourceLabel }}
      </span>
      <span v-if="latest.aqi != null"
            class="absolute top-2 right-3 max-w-[65%] flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wider text-white/90"
            role="status" aria-live="polite">
        <span class="w-1.5 h-1.5 rounded-full shrink-0" :style="{ background: dotColor }" />
        <span class="truncate">{{ $t('map.env.aqi_label') }} {{ latest.aqi }} · {{ $t(`map.env.aqi.${latest.aqi_category}`) }}</span>
      </span>
    </div>

    <div class="p-4 pt-2.5 flex-1 flex flex-col gap-3">
    <!-- Header (name is inline-editable) -->
    <div class="min-w-0">
      <div v-if="!editingName" class="flex items-center gap-1.5 min-w-0">
        <div class="font-medium text-neutral-900 dark:text-neutral-100 truncate">{{ station.name }}</div>
        <button @click="startEditName" class="text-neutral-400 hover:text-secondary dark:hover:text-secondary-400 shrink-0"
                :title="$t('map.env.rename')" :aria-label="$t('map.env.rename')">
          <Pencil class="w-3 h-3" />
        </button>
      </div>
      <div v-else>
        <div class="flex items-center gap-2">
          <input
            v-model="nameDraft" type="text" maxlength="100"
            class="flex-1 min-w-0 px-1.5 py-1 rounded border text-sm bg-white dark:bg-neutral-800 text-neutral-800 dark:text-neutral-200 focus:outline-none focus:ring-2 focus:border-transparent"
            :class="nameError ? 'border-error focus:ring-error' : 'border-neutral-200 dark:border-neutral-700 focus:ring-primary'"
            @input="nameError = false"
            @keyup.enter="saveName" @keyup.esc="editingName = false"
          />
          <button @click="saveName" :disabled="nameSaving || !nameDraft.trim()"
                  class="text-neutral-400 hover:text-green-600 disabled:opacity-40 shrink-0" :title="$t('map.env.save')">
            <Loader2 v-if="nameSaving" class="w-3.5 h-3.5 animate-spin" />
            <Check v-else class="w-3.5 h-3.5" />
          </button>
          <button @click="editingName = false" class="text-neutral-400 hover:text-red-500 shrink-0" :title="$t('map.env.cancel')">
            <X class="w-3.5 h-3.5" />
          </button>
        </div>
        <div v-if="nameError" class="mt-0.5 text-xs text-error">{{ $t('map.env.rename_taken') }}</div>
      </div>
      <div class="flex items-center flex-wrap gap-x-3 gap-y-0.5 mt-0.5 text-xs text-neutral-500 dark:text-neutral-400">
        <span class="inline-flex items-center gap-1">
          <component :is="station.is_public ? Globe : Lock" class="w-3 h-3" />
          {{ station.is_public ? $t('map.env.public') : $t('map.env.private') }}
        </span>
        <!-- Freshness: live-ticking dot + relative time (the key status for a station) -->
        <span v-if="station.last_reading_at" class="inline-flex items-center gap-1.5">
          <span class="relative flex w-2 h-2">
            <span v-if="!isStale" class="animate-ping absolute inline-flex w-full h-full rounded-full bg-green-400 opacity-75" />
            <span class="relative inline-flex rounded-full w-2 h-2" :class="isStale ? 'bg-neutral-400' : 'bg-green-500'" />
          </span>
          <span :class="isStale ? '' : 'text-green-700 dark:text-green-400'" :title="absoluteTime">{{ relativeTime }}</span>
        </span>
      </div>
    </div>

    <!-- Latest metrics -->
    <div v-if="metricRows.length" class="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
      <div v-for="row in metricRows" :key="row.k" class="flex justify-between gap-2">
        <span class="text-neutral-500 dark:text-neutral-400">{{ $t(`map.env.metric.${row.k}`) }}</span>
        <b class="text-neutral-800 dark:text-neutral-200 whitespace-nowrap">{{ row.v }}</b>
      </div>
    </div>
    <div v-else class="text-sm text-neutral-400 dark:text-neutral-500">
      {{ $t('map.env.no_data') }}
    </div>

    <!-- History charts (hidden until the station has readings) -->
    <div v-if="chartDefs.length">
      <div class="flex items-center justify-between mb-1.5">
        <span class="text-xs font-semibold uppercase tracking-wide text-neutral-400 dark:text-neutral-500">{{ $t('map.env.history') }}</span>
        <div class="flex items-center gap-1">
          <button
            v-for="r in [24, 168]" :key="r" @click="readingsHours = r"
            class="px-1.5 py-0.5 rounded text-[11px] font-medium transition-colors"
            :class="readingsHours === r
              ? 'bg-secondary text-white'
              : 'text-neutral-500 dark:text-neutral-400 hover:bg-primary-100 dark:hover:bg-primary-900/40'"
          >
            {{ r === 24 ? $t('map.env.range_24h') : $t('map.env.range_7d') }}
          </button>
          <button
            @click="downloadCsv" :disabled="csvBusy"
            class="p-1 rounded text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 hover:bg-neutral-200 dark:hover:bg-neutral-700 transition-colors shrink-0"
            :title="$t('map.env.export_csv')" :aria-label="$t('map.env.export_csv')"
          >
            <Loader2 v-if="csvBusy" class="w-3.5 h-3.5 animate-spin" />
            <Download v-else class="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
      <div v-for="c in chartDefs" :key="c.metric" class="mb-2 last:mb-0">
        <div class="text-[11px] text-neutral-400 dark:text-neutral-500 mb-0.5">
          {{ $t(`map.env.metric.${c.metric}`) }}<template v-if="c.unit">, {{ c.unit }}</template>
        </div>
        <UiTimeChart :series="c.series" :height="64" :zero-base="c.zeroBase" :format="c.format" />
      </div>
    </div>

    <!-- Ecowitt ingest path (needed to configure the console) -->
    <div v-if="station.ingest_path" class="text-xs bg-neutral-50 dark:bg-neutral-900 rounded p-2 border border-neutral-200 dark:border-neutral-700">
      <div class="text-neutral-500 dark:text-neutral-400 mb-0.5">{{ $t('map.env.ingest_hint') }}</div>
      <div class="flex items-center gap-2">
        <code class="flex-1 truncate text-neutral-700 dark:text-neutral-300">wx.parahub.io{{ station.ingest_path }}</code>
        <button @click="copyPath" class="text-neutral-400 hover:text-secondary dark:hover:text-secondary-400" :title="$t('map.env.copy')">
          <Check v-if="copied" class="w-3.5 h-3.5 text-green-500" />
          <Copy v-else class="w-3.5 h-3.5" />
        </button>
      </div>
    </div>

    <!-- Public page link (owner-set; shown to everyone on the map panel) -->
    <div class="text-xs bg-neutral-50 dark:bg-neutral-900 rounded p-2 border border-neutral-200 dark:border-neutral-700">
      <div class="text-neutral-500 dark:text-neutral-400 mb-0.5">{{ $t('map.env.public_page_hint') }}</div>
      <div v-if="!editingUrl" class="flex items-center gap-2">
        <a
          v-if="station.public_url"
          :href="station.public_url" target="_blank" rel="noopener noreferrer nofollow"
          class="flex-1 truncate text-link"
        >{{ station.public_url }}</a>
        <span v-else class="flex-1 text-neutral-400 dark:text-neutral-500">{{ $t('map.env.public_page_empty') }}</span>
        <button @click="startEditUrl" class="text-neutral-400 hover:text-secondary dark:hover:text-secondary-400 shrink-0"
                :title="$t('map.env.edit_public_page')" :aria-label="$t('map.env.edit_public_page')">
          <Pencil class="w-3.5 h-3.5" />
        </button>
      </div>
      <div v-else class="flex items-center gap-2">
        <input
          v-model="urlDraft" type="url" placeholder="https://"
          class="flex-1 min-w-0 px-1.5 py-1 rounded border bg-white dark:bg-neutral-800 text-neutral-800 dark:text-neutral-200 focus:outline-none focus:ring-2 focus:border-transparent"
          :class="urlInvalid ? 'border-error focus:ring-error' : 'border-neutral-200 dark:border-neutral-700 focus:ring-primary'"
          @keyup.enter="saveUrl" @keyup.esc="editingUrl = false"
        />
        <button @click="saveUrl" :disabled="urlSaving || urlInvalid"
                class="text-neutral-400 hover:text-green-600 disabled:opacity-40 shrink-0" :title="$t('map.env.save')">
          <Loader2 v-if="urlSaving" class="w-3.5 h-3.5 animate-spin" />
          <Check v-else class="w-3.5 h-3.5" />
        </button>
        <button @click="editingUrl = false" class="text-neutral-400 hover:text-red-500 shrink-0" :title="$t('map.env.cancel')">
          <X class="w-3.5 h-3.5" />
        </button>
      </div>
    </div>

    <!-- Actions -->
    <div class="flex items-center flex-wrap gap-2 pt-1 border-t border-neutral-100 dark:border-neutral-700/50">
      <button @click="showPicker = true"
              class="inline-flex items-center gap-1 text-xs text-neutral-600 dark:text-neutral-300 hover:text-secondary dark:hover:text-secondary-400">
        <MapPin class="w-3.5 h-3.5" /> {{ $t('map.env.set_location') }}
      </button>
      <button @click="togglePublic" :disabled="busy"
              class="inline-flex items-center gap-1 text-xs text-neutral-600 dark:text-neutral-300 hover:text-secondary dark:hover:text-secondary-400">
        <component :is="station.is_public ? EyeOff : Eye" class="w-3.5 h-3.5" />
        {{ station.is_public ? $t('map.env.make_private') : $t('map.env.make_public') }}
      </button>
      <!-- Owner attribution opt-in — only meaningful while the station is public -->
      <button v-if="station.is_public" @click="toggleShowOwner" :disabled="busy"
              class="inline-flex items-center gap-1 text-xs text-neutral-600 dark:text-neutral-300 hover:text-secondary dark:hover:text-secondary-400">
        <component :is="station.show_owner ? UserX : User" class="w-3.5 h-3.5" />
        {{ station.show_owner ? $t('map.env.hide_owner') : $t('map.env.show_owner') }}
      </button>
      <button @click="onDelete" :disabled="busy"
              class="inline-flex items-center gap-1 text-xs text-red-500 hover:text-red-600 ml-auto">
        <Trash2 class="w-3.5 h-3.5" /> {{ $t('map.env.delete') }}
      </button>
    </div>
    </div>

    <IoTLocationPickerModal
      v-if="showPicker"
      :initial-lat="station.latitude"
      :initial-lng="station.longitude"
      :save-fn="saveLocation"
      :hint="$t('map.env.click_map')"
      :marker-fill="dotColor"
      :marker-glyph="latest.aqi != null ? LEAF_GLYPH : WIND_GLYPH"
      @close="showPicker = false"
      @saved="showPicker = false"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { Globe, Lock, MapPin, Eye, EyeOff, Trash2, Copy, Check, Download, Loader2, Pencil, User, UserX, X } from 'lucide-vue-next'
import { LEAF_GLYPH, WIND_GLYPH } from '~/composables/useMapToggleableLayer'
import { saveFile } from '~/utils/download'
import type { EnvStation } from '~/stores/env'
import type { TimeChartSeries } from '~/components/ui/TimeChart.vue'

const props = defineProps<{ station: EnvStation }>()
const emit = defineEmits<{ (e: 'changed'): void; (e: 'deleted', id: string): void }>()

const { t: $t } = useI18n()
const envStore = useEnvStore()
const authStore = useAuthStore()

const busy = ref(false)
const showPicker = ref(false)
const copied = ref(false)

const latest = computed(() => props.station.latest || {})

const AQI_COLORS: Record<string, string> = {
  good: '#22c55e', moderate: '#eab308', unhealthy_sensitive: '#f97316',
  unhealthy: '#ef4444', very_unhealthy: '#a855f7', hazardous: '#7f1d1d',
}
const dotColor = computed(() => AQI_COLORS[latest.value.aqi_category] || '#38bdf8')

const sourceLabel = computed(() => ({
  ECOWITT: 'Ecowitt', AIRGRADIENT: 'AirGradient', GENERIC: $t('map.env.generic'),
}[props.station.source] || props.station.source))

// Map viewport (shared single MapLibre instance across all cards)
const { capture, invalidate } = useMapSnapshots()
const snapshotUrl = ref<string | null>(null)

async function loadSnapshot() {
  if (props.station.latitude == null || props.station.longitude == null) return
  snapshotUrl.value = await capture(props.station.latitude, props.station.longitude)
}
onMounted(loadSnapshot)

// Recapture when the station is moved via the location picker
watch(
  [() => props.station.latitude, () => props.station.longitude],
  ([lat, lon], [oldLat, oldLon]) => {
    if (lat == null || lon == null) return
    if (lat === oldLat && lon === oldLon) return
    if (oldLat != null && oldLon != null) invalidate(oldLat, oldLon)
    loadSnapshot()
  },
)

// [key, unit, decimals] — same order/units as the map popup.
const METRIC_DEFS: Array<[string, string, number]> = [
  ['temperature', '°C', 1], ['humidity', '%', 0], ['pressure', 'hPa', 0],
  ['wind_speed', 'km/h', 1], ['wind_gust', 'km/h', 1], ['wind_dir', '°', 0],
  ['rain_rate', 'mm/h', 1], ['rain_daily', 'mm', 1],
  ['solar_radiation', 'W/m²', 0], ['uv', '', 1],
  ['pm25', 'µg/m³', 1], ['pm10', 'µg/m³', 1], ['pm01', 'µg/m³', 1],
  ['co2', 'ppm', 0], ['tvoc_index', '', 0], ['nox_index', '', 0],
]
const metricRows = computed(() =>
  METRIC_DEFS.filter(([k]) => latest.value[k] != null).map(([k, unit, dec]) => ({
    k, v: `${Number(latest.value[k]).toFixed(dec)}${unit ? ' ' + unit : ''}`,
  }))
)

// ---- Reading history charts ----
// Priority order; up to three charts for the metrics the station reports.
// zeroBase off where zero is not a meaningful floor (ambient baselines).
const CHART_METRICS: Array<{ metric: string; unit: string; zeroBase: boolean; dec: number }> = [
  { metric: 'temperature', unit: '°C', zeroBase: false, dec: 1 },
  { metric: 'pm25', unit: 'µg/m³', zeroBase: true, dec: 1 },
  { metric: 'co2', unit: 'ppm', zeroBase: false, dec: 0 },
  { metric: 'humidity', unit: '%', zeroBase: false, dec: 0 },
]

const readingsHours = ref(24)
const readings = ref<any[]>([])
const csvBusy = ref(false)

async function loadReadings() {
  try {
    await authStore.ensureToken()
    const res = await $fetch<any>(`/api/v1/iot/env-stations/${props.station.id}/readings`, {
      params: { hours: readingsHours.value },
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    readings.value = res?.points || []
  } catch { readings.value = [] }
}
onMounted(loadReadings)
watch(readingsHours, loadReadings)

const chartDefs = computed(() => CHART_METRICS
  .map((def) => {
    const points = readings.value.map(p => ({ t: Date.parse(p.t), v: p[def.metric] }))
    if (!points.some(p => p.v != null)) return null
    return {
      ...def,
      format: (v: number) => v.toFixed(def.dec),
      series: [{ key: def.metric, label: $t(`map.env.metric.${def.metric}`), points }] as TimeChartSeries[],
    }
  })
  .filter((c): c is NonNullable<typeof c> => c !== null)
  .slice(0, 3))

async function downloadCsv() {
  if (csvBusy.value) return
  csvBusy.value = true
  try {
    await authStore.ensureToken()
    const res = await fetch(`/api/v1/iot/env-stations/${props.station.id}/readings.csv?hours=720`, {
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    if (!res.ok) throw new Error(String(res.status))
    await saveFile(await res.blob(), `${props.station.name.replace(/[^\w-]+/g, '_')}-readings-30d.csv`)
  } catch { /* transient network failure; button stays available */ }
  finally { csvBusy.value = false }
}

// Freshness chip in the header (live-ticking, shared with the map panel)
const { isStale, absoluteTime, relativeTime } = useEnvFreshness(
  computed(() => props.station.last_reading_at),
)

// ---- Name inline editor ----
const editingName = ref(false)
const nameDraft = ref('')
const nameSaving = ref(false)
const nameError = ref(false)

const startEditName = () => {
  nameDraft.value = props.station.name
  nameError.value = false
  editingName.value = true
}

const saveName = async () => {
  const name = nameDraft.value.trim()
  if (!name || nameSaving.value) return
  nameSaving.value = true
  try {
    await envStore.patchStation(props.station.id, { name })
    editingName.value = false
    emit('changed')
  } catch {
    // 409 — another of the owner's stations already uses this name
    nameError.value = true
  } finally { nameSaving.value = false }
}

// ---- Public page URL inline editor ----
const editingUrl = ref(false)
const urlDraft = ref('')
const urlSaving = ref(false)
const urlInvalid = computed(() => !!urlDraft.value.trim() && !/^https:\/\/.+/.test(urlDraft.value.trim()))

const startEditUrl = () => {
  urlDraft.value = props.station.public_url || ''
  editingUrl.value = true
}

const saveUrl = async () => {
  if (urlInvalid.value || urlSaving.value) return
  urlSaving.value = true
  try {
    await envStore.patchStation(props.station.id, { public_url: urlDraft.value.trim() })
    editingUrl.value = false
    emit('changed')
  } finally { urlSaving.value = false }
}

const saveLocation = async (lat: number, lng: number) => {
  await envStore.setLocation(props.station.id, lat, lng)
  emit('changed')
}

const togglePublic = async () => {
  busy.value = true
  try {
    await envStore.patchStation(props.station.id, { is_public: !props.station.is_public })
    emit('changed')
  } finally { busy.value = false }
}

const toggleShowOwner = async () => {
  busy.value = true
  try {
    await envStore.patchStation(props.station.id, { show_owner: !props.station.show_owner })
    emit('changed')
  } finally { busy.value = false }
}

const onDelete = async () => {
  if (!confirm($t('map.env.delete_confirm', { name: props.station.name }))) return
  busy.value = true
  try {
    await envStore.deleteStation(props.station.id)
    emit('deleted', props.station.id)
  } finally { busy.value = false }
}

const copyPath = async () => {
  try {
    await navigator.clipboard.writeText(`wx.parahub.io${props.station.ingest_path}`)
    copied.value = true
    setTimeout(() => { copied.value = false }, 1500)
  } catch { /* clipboard unavailable */ }
}
</script>

