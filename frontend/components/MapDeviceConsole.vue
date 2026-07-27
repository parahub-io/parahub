<template>
  <div class="mdc-root">
    <!-- Type scope chips (shown only when the fleet spans 2+ types) -->
    <div v-if="chips.length > 2" class="mdc-chips">
      <button
        v-for="c in chips"
        :key="c.id"
        class="mdc-chip"
        :class="{ active: filter === c.id }"
        @click="filter = c.id"
      >
        {{ c.label }}
        <span class="mdc-chip-count">{{ c.count }}</span>
      </button>
    </div>

    <!-- Name filter: appears only for large fleets -->
    <div v-if="totalCount > 8" class="mdc-search">
      <Search :size="13" class="mdc-search-icon" />
      <input
        v-model="query"
        type="text"
        class="mdc-search-input"
        :placeholder="$t('map.controls.filter_devices')"
      />
      <button v-if="query" class="mdc-search-clear" :aria-label="$t('map.controls.clear')" @click="query = ''">
        <X :size="12" />
      </button>
    </div>

    <!-- Scrollable list, sticky section headers, scroll fades -->
    <div class="mdc-list-wrap">
      <div ref="listEl" class="mdc-list" @scroll="updateFades">
        <template v-for="s in sections" :key="s.kind">
          <div class="mdc-section-head">
            <component :is="s.icon" :size="13" class="mdc-section-icon" />
            <span class="mdc-section-title">{{ s.label }}</span>
            <span class="mdc-section-count">{{ s.online }}/{{ s.items.length }}</span>
            <button
              v-if="s.layerOn !== undefined"
              class="mdc-eye"
              :aria-label="s.layerOn
                ? $t('map.toggle_hide_layer', { layer: s.label })
                : $t('map.toggle_show_layer', { layer: s.label })"
              @click="$emit('toggle-layer', s.kind)"
            >
              <Eye v-if="s.layerOn" :size="13" />
              <EyeOff v-else :size="13" class="opacity-50" />
            </button>
          </div>
          <button
            v-for="row in s.items"
            :key="row.key"
            class="mdc-row"
            :class="{ dimmed: s.layerOn === false }"
            :disabled="row.disabled"
            @click="$emit('select', row.kind, row.raw)"
            @mouseenter="onRowEnter(row)"
            @mouseleave="$emit('preview', null)"
          >
            <!-- Marker-grammar status: mini device hex mirroring the map marker;
                 property icon for homes (no map marker) -->
            <component :is="row.homeIcon" v-if="row.kind === 'home'" :size="14" class="mdc-home-icon" />
            <span v-else class="mdc-hex" :style="{ opacity: row.hexOpacity ?? 1 }">
              <svg viewBox="0 0 100 100">
                <polygon :points="HEX" :fill="row.fill" stroke="#1f2937" stroke-width="1" vector-effect="non-scaling-stroke" />
              </svg>
              <component :is="row.glyph" v-if="row.glyph" :size="8" :stroke-width="3" class="mdc-hex-glyph" :style="{ color: glyphColor(row.fill) }" />
            </span>
            <span class="mdc-name">{{ row.name }}</span>
            <span v-if="row.metaLost" class="mdc-meta-lost">{{ row.metaLost }}</span>
            <span v-else-if="row.meta" class="mdc-meta">{{ row.meta }}</span>
          </button>
        </template>
        <div v-if="sections.length === 0" class="mdc-empty">{{ $t('map.controls.no_devices') }}</div>
      </div>
      <div v-show="!atTop" class="mdc-fade mdc-fade-top" />
      <div v-show="!atBottom" class="mdc-fade mdc-fade-bottom" />
    </div>

    <div class="mdc-hint">{{ $t('map.controls.hint') }}</div>
  </div>
</template>

<script setup lang="ts">
/**
 * IoT device console for the map control strip: type scope chips with counts,
 * name filter for large fleets, sticky sections (homes / trackers / routers /
 * energy cells / env stations) with per-layer visibility eyes, rows sorted
 * live-first with marker-grammar status hexes mirroring the map markers 1:1.
 *
 * Data comes in production shapes: propertyStore.properties,
 * iot.trackerPositionsList, iot.meshRouterPositionsList, iot.energyCellsList,
 * iot.envStationsList.
 */
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { Building2, Eye, EyeOff, Home, LandPlot, Leaf, Navigation, Radar, Search, Warehouse, Wifi, Wind, X, Zap } from 'lucide-vue-next'

type Kind = 'home' | 'tracker' | 'router' | 'energy' | 'env'

interface ConsoleRow {
  key: string
  kind: Kind
  name: string
  /** Live-first sort rank within the section: 0 = live, higher = worse */
  rank: number
  /** Hex fill — same color the device's map marker uses */
  fill: string
  glyph?: any
  /** Stale readings render at reduced opacity (marker grammar) */
  hexOpacity?: number
  meta?: string
  metaLost?: string
  homeIcon?: any
  disabled?: boolean
  lat?: number
  lon?: number
  raw: any
}

const props = defineProps<{
  properties: any[]
  trackers: any[]
  routers: any[]
  energyCells: any[]
  envStations: any[]
  trackersEnabled: boolean
  routersEnabled: boolean
  energyEnabled: boolean
  envEnabled: boolean
}>()

const emit = defineEmits<{
  (e: 'select', kind: Kind, item: any): void
  (e: 'toggle-layer', kind: Kind): void
  (e: 'preview', pos: { lat: number; lon: number } | null): void
}>()

const { t } = useI18n()

const HEX = '27,9 73,9 97,50 73,91 27,91 3,50'

const filter = ref<'all' | Kind>('all')
const query = ref('')

// ── Marker colors (mirror useMapIoTLayers painters) ──

const DEVICE_STATUS_COLORS: Record<string, string> = {
  online: '#4E4EC8', unknown: '#a3a3a3', offline: '#ef4444',
}

const ENERGY_STATUS_COLORS: Record<string, string> = {
  GREEN: '#22c55e', YELLOW: '#eab308', RED: '#ef4444', OFFLINE: '#6b7280',
}

const AQI_COLORS: Record<string, string> = {
  good: '#22c55e',
  moderate: '#eab308',
  unhealthy_sensitive: '#f97316',
  unhealthy: '#ef4444',
  very_unhealthy: '#a855f7',
  hazardous: '#7f1d1d',
}
const ENV_WEATHER_COLOR = '#38bdf8'

// ── Row builders (normalize production shapes) ──

const propertyTypeIcon = (type: string) => {
  switch (type) {
    case 'apartment': return Building2
    case 'garage': return Warehouse
    case 'land': return LandPlot
    default: return Home
  }
}

/** Age in minutes since last tracker update, or 0 if fresh/unavailable. */
const trackerSignalAge = (tr: any): number => {
  if (!tr.last_update) return 0
  return Math.floor((Date.now() - new Date(tr.last_update).getTime()) / 60_000)
}

const ageText = (min: number): string => {
  if (min < 60) return `${min}m`
  const h = Math.floor(min / 60)
  const rem = min % 60
  return rem > 0 ? `${h}h${rem}m` : `${h}h`
}

const homeRows = computed<ConsoleRow[]>(() => props.properties.map((p) => ({
  key: `home-${p.id}`,
  kind: 'home' as const,
  name: p.name,
  rank: 0,
  fill: '',
  meta: p.device_count ? `${p.device_count} IoT` : undefined,
  homeIcon: propertyTypeIcon(p.property_type),
  disabled: !p.latitude,
  lat: p.latitude,
  lon: p.longitude,
  raw: p,
})))

const trackerRows = computed<ConsoleRow[]>(() => props.trackers.map((tr) => {
  const age = trackerSignalAge(tr)
  const status = tr.traccar_status === 'online' ? 'online' : tr.traccar_status === 'offline' ? 'offline' : 'unknown'
  return {
    key: `tr-${tr.device_id}`,
    kind: 'tracker' as const,
    name: tr.name,
    rank: status === 'online' ? 0 : status === 'unknown' ? 1 : 2,
    fill: DEVICE_STATUS_COLORS[status],
    glyph: Navigation,
    metaLost: age >= 5 ? ageText(age) : undefined,
    meta: tr.speed && tr.speed > 1 ? `${Math.round(tr.speed)} km/h` : undefined,
    lat: tr.latitude,
    lon: tr.longitude,
    raw: tr,
  }
}))

const routerRows = computed<ConsoleRow[]>(() => props.routers.map((r) => {
  // Mesh status: 'recent' (10-30 min) renders as stale grey, per marker grammar
  const status = r.status === 'online' ? 'online' : r.status === 'offline' ? 'offline' : 'unknown'
  return {
    key: `rt-${r.device_id}`,
    kind: 'router' as const,
    name: r.name,
    rank: status === 'online' ? 0 : status === 'unknown' ? 1 : 2,
    fill: DEVICE_STATUS_COLORS[status],
    glyph: Wifi,
    lat: r.latitude,
    lon: r.longitude,
    raw: r,
  }
}))

const energyRows = computed<ConsoleRow[]>(() => props.energyCells.map((c) => ({
  key: `en-${c.id}`,
  kind: 'energy' as const,
  name: c.name,
  rank: c.status === 'OFFLINE' ? 1 : 0,
  fill: ENERGY_STATUS_COLORS[c.status] || '#6b7280',
  glyph: Zap,
  meta: c.current_price_eur != null ? `${c.current_price_eur} €/kWh` : undefined,
  lat: c.latitude,
  lon: c.longitude,
  raw: c,
})))

const envRows = computed<ConsoleRow[]>(() => props.envStations.map((s) => {
  const isAir = s.latest?.aqi != null
  return {
    key: `env-${s.id}`,
    kind: 'env' as const,
    name: s.name,
    rank: s.stale ? 1 : 0,
    // Fill = data (AQI category), not status — env stations are the marker
    // grammar's data exception; staleness = opacity
    fill: (s.latest?.aqi_category && AQI_COLORS[s.latest.aqi_category]) || ENV_WEATHER_COLOR,
    glyph: isAir ? Leaf : Wind,
    hexOpacity: s.stale ? 0.45 : 1,
    meta: isAir ? `AQI ${s.latest.aqi}` : s.latest?.temperature != null ? `${Math.round(s.latest.temperature)}°` : undefined,
    lat: s.latitude,
    lon: s.longitude,
    raw: s,
  }
}))

// ── Chips / sections ──

const totalCount = computed(() =>
  homeRows.value.length + trackerRows.value.length + routerRows.value.length
  + energyRows.value.length + envRows.value.length)

const chips = computed(() => [
  { id: 'all' as const, label: t('map.controls.all'), count: totalCount.value },
  { id: 'home' as const, label: t('map.controls.homes'), count: homeRows.value.length },
  { id: 'tracker' as const, label: t('map.controls.trackers'), count: trackerRows.value.length },
  { id: 'router' as const, label: t('map.controls.routers'), count: routerRows.value.length },
  { id: 'energy' as const, label: t('map.layers.energy'), count: energyRows.value.length },
  { id: 'env' as const, label: t('map.layers.environment'), count: envRows.value.length },
].filter((c) => c.count > 0))

const sections = computed(() => {
  const q = query.value.trim().toLowerCase()
  const defs = [
    { kind: 'home' as const, label: t('property.my_homes'), icon: Home, rows: homeRows.value, layerOn: undefined as boolean | undefined },
    { kind: 'tracker' as const, label: t('map.controls.gps_trackers'), icon: Radar, rows: trackerRows.value, layerOn: props.trackersEnabled },
    { kind: 'router' as const, label: t('map.controls.mesh_routers'), icon: Wifi, rows: routerRows.value, layerOn: props.routersEnabled },
    { kind: 'energy' as const, label: t('map.controls.energy_cells'), icon: Zap, rows: energyRows.value, layerOn: props.energyEnabled },
    { kind: 'env' as const, label: t('map.controls.env_stations'), icon: Wind, rows: envRows.value, layerOn: props.envEnabled },
  ]
  return defs
    .filter((d) => filter.value === 'all' || filter.value === d.kind)
    .map((d) => {
      const items = d.rows
        .filter((row) => !q || row.name.toLowerCase().includes(q))
        .sort((a, b) => a.rank - b.rank || a.name.localeCompare(b.name))
      return { ...d, items, online: items.filter((row) => row.rank === 0).length }
    })
    .filter((s) => s.items.length > 0)
})

// ── Interactions ──

function onRowEnter(row: ConsoleRow) {
  if (row.lat != null && row.lon != null) emit('preview', { lat: row.lat, lon: row.lon })
}

// Auto-contrast glyph (production glyphColorFor, luminance cut 0.55)
function glyphColor(hex: string): string {
  const h = hex.slice(1)
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255)
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.55 ? '#1f2937' : '#ffffff'
}

// ── Scroll fades: signal hidden content above/below ──

const listEl = ref<HTMLElement | null>(null)
const atTop = ref(true)
const atBottom = ref(true)

function updateFades() {
  const el = listEl.value
  if (!el) return
  atTop.value = el.scrollTop <= 2
  atBottom.value = el.scrollTop + el.clientHeight >= el.scrollHeight - 2
}

onMounted(() => nextTick(updateFades))
watch([sections], () => nextTick(updateFades))
</script>

<style scoped>
.mdc-root {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

/* ── Type scope chips ── */
.mdc-chips {
  display: flex;
  gap: 4px;
  padding: 0 2px 8px;
  flex-wrap: wrap;
}

.mdc-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border: 1px solid var(--color-border, #e5e5e5);
  border-radius: 999px;
  background: none;
  color: var(--color-text);
  font-size: 10px;
  font-weight: 500;
  cursor: pointer;
}
.mdc-chip:hover {
  background: var(--color-primary-100, #fef9c3);
}
:root.dark .mdc-chip:hover {
  background: var(--color-primary-900, #422006);
}
.mdc-chip.active,
:root.dark .mdc-chip.active {
  background: var(--color-primary, #ffe216);
  border-color: transparent;
  color: #171717;
}
.mdc-chip-count {
  font-variant-numeric: tabular-nums;
  opacity: 0.65;
}

/* ── Search ── */
.mdc-search {
  position: relative;
  display: flex;
  align-items: center;
  margin: 0 2px 8px;
}
.mdc-search-icon {
  position: absolute;
  left: 8px;
  color: var(--color-text-muted, #737373);
  pointer-events: none;
}
.mdc-search-input {
  width: 100%;
  height: 28px;
  padding: 0 24px 0 26px;
  border: 1px solid var(--color-border, #e5e5e5);
  border-radius: 8px;
  background: transparent;
  color: var(--color-text);
  font-size: 11px;
  outline: none;
}
.mdc-search-input:focus {
  border-color: transparent;
  box-shadow: 0 0 0 2px var(--color-primary, #ffe216);
}
.mdc-search-input::placeholder { color: var(--color-text-muted, #a3a3a3); }
.mdc-search-clear {
  position: absolute;
  right: 6px;
  display: flex;
  padding: 2px;
  border: none;
  background: none;
  color: var(--color-text-muted, #737373);
  cursor: pointer;
}

/* ── List ── */
.mdc-list-wrap {
  position: relative;
  min-height: 0;
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
}

.mdc-list {
  overflow-y: auto;
  scrollbar-gutter: stable;
  overscroll-behavior: contain;
  min-height: 0;
  flex: 1 1 auto;
}

.mdc-section-head {
  position: sticky;
  top: 0;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 6px 4px 4px;
  background: var(--color-surface, #fff);
  border-bottom: 1px solid var(--color-border, #e5e5e5);
}
:root.dark .mdc-section-head { background: #171717; }

.mdc-section-icon { color: var(--color-text-muted, #737373); flex-shrink: 0; }

.mdc-section-title {
  flex: 1;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-muted, #737373);
}

.mdc-section-count {
  font-size: 10px;
  font-variant-numeric: tabular-nums;
  color: var(--color-text-muted, #a3a3a3);
}

.mdc-eye {
  display: flex;
  padding: 2px;
  border: none;
  background: none;
  color: var(--color-text-muted, #737373);
  cursor: pointer;
}
.mdc-eye:hover { color: var(--color-secondary, #4e4ec8); }

.mdc-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 0 4px;
  height: 34px;
  border: none;
  background: none;
  cursor: pointer;
  text-align: left;
  font-size: 12px;
  color: var(--color-text);
  border-radius: 6px;
}
.mdc-row:hover {
  background: var(--color-primary-100, #fef9c3);
}
:root.dark .mdc-row:hover {
  background: var(--color-primary-900, #422006);
}
.mdc-row.dimmed { opacity: 0.45; }
.mdc-row:disabled { opacity: 0.4; cursor: default; }

.mdc-hex {
  position: relative;
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}
.mdc-hex svg { width: 100%; height: 100%; display: block; overflow: visible; }
.mdc-hex-glyph {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  pointer-events: none;
}

.mdc-home-icon {
  flex-shrink: 0;
  color: var(--color-text-muted, #737373);
}

.mdc-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mdc-meta {
  flex-shrink: 0;
  font-size: 10px;
  font-variant-numeric: tabular-nums;
  color: var(--color-text-muted, #737373);
}

.mdc-meta-lost {
  flex-shrink: 0;
  font-size: 10px;
  font-variant-numeric: tabular-nums;
  color: var(--color-error, #dc2626);
  opacity: 0.85;
}

.mdc-empty {
  padding: 20px 8px;
  text-align: center;
  font-size: 11px;
  color: var(--color-text-muted, #a3a3a3);
}

/* Scroll fades (overlay the list, not scrolling with it) */
.mdc-fade {
  position: absolute;
  left: 0;
  right: 0;
  height: 22px;
  pointer-events: none;
}
.mdc-fade-top {
  top: 0;
  background: linear-gradient(to bottom, var(--color-surface, #fff), transparent);
}
.mdc-fade-bottom {
  bottom: 0;
  background: linear-gradient(to top, var(--color-surface, #fff), transparent);
}
:root.dark .mdc-fade-top { background: linear-gradient(to bottom, #171717, transparent); }
:root.dark .mdc-fade-bottom { background: linear-gradient(to top, #171717, transparent); }

.mdc-hint {
  padding: 7px 4px 1px;
  border-top: 1px solid var(--color-border, #e5e5e5);
  margin-top: 6px;
  font-size: 9px;
  letter-spacing: 0.02em;
  color: var(--color-text-muted, #a3a3a3);
}

/* Hover hints are meaningless on touch */
@media (max-width: 767px) {
  .mdc-hint { display: none; }
}
</style>
