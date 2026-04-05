<template>
  <div class="relative w-full overflow-hidden bg-neutral-100 dark:bg-neutral-800" :style="{ height: containerHeight + 'px' }">
    <!-- Uploaded / existing image -->
    <template v-if="imageUrl">
      <img
        :src="imageUrl"
        :alt="alt"
        class="w-full h-full object-cover"
        loading="lazy"
      />
      <!-- Upload overlay (own items only) -->
      <label
        v-if="canUpload"
        class="absolute inset-0 flex items-center justify-center bg-black/0 hover:bg-black/30 transition cursor-pointer group"
      >
        <input type="file" accept="image/jpeg,image/png,image/webp" class="hidden" @change="onFileSelected" />
        <Camera :size="24" class="text-white opacity-0 group-hover:opacity-100 transition drop-shadow-lg" />
      </label>
    </template>

    <!-- Building / geometric object: rotating 2D polygon with scanlines -->
    <template v-else-if="buildingGeometry">
      <canvas ref="canvasRef" class="w-full h-full" />
      <!-- Scanline overlay -->
      <div class="absolute inset-0 pointer-events-none scanline-overlay" />
    </template>

    <!-- POI icon blueprint (point features with class) -->
    <template v-else-if="poiClass">
      <canvas ref="poiCanvasRef" class="w-full h-full" />
      <div class="absolute inset-0 pointer-events-none scanline-overlay" />
    </template>

    <!-- Empty placeholder with upload -->
    <template v-else>
      <label
        v-if="canUpload"
        class="absolute inset-0 flex flex-col items-center justify-center cursor-pointer hover:bg-neutral-200 dark:hover:bg-neutral-700 transition gap-2"
      >
        <input type="file" accept="image/jpeg,image/png,image/webp" class="hidden" @change="onFileSelected" />
        <Camera :size="24" class="text-neutral-400" />
        <span class="text-xs text-neutral-400">{{ t('map.panel.add_photo') }}</span>
      </label>
      <div v-else class="absolute inset-0 flex items-center justify-center">
        <ImageOff :size="24" class="text-neutral-300 dark:text-neutral-600" />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { Camera, ImageOff } from 'lucide-vue-next'

const { t } = useI18n()

const props = defineProps<{
  containerWidth?: number
  imageUrl?: string | null
  alt?: string
  canUpload?: boolean
  buildingGeometry?: number[][][] | null
  buildingLevels?: number | null
  /** POI class from OpenMapTiles (hospital, shop, cafe...) for icon blueprint */
  poiClass?: string | null
}>()

const emit = defineEmits<{
  (e: 'upload', file: File): void
}>()

const canvasRef = ref<HTMLCanvasElement | null>(null)
const poiCanvasRef = ref<HTMLCanvasElement | null>(null)
let animationFrame: number | null = null
let angle = 0

const containerHeight = computed(() => {
  const w = props.containerWidth || 384
  return Math.round(w / 1.618)
})

function onFileSelected(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) emit('upload', file)
  input.value = ''
}

// ---- Geo math helpers ----

const DEG2RAD = Math.PI / 180
const EARTH_R = 6371000 // meters

/** Approximate distance in meters between two lng/lat points */
function haversineM(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const dLat = (lat2 - lat1) * DEG2RAD
  const dLon = (lon2 - lon1) * DEG2RAD
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * DEG2RAD) * Math.cos(lat2 * DEG2RAD) * Math.sin(dLon / 2) ** 2
  return EARTH_R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
}

/** Polygon area in m² using Shoelace on projected coords */
function polygonAreaM2(ring: number[][]): number {
  const centerLat = ring.reduce((s, c) => s + c[1], 0) / ring.length
  const cosLat = Math.cos(centerLat * DEG2RAD)
  // Project to meters (approximate)
  const mPerDegLat = 111320
  const mPerDegLng = 111320 * cosLat
  const projected = ring.map(c => [c[0] * mPerDegLng, c[1] * mPerDegLat])
  let area = 0
  for (let i = 0; i < projected.length; i++) {
    const j = (i + 1) % projected.length
    area += projected[i][0] * projected[j][1]
    area -= projected[j][0] * projected[i][1]
  }
  return Math.abs(area / 2)
}

/** Format meters nicely */
function fmtM(m: number): string {
  if (m < 1) return '< 1 m'
  if (m < 100) return `${m.toFixed(1)} m`
  return `${Math.round(m)} m`
}

function fmtArea(m2: number): string {
  if (m2 < 1) return '< 1 m²'
  if (m2 < 100) return `${m2.toFixed(1)} m²`
  return `${Math.round(m2)} m²`
}

// ---- Building polygon rotation + rulers ----

function drawBuildingFrame() {
  const canvas = canvasRef.value
  const geom = props.buildingGeometry
  if (!canvas || !geom || !geom[0]) return

  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const dpr = window.devicePixelRatio || 1
  const w = canvas.clientWidth
  const h = canvas.clientHeight
  canvas.width = w * dpr
  canvas.height = h * dpr
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

  const ring = geom[0]
  const lngs = ring.map(c => c[0])
  const lats = ring.map(c => c[1])
  const minLng = Math.min(...lngs)
  const maxLng = Math.max(...lngs)
  const minLat = Math.min(...lats)
  const maxLat = Math.max(...lats)

  // Real-world dimensions
  const widthM = haversineM(minLat, minLng, minLat, maxLng)
  const heightM = haversineM(minLat, minLng, maxLat, minLng)
  const areaM2 = polygonAreaM2(ring)

  // Aspect-correct projection
  const centerLat = (minLat + maxLat) / 2
  const cosLat = Math.cos(centerLat * DEG2RAD)
  const spanLng = (maxLng - minLng) * cosLat
  const spanLat = maxLat - minLat

  // Ruler margins: bottom 28px, left 28px
  const rulerB = 28
  const rulerL = 28
  const padT = 24
  const padR = 16
  const availW = w - rulerL - padR
  const availH = h - rulerB - padT
  const scale = Math.min(availW / (spanLng || 1e-6), availH / (spanLat || 1e-6))

  // Center of polygon in projected space
  const cx = ((minLng + maxLng) / 2 - minLng) * cosLat * scale
  const cy = ((maxLat + minLat) / 2 - minLat) * scale

  // Drawing area center
  const drawCenterX = rulerL + availW / 2
  const drawCenterY = padT + availH / 2

  // Convert to canvas coords (centered in drawing area)
  const points = ring.map(c => {
    const px = (c[0] - minLng) * cosLat * scale - cx
    const py = (maxLat - c[1]) * scale - cy
    return [px, py] as [number, number]
  })

  // Bounding box of the polygon in canvas-relative coords
  const polyW = spanLng * scale
  const polyH = spanLat * scale

  // ---- Background ----
  ctx.clearRect(0, 0, w, h)
  ctx.fillStyle = '#2A2A78' // secondary-800
  ctx.fillRect(0, 0, w, h)

  // ---- Grid ----
  const GRID_COLOR = 'rgba(255, 193, 7, 0.06)'
  const gridStep = 24 // px between lines
  ctx.strokeStyle = GRID_COLOR
  ctx.lineWidth = 0.5
  for (let gx = rulerL; gx < w; gx += gridStep) {
    ctx.beginPath()
    ctx.moveTo(gx, padT)
    ctx.lineTo(gx, h - rulerB)
    ctx.stroke()
  }
  for (let gy = padT; gy < h - rulerB; gy += gridStep) {
    ctx.beginPath()
    ctx.moveTo(rulerL, gy)
    ctx.lineTo(w, gy)
    ctx.stroke()
  }

  // ---- Rulers ----
  const RULER_COLOR = 'rgba(255, 193, 7, 0.35)'
  const RULER_TEXT = 'rgba(255, 193, 7, 0.6)'
  const TICK = 4

  ctx.strokeStyle = RULER_COLOR
  ctx.lineWidth = 1

  // Bottom ruler (width)
  const rulerY = h - rulerB + 10
  const rulerXStart = drawCenterX - polyW / 2
  const rulerXEnd = drawCenterX + polyW / 2
  // Line
  ctx.beginPath()
  ctx.moveTo(rulerXStart, rulerY)
  ctx.lineTo(rulerXEnd, rulerY)
  ctx.stroke()
  // End ticks
  ctx.beginPath()
  ctx.moveTo(rulerXStart, rulerY - TICK)
  ctx.lineTo(rulerXStart, rulerY + TICK)
  ctx.moveTo(rulerXEnd, rulerY - TICK)
  ctx.lineTo(rulerXEnd, rulerY + TICK)
  ctx.stroke()
  // Label
  ctx.fillStyle = RULER_TEXT
  ctx.font = '10px monospace'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'top'
  ctx.fillText(fmtM(widthM), (rulerXStart + rulerXEnd) / 2, rulerY + TICK + 1)

  // Left ruler (height)
  const rulerX = rulerL - 10
  const rulerYStart = drawCenterY - polyH / 2
  const rulerYEnd = drawCenterY + polyH / 2
  // Line
  ctx.beginPath()
  ctx.moveTo(rulerX, rulerYStart)
  ctx.lineTo(rulerX, rulerYEnd)
  ctx.stroke()
  // End ticks
  ctx.beginPath()
  ctx.moveTo(rulerX - TICK, rulerYStart)
  ctx.lineTo(rulerX + TICK, rulerYStart)
  ctx.moveTo(rulerX - TICK, rulerYEnd)
  ctx.lineTo(rulerX + TICK, rulerYEnd)
  ctx.stroke()
  // Label (rotated)
  ctx.save()
  ctx.translate(rulerX - TICK - 2, (rulerYStart + rulerYEnd) / 2)
  ctx.rotate(-Math.PI / 2)
  ctx.textAlign = 'center'
  ctx.textBaseline = 'bottom'
  ctx.fillStyle = RULER_TEXT
  ctx.fillText(fmtM(heightM), 0, 0)
  ctx.restore()

  // ---- Info text: area + levels (top-right corner) ----
  ctx.fillStyle = RULER_TEXT
  ctx.font = '10px monospace'
  ctx.textAlign = 'right'
  ctx.textBaseline = 'top'
  const infoLines: string[] = [fmtArea(areaM2)]
  if (props.buildingLevels && props.buildingLevels > 0) {
    infoLines.push(`${props.buildingLevels}F`)
  }
  const infoText = infoLines.join(' · ')
  ctx.fillText(infoText, w - 8, 8)

  // ---- Rotated polygon ----
  ctx.save()
  ctx.translate(drawCenterX, drawCenterY)
  ctx.rotate(angle)

  // Fill
  ctx.beginPath()
  points.forEach(([px, py], i) => {
    if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py)
  })
  ctx.closePath()
  ctx.fillStyle = 'rgba(255, 193, 7, 0.15)'
  ctx.fill()

  // Stroke
  ctx.strokeStyle = '#FFC107'
  ctx.lineWidth = 1.5
  ctx.stroke()

  // Vertices
  points.forEach(([px, py]) => {
    ctx.beginPath()
    ctx.arc(px, py, 2.5, 0, Math.PI * 2)
    ctx.fillStyle = '#FFC107'
    ctx.fill()
  })

  // North indicator — rotates with polygon, sits at top (north) edge
  ctx.font = 'bold 10px monospace'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'bottom'
  ctx.fillStyle = 'rgba(255, 193, 7, 0.7)'
  ctx.fillText('N', 0, -polyH / 2 - 6)

  ctx.restore()

  // Counter-clockwise
  angle -= 0.003

  animationFrame = requestAnimationFrame(drawBuildingFrame)
}

// ---- POI icon blueprint ----

// Lucide SVG paths for POI classes (24x24 viewBox)
const POI_ICON_PATHS: Record<string, string> = {
  // Healthcare
  hospital: 'M18 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2ZM9 12h6M12 9v6',
  pharmacy: 'M3 3h18v18H3zM9 12h6M12 9v6',
  doctors: 'M18 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2ZM9 12h6M12 9v6',
  dentist: 'M12 2a7 7 0 0 0-7 7c0 3 2 5 3 7l2 4h4l2-4c1-2 3-4 3-7a7 7 0 0 0-7-7Z',
  clinic: 'M18 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2ZM9 12h6M12 9v6',
  veterinary: 'M10 5.172C10 3.782 8.423 2.679 6.5 3c-2.823.47-4.113 6.006-4 7 .08.703 1.725 1.722 3.656 1 1.261-.472 1.96-1.45 2.344-2.5M14.267 5.172c0-1.39 1.577-2.493 3.5-2.172 2.823.47 4.113 6.006 4 7-.08.703-1.725 1.722-3.656 1-1.261-.472-1.855-1.45-2.239-2.5M8 14v.5M16 14v.5M11.25 16.25h1.5L12 17l-.75-.75Z',
  // Food & drink
  restaurant: 'M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2M7 2v20M21 15V2v0a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3Zm0 0v7',
  cafe: 'M17 8h1a4 4 0 1 1 0 8h-1M3 8h14v9a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4ZM6 2v4M10 2v4M14 2v4',
  bar: 'M8 22h8M12 11v11M20 2H4l8 9Z',
  pub: 'M8 22h8M12 11v11M20 2H4l8 9Z',
  fast_food: 'M17 8h1a4 4 0 1 1 0 8h-1M3 8h14v9a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4Z',
  ice_cream: 'M12 2a5 5 0 0 0-5 5c0 .47.04.93.13 1.37-1.79.46-3.13 2-3.13 3.63 0 2.21 2.69 4 6 4h4c3.31 0 6-1.79 6-4 0-1.63-1.34-3.17-3.13-3.63.09-.44.13-.9.13-1.37a5 5 0 0 0-5-5ZM10 16l2 6 2-6',
  bakery: 'M12 2a5 5 0 0 0-5 5c0 .47.04.93.13 1.37-1.79.46-3.13 2-3.13 3.63 0 2.21 2.69 4 6 4h4c3.31 0 6-1.79 6-4 0-1.63-1.34-3.17-3.13-3.63.09-.44.13-.9.13-1.37a5 5 0 0 0-5-5Z',
  // Shopping
  shop: 'M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4ZM3 6h18M16 10a4 4 0 0 1-8 0',
  supermarket: 'M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4ZM3 6h18M16 10a4 4 0 0 1-8 0',
  grocery: 'M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4ZM3 6h18M16 10a4 4 0 0 1-8 0',
  marketplace: 'M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4ZM3 6h18',
  // Education
  school: 'M22 10v6M2 10l10-5 10 5-10 5ZM6 12v5c3 3 9 3 12 0v-5',
  university: 'M22 10v6M2 10l10-5 10 5-10 5ZM6 12v5c3 3 9 3 12 0v-5',
  college: 'M22 10v6M2 10l10-5 10 5-10 5ZM6 12v5c3 3 9 3 12 0v-5',
  kindergarten: 'M22 10v6M2 10l10-5 10 5-10 5ZM6 12v5c3 3 9 3 12 0v-5',
  library: 'M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20',
  // Accommodation
  hotel: 'M18 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2ZM12 10a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM8 14h8',
  hostel: 'M18 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2ZM12 10a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM8 14h8',
  // Finance
  bank: 'M3 22h18M6 18V9M10 18V9M14 18V9M18 18V9M2 6l10-4 10 4Z',
  atm: 'M3 5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2ZM12 9v4M8 15h8',
  // Services
  post_office: 'M22 7 12 13 2 7M2 7l10 6 10-6V17a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2Z',
  police: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z',
  fire_station: 'M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5Z',
  fuel: 'M3 22V5a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v17M13 10h1a2 2 0 0 1 2 2v2a2 2 0 0 0 2 2 2 2 0 0 0 2-2V9.83a2 2 0 0 0-.59-1.42L18 7M3 22h10',
  parking: 'M9 17V7h4a3 3 0 0 1 0 6H9',
  car_repair: 'M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76Z',
  car_wash: 'M3 22V5a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v17M17 5s2 1 2 3-2 3-2 3 2 1 2 3M21 5s2 1 2 3-2 3-2 3 2 1 2 3',
  hairdresser: 'M6 3v18M18 3v18M6 12h12',
  laundry: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20ZM12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z',
  // Culture
  museum: 'M3 22h18M6 18V11M10 18V11M14 18V11M18 18V11M2 8l10-5 10 5Z',
  cinema: 'M7 2h10M5 6h14M4 10h16v10a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2Z',
  theatre: 'M2 10s3-3 5-3 5 3 8 3 4 0 7-3M22 10s-3-3-5-3-5 3-8 3c-2 0-4.5-1.5-7-3M2 2s3 3 5 3 5-3 8-3c2 0 4.5 1.5 7 3',
  // Recreation
  park: 'M12 13V4a1 1 0 0 0-1.6-.8L6 6.7 1.6 3.2A1 1 0 0 0 0 4v9M5 22v-5M12 22v-9M12 13l6.4-3.3A1 1 0 0 1 20 10.5V22M0 22h24',
  garden: 'M7 20h10M10 20c5.5-2.5.8-6.4 3-10M9.5 9.4c1.1.8 1.8 2.2 2.3 3.7-2 .4-3.5.4-4.8-.3-1.2-.6-2.3-1.9-3-4.2 2.8-.5 4.4 0 5.5.8ZM14.1 6a7 7 0 0 0-1.1 4c1.9-.1 3.3-.6 4.3-1.4 1-1 1.6-2.3 1.7-4.6-2.7.1-4 1-4.9 2Z',
  playground: 'M12 12m-2 0a2 2 0 1 0 4 0 2 2 0 1 0-4 0M2 22l4-10M22 22l-4-10M6 12l6-7 6 7',
  sports_centre: 'M6 9a6 6 0 0 0 12 0A6 6 0 0 0 6 9ZM12 3v6M6 9h12',
  swimming_pool: 'M2 6c.6.5 1.2 1 2.5 1C7 7 7 5 9.5 5c2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1M2 12c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1M2 18c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1',
  stadium: 'M2 6c0-1.1.9-2 2-2h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2ZM2 12h20',
  // Transport
  bus: 'M8 6v6M15 6v6M2 12h19.6M18 18h3s.5-1.7.8-2.8c.1-.4.2-.8.2-1.2 0-.4-.1-.8-.2-1.2l-1.4-5C20.1 6.8 19.1 6 18 6H4a2 2 0 0 0-2 2v10h3M7 18h8M6 18m-2 0a2 2 0 1 0 4 0 2 2 0 1 0-4 0ZM15 18m-2 0a2 2 0 1 0 4 0 2 2 0 1 0-4 0Z',
  rail: 'M4 11V4a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v7M9 18l-6 4M15 18l6 4M4 11h16v5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2ZM8 15h0M16 15h0',
  airport: 'M17.8 19.2 16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2c-.5-.1-.9.1-1.1.5l-.3.5c-.2.5-.1 1 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 3.5 5.3c.3.4.8.5 1.3.3l.5-.2c.4-.3.6-.7.5-1.2Z',
  // Religion
  place_of_worship: 'M18 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2ZM9 12h6M12 9v6',
  // Other
  cemetery: 'M9 2v4M15 2v4M12 10v12M7 10h10M5 22h14',
  townhall: 'M3 22h18M6 18V11M10 18V11M14 18V11M18 18V11M2 8l10-5 10 5Z',
  courthouse: 'M3 22h18M6 18V11M10 18V11M14 18V11M18 18V11M2 8l10-5 10 5Z',
  bicycle: 'M5 18m-3 0a3 3 0 1 0 6 0 3 3 0 1 0-6 0ZM16 18m-3 0a3 3 0 1 0 6 0 3 3 0 1 0-6 0ZM12 18V9l-3 3.5M16 7l-1.5 4.5L8 18',
}

// Fallback: generic map-pin
const FALLBACK_ICON = 'M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0ZM12 10m-3 0a3 3 0 1 0 6 0 3 3 0 1 0-6 0Z'

function drawPoiIcon() {
  const canvas = poiCanvasRef.value
  if (!canvas || !props.poiClass) return

  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const dpr = window.devicePixelRatio || 1
  const w = canvas.clientWidth
  const h = canvas.clientHeight
  canvas.width = w * dpr
  canvas.height = h * dpr
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

  // Background
  ctx.fillStyle = '#2A2A78'
  ctx.fillRect(0, 0, w, h)

  // Grid
  const gridStep = 24
  ctx.strokeStyle = 'rgba(255, 193, 7, 0.06)'
  ctx.lineWidth = 0.5
  for (let gx = 0; gx < w; gx += gridStep) {
    ctx.beginPath(); ctx.moveTo(gx, 0); ctx.lineTo(gx, h); ctx.stroke()
  }
  for (let gy = 0; gy < h; gy += gridStep) {
    ctx.beginPath(); ctx.moveTo(0, gy); ctx.lineTo(w, gy); ctx.stroke()
  }

  // Draw icon centered, large
  const pathStr = POI_ICON_PATHS[props.poiClass] || FALLBACK_ICON
  const iconScale = Math.min(w, h) * 0.3 / 24  // 30% of smallest dimension, paths are 24x24
  ctx.save()
  ctx.translate(w / 2 - 12 * iconScale, h / 2 - 12 * iconScale)
  ctx.scale(iconScale, iconScale)

  ctx.strokeStyle = '#FFC107'
  ctx.lineWidth = 2 / iconScale * 1.5
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'
  ctx.fillStyle = 'rgba(255, 193, 7, 0.08)'

  // Parse and draw SVG path segments
  const paths = pathStr.split(/(?=[Mm])/).filter(Boolean)
  for (const segment of paths) {
    const p = new Path2D(segment)
    ctx.stroke(p)
  }
  // Light fill on the full combined path
  const fullPath = new Path2D(pathStr)
  ctx.fill(fullPath)

  ctx.restore()

  // Class label bottom-right
  ctx.fillStyle = 'rgba(255, 193, 7, 0.5)'
  ctx.font = '10px monospace'
  ctx.textAlign = 'right'
  ctx.textBaseline = 'bottom'
  ctx.fillText(props.poiClass.replace(/_/g, ' '), w - 8, h - 6)
}

watch(() => props.buildingGeometry, (geom) => {
  if (geom) {
    angle = 0
    nextTick(() => {
      if (canvasRef.value && !animationFrame) drawBuildingFrame()
    })
  } else {
    if (animationFrame) {
      cancelAnimationFrame(animationFrame)
      animationFrame = null
    }
  }
}, { immediate: false })

watch(() => props.poiClass, (cls) => {
  if (cls) {
    nextTick(() => {
      if (poiCanvasRef.value) drawPoiIcon()
    })
  }
}, { immediate: false })

onMounted(() => {
  if (props.buildingGeometry && canvasRef.value) {
    drawBuildingFrame()
  }
  if (props.poiClass && poiCanvasRef.value) {
    drawPoiIcon()
  }
})

onUnmounted(() => {
  if (animationFrame) {
    cancelAnimationFrame(animationFrame)
    animationFrame = null
  }
})
</script>

<style scoped>
.scanline-overlay {
  background: repeating-linear-gradient(
    0deg,
    transparent,
    transparent 3px,
    rgba(255, 255, 255, 0.02) 3px,
    rgba(255, 255, 255, 0.02) 4px
  );
  mix-blend-mode: overlay;
}

/* Slow vertical sweep — subtle CRT effect */
.scanline-overlay::after {
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
  animation: scanline-sweep 6s linear infinite;
}

@keyframes scanline-sweep {
  0% { transform: translateY(-100%); }
  100% { transform: translateY(100%); }
}
</style>
