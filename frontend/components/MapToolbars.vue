<template>
  <!-- Measure bar (bottom center) -->
  <div v-if="measureActive" class="measure-bar">
    <span v-if="measure.measurePoints.value.length === 0" class="measure-bar-hint">{{ $t('map.architect.click_to_measure') }}</span>
    <template v-else-if="measureMode === 'area'">
      <span class="measure-bar-distance">{{ measure.formattedArea.value }}</span>
      <span class="measure-bar-segments">{{ $t('map.architect.perimeter') }}: {{ measure.formattedPerimeter.value }}</span>
    </template>
    <template v-else>
      <span class="measure-bar-distance">{{ measure.formattedTotal.value }}</span>
      <span class="measure-bar-segments">{{ measure.measurePoints.value.length }} {{ $t('map.architect.points') }}</span>
    </template>
    <button @click="measure.undoLastPoint()" class="measure-bar-btn" :disabled="measure.measurePoints.value.length === 0">
      {{ $t('map.architect.undo') }}
    </button>
    <button @click="measure.clearMeasure()" class="measure-bar-btn" :disabled="measure.measurePoints.value.length === 0">
      {{ $t('map.architect.clear') }}
    </button>
    <button @click="measure.stopMeasure()" class="measure-bar-btn measure-bar-btn-close">
      ×
    </button>
  </div>

  <!-- Sun study panel (bottom center) -->
  <div v-if="sunStudyActive" class="sun-study-panel">
    <div class="sun-study-header">
      <Sun class="w-4 h-4 flex-shrink-0 text-amber-500" />
      <input type="date" v-model="sunDateISO" class="sun-study-date" />
      <span class="sun-study-time-display">{{ formattedTime }}</span>
      <div class="sun-study-badges">
        <button
          class="sun-study-badge"
          :class="realtimeMode ? 'sun-live' : 'sun-live-off'"
          @click="!realtimeMode && sunStudy.startSunStudy()"
        >{{ $t('map.architect.live') }}</button>
        <span v-if="isGoldenHour" class="sun-study-badge sun-golden">{{ $t('map.architect.golden_hour') }}</span>
        <span v-else-if="isNight" class="sun-study-badge sun-night">{{ $t('map.architect.night') }}</span>
      </div>
      <button @click="sunStudy.stopSunStudy()" class="sun-study-close">×</button>
    </div>
    <div class="sun-study-slider-wrap">
      <input
        type="range"
        v-model.number="sunTimeMinutes"
        min="0" max="1440" step="1"
        class="sun-study-slider"
        @input="realtimeMode = false"
      />
      <div class="sun-study-ticks">
        <span v-for="h in [0, 3, 6, 9, 12, 15, 18, 21, 24]" :key="h"
          class="sun-study-tick" :style="{ left: (h / 24 * 100) + '%' }">{{ h }}:00</span>
      </div>
    </div>
    <div class="sun-study-info">
      <span class="sun-study-stat">↑ {{ sunTimes?.sunrise }}</span>
      <span class="sun-study-stat">
        Az {{ sunPosition?.azimuthDeg?.toFixed(0) }}° · Alt {{ sunPosition?.altitudeDeg?.toFixed(1) }}°
      </span>
      <span
        class="sun-study-stat sun-study-uv"
        :title="$t('map.architect.uv_tooltip')"
      >
        <span class="sun-study-uv-dot" :style="{ background: uvCategory.color }"></span>
        UV {{ uvIndex }} · {{ $t(`map.architect.uv_${uvCategory.tier}`) }}
      </span>
      <span class="sun-study-stat">↓ {{ sunTimes?.sunset }}</span>
    </div>
    <div class="sun-study-info sun-study-moon">
      <span class="sun-study-stat sun-study-moon-phase">
        <Moon class="w-3 h-3 flex-shrink-0" :style="{ opacity: 0.35 + 0.6 * (moonFractionPct / 100) }" />
        {{ $t(`map.architect.moon_${moonPhaseKey}`) }} · {{ moonFractionPct }}%
      </span>
      <span class="sun-study-stat" :class="{ 'sun-study-dim': !isMoonUp }">
        Az {{ moonPosition?.azimuthDeg?.toFixed(0) }}° · Alt {{ moonPosition?.altitudeDeg?.toFixed(1) }}°
      </span>
      <span class="sun-study-stat">☾↑ {{ moonTimes?.moonrise }} · ↓ {{ moonTimes?.moonset }}</span>
    </div>
  </div>

  <!-- Isochrone panel (bottom center) -->
  <div v-if="isochroneActive" class="isochrone-bar">
    <template v-if="!isochrone.isochroneCenter.value">
      <span class="measure-bar-hint">{{ $t('map.architect.click_for_isochrone') }}</span>
    </template>
    <template v-else>
      <span class="isochrone-bar-legend">
        <span class="isochrone-dot" style="background: #22c55e"></span>5 min
        <span class="isochrone-dot" style="background: #f59e0b"></span>10 min
        <span class="isochrone-dot" style="background: #ef4444"></span>15 min
      </span>
    </template>
    <div class="isochrone-mode-btns">
      <button
        class="isochrone-mode-btn" :class="{ active: costingMode === 'pedestrian' }"
        @click="isochrone.setCostingMode('pedestrian')" :title="$t('map.architect.pedestrian')"
      >🚶</button>
      <button
        class="isochrone-mode-btn" :class="{ active: costingMode === 'bicycle' }"
        @click="isochrone.setCostingMode('bicycle')" :title="$t('map.architect.bicycle')"
      >🚲</button>
      <button
        class="isochrone-mode-btn" :class="{ active: costingMode === 'auto' }"
        @click="isochrone.setCostingMode('auto')" :title="$t('map.architect.car')"
      >🚗</button>
    </div>
    <span v-if="isochroneLoading" class="isochrone-loading">⏳</span>
    <button @click="isochrone.stopIsochrone()" class="measure-bar-btn measure-bar-btn-close">×</button>
  </div>

  <!-- Drone reachability panel (bottom center) -->
  <div v-if="droneReachActive" class="dronereach-bar">
    <template v-if="!droneReach.launchPoint.value">
      <span class="measure-bar-hint">{{ $t('map.architect.drone_reach_hint') }}</span>
    </template>
    <template v-else>
      <span class="isochrone-bar-legend">
        <span class="isochrone-dot" style="background: #22c55e"></span>{{ $t('map.architect.dr_capturable') }}<span v-if="droneReach.stats.value"> {{ droneReach.stats.value.capturable }}</span>
        <span class="isochrone-dot" style="background: #ef4444; margin-left: 8px"></span>{{ $t('map.architect.dr_terrain') }}<span v-if="droneReach.stats.value"> {{ droneReach.stats.value.terrain }}</span>
        <span class="isochrone-dot" style="background: #f59e0b; margin-left: 8px"></span>{{ $t('map.architect.dr_los') }}<span v-if="droneReach.stats.value"> {{ droneReach.stats.value.los }}</span>
        <span class="isochrone-dot" style="background: #7e22ce; margin-left: 8px"></span>{{ $t('map.architect.dr_restricted') }}<span v-if="droneReach.stats.value"> {{ droneReach.stats.value.restricted }}</span>
      </span>
    </template>
    <span v-if="droneReachSelectedZone" class="dronereach-zoneinfo">
      <span class="isochrone-dot" :style="{ background: '#dc2626' }"></span>
      {{ droneReachSelectedZone.name || droneReachSelectedZone.id }} ·
      {{ $t('map.architect.dr_zone_' + String(droneReachSelectedZone.restriction).toLowerCase(), String(droneReachSelectedZone.restriction)) }}
      · {{ droneReachSelectedZone.lower_m }}–{{ droneReachSelectedZone.upper_m }}m {{ droneReachSelectedZone.upper_ref }}
    </span>
    <div class="dronereach-controls">
      <label class="dronereach-ctl" :title="$t('map.architect.dr_agl_hint')">
        <span>AGL</span>
        <input type="range" min="30" max="120" step="10" :value="droneReachAgl"
          @input="droneReach.setParam('agl', +($event.target as HTMLInputElement).value)" />
        <span class="dronereach-val">{{ droneReachAgl }}m</span>
      </label>
      <label class="dronereach-ctl" :title="$t('map.architect.dr_margin_hint')">
        <span>{{ $t('map.architect.dr_margin') }}</span>
        <input type="range" min="0" max="100" step="10" :value="droneReachMargin"
          @input="droneReach.setParam('margin', +($event.target as HTMLInputElement).value)" />
        <span class="dronereach-val">{{ droneReachMargin }}m</span>
      </label>
      <div class="dronereach-radius">
        <button v-for="r in [500, 2000, 5000]" :key="r"
          class="isochrone-mode-btn" :class="{ active: droneReachRadius === r }"
          @click="droneReach.setParam('radiusM', r)">{{ r < 1000 ? r + 'm' : (r / 1000) + 'km' }}</button>
      </div>
      <button class="isochrone-mode-btn dronereach-zonetoggle" :class="{ active: droneReachShowZones }"
        :title="$t('map.architect.dr_zones_hint')"
        @click="droneReach.setShowZones(!droneReachShowZones)">{{ $t('map.architect.dr_zones') }}</button>
    </div>
    <span v-if="droneReachLoading" class="isochrone-loading">⏳</span>
    <button @click="droneReach.stopDroneReach()" class="measure-bar-btn measure-bar-btn-close">×</button>
  </div>

  <!-- Urban analysis: draw / use-type bar (drawing phase; result shows in the side panel) -->
  <div v-if="urbanActive && !urbanResult" class="urban-bar">
    <Building class="w-4 h-4 flex-shrink-0" style="color: #7c3aed" aria-hidden="true" />
    <!-- Drawing in progress — draw by hand, or upload a ready plot polygon -->
    <template v-if="!urban.closed.value">
      <span class="measure-bar-hint">{{ $t('map.urban.draw_hint') }}</span>
      <span v-if="urban.area.value > 0" class="measure-bar-distance" style="color: #7c3aed">{{ urban.formattedArea.value }}</span>
      <button class="urban-upload-btn" :title="$t('map.urban.load_geojson')" @click="triggerUrbanUpload">
        <Upload class="w-3.5 h-3.5" />
        <span>{{ $t('map.urban.load_geojson') }}</span>
      </button>
      <input ref="urbanFileInput" type="file" accept=".geojson,.json,application/geo+json,application/json" class="hidden" @change="onUrbanFileSelected" />
    </template>
    <!-- Ring closed: pick use type and analyze -->
    <template v-else>
      <span class="measure-bar-distance" style="color: #7c3aed">{{ urban.formattedArea.value }}</span>
      <label class="urban-typesel">
        <span class="urban-typesel-label">{{ $t('map.urban.use_type') }}</span>
        <select v-model="urbanUseType" class="urban-select">
          <option v-for="t in URBAN_USE_TYPES" :key="t" :value="t">{{ $t(`map.urban.types.${t}`) }}</option>
        </select>
      </label>
      <button class="urban-analyze-btn" :disabled="!urban.canAnalyze.value" @click="urban.analyze()">
        {{ urbanLoading ? $t('map.urban.analyzing') : $t('map.urban.analyze') }}
      </button>
      <button class="measure-bar-btn" @click="urban.redraw()">{{ $t('map.urban.redraw') }}</button>
    </template>
    <button @click="urban.stopUrban()" class="measure-bar-btn measure-bar-btn-close">×</button>
  </div>
</template>

<script setup lang="ts">
/**
 * Bottom-center tool bars for the map's architect tools: measure, sun study,
 * isochrone, drone reach, urban analysis. Each bar binds to the composable
 * object MapView passes in; activation/deactivation stays with MapView's
 * controls and Escape handling.
 */
import { ref } from 'vue'
import { Sun, Moon, Building, Upload } from 'lucide-vue-next'
import { URBAN_USE_TYPES } from '~/composables/useMapUrbanAnalysis'

const props = defineProps<{
  measure: any
  sunStudy: any
  isochrone: any
  droneReach: any
  urban: any
}>()

const { measure, sunStudy, isochrone, droneReach, urban } = props

const { t } = useI18n()

// Template aliases (refs auto-unwrap as top-level bindings)
const { measureActive, measureMode } = measure
const { sunStudyActive, sunTimeMinutes, sunDateISO, realtimeMode, sunPosition, sunTimes, formattedTime, isGoldenHour, isNight, uvIndex, uvCategory, moonPosition, moonFractionPct, moonPhaseKey, moonTimes, isMoonUp } = sunStudy
const { isochroneActive, isochroneLoading, costingMode } = isochrone
const { droneReachActive, droneReachLoading } = droneReach
const { agl: droneReachAgl, margin: droneReachMargin, radiusM: droneReachRadius } = droneReach
const { showZones: droneReachShowZones, selectedZone: droneReachSelectedZone } = droneReach
const { urbanActive, urbanLoading } = urban
const urbanUseType = urban.useType
const urbanResult = urban.result

// Upload a ready plot polygon from a GeoJSON file (the professionals' path —
// skip hand-drawing). loadPlotFromGeoJSON validates WGS84 and returns a code.
const urbanFileInput = ref<HTMLInputElement | null>(null)
function triggerUrbanUpload() {
  urbanFileInput.value?.click()
}
async function onUrbanFileSelected(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = '' // allow re-picking the same file
  if (!file) return
  let text: string
  try {
    text = await file.text()
  } catch {
    useToastStore().error(t('map.urban.upload_invalid_json'))
    return
  }
  const res = urban.loadPlotFromGeoJSON(text)
  if (res.ok) useToastStore().success(t('map.urban.upload_loaded'))
  else useToastStore().error(t(`map.urban.upload_${res.error}`))
}
</script>

<style scoped>
/* Measure distance bar */
.measure-bar {
  position: absolute;
  bottom: 40px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1001;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 16px;
  background: var(--color-surface);
  border-radius: 24px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.18);
  white-space: nowrap;
}
:root.dark .measure-bar {
  background: rgba(30, 30, 30, 0.9);
  backdrop-filter: blur(8px);
}

.measure-bar-distance {
  font-size: 16px;
  font-weight: 700;
  color: #3b82f6;
}

.measure-bar-segments {
  font-size: 12px;
  color: var(--color-text-muted);
}

.measure-bar-hint {
  font-size: 13px;
  color: var(--color-text-muted);
}

.measure-bar-btn {
  padding: 4px 10px;
  font-size: 12px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: none;
  color: var(--color-text);
  cursor: pointer;
  transition: background 0.15s;
}
.measure-bar-btn:hover:not(:disabled) {
  background: var(--color-primary-100, #fef9c3);
}
:root.dark .measure-bar-btn:hover:not(:disabled) {
  background: var(--color-primary-900, #422006);
}
.measure-bar-btn:disabled {
  opacity: 0.4;
  cursor: default;
}

.measure-bar-btn-close {
  border: none;
  font-size: 18px;
  padding: 2px 6px;
  line-height: 1;
}

/* Sun study panel */
.sun-study-panel {
  position: absolute;
  bottom: 40px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1001;
  width: 600px;
  max-width: calc(100vw - 20px);
  padding: 12px 16px;
  background: var(--color-surface);
  border-radius: 12px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.18);
}
:root.dark .sun-study-panel {
  background: rgba(30, 30, 30, 0.9);
  backdrop-filter: blur(8px);
}

.sun-study-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  min-width: 0;
}

.sun-study-date {
  flex: 0 0 auto;
  padding: 3px 6px;
  font-size: 13px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: transparent;
  color: var(--color-text);
  cursor: pointer;
}

.sun-study-time-display {
  font-size: 18px;
  font-weight: 700;
  color: #f59e0b;
  flex: 0 0 auto;
}

.sun-study-badges {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  min-width: 0;
}

.sun-study-close {
  border: none;
  background: none;
  font-size: 20px;
  color: var(--color-text-muted);
  cursor: pointer;
  padding: 0 4px;
  line-height: 1;
  flex-shrink: 0;
}
.sun-study-close:hover {
  color: var(--color-text);
}

.sun-study-slider-wrap {
  position: relative;
  padding-bottom: 18px;
}

.sun-study-slider {
  width: 100%;
  height: 6px;
  -webkit-appearance: none;
  appearance: none;
  border-radius: 3px;
  background: linear-gradient(to right, #1e3a5f, #3b82f6, #f59e0b, #f59e0b, #3b82f6, #1e3a5f);
  outline: none;
  margin: 4px 0 0;
}
.sun-study-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #f59e0b;
  border: 2px solid white;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
  cursor: grab;
}
.sun-study-slider::-moz-range-thumb {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #f59e0b;
  border: 2px solid white;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
  cursor: grab;
}

.sun-study-ticks {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 16px;
  pointer-events: none;
}
.sun-study-tick {
  position: absolute;
  transform: translateX(-50%);
  font-size: 9px;
  color: var(--color-text-muted);
  opacity: 0.7;
  &::before {
    content: '';
    position: absolute;
    top: -4px;
    left: 50%;
    width: 1px;
    height: 4px;
    background: var(--color-text-muted);
    opacity: 0.4;
  }
}

.sun-study-info {
  display: flex;
  justify-content: space-between;
  margin-top: 4px;
}

.sun-study-stat {
  font-size: 12px;
  color: var(--color-text-muted);
}

.sun-study-uv {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  cursor: help;
}

.sun-study-moon {
  margin-top: 2px;
  padding-top: 4px;
  border-top: 1px solid var(--color-border);
}

.sun-study-moon-phase {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.sun-study-dim {
  opacity: 0.45;
}

.sun-study-uv-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.sun-study-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
  flex-shrink: 0;
  white-space: nowrap;
}

.sun-golden {
  background: rgba(245, 158, 11, 0.2);
  color: #f59e0b;
}

.sun-night {
  background: rgba(30, 58, 95, 0.3);
  color: #60a5fa;
}

.sun-live {
  background: rgba(239, 68, 68, 0.2);
  color: #ef4444;
  cursor: default;
  letter-spacing: 0.05em;
}

.sun-live-off {
  background: rgba(107, 114, 128, 0.15);
  color: var(--color-text-muted);
  cursor: pointer;
  letter-spacing: 0.05em;
  opacity: 0.6;
  &:hover { opacity: 1; }
}

/* Isochrone bar */
.isochrone-bar {
  position: absolute;
  bottom: 40px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1001;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 16px;
  background: var(--color-surface);
  border-radius: 24px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.18);
  white-space: nowrap;
}
:root.dark .isochrone-bar {
  background: rgba(30, 30, 30, 0.9);
  backdrop-filter: blur(8px);
}

.isochrone-bar-legend {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--color-text-muted);
}

.isochrone-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
  margin-left: 4px;
}

.isochrone-mode-btns {
  display: flex;
  gap: 2px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  overflow: hidden;
}

.isochrone-mode-btn {
  padding: 4px 8px;
  font-size: 14px;
  border: none;
  background: none;
  cursor: pointer;
  transition: background 0.15s;
  line-height: 1;
}
.isochrone-mode-btn:hover {
  background: var(--color-primary-100, #fef9c3);
}
:root.dark .isochrone-mode-btn:hover {
  background: var(--color-primary-900, #422006);
}
.isochrone-mode-btn.active {
  background: var(--color-secondary-50, #eff6ff);
}
:root.dark .isochrone-mode-btn.active {
  background: rgba(59, 130, 246, 0.2);
}

.isochrone-loading {
  font-size: 14px;
  animation: pulse 1s infinite;
}

@keyframes pulse {
  0% {
    transform: scale(0.8);
    opacity: 1;
  }
  100% {
    transform: scale(2.5);
    opacity: 0;
  }
}

/* Drone reachability bar (reuses isochrone-bar look) */
.dronereach-bar {
  position: absolute;
  bottom: 40px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1001;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  background: var(--color-surface);
  border-radius: 24px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.18);
  white-space: nowrap;
}
:root.dark .dronereach-bar {
  background: rgba(30, 30, 30, 0.9);
  backdrop-filter: blur(8px);
}
.dronereach-controls {
  display: flex;
  align-items: center;
  gap: 12px;
}
.dronereach-ctl {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: var(--color-text-muted);
}
.dronereach-ctl input[type="range"] {
  width: 64px;
  accent-color: #2563eb;
  cursor: pointer;
}
.dronereach-val {
  min-width: 30px;
  font-variant-numeric: tabular-nums;
  color: var(--color-text);
}
.dronereach-radius {
  display: flex;
  gap: 2px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  overflow: hidden;
}
.dronereach-radius .isochrone-mode-btn {
  font-size: 11px;
  padding: 4px 7px;
}
.dronereach-zonetoggle {
  font-size: 11px;
  padding: 4px 9px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
}
.dronereach-zoneinfo {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: var(--color-text);
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Urban analysis bar (reuses the measure/isochrone bar look) */
.urban-bar {
  position: absolute;
  bottom: 40px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1001;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 16px;
  background: var(--color-surface);
  border-radius: 24px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.18);
  white-space: nowrap;
}
:root.dark .urban-bar {
  background: rgba(30, 30, 30, 0.9);
  backdrop-filter: blur(8px);
}
.urban-typesel {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--color-text-muted);
}
.urban-typesel-label {
  font-size: 12px;
}
.urban-select {
  padding: 4px 8px;
  font-size: 13px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-surface);
  color: var(--color-text);
  cursor: pointer;
}
:root.dark .urban-select {
  background: rgba(30, 30, 30, 0.6);
}
.urban-upload-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 11px;
  font-size: 12.5px;
  font-weight: 600;
  border: 1px solid #7c3aed;
  border-radius: 8px;
  background: rgba(124, 58, 237, 0.06);
  color: #7c3aed;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s;
}
.urban-upload-btn:hover {
  background: rgba(124, 58, 237, 0.14);
}
:root.dark .urban-upload-btn {
  background: rgba(124, 58, 237, 0.16);
  color: #c4b5fd;
}
.urban-analyze-btn {
  padding: 5px 14px;
  font-size: 13px;
  font-weight: 600;
  border: none;
  border-radius: 8px;
  background: #7c3aed;
  color: #ffffff;
  cursor: pointer;
  transition: background 0.15s, opacity 0.15s;
}
.urban-analyze-btn:hover:not(:disabled) {
  background: #6d28d9;
}
.urban-analyze-btn:disabled {
  opacity: 0.45;
  cursor: default;
}

@media (max-width: 640px) {
  .measure-bar {
    left: 10px;
    right: 10px;
    transform: none;
    justify-content: center;
  }
  .sun-study-panel {
    left: 10px;
    right: 10px;
    width: auto;
    transform: none;
  }
  .isochrone-bar {
    left: 10px;
    right: 10px;
    transform: none;
    justify-content: center;
  }
  .dronereach-bar {
    left: 10px;
    right: 10px;
    transform: none;
    justify-content: center;
    flex-wrap: wrap;
    font-size: 11px;
  }
  .urban-bar {
    left: 10px;
    right: 10px;
    transform: none;
    justify-content: center;
    flex-wrap: wrap;
  }
}
</style>
