<template>
  <!-- Canvas 2D: VFX particle system -->
  <canvas ref="fxCanvas" class="layer" aria-hidden="true" />
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'

const fxCanvas = ref<HTMLCanvasElement | null>(null)
let animationId: number | null = null

// === Canvas 2D state ===
let ctx: CanvasRenderingContext2D | null = null
let embers: Ember[] = []
let ambientSparks: AmbientSpark[] = []
const dt = 1 / 60
let isDark = true

// =============================================
// CANVAS 2D TYPES
// =============================================

interface Debris {
  x: number; y: number
  vx: number; vy: number
  age: number; maxAge: number
  brightness: number
  size: number
  twinklePhase: number
  twinkleSpeed: number
}

interface Ember {
  x: number; y: number
  speed: number
  drift: number; driftPhase: number; driftSpeed: number
  age: number; maxLife: number
  brightness: number
  streakLength: number
  streakWidth: number
  debris: Debris[]
  debrisTimer: number
}

interface AmbientSpark {
  x: number; y: number
  speed: number
  brightness: number
  maxBright: number
  age: number; maxAge: number
  size: number
}

const EMBER_COUNT = 30
const AMBIENT_COUNT = 200

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
    debris: [],
    debrisTimer: 0.2 + Math.random() * 1.0,
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

function spawnDebris(ember: Ember, count: number) {
  const ex = ember.x + Math.sin(ember.driftPhase) * ember.drift
  const ey = ember.y
  for (let i = 0; i < count; i++) {
    const angle = Math.random() * Math.PI * 2
    const speed = 20 + Math.random() * 100
    ember.debris.push({
      x: ex,
      y: ey,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed,
      age: 0,
      maxAge: 0.2 + Math.random() * 0.8,
      brightness: 0.6 + Math.random() * 0.4,
      size: 0.5 + Math.random() * 2.0,
      twinklePhase: Math.random() * Math.PI * 2,
      twinkleSpeed: 10 + Math.random() * 25,
    })
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

function animate() {
  if (ctx && fxCanvas.value) {
    const dpr = window.devicePixelRatio || 1
    const w = fxCanvas.value.width / dpr
    const h = fxCanvas.value.height / dpr

    ctx.clearRect(0, 0, fxCanvas.value.width, fxCanvas.value.height)
    ctx.globalCompositeOperation = isDark ? 'lighter' : 'source-over'

    for (let i = embers.length - 1; i >= 0; i--) {
      const e = embers[i]
      e.age += dt
      e.y -= e.speed
      e.driftPhase += e.driftSpeed * dt
      const px = e.x + Math.sin(e.driftPhase) * e.drift
      const py = e.y

      const lifeRatio = e.age / e.maxLife
      let lifeFade = 1.0
      if (lifeRatio < 0.08) lifeFade = lifeRatio / 0.08
      else if (lifeRatio > 0.65) lifeFade = 1.0 - (lifeRatio - 0.65) / 0.35

      if (e.age > e.maxLife || py < -50) {
        if (e.age <= e.maxLife + dt * 2) spawnDebris(e, 5 + Math.floor(Math.random() * 8))
        if (e.debris.length === 0) {
          embers[i] = createEmber(w, h, true)
          continue
        }
        lifeFade = 0
      }

      const alpha = e.brightness * lifeFade


      // --- Draw debris ---
      for (let d = e.debris.length - 1; d >= 0; d--) {
        const db = e.debris[d]
        db.age += dt
        if (db.age > db.maxAge) { e.debris.splice(d, 1); continue }

        db.vy += 25 * dt
        db.vx *= 0.97; db.vy *= 0.97
        db.x += db.vx * dt; db.y += db.vy * dt

        const lt = db.age / db.maxAge
        const fadeOut = (1 - lt) * (1 - lt)

        db.twinklePhase += db.twinkleSpeed * dt
        const twinkle = 0.3 + 0.7 * Math.abs(Math.sin(db.twinklePhase))

        const da = db.brightness * fadeOut * twinkle
        const sz = db.size * (1 - lt * 0.3)

        ctx.beginPath()
        ctx.arc(db.x, db.y, sz, 0, Math.PI * 2)
        ctx.fillStyle = isDark
          ? `rgba(255, 255, 255, ${da})`
          : `rgba(255, 210, 0, ${da})`
        ctx.fill()

        // Motion trail
        const speed = Math.sqrt(db.vx * db.vx + db.vy * db.vy)
        if (speed > 5) {
          const trailLen = Math.min(speed * dt * 5, 12)
          const nx = db.vx / speed, ny = db.vy / speed
          ctx.beginPath()
          ctx.moveTo(db.x, db.y)
          ctx.lineTo(db.x - nx * trailLen, db.y - ny * trailLen)
          ctx.strokeStyle = isDark
            ? `rgba(255, 240, 200, ${da * 0.5})`
            : `rgba(255, 200, 0, ${da * 0.6})`
          ctx.lineWidth = sz * 0.7
          ctx.lineCap = 'round'
          ctx.stroke()
        }
      }

      // --- Vertical streak (replaces glow) ---
      if (alpha > 0.01) {
        const len = e.streakLength
        ctx.beginPath()
        ctx.moveTo(px, py)
        ctx.lineTo(px, py + len)
        ctx.strokeStyle = isDark
          ? `rgba(255, 255, 255, ${alpha})`
          : `rgba(255, 210, 0, ${alpha})`
        ctx.lineWidth = e.streakWidth
        ctx.lineCap = 'butt'
        ctx.stroke()
      }

    }

    // --- Ambient sparkles ---
    for (let i = ambientSparks.length - 1; i >= 0; i--) {
      const s = ambientSparks[i]
      s.age += dt; s.y -= s.speed
      if (s.age > s.maxAge || s.y < -10) {
        ambientSparks[i] = createAmbient(w, h, true)
        continue
      }
      const st = s.age / s.maxAge
      let fade = 1.0
      if (st < 0.12) fade = st / 0.12
      else if (st > 0.55) fade = 1.0 - (st - 0.55) / 0.45
      s.brightness = s.maxBright * fade
      ctx.beginPath()
      ctx.arc(s.x, s.y, s.size, 0, Math.PI * 2)
      ctx.fillStyle = isDark
        ? `rgba(255, 255, 255, ${s.brightness})`
        : `rgba(255, 210, 0, ${s.brightness})`
      ctx.fill()
    }

    ctx.globalCompositeOperation = 'source-over'
    ctx.globalAlpha = 1.0
  }

  animationId = requestAnimationFrame(animate)
}

let themeObserver: MutationObserver | null = null

onMounted(async () => {
  await nextTick()
  if (!fxCanvas.value) return

  isDark = document.documentElement.classList.contains('dark')
  themeObserver = new MutationObserver(() => {
    isDark = document.documentElement.classList.contains('dark')
  })
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })

  handleResize()

  const rect = fxCanvas.value.getBoundingClientRect()
  embers = Array.from({ length: EMBER_COUNT }, () => createEmber(rect.width, rect.height, false))
  ambientSparks = Array.from({ length: AMBIENT_COUNT }, () => createAmbient(rect.width, rect.height, false))

  animationId = requestAnimationFrame(animate)
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  if (animationId) cancelAnimationFrame(animationId)
  if (themeObserver) themeObserver.disconnect()
  window.removeEventListener('resize', handleResize)
})
</script>

<style scoped>
.layer {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  pointer-events: none;
}
</style>
