<template>
  <div ref="wrapEl" class="utc-wrap">
    <!-- Legend (≥2 series only — a single series is named by its section title) -->
    <div v-if="series.length >= 2" class="flex items-center gap-3 mb-1">
      <span
        v-for="(s, i) in series" :key="s.key"
        class="inline-flex items-center gap-1.5 text-[11px] text-neutral-500 dark:text-neutral-400"
      >
        <span class="w-2 h-2 rounded-full" :class="`utc-swatch-${i}`" />
        {{ s.label }}
      </span>
    </div>

    <div class="relative" :style="{ height: height + 'px' }">
      <svg
        v-if="width > 0 && hasData"
        :width="width" :height="height" class="block touch-none select-none"
        @pointermove="onMove" @pointerleave="hover = null"
      >
        <g v-if="!compact">
          <line
            v-for="g in yTicks" :key="'g' + g.y"
            :x1="0" :x2="width" :y1="g.y" :y2="g.y" class="utc-grid"
          />
          <text v-for="g in yTicks" :key="'l' + g.y" :x="1" :y="g.y - 3" class="utc-label">{{ g.label }}</text>
          <text
            v-for="(xl, i) in xTicks" :key="'x' + i"
            :x="xl.x" :y="height - 2" class="utc-label"
            :text-anchor="xl.anchor"
          >{{ xl.label }}</text>
        </g>

        <path v-if="series.length === 1 && areaPath" :d="areaPath" class="utc-area-0" />
        <g v-for="(sp, i) in seriesPaths" :key="'s' + i">
          <path
            v-if="sp.path" :d="sp.path" fill="none" stroke-width="2"
            stroke-linejoin="round" stroke-linecap="round" :class="`utc-line-${i}`"
          />
          <circle
            v-for="(lp, j) in sp.lonePoints" :key="'lp' + j"
            :cx="lp.x" :cy="lp.y" r="2" :class="`utc-fill-${i}`"
          />
        </g>

        <g v-if="hover">
          <line :x1="hover.x" :x2="hover.x" :y1="0" :y2="plotH" class="utc-cross" />
          <circle
            v-for="(d, i) in hover.dots" :key="'h' + i"
            :cx="hover.x" :cy="d.y" r="3" :class="`utc-fill-${d.si}`"
          />
        </g>
      </svg>
      <div
        v-else-if="width > 0"
        class="h-full flex items-center justify-center text-xs text-neutral-400 dark:text-neutral-500"
      >
        {{ emptyText || '—' }}
      </div>

      <div v-if="hover" class="utc-tip" :style="tipStyle">
        <div class="text-neutral-400 dark:text-neutral-500 mb-0.5">{{ hover.timeLabel }}</div>
        <div v-for="r in hover.rows" :key="r.si" class="flex items-center gap-1.5 whitespace-nowrap">
          <span class="w-1.5 h-1.5 rounded-full shrink-0" :class="`utc-swatch-${r.si}`" />
          <span v-if="series.length >= 2" class="text-neutral-500 dark:text-neutral-400">{{ series[r.si].label }}</span>
          <span class="font-medium text-neutral-900 dark:text-neutral-100 ml-auto">{{ r.value }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'

export interface TimeChartSeries {
  key: string
  label: string
  /** [epoch ms, value|null] — null breaks the line (honest gap) */
  points: Array<{ t: number; v: number | null }>
}

const props = withDefaults(defineProps<{
  series: TimeChartSeries[]
  height?: number
  /** No grid/axis labels — sparkline for tight panels (tooltip stays) */
  compact?: boolean
  /** Anchor y at zero (rates, counts). Off for temperature-like metrics */
  zeroBase?: boolean
  format?: (v: number) => string
  emptyText?: string
}>(), {
  height: 96,
  compact: false,
  zeroBase: true,
  format: (v: number) => (Math.abs(v) >= 100 ? String(Math.round(v)) : String(Math.round(v * 10) / 10)),
})

const { locale } = useI18n()

const wrapEl = ref<HTMLElement | null>(null)
const width = ref(0)
let ro: ResizeObserver | null = null
onMounted(() => {
  if (!wrapEl.value) return
  ro = new ResizeObserver((entries) => { width.value = entries[0]?.contentRect.width ?? 0 })
  ro.observe(wrapEl.value)
  width.value = wrapEl.value.clientWidth
})
onUnmounted(() => { ro?.disconnect(); ro = null })

const plotH = computed(() => props.height - (props.compact ? 0 : 12))

const allTs = computed(() => {
  const set = new Set<number>()
  for (const s of props.series) for (const p of s.points) set.add(p.t)
  return [...set].sort((a, b) => a - b)
})
const hasData = computed(() =>
  props.series.some(s => s.points.some(p => p.v != null)))

const xDomain = computed<[number, number]>(() => {
  const ts = allTs.value
  if (!ts.length) return [0, 1]
  return ts.length > 1 ? [ts[0], ts[ts.length - 1]] : [ts[0] - 1, ts[0] + 1]
})

const yDomain = computed<[number, number]>(() => {
  let min = Infinity, max = -Infinity
  for (const s of props.series) for (const p of s.points) {
    if (p.v == null) continue
    if (p.v < min) min = p.v
    if (p.v > max) max = p.v
  }
  if (min === Infinity) return [0, 1]
  if (props.zeroBase) min = Math.min(0, min)
  if (min === max) { max = min + 1; if (!props.zeroBase) min -= 1 }
  else if (!props.zeroBase) {
    const pad = (max - min) * 0.1
    min -= pad; max += pad
  } else max *= 1.05
  return [min, max]
})

const sx = (t: number) => {
  const [a, b] = xDomain.value
  return ((t - a) / (b - a)) * width.value
}
const sy = (v: number) => {
  const [a, b] = yDomain.value
  return plotH.value - 2 - ((v - a) / (b - a)) * (plotH.value - 6)
}

// A missing heartbeat run reads as a gap, not a straight bridge: break the
// line when the step exceeds 3× the median interval (min 15 min).
const gapMs = computed(() => {
  const ts = allTs.value
  if (ts.length < 3) return Infinity
  const deltas = ts.slice(1).map((t, i) => t - ts[i]).sort((a, b) => a - b)
  return Math.max(3 * deltas[Math.floor(deltas.length / 2)], 15 * 60_000)
})

const seriesPaths = computed(() => props.series.map((s) => {
  let path = ''
  const lonePoints: Array<{ x: number; y: number }> = []
  let seg: string[] = []
  let prevT = -Infinity
  const flush = () => {
    if (seg.length === 1) {
      const [x, y] = seg[0].split(',').map(Number)
      lonePoints.push({ x, y })
    } else if (seg.length > 1) {
      path += 'M' + seg.join('L')
    }
    seg = []
  }
  for (const p of s.points) {
    if (p.v == null || p.t - prevT > gapMs.value) flush()
    if (p.v != null) seg.push(`${sx(p.t).toFixed(1)},${sy(p.v).toFixed(1)}`)
    prevT = p.t
  }
  flush()
  return { path, lonePoints }
}))

const areaPath = computed(() => {
  const line = seriesPaths.value[0]?.path
  if (!line || props.series.length !== 1) return ''
  // Close each segment down to the baseline
  const base = (plotH.value - 2).toFixed(1)
  return line.split('M').filter(Boolean).map((seg) => {
    const pts = seg.split('L')
    const x0 = pts[0].split(',')[0]
    const x1 = pts[pts.length - 1].split(',')[0]
    return `M${x0},${base}L${seg}L${x1},${base}Z`
  }).join('')
})

function niceStep(raw: number): number {
  const mag = 10 ** Math.floor(Math.log10(raw))
  for (const m of [1, 2, 5, 10]) if (raw <= m * mag) return m * mag
  return 10 * mag
}

const yTicks = computed(() => {
  if (props.compact) return []
  const [min, max] = yDomain.value
  const step = niceStep((max - min) / 3)
  const out: Array<{ y: number; label: string }> = []
  for (let v = Math.ceil(min / step) * step; v <= max; v += step) {
    const y = sy(v)
    if (y < 10 || y > plotH.value - 2) continue
    out.push({ y, label: props.format(v) })
  }
  return out
})

const spanMs = computed(() => xDomain.value[1] - xDomain.value[0])

function fmtTime(t: number, withDate = spanMs.value > 48 * 3600_000): string {
  const d = new Date(t)
  try {
    return withDate
      ? new Intl.DateTimeFormat(locale.value, { day: 'numeric', month: 'short' }).format(d)
      : new Intl.DateTimeFormat(locale.value, { hour: '2-digit', minute: '2-digit' }).format(d)
  } catch { return d.toISOString().slice(withDate ? 5 : 11, withDate ? 10 : 16) }
}

function fmtTooltipTime(t: number): string {
  const d = new Date(t)
  try {
    return new Intl.DateTimeFormat(locale.value, {
      ...(spanMs.value > 24 * 3600_000 ? { day: 'numeric', month: 'short' } : {}),
      hour: '2-digit', minute: '2-digit',
    }).format(d)
  } catch { return d.toISOString().slice(5, 16) }
}

const xTicks = computed(() => {
  if (props.compact || !allTs.value.length) return []
  const [a, b] = xDomain.value
  return [
    { x: 1, label: fmtTime(a), anchor: 'start' },
    { x: width.value / 2, label: fmtTime(a + (b - a) / 2), anchor: 'middle' },
    { x: width.value - 1, label: fmtTime(b), anchor: 'end' },
  ]
})

// ---- Hover: crosshair + tooltip on the nearest shared timestamp ----
const hover = ref<null | {
  x: number
  timeLabel: string
  dots: Array<{ si: number; y: number }>
  rows: Array<{ si: number; value: string }>
}>(null)

const valueAt = computed(() =>
  props.series.map(s => new Map(s.points.map(p => [p.t, p.v]))))

function onMove(e: PointerEvent) {
  const ts = allTs.value
  if (!ts.length || !width.value) return
  const rect = (e.currentTarget as SVGElement).getBoundingClientRect()
  const px = e.clientX - rect.left
  const [a, b] = xDomain.value
  const target = a + (px / width.value) * (b - a)
  let lo = 0, hi = ts.length - 1
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1
    if (ts[mid] < target) lo = mid; else hi = mid
  }
  const t = Math.abs(ts[lo] - target) <= Math.abs(ts[hi] - target) ? ts[lo] : ts[hi]
  const dots: Array<{ si: number; y: number }> = []
  const rows: Array<{ si: number; value: string }> = []
  props.series.forEach((_, si) => {
    const v = valueAt.value[si].get(t)
    if (v == null) return
    dots.push({ si, y: sy(v) })
    rows.push({ si, value: props.format(v) })
  })
  if (!rows.length) { hover.value = null; return }
  hover.value = { x: sx(t), timeLabel: fmtTooltipTime(t), dots, rows }
}

const tipStyle = computed(() => {
  if (!hover.value) return {}
  const flip = hover.value.x > width.value * 0.6
  return {
    left: flip ? 'auto' : `${hover.value.x + 8}px`,
    right: flip ? `${width.value - hover.value.x + 8}px` : 'auto',
    top: '0px',
  }
})
</script>

<style>
.utc-wrap { min-width: 0; }
.utc-grid { stroke: rgb(0 0 0 / 0.07); }
.dark .utc-grid { stroke: rgb(255 255 255 / 0.09); }
.utc-label { fill: #a3a3a3; font-size: 10px; }
.dark .utc-label { fill: #737373; }
.utc-cross { stroke: #a3a3a3; stroke-dasharray: 2 2; }
.utc-tip {
  position: absolute; z-index: 10; pointer-events: none;
  font-size: 11px; line-height: 1.35; padding: 4px 8px; border-radius: 6px;
  background: #ffffff; border: 1px solid #e5e5e5;
  box-shadow: 0 2px 8px rgb(0 0 0 / 0.08); min-width: 72px;
}
.dark .utc-tip { background: #171717; border-color: #404040; }

/* Series palette — CVD-validated pair (indigo / amber), dark steps re-validated
   against the neutral-800 card surface. */
.utc-line-0 { stroke: #4E4EC8; }
.utc-fill-0, .utc-swatch-0 { fill: #4E4EC8; background: #4E4EC8; }
.utc-area-0 { fill: #4E4EC8; opacity: 0.08; }
.dark .utc-line-0 { stroke: #6E6ECE; }
.dark .utc-fill-0, .dark .utc-swatch-0 { fill: #6E6ECE; background: #6E6ECE; }
.dark .utc-area-0 { fill: #6E6ECE; opacity: 0.14; }
.utc-line-1 { stroke: #D97706; }
.utc-fill-1, .utc-swatch-1 { fill: #D97706; background: #D97706; }
</style>
