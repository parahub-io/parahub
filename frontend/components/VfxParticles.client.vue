<template>
  <!-- Canvas 2D: VFX particle system -->
  <canvas ref="fxCanvas" class="layer" aria-hidden="true" />
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'

// Rising embers, drawn to fill the nearest positioned ancestor. Meant for the
// landing's dark sections: the palette is fixed to light-on-dark and additive,
// because those sections stay dark in both themes. Put it inside a `relative
// overflow-hidden` block and keep the content above it (`relative z-10`).
const fxCanvas = ref<HTMLCanvasElement | null>(null)
let animationId: number | null = null
let lastFrameTime = 0
const FRAME_INTERVAL = 1000 / 30 // 30fps cap

const STREAK_COLOR = 'rgba(255, 255, 255,'
const SPARK_COLOR = 'rgba(255, 255, 255, 0.35)'

// === Canvas 2D state ===
let ctx: CanvasRenderingContext2D | null = null
let embers: Ember[] = []
let ambientSparks: AmbientSpark[] = []
const dt = 1 / 30 // match 30fps
let tabHidden = false
// The section is below the fold — don't paint until it is actually on screen
let offScreen = true

// =============================================
// CANVAS 2D TYPES
// =============================================

interface Ember {
  x: number; y: number
  speed: number
  drift: number; driftPhase: number; driftSpeed: number
  age: number; maxLife: number
  brightness: number
  streakLength: number
  streakWidth: number
}

interface AmbientSpark {
  x: number; y: number
  speed: number
  brightness: number
  maxBright: number
  age: number; maxAge: number
  size: number
}

const EMBER_COUNT = 18
const AMBIENT_COUNT = 80

function createEmber(w: number, h: number, fresh: boolean): Ember {
  const maxLife = 0.8 + Math.random() * 2.0
  return {
    x: Math.random() * w,
    y: fresh ? h + Math.random() * 40 : Math.random() * h,
    speed: 8 + Math.random() * 16,
    drift: 0.5 + Math.random() * 2.5,
    driftPhase: Math.random() * Math.PI * 2,
    driftSpeed: 0.6 + Math.random() * 2.5,
    age: fresh ? 0 : Math.random() * maxLife * 0.7,
    maxLife,
    brightness: 0.7 + Math.random() * 0.3,
    streakLength: 30 + Math.random() * 50,
    streakWidth: 0.5 + Math.random() * 1.0,
  }
}

function createAmbient(w: number, h: number, fresh: boolean): AmbientSpark {
  const maxAge = 1.5 + Math.random() * 3.5
  return {
    x: Math.random() * w,
    y: fresh ? h + Math.random() * 20 : Math.random() * h,
    speed: 1.5 + Math.random() * 4.0,
    brightness: 0,
    maxBright: 0.2 + Math.random() * 0.5,
    age: fresh ? 0 : Math.random() * maxAge,
    maxAge,
    size: 0.6 + Math.random() * 2.0,
  }
}

// =============================================
// Main loop
// =============================================

function handleResize() {
  if (fxCanvas.value) {
    const c = fxCanvas.value
    const rect = c.getBoundingClientRect()
    const dpr = window.devicePixelRatio || 1
    c.width = rect.width * dpr
    c.height = rect.height * dpr
    ctx = c.getContext('2d')
    if (ctx) ctx.scale(dpr, dpr)
  }
}

function animate(now: number) {
  animationId = requestAnimationFrame(animate)

  if (tabHidden || offScreen) return

  // Throttle to 30fps
  const elapsed = now - lastFrameTime
  if (elapsed < FRAME_INTERVAL) return
  lastFrameTime = now - (elapsed % FRAME_INTERVAL)

  if (!ctx || !fxCanvas.value) return

  const dpr = window.devicePixelRatio || 1
  const w = fxCanvas.value.width / dpr
  const h = fxCanvas.value.height / dpr

  ctx.clearRect(0, 0, fxCanvas.value.width, fxCanvas.value.height)
  ctx.globalCompositeOperation = 'lighter'

  // --- Embers ---
  for (let i = embers.length - 1; i >= 0; i--) {
    const e = embers[i]
    e.age += dt
    e.y -= e.speed * dt * 30 // compensate for dt change
    e.driftPhase += e.driftSpeed * dt
    const px = e.x + Math.sin(e.driftPhase) * e.drift
    const py = e.y

    const lifeRatio = e.age / e.maxLife
    let lifeFade = 1.0
    if (lifeRatio < 0.08) lifeFade = lifeRatio / 0.08
    else if (lifeRatio > 0.65) lifeFade = 1.0 - (lifeRatio - 0.65) / 0.35

    if (e.age > e.maxLife || py < -50) {
      embers[i] = createEmber(w, h, true)
      continue
    }

    const alpha = e.brightness * lifeFade

    // --- Vertical streak ---
    if (alpha > 0.01) {
      const len = e.streakLength
      ctx.beginPath()
      ctx.moveTo(px, py)
      ctx.lineTo(px, py + len)
      ctx.strokeStyle = `${STREAK_COLOR} ${alpha})`
      ctx.lineWidth = e.streakWidth
      ctx.lineCap = 'butt'
      ctx.stroke()
    }
  }

  // --- Ambient sparkles (single batched path) ---
  ctx.beginPath()
  let hasAmbient = false
  for (let i = ambientSparks.length - 1; i >= 0; i--) {
    const s = ambientSparks[i]
    s.age += dt; s.y -= s.speed * dt * 30
    if (s.age > s.maxAge || s.y < -10) {
      ambientSparks[i] = createAmbient(w, h, true)
      continue
    }
    const st = s.age / s.maxAge
    let fade = 1.0
    if (st < 0.12) fade = st / 0.12
    else if (st > 0.55) fade = 1.0 - (st - 0.55) / 0.45
    s.brightness = s.maxBright * fade

    if (s.brightness < 0.02) continue

    ctx.moveTo(s.x + s.size, s.y)
    ctx.arc(s.x, s.y, s.size, 0, Math.PI * 2)
    hasAmbient = true
  }
  if (hasAmbient) {
    ctx.fillStyle = SPARK_COLOR
    ctx.fill()
  }

  ctx.globalCompositeOperation = 'source-over'
  ctx.globalAlpha = 1.0
}

function handleVisibility() {
  tabHidden = document.hidden
}

let viewObserver: IntersectionObserver | null = null

onMounted(async () => {
  await nextTick()
  if (!fxCanvas.value) return

  viewObserver = new IntersectionObserver(
    ([entry]) => { offScreen = !entry.isIntersecting },
    { threshold: 0 },
  )
  viewObserver.observe(fxCanvas.value)

  handleResize()

  const rect = fxCanvas.value.getBoundingClientRect()
  embers = Array.from({ length: EMBER_COUNT }, () => createEmber(rect.width, rect.height, false))
  ambientSparks = Array.from({ length: AMBIENT_COUNT }, () => createAmbient(rect.width, rect.height, false))

  document.addEventListener('visibilitychange', handleVisibility)
  lastFrameTime = performance.now()
  animationId = requestAnimationFrame(animate)
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  if (animationId) cancelAnimationFrame(animationId)
  if (viewObserver) viewObserver.disconnect()
  document.removeEventListener('visibilitychange', handleVisibility)
  window.removeEventListener('resize', handleResize)
})
</script>

<style scoped>
.layer {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

@media (prefers-reduced-motion: reduce) {
  .layer {
    display: none;
  }
}
</style>
