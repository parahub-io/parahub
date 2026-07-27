<template>
  <div class="pdm-root" @click="$emit('map-click')">
    <!-- Abstract city: streets / avenues / river / parks -->
    <svg class="pdm-city" viewBox="0 0 1000 600" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      <path d="M -20 470 C 200 430, 320 520, 520 470 S 860 380, 1030 430 L 1030 630 L -20 630 Z" class="pdm-water" />
      <rect x="640" y="60" width="220" height="150" rx="24" class="pdm-park" />
      <rect x="90" y="300" width="150" height="110" rx="20" class="pdm-park" />
      <g class="pdm-street">
        <path v-for="y in [80, 160, 240, 320, 400]" :key="'h' + y" :d="`M 0 ${y} H 1000`" />
        <path v-for="x in [120, 240, 360, 480, 600, 720, 840, 960]" :key="'v' + x" :d="`M ${x} 0 V 600`" />
      </g>
      <g class="pdm-avenue">
        <path d="M 0 280 H 1000" />
        <path d="M 300 0 L 560 600" />
      </g>
    </svg>

    <!-- Satellite basemap tint -->
    <div v-if="layers.satellite" class="pdm-sat">
      <span class="pdm-sat-tag">DGT Ortos 2021</span>
    </div>

    <!-- Aerial (OpenSky) coverage footprint -->
    <div v-if="layers.aerial || layers.tiles3d" class="pdm-aerial">
      <span class="pdm-aerial-tag">{{ layers.tiles3d ? 'OpenSky 3D' : 'OpenSky' }}</span>
    </div>

    <!-- POI dots -->
    <template v-if="layers.poi">
      <span v-for="(p, i) in poiDots" :key="'poi' + i" class="pdm-poi" :style="pos(p)" />
    </template>

    <!-- Transit vehicles -->
    <template v-if="layers.transit">
      <div v-for="(v, i) in transitVehicles" :key="'tv' + i" class="pdm-vehicle" :style="{ ...pos(v), background: v.color }">
        <Bus :size="10" :stroke-width="2.6" />
      </div>
    </template>

    <!-- Static places (rounded square, marker grammar) -->
    <template v-for="m in placeMarkers" :key="m.layer">
      <div v-if="layers[m.layer]" class="pdm-mk" :style="pos(m)">
        <svg viewBox="0 0 100 100" class="pdm-mk-svg" style="width:20px;height:20px">
          <rect x="7.5" y="7.5" width="85" height="85" rx="15" :fill="m.color" stroke="#1f2937" stroke-width="1" vector-effect="non-scaling-stroke" />
        </svg>
        <component :is="m.glyph" class="pdm-mk-glyph" :size="11" :stroke-width="2.6" style="color:#fff" />
      </div>
    </template>

    <!-- Live devices: trackers, mesh routers, energy cells, env stations -->
    <template v-for="d in devices" :key="d.id">
      <button
        v-if="deviceVisible(d)"
        class="pdm-mk pdm-mk-btn"
        :style="{ ...pos(d), opacity: d.stale ? 0.45 : 1 }"
        :aria-label="d.name"
        @click.stop="$emit('pick', d.id)"
      >
        <svg viewBox="0 0 100 100" class="pdm-mk-svg" style="width:22px;height:22px">
          <polygon :points="HEX" :fill="deviceFill(d)" stroke="#1f2937" stroke-width="1" vector-effect="non-scaling-stroke" />
        </svg>
        <component :is="deviceGlyph(d)" v-if="deviceGlyph(d)" class="pdm-mk-glyph" :size="11" :stroke-width="2.6" :style="{ color: glyphColor(deviceFill(d)) }" />
      </button>
    </template>

    <!-- Hover preview hex (yellow) -->
    <div v-if="hoverPos" class="pdm-hoverhex" :style="pos(hoverPos)">
      <svg viewBox="0 0 100 100"><polygon :points="HEX" fill="rgba(255,193,7,0.12)" stroke="#FFC107" stroke-width="2" vector-effect="non-scaling-stroke" /></svg>
    </div>

    <!-- Lock-on (selection) -->
    <div v-if="lockPos" class="pdm-lockon" :style="pos(lockPos)">
      <div class="pdm-lockon-zoom">
        <div class="pdm-lockon-spin">
          <svg viewBox="0 0 100 100"><polygon :points="HEX" fill="none" stroke="currentColor" stroke-width="5" /></svg>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Bus, Building2, Cross, Landmark, Leaf, Package, Wifi, Wind, Zap } from 'lucide-vue-next'

export interface DemoDevice {
  id: string
  kind: 'home' | 'tracker' | 'router' | 'energy' | 'env'
  name: string
  status: 'online' | 'unknown' | 'offline'
  x: number
  y: number
  speed?: number
  ageMin?: number
  iotCount?: number
  ptype?: string
  /** Explicit hex fill (energy status / AQI colors); defaults to status color */
  fill?: string
  glyphKind?: 'wifi' | 'zap' | 'leaf' | 'wind'
  /** Stale readings render at 0.45 opacity (marker grammar) */
  stale?: boolean
}

const props = defineProps<{
  layers: Record<string, boolean>
  devices: DemoDevice[]
  trackersOn: boolean
  hoveredId: string | null
  lockedId: string | null
}>()

defineEmits<{
  (e: 'pick', id: string): void
  (e: 'map-click'): void
}>()

// Flat-top hexagon, same geometry as lock-on bracket (utils/lockOnMarker.ts)
const HEX = '27,9 73,9 97,50 73,91 27,91 3,50'

const placeMarkers = [
  { layer: 'government', color: '#d97706', glyph: Landmark, x: 63, y: 66 },
  { layer: 'churches', color: '#9f1239', glyph: Cross, x: 27, y: 20 },
  { layer: 'condos', color: '#7c3aed', glyph: Building2, x: 76, y: 24 },
  { layer: 'hubs', color: '#ea580c', glyph: Package, x: 68, y: 78 },
]

const poiDots = [
  { x: 22, y: 52 }, { x: 63, y: 38 }, { x: 52, y: 20 },
  { x: 80, y: 64 }, { x: 30, y: 30 }, { x: 72, y: 70 },
]

const transitVehicles = [
  { x: 25, y: 46.5, color: '#0033A0' },
  { x: 66, y: 46.5, color: '#00A550' },
]

function pos(p: { x: number; y: number }) {
  return { left: p.x + '%', top: p.y + '%' }
}

function statusColor(s: DemoDevice['status']): string {
  return s === 'online' ? '#4E4EC8' : s === 'offline' ? '#ef4444' : '#a3a3a3'
}

// Auto-contrast glyph (production glyphColorFor, luminance cut 0.55)
function glyphColor(hex: string): string {
  const h = hex.slice(1)
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255)
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.55 ? '#1f2937' : '#ffffff'
}

function deviceVisible(d: DemoDevice): boolean {
  if (d.kind === 'tracker') return props.trackersOn
  if (d.kind === 'router') return !!props.layers.mesh
  if (d.kind === 'energy') return !!props.layers.energy
  if (d.kind === 'env') return !!props.layers.environment
  return false // homes have no map marker, only fly-to preview
}

const GLYPHS = { wifi: Wifi, zap: Zap, leaf: Leaf, wind: Wind }

function deviceFill(d: DemoDevice): string {
  return d.fill ?? statusColor(d.status)
}

function deviceGlyph(d: DemoDevice) {
  if (d.glyphKind) return GLYPHS[d.glyphKind]
  return d.kind === 'router' ? Wifi : null
}

const hoverPos = computed(() => props.devices.find((d) => d.id === props.hoveredId) || null)
const lockPos = computed(() => props.devices.find((d) => d.id === props.lockedId) || null)
</script>

<style scoped>
.pdm-root {
  position: absolute;
  inset: 0;
  background: #f2efe9;
  overflow: hidden;
}
:root.dark .pdm-root { background: #101019; }

.pdm-city { position: absolute; inset: 0; width: 100%; height: 100%; }
.pdm-water { fill: #b3d2e6; }
:root.dark .pdm-water { fill: #1b2a3d; }
.pdm-park { fill: #cde4c2; }
:root.dark .pdm-park { fill: #1c2b21; }
.pdm-street path { stroke: #e2ddd2; stroke-width: 6; fill: none; }
:root.dark .pdm-street path { stroke: #212134; }
.pdm-avenue path { stroke: #d6cfc0; stroke-width: 14; fill: none; }
:root.dark .pdm-avenue path { stroke: #2b2b46; }

.pdm-sat {
  position: absolute;
  inset: 0;
  background: linear-gradient(160deg, rgba(110, 96, 60, 0.22), rgba(70, 82, 52, 0.3));
  pointer-events: none;
}
.pdm-sat-tag {
  position: absolute;
  left: 8px;
  bottom: 6px;
  font-size: 9px;
  letter-spacing: 0.04em;
  color: rgba(255, 255, 255, 0.85);
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);
}

.pdm-aerial {
  position: absolute;
  left: 8%;
  top: 10%;
  width: 34%;
  height: 42%;
  border: 1.5px dashed #eab308;
  border-radius: 6px;
  background: rgba(234, 179, 8, 0.08);
  pointer-events: none;
}
.pdm-aerial-tag {
  position: absolute;
  top: 4px;
  left: 6px;
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.05em;
  color: #a16207;
}
:root.dark .pdm-aerial-tag { color: #facc15; }

.pdm-poi {
  position: absolute;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #9ca3af;
  border: 1px solid #6b7280;
  transform: translate(-50%, -50%);
}

.pdm-vehicle {
  position: absolute;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 1px solid #1f2937;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  transform: translate(-50%, -50%);
}

.pdm-mk {
  position: absolute;
  transform: translate(-50%, -50%);
  display: flex;
  align-items: center;
  justify-content: center;
}
.pdm-mk-btn { background: none; border: none; padding: 0; cursor: pointer; }
.pdm-mk-svg { display: block; overflow: visible; }
.pdm-mk-glyph {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  pointer-events: none;
}

.pdm-hoverhex {
  position: absolute;
  width: 42px;
  height: 42px;
  transform: translate(-50%, -50%);
  pointer-events: none;
}
.pdm-hoverhex svg { width: 100%; height: 100%; overflow: visible; display: block; }

/* Lock-on replica of utils/lockOnMarker.ts: zoom and spin on separate nested
   elements — two animations on one element's transform suppress each other. */
.pdm-lockon {
  position: absolute;
  width: 0;
  height: 0;
  pointer-events: none;
}
.pdm-lockon-zoom {
  position: absolute;
  top: 0;
  left: 0;
  width: 36px;
  height: 36px;
  margin: -18px 0 0 -18px;
  animation: pdm-lock-in 0.5s cubic-bezier(0, 0.55, 0.45, 1) both;
}
.pdm-lockon-spin {
  width: 100%;
  height: 100%;
  color: #f4c110;
  animation: pdm-lock-spin 12s linear infinite;
}
.pdm-lockon-spin svg { width: 100%; height: 100%; overflow: visible; display: block; }
@keyframes pdm-lock-in {
  0% { transform: scale(6); opacity: 0.3; }
  60% { opacity: 1; }
  100% { transform: scale(1); opacity: 1; }
}
@keyframes pdm-lock-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
