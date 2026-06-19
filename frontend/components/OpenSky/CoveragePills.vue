<template>
  <div class="flex items-center gap-1">
    <div
      v-for="pill in pills"
      :key="pill.key"
      :class="pillClass(pill.level)"
      class="px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold leading-none min-w-[1.75rem] text-center transition-colors"
      :title="tooltip(pill)"
    >
      {{ pill.label }}
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * Coverage pills — 5 compact pills (2D, N, E, S, W) showing per-direction
 * photo counts for an OpenSky mission. Informational only; no warnings
 * or "missing direction" framing.
 *
 * Levels:
 *   - full (green):  count ≥ COVERAGE_THRESHOLD
 *   - partial (amber): 0 < count < COVERAGE_THRESHOLD
 *   - empty (gray outline): count === 0
 *
 * Extra ? pill shown only if there are "unknown" photos (EXIF missing yaw/pitch,
 * typically legacy DJI firmware), to inform rather than alarm.
 */

interface DirectionCounts {
  nadir: number
  n: number
  e: number
  s: number
  w: number
  unknown: number
}

const props = defineProps<{ counts: DirectionCounts }>()

// Must match DIRECTION_COVERAGE_THRESHOLD in geo/endpoints/opensky.py
const COVERAGE_THRESHOLD = 50

type Level = 'full' | 'partial' | 'empty'

interface Pill {
  key: string
  label: string
  count: number
  level: Level
  tooltipKey: string
}

const { t } = useI18n()

const levelFor = (count: number): Level => {
  if (count >= COVERAGE_THRESHOLD) return 'full'
  if (count > 0) return 'partial'
  return 'empty'
}

const pills = computed<Pill[]>(() => {
  const c = props.counts
  const base: Pill[] = [
    { key: 'nadir', label: '2D', count: c.nadir, level: levelFor(c.nadir), tooltipKey: 'opensky.direction_nadir' },
    { key: 'n',     label: 'N',  count: c.n,     level: levelFor(c.n),     tooltipKey: 'opensky.direction_n' },
    { key: 'e',     label: 'E',  count: c.e,     level: levelFor(c.e),     tooltipKey: 'opensky.direction_e' },
    { key: 's',     label: 'S',  count: c.s,     level: levelFor(c.s),     tooltipKey: 'opensky.direction_s' },
    { key: 'w',     label: 'W',  count: c.w,     level: levelFor(c.w),     tooltipKey: 'opensky.direction_w' },
  ]
  // Unknown pill appears only when legacy EXIF photos exist
  if (c.unknown > 0) {
    base.push({ key: 'unknown', label: '?', count: c.unknown, level: 'partial', tooltipKey: 'opensky.direction_unknown' })
  }
  return base
})

const pillClass = (level: Level) => {
  if (level === 'full') return 'bg-success text-white'
  if (level === 'partial') return 'bg-warning/20 text-warning border border-warning/40'
  return 'border border-neutral-300 dark:border-neutral-600 text-neutral-400'
}

const tooltip = (pill: Pill) => {
  const label = t(pill.tooltipKey, pill.label)
  return `${label}: ${pill.count}`
}
</script>
