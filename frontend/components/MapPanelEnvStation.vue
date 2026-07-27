<template>
  <div>
    <!-- Live wind compass in the hero spot other panels use for a photo -->
    <div
      v-if="hasWind"
      class="relative w-full h-40 bg-neutral-100 dark:bg-neutral-800 overflow-hidden select-none flex-shrink-0"
      :class="{ 'opacity-50': isStale }"
    >
      <svg
        viewBox="0 0 120 120"
        class="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-32 h-32 text-neutral-300 dark:text-neutral-600"
        aria-hidden="true"
      >
        <circle cx="60" cy="60" r="44" fill="none" stroke="currentColor" stroke-width="1.5" />
        <line
          v-for="tk in compassTicks" :key="tk.a"
          :x1="tk.x1" :y1="tk.y1" :x2="tk.x2" :y2="tk.y2"
          :stroke="tk.north ? '#dc2626' : 'currentColor'"
          :stroke-width="tk.north ? 2.2 : tk.cardinal ? 1.6 : 1"
          :opacity="tk.north ? 1 : tk.cardinal ? 0.9 : 0.5"
          stroke-linecap="round"
          class="text-neutral-400 dark:text-neutral-500"
        />
        <text
          v-for="c in compassLetters" :key="c.key"
          :x="c.x" :y="c.y"
          text-anchor="middle" dominant-baseline="central"
          :fill="c.key === 'n' ? '#dc2626' : 'currentColor'"
          class="font-mono text-neutral-400 dark:text-neutral-500"
          font-size="8" font-weight="600"
        >{{ t(`map.weather.compass.${c.key}`) }}</text>
        <!-- Wind ORIGIN bearing, apex inward — same convention as the map bezel -->
        <g v-if="dartStyle" class="env-wind-dart" :style="dartStyle">
          <polygon points="60,26.5 53.5,10.5 60,16 66.5,10.5" fill="#4E4EC8" stroke="#ffffff" stroke-width="1.2" stroke-linejoin="round" />
        </g>
      </svg>
      <div v-if="windSpeed != null" class="absolute inset-0 flex flex-col items-center justify-center pointer-events-none font-mono tabular-nums">
        <span class="text-xl font-bold leading-none text-neutral-900 dark:text-neutral-100">{{ Math.round(windSpeed) }}</span>
        <span class="text-[9px] uppercase tracking-wide text-neutral-400 dark:text-neutral-500">km/h</span>
        <span v-if="windGust != null && windGust > windSpeed" class="text-[10px] font-semibold text-neutral-500 dark:text-neutral-400">G {{ Math.round(windGust) }}</span>
      </div>
      <span class="absolute top-2 left-3 text-[10px] font-mono font-semibold uppercase tracking-widest text-neutral-400 dark:text-neutral-500">
        {{ t('map.env.metric.wind_speed') }}
      </span>
      <span v-if="windDir != null" class="absolute bottom-2 right-3 text-[11px] font-mono tabular-nums text-neutral-500 dark:text-neutral-400">
        {{ Math.round(windDir) }}° {{ windCardinal }}
      </span>
      <div class="absolute inset-0 pointer-events-none env-scanlines" />
    </div>

    <div class="px-4 pt-3 space-y-4">
    <template v-if="envStationData">
      <!-- Last update + live indicator -->
      <div class="flex items-center gap-3 flex-wrap">
        <div
          class="flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium"
          :class="isStale
            ? 'bg-neutral-100 dark:bg-neutral-800 text-neutral-500 dark:text-neutral-400'
            : 'bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-300'"
        >
          <span class="relative flex w-2.5 h-2.5">
            <span
              v-if="!isStale"
              class="animate-ping absolute inline-flex w-full h-full rounded-full bg-green-400 opacity-75"
            ></span>
            <span
              class="relative inline-flex rounded-full w-2.5 h-2.5"
              :class="isStale ? 'bg-neutral-400' : 'bg-green-500'"
            ></span>
          </span>
          {{ isStale ? t('map.env.stale') : t('map.env.live') }}
        </div>
        <div
          v-if="aqi != null"
          class="flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-semibold text-white"
          :style="{ background: aqiColor }"
        >
          {{ t('map.env.aqi_label') }} {{ aqi }} · {{ t(`map.env.aqi.${aqiCategory}`) }}
        </div>
      </div>

      <!-- Timestamp -->
      <div v-if="envStationData.last_reading_at" class="flex items-center gap-2 text-sm text-neutral-500 dark:text-neutral-400">
        <Clock :size="14" class="flex-shrink-0" />
        <span class="text-neutral-700 dark:text-neutral-300">{{ absoluteTime }}</span>
        <span class="text-neutral-400 dark:text-neutral-500">· {{ relativeTime }}</span>
      </div>

      <!-- Owner attribution (owner opt-in via show_owner) -->
      <div v-if="ownerCri" class="flex items-center gap-2 text-sm text-neutral-500 dark:text-neutral-400">
        <User :size="14" class="flex-shrink-0" />
        <span>{{ t('map.panel.owner') }}</span>
        <NuxtLink :to="localePath(`/u/${ownerCri}`)" class="text-link font-medium truncate">{{ ownerName }}</NuxtLink>
      </div>

      <!-- Weather metrics -->
      <div v-if="weatherRows.length">
        <h3 class="text-xs font-semibold uppercase tracking-wide text-neutral-400 dark:text-neutral-500 mb-1">
          {{ t('map.env.weather') }}
        </h3>
        <div class="text-sm">
          <div
            v-for="row in weatherRows" :key="row.k"
            class="flex items-center justify-between py-1.5 border-b border-neutral-100 dark:border-neutral-800 last:border-0"
          >
            <span class="text-neutral-500 dark:text-neutral-400">{{ t(`map.env.metric.${row.k}`) }}</span>
            <span class="font-medium text-neutral-900 dark:text-neutral-100">{{ row.v }}</span>
          </div>
        </div>
      </div>

      <!-- Air-quality metrics -->
      <div v-if="airRows.length">
        <h3 class="text-xs font-semibold uppercase tracking-wide text-neutral-400 dark:text-neutral-500 mb-1">
          {{ t('map.env.air_quality') }}
        </h3>
        <div class="text-sm">
          <div
            v-for="row in airRows" :key="row.k"
            class="flex items-center justify-between py-1.5 border-b border-neutral-100 dark:border-neutral-800 last:border-0"
          >
            <span class="text-neutral-500 dark:text-neutral-400">{{ t(`map.env.metric.${row.k}`) }}</span>
            <span class="font-medium text-neutral-900 dark:text-neutral-100">{{ row.v }}</span>
          </div>
        </div>
      </div>

      <!-- Reading history (public endpoint; section hidden while empty) -->
      <div v-if="chartDefs.length">
        <div class="flex items-center justify-between mb-1">
          <h3 class="text-xs font-semibold uppercase tracking-wide text-neutral-400 dark:text-neutral-500">
            {{ t('map.env.history') }} · {{ t('map.env.range_24h') }}
          </h3>
          <a
            :href="csvHref" :download="csvFilename"
            class="p-1 rounded text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
            :title="t('map.env.export_csv')" :aria-label="t('map.env.export_csv')"
          >
            <Download :size="14" />
          </a>
        </div>
        <div v-for="c in chartDefs" :key="c.metric" class="mb-2 last:mb-0">
          <div class="text-[11px] text-neutral-400 dark:text-neutral-500 mb-0.5">
            {{ t(`map.env.metric.${c.metric}`) }}<template v-if="c.unit">, {{ c.unit }}</template>
          </div>
          <UiTimeChart :series="c.series" :height="64" :zero-base="c.zeroBase" :format="c.format" />
        </div>
      </div>

      <!-- Owner-set public page (vendor cloud map etc.) for independent cross-checking -->
      <UiButton
        v-if="publicUrl"
        variant="outline" size="sm" :icon="ExternalLink" tag="a"
        :href="publicUrl" target="_blank" rel="noopener noreferrer nofollow"
        class="w-full !whitespace-normal min-w-0 text-center"
        :title="publicUrl"
      >
        {{ t('map.env.external_page') }}<template v-if="publicUrlHost"> ({{ publicUrlHost }})</template>
      </UiButton>

      <!-- Empty -->
      <p v-if="!weatherRows.length && !airRows.length" class="text-sm text-neutral-400 dark:text-neutral-500">
        {{ t('map.env.no_data') }}
      </p>
    </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Clock, Download, ExternalLink, User } from 'lucide-vue-next'
import type { TimeChartSeries } from '~/components/ui/TimeChart.vue'

const { t } = useI18n()
const localePath = useLocalePath()

const props = defineProps<{ envStationData: any }>()

// US EPA AQI category → color (matches the map layer).
const AQI_COLORS: Record<string, string> = {
  good: '#22c55e',
  moderate: '#eab308',
  unhealthy_sensitive: '#f97316',
  unhealthy: '#ef4444',
  very_unhealthy: '#a855f7',
  hazardous: '#7f1d1d',
}

// [key, unit, decimals] — split by domain for the two panel sections.
const WEATHER_METRICS: Array<[string, string, number]> = [
  ['temperature', '°C', 1], ['humidity', '%', 0], ['pressure', 'hPa', 0],
  ['wind_speed', 'km/h', 1], ['wind_gust', 'km/h', 1], ['wind_dir', '°', 0],
  ['rain_rate', 'mm/h', 1], ['rain_daily', 'mm', 1],
  ['solar_radiation', 'W/m²', 0], ['uv', '', 1],
]
const AIR_METRICS: Array<[string, string, number]> = [
  ['pm25', 'µg/m³', 1], ['pm10', 'µg/m³', 1], ['pm01', 'µg/m³', 1],
  ['co2', 'ppm', 0], ['tvoc_index', '', 0], ['nox_index', '', 0],
]

const latest = computed(() => props.envStationData?.latest || {})

const aqi = computed(() => latest.value.aqi ?? null)
const aqiCategory = computed(() => latest.value.aqi_category || 'good')
const aqiColor = computed(() => AQI_COLORS[aqiCategory.value] || '#38bdf8')

function buildRows(defs: Array<[string, string, number]>) {
  return defs
    .filter(([k]) => latest.value[k] != null)
    .map(([k, unit, dec]) => ({
      k,
      v: `${Number(latest.value[k]).toFixed(dec)}${unit ? ' ' + unit : ''}`,
    }))
}
const weatherRows = computed(() => buildRows(WEATHER_METRICS))
const airRows = computed(() => buildRows(AIR_METRICS))

// ---- Reading history (public stations — anonymous endpoint) ----
const CHART_METRICS: Array<{ metric: string; unit: string; zeroBase: boolean; dec: number }> = [
  { metric: 'temperature', unit: '°C', zeroBase: false, dec: 1 },
  { metric: 'pm25', unit: 'µg/m³', zeroBase: true, dec: 1 },
  { metric: 'co2', unit: 'ppm', zeroBase: false, dec: 0 },
]

const readings = ref<any[]>([])
const stationId = computed(() => props.envStationData?.id || null)

async function loadReadings(id: string) {
  try {
    const res = await $fetch<any>(`/api/v1/iot/env-stations/${id}/readings`, { params: { hours: 24 } })
    readings.value = res?.points || []
  } catch { readings.value = [] }
}
watch(stationId, (id) => {
  readings.value = []
  if (id) loadReadings(id)
}, { immediate: true })

const chartDefs = computed(() => CHART_METRICS
  .map((def) => {
    const points = readings.value.map(p => ({ t: Date.parse(p.t), v: p[def.metric] }))
    if (!points.some(p => p.v != null)) return null
    return {
      ...def,
      format: (v: number) => v.toFixed(def.dec),
      series: [{ key: def.metric, label: t(`map.env.metric.${def.metric}`), points }] as TimeChartSeries[],
    }
  })
  .filter((c): c is NonNullable<typeof c> => c !== null)
  .slice(0, 3))

const ownerName = computed(() => props.envStationData?.owner_name || '')
const ownerCri = computed(() => props.envStationData?.owner_cri || '')

const publicUrl = computed(() => props.envStationData?.public_url || '')
const publicUrlHost = computed(() => {
  try { return new URL(publicUrl.value).hostname } catch { return '' }
})

const csvHref = computed(() => `/api/v1/iot/env-stations/${stationId.value}/readings.csv?hours=720`)
const csvFilename = computed(() =>
  `${(props.envStationData?.name || 'station').replace(/[^\w-]+/g, '_')}-readings-30d.csv`)

// ======== Freshness / timestamps (live-ticking, shared with the card) ========
const { isStale, absoluteTime, relativeTime } = useEnvFreshness(
  computed(() => props.envStationData?.last_reading_at),
)

// ======== Wind compass hero (live — the env WS refreshes the panel object) ========
const COMPASS = ['n', 'ne', 'e', 'se', 's', 'sw', 'w', 'nw']
const windSpeed = computed(() => latest.value.wind_speed != null ? Number(latest.value.wind_speed) : null)
const windGust = computed(() => latest.value.wind_gust != null ? Number(latest.value.wind_gust) : null)
const windDir = computed(() => latest.value.wind_dir != null ? Number(latest.value.wind_dir) : null)
const hasWind = computed(() => windSpeed.value != null || windDir.value != null)
const windCardinal = computed(() =>
  windDir.value != null ? t(`map.weather.compass.${COMPASS[Math.round(windDir.value / 45) % 8]}`) : '')

// Bearing accumulates continuously so 350°→10° sweeps 20°, not −340°
const dartAngle = ref<number | null>(null)
watch(windDir, (d) => {
  if (d == null) { dartAngle.value = null; return }
  const target = ((d % 360) + 360) % 360
  const prev = dartAngle.value
  if (prev == null) { dartAngle.value = target; return }
  const prevNorm = ((prev % 360) + 360) % 360
  let delta = target - prevNorm
  if (delta > 180) delta -= 360
  if (delta < -180) delta += 360
  dartAngle.value = prev + delta
}, { immediate: true })
const dartStyle = computed(() =>
  dartAngle.value != null ? { transform: `rotate(${dartAngle.value}deg)` } : null)

const DEG2RAD = Math.PI / 180
const compassTicks = Array.from({ length: 12 }, (_, i) => {
  const a = i * 30
  const north = a === 0
  const cardinal = a % 90 === 0
  const r1 = north ? 35.5 : cardinal ? 37 : 39
  return {
    a, north, cardinal,
    x1: +(60 + r1 * Math.sin(a * DEG2RAD)).toFixed(2),
    y1: +(60 - r1 * Math.cos(a * DEG2RAD)).toFixed(2),
    x2: +(60 + 44 * Math.sin(a * DEG2RAD)).toFixed(2),
    y2: +(60 - 44 * Math.cos(a * DEG2RAD)).toFixed(2),
  }
})
const compassLetters = ['n', 'e', 's', 'w'].map((key, i) => {
  const a = i * 90
  return {
    key,
    x: +(60 + 28 * Math.sin(a * DEG2RAD)).toFixed(2),
    y: +(60 - 28 * Math.cos(a * DEG2RAD)).toFixed(2),
  }
})
</script>

<style scoped>
.env-wind-dart {
  transform-box: view-box;
  transform-origin: 60px 60px;
  transition: transform 0.9s cubic-bezier(0.22, 1, 0.36, 1);
}
/* CRT scanlines matching the blueprint hero blocks */
.env-scanlines {
  background: repeating-linear-gradient(
    0deg,
    transparent,
    transparent 3px,
    rgba(255, 255, 255, 0.02) 3px,
    rgba(255, 255, 255, 0.02) 4px
  );
  mix-blend-mode: overlay;
}
.env-scanlines::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(
    180deg,
    transparent 0%,
    rgba(255, 193, 7, 0.03) 45%,
    rgba(255, 193, 7, 0.06) 50%,
    rgba(255, 193, 7, 0.03) 55%,
    transparent 100%
  );
  animation: env-scanline-sweep 6s linear infinite;
}
@keyframes env-scanline-sweep {
  0% { transform: translateY(-100%); }
  100% { transform: translateY(100%); }
}
@media (prefers-reduced-motion: reduce) {
  .env-wind-dart { transition: none; }
  .env-scanlines::after { animation: none; }
}
</style>
