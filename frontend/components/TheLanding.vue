<template>
  <div ref="pageRef" class="bg-neutral-900" style="margin-bottom: calc(-0.5rem - var(--safe-area-inset-bottom, env(safe-area-inset-bottom, 0px)))">
    <!-- ═══════════════ HERO (V1 centered) ═══════════════ -->
    <div ref="heroRef" class="relative py-24 overflow-hidden bg-primary">
      <!-- Background pattern: WebGPU spiral or static SVG tiling -->
      <div class="absolute inset-0 overflow-hidden pointer-events-none" style="opacity: 0.05">
        <canvas v-if="useWebGPU" ref="canvasRef" class="absolute inset-0 w-full h-full" aria-hidden="true" />
        <svg v-else class="absolute inset-0 w-full h-full">
          <defs>
            <pattern id="hero-tile" :width="60" :height="60" patternUnits="userSpaceOnUse">
              <g :transform="`translate(30,30) scale(0.22)`">
                <path :d="LOGO_PATH" fill="currentColor" :transform="`translate(-91,-140)`" />
              </g>
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#hero-tile)" />
        </svg>
      </div>

      <div class="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        <div class="text-center">
          <!-- Logo -->
          <div class="flex justify-center mb-8">
            <img src="/logo.svg" alt="Parahub" class="h-28 w-28 hero-logo" />
          </div>

          <h1 class="hero-stagger text-5xl sm:text-6xl lg:text-7xl font-bold mb-6 leading-tight text-neutral-900"
              style="--stagger: 1">
            Parahub
          </h1>
          <p class="hero-stagger text-xl sm:text-2xl max-w-3xl mx-auto mb-4 leading-relaxed text-neutral-800"
             style="--stagger: 2">
            {{ $t('landing.hero.subtitle') }}
          </p>
          <p class="hero-stagger text-base max-w-2xl mx-auto mb-10 text-neutral-700"
             style="--stagger: 3">
            {{ $t('landing.hero.tagline') }}
          </p>

          <!-- CTA Buttons -->
          <div class="hero-stagger flex flex-col sm:flex-row gap-4 justify-center" style="--stagger: 4">
            <NuxtLink
              :to="localePath('/register')"
              class="inline-flex items-center justify-center gap-2 px-8 py-4 bg-neutral-900 text-white rounded-xl hover:bg-neutral-800 transition-colors text-lg font-semibold"
            >
              <Rocket class="w-5 h-5" />
              {{ $t('landing.hero.cta_start') }}
            </NuxtLink>
            <NuxtLink
              :to="localePath('/docs/getting-started')"
              class="inline-flex items-center justify-center gap-2 px-8 py-4 bg-black/30 text-neutral-900 border-2 border-neutral-900/30 rounded-xl hover:bg-black/35 transition-colors text-lg font-semibold"
            >
              <BookOpen class="w-5 h-5" />
              {{ $t('landing.hero.cta_docs') }}
            </NuxtLink>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══════════════ MANIFESTO ═══════════════ -->
    <section class="relative bg-neutral-900 text-white py-20 sm:py-28 overflow-hidden">
      <!-- Grid texture -->
      <div class="absolute inset-0 opacity-[0.03]"
        style="background-image: linear-gradient(rgba(255,255,255,.1) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.1) 1px, transparent 1px); background-size: 48px 48px;"></div>

      <div class="max-w-5xl mx-auto px-6 sm:px-8 relative z-10">
        <h2 class="landing-reveal text-3xl sm:text-5xl lg:text-[3.5rem] font-extrabold leading-[1.1] mb-10 max-w-4xl">
          {{ $t('landing.problem.title') }}
        </h2>

        <ul class="space-y-4 mb-14 max-w-3xl">
          <li v-for="i in 3" :key="i" class="landing-reveal flex items-start gap-3 text-lg text-neutral-300 leading-relaxed">
            <span class="mt-1.5 block w-2 h-2 rounded-full bg-primary shrink-0" />
            {{ $t(`landing.problem.point${i}`) }}
          </li>
        </ul>

        <!-- Manifesto stats -->
        <div class="grid grid-cols-3 gap-3 sm:gap-5">
          <div v-for="stat in manifestoStats" :key="stat.label" class="landing-reveal border border-neutral-700 rounded-xl p-4 sm:p-6 text-center">
            <div class="text-2xl sm:text-4xl font-extrabold text-primary mb-1">{{ stat.value }}</div>
            <div class="text-xs text-neutral-400 uppercase tracking-[0.12em]">{{ stat.label }}</div>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══════════════ FEATURES ═══════════════ -->
    <section class="bg-white dark:bg-neutral-900 py-24 sm:py-32">
      <div class="max-w-6xl mx-auto px-6 sm:px-8">
        <h2 class="landing-reveal text-3xl sm:text-5xl font-extrabold text-neutral-900 dark:text-white mb-16 sm:mb-20 text-center">
          {{ $t('landing.features.title') }}
        </h2>

        <div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          <div
            v-for="(feat, idx) in features"
            :key="feat.key"
            class="landing-reveal group flex flex-col card rounded-2xl p-6 hover:border-primary transition-colors duration-200"
            :style="{ transitionDelay: `${(idx % 3) * 60}ms` }"
          >
            <div class="w-12 h-12 bg-primary/10 dark:bg-primary/5 rounded-xl flex items-center justify-center mb-5">
              <component :is="feat.icon" class="w-6 h-6 text-neutral-800 dark:text-neutral-200" />
            </div>
            <h3 class="text-lg font-bold text-neutral-900 dark:text-white mb-2">
              {{ $t(`landing.features.${feat.key}.title`) }}
            </h3>
            <p class="text-sm text-neutral-600 dark:text-neutral-400 leading-relaxed flex-1">
              {{ $t(`landing.features.${feat.key}.desc`) }}
            </p>
            <NuxtLink v-if="feat.doc" :to="localePath(feat.doc)" class="mt-4 text-sm text-secondary hover:underline font-medium self-start">{{ $t('landing.features.learn_more') }} →</NuxtLink>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══════════════ MISSION + TECH ═══════════════ -->
    <section class="bg-neutral-50 dark:bg-neutral-800/50 py-20 sm:py-28">
      <div class="max-w-5xl mx-auto px-6 sm:px-8">
        <div class="landing-reveal border-l-4 border-primary pl-8 sm:pl-12 mb-14">
          <h2 class="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-neutral-900 dark:text-white mb-4 leading-[1.1]">
            {{ $t('landing.mission.title') }}
          </h2>
          <p class="text-lg text-neutral-600 dark:text-neutral-300 leading-relaxed">
            {{ $t('landing.mission.text') }}
          </p>
        </div>

        <div class="grid md:grid-cols-3 gap-5">
          <div
            v-for="tech in techPillars"
            :key="tech.key"
            class="landing-reveal card rounded-2xl p-6 sm:p-8 text-center hover:border-primary transition-colors duration-200"
          >
            <div class="w-14 h-14 bg-neutral-200 dark:bg-neutral-700 rounded-full flex items-center justify-center mx-auto mb-5">
              <component :is="tech.icon" class="w-6 h-6 text-neutral-700 dark:text-neutral-300" />
            </div>
            <h3 class="font-bold text-lg mb-2 text-neutral-900 dark:text-white">
              {{ $t(`landing.tech.${tech.key}.title`) }}
            </h3>
            <p class="text-sm text-neutral-600 dark:text-neutral-400 leading-relaxed">
              {{ $t(`landing.tech.${tech.key}.desc`) }}
            </p>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══════════════ CTA ═══════════════ -->
    <section class="relative bg-neutral-900 py-20 sm:py-28 overflow-hidden">
      <!-- Radial glow -->
      <div class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] rounded-full opacity-[0.05]"
        style="background: radial-gradient(circle, var(--color-primary), transparent 70%);"></div>

      <div class="max-w-4xl mx-auto px-6 sm:px-8 text-center relative z-10">
        <span class="landing-reveal inline-block px-3 py-1 mb-6 text-xs font-semibold uppercase tracking-widest text-primary border border-primary/30 rounded-full">Beta</span>
        <h2 class="landing-reveal text-3xl sm:text-5xl font-extrabold text-white mb-4 leading-tight">
          {{ $t('landing.cta.title') }}
        </h2>
        <p class="landing-reveal text-lg text-neutral-300 mb-10">
          {{ $t('landing.cta.text') }}
        </p>

        <div class="landing-reveal flex flex-col sm:flex-row gap-4 justify-center">
          <NuxtLink
            :to="localePath('/register')"
            class="cta-pulse group inline-flex items-center justify-center gap-2.5 px-10 py-4 bg-primary text-neutral-900 rounded-xl hover:bg-primary-600 transition-all duration-200 text-lg font-bold"
          >
            <Rocket class="w-5 h-5 transition-transform duration-300 group-hover:-rotate-12" />
            {{ $t('landing.cta.start') }}
          </NuxtLink>
          <a
            href="https://github.com/parahub-io"
            target="_blank"
            rel="noopener noreferrer"
            class="inline-flex items-center justify-center gap-2.5 px-10 py-4 border border-neutral-600 text-neutral-300 rounded-xl hover:border-neutral-400 hover:text-white transition-all duration-200 text-lg font-semibold"
          >
            <Github class="w-5 h-5" />
            GitHub
          </a>
        </div>
      </div>
    </section>

    <!-- ═══════════════ FOOTER ═══════════════ -->
    <footer class="bg-neutral-950 py-8 border-t border-neutral-800">
      <div class="max-w-5xl mx-auto px-6 sm:px-8">
        <div class="flex flex-col sm:flex-row items-center justify-between gap-4">
          <div class="flex items-center gap-2 text-neutral-500 text-sm">
            <img src="/logo.svg" alt="Parahub" class="h-5 w-5 opacity-40" />
            <span>&copy; {{ new Date().getFullYear() }} Parahub</span>
          </div>
          <nav class="flex items-center gap-6 text-sm" aria-label="Footer navigation">
            <NuxtLink :to="localePath('/about')" class="text-neutral-300 hover:text-white transition-colors">{{ $t('footer.about') }}</NuxtLink>
            <NuxtLink :to="localePath('/about/terms')" class="text-neutral-300 hover:text-white transition-colors">{{ $t('footer.terms') }}</NuxtLink>
            <NuxtLink :to="localePath('/about/privacy')" class="text-neutral-300 hover:text-white transition-colors">{{ $t('footer.privacy') }}</NuxtLink>
            <a href="https://github.com/parahub-io" target="_blank" rel="noopener noreferrer" class="text-neutral-300 hover:text-white transition-colors">GitHub</a>
          </nav>
          <LanguageSwitcher variant="dark" class="mt-3 sm:mt-0" />
        </div>
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
const localePath = useLocalePath()
const { t } = useI18n()
import { ref, computed, nextTick, onMounted, onBeforeUnmount } from 'vue'
import {
  Rocket, BookOpen, Github,
  Fingerprint, Store, Wallet, Bus,
  ShieldCheck, Vote, Network, WifiOff,
} from 'lucide-vue-next'

// ── Logo SVG path ──
const LOGO_PATH = 'm 91.961093,113.16417 c -5.172666,5.17267 -5.172666,13.65582 0,18.8285 l 2.275966,2.27596 6.621011,-4.13808 -3.517415,-3.51748 c -2.275965,-2.27595 -2.275965,-6.00027 0,-8.06931 2.275973,-2.27595 6.000285,-2.27595 8.069355,0 2.27597,2.27596 2.27597,6.00028 0,8.06931 l -23.587337,23.79426 -4.138123,-4.13808 c -5.172666,-5.17267 -13.655824,-5.17267 -18.82849,0 -5.172658,5.1726 -5.172658,13.65582 0,18.82842 5.172666,5.17267 13.655824,5.17267 18.82849,0 l 3.517404,-3.31048 -6.414097,-4.34499 -2.482877,2.48287 c -2.275973,2.27596 -6.000289,2.27596 -8.06935,0 -2.069062,-2.27603 -2.275974,-6.00035 -0.20692,-8.2763 2.275966,-2.27596 6.000281,-2.27596 8.069351,0 l 22.759701,22.75973 3.724316,-1.65528 -6.621,6.62103 c -5.172666,5.17268 -5.172666,13.65583 0,18.8285 5.172658,5.17267 13.655822,5.17267 18.828482,0 5.17266,-5.17267 5.17266,-13.65582 0,-18.8285 l -2.27597,-2.27595 -6.621,4.13807 3.5174,3.51748 c 2.27597,2.27595 2.27597,6.00027 0,8.06931 -2.27597,2.27596 -6.000281,2.27596 -8.06935,0 -2.275966,-2.27596 -2.275966,-6.00028 0,-8.06931 l 23.79424,-23.79426 4.13813,4.13808 c 5.17266,5.17267 13.65582,5.17267 18.82849,0 5.17265,-5.1726 5.17265,-13.65582 0,-18.82842 -5.17267,-5.17267 -13.65583,-5.17267 -18.82849,0 l -3.51741,3.5174 6.4141,4.13807 2.27597,-2.27595 c 2.27597,-2.27596 6.00028,-2.27596 8.06935,0 2.27597,2.27595 2.27597,6.00027 0,8.06939 -2.27597,2.27595 -6.00029,2.27595 -8.06935,0 l -22.5528,-22.55282 -3.93122,1.65528 6.82791,-6.82795 c 5.17266,-5.17268 5.17266,-13.65583 0,-18.8285 -5.17266,-5.17267 -13.655824,-5.17267 -18.828482,0 z m 26.897837,45.72631 -4.34504,-1.86212 -13.0351,13.03506 -17.17324,-17.38014 4.138131,1.8622 13.242009,-13.24198 z'

// ── Phyllotaxis spiral ──
const GPU_COUNT = 2000

// ── Feature definitions ──
const features = [
  { key: 'id', icon: Fingerprint, doc: '/docs/wot' },
  { key: 'market', icon: Store, doc: '/docs/barter' },
  { key: 'finance', icon: Wallet },
  { key: 'governance', icon: Vote, doc: '/docs/governance' },
  { key: 'communication', icon: ShieldCheck },
  { key: 'mobility', icon: Bus },
]

// ── Manifesto stats ──
const manifestoStats = computed(() => [
  { value: '0%', label: t('landing.stats.commission') },
  { value: '100%', label: t('landing.stats.opensource') },
  { value: '0', label: t('landing.stats.middlemen') },
])

const techPillars = [
  { key: 'decentralization', icon: Network },
  { key: 'opensource', icon: Github },
  { key: 'offline', icon: WifiOff },
]

// ── Scroll reveal (below-fold sections) ──
const pageRef = ref<HTMLElement>()
const canvasRef = ref<HTMLCanvasElement>()
const heroRef = ref<HTMLElement>()
const useWebGPU = ref(!!(globalThis.navigator as any)?.gpu)
let observer: IntersectionObserver | null = null
let heroObserver: IntersectionObserver | null = null
let rafId: number | null = null
let heroVisible = true


// ── WGSL shader — Vogel phyllotaxis (sunflower) ──
const WGSL = /* wgsl */`
struct P { time: f32, count: f32, aspect: f32, cy: f32, maxR: f32, _p1: f32, _p2: f32, _p3: f32 };
@group(0) @binding(0) var<uniform> p: P;
@group(0) @binding(1) var tex: texture_2d<f32>;
@group(0) @binding(2) var smp: sampler;
struct V { @builtin(position) pos: vec4f, @location(0) uv: vec2f, @location(1) alpha: f32 };
const GA: f32 = 2.39996323;
@vertex fn vs(@builtin(vertex_index) v: u32, @builtin(instance_index) ii: u32) -> V {
  var qx = array<f32,6>(-0.5, 0.5, 0.5, -0.5, 0.5, -0.5);
  var qy = array<f32,6>(-0.5,-0.5, 0.5, -0.5, 0.5,  0.5);
  var ux = array<f32,6>( 0.0, 1.0, 1.0,  0.0, 1.0,  0.0);
  var uy = array<f32,6>( 1.0, 1.0, 0.0,  1.0, 0.0,  0.0);
  let i = f32(ii) + 1.0;
  let sqrtN = sqrt(p.count);
  let nr = sqrt(i) / sqrtN;
  let r = nr * p.maxR;
  let a = i * GA + p.time * 0.02;
  let px = r * cos(a) * p.aspect;
  let py = r * sin(a);
  let breathe = 1.0 + 0.1 * sin(nr * 6.28 - p.time * 0.2);
  let sz = (0.04 + 0.08 * nr) * breathe;
  let vx = qx[v]; let vy = qy[v];
  var al = 1.0;
  if (nr < 0.02) { al = nr / 0.02; }
  if (nr > 0.85) { al = (1.0 - nr) / 0.15; }
  var o: V;
  o.pos = vec4f((px + vx*sz) / p.aspect, py + vy*sz + p.cy, 0.0, 1.0);
  o.uv = vec2f(ux[v], uy[v]);
  o.alpha = al;
  return o;
}
@fragment fn fs(i: V) -> @location(0) vec4f {
  let a = textureSample(tex, smp, i.uv).a * i.alpha;
  return vec4f(0.0, 0.0, 0.0, a);
}`

function createLogoTex(): HTMLCanvasElement {
  const c = document.createElement('canvas')
  c.width = 128; c.height = 128
  const x = c.getContext('2d')!
  x.scale(128 / 93, 128 / 93)
  x.translate(-54.976568, -109.28466)
  x.fill(new Path2D(LOGO_PATH))
  return c
}

async function startWebGPU(canvas: HTMLCanvasElement) {
  const gpu = (navigator as any).gpu
  const adapter = await gpu.requestAdapter()
  if (!adapter) throw 'no adapter'
  const device = await adapter.requestDevice()
  const fmt = gpu.getPreferredCanvasFormat()
  const gctx = canvas.getContext('webgpu') as any
  if (!gctx) throw 'no webgpu ctx'
  gctx.configure({ device, format: fmt, alphaMode: 'premultiplied' })

  const logo = createLogoTex()
  const tex = device.createTexture({
    size: [128, 128], format: 'rgba8unorm',
    usage: 4 | 2 | 16, // TEXTURE_BINDING | COPY_DST | RENDER_ATTACHMENT
  })
  device.queue.copyExternalImageToTexture({ source: logo }, { texture: tex }, [128, 128])
  const smp = device.createSampler({ magFilter: 'linear', minFilter: 'linear' })
  const ubuf = device.createBuffer({ size: 32, usage: 64 | 8 }) // UNIFORM | COPY_DST
  const mod = device.createShaderModule({ code: WGSL })
  const pipe = device.createRenderPipeline({
    layout: 'auto',
    vertex: { module: mod, entryPoint: 'vs' },
    fragment: {
      module: mod, entryPoint: 'fs',
      targets: [{
        format: fmt,
        blend: {
          color: { srcFactor: 'one', dstFactor: 'one-minus-src-alpha' },
          alpha: { srcFactor: 'one', dstFactor: 'one-minus-src-alpha' },
        },
      }],
    },
    primitive: { topology: 'triangle-list' },
  })
  const bg = device.createBindGroup({
    layout: pipe.getBindGroupLayout(0),
    entries: [
      { binding: 0, resource: { buffer: ubuf } },
      { binding: 1, resource: tex.createView() },
      { binding: 2, resource: smp },
    ],
  })

  const t0 = performance.now()
  const ud = new Float32Array(8)
  let cachedCY = 0
  let lastCh = 0

  const tick = (now: number) => {
    rafId = requestAnimationFrame(tick)
    if (!heroVisible) return
    const par = canvas.parentElement!
    const rect = par.getBoundingClientRect()
    const dpr = window.devicePixelRatio || 1
    const cw = Math.round(rect.width * dpr)
    const ch = Math.round(rect.height * dpr)
    if (canvas.width !== cw || canvas.height !== ch) {
      canvas.width = cw; canvas.height = ch
      gctx.configure({ device, format: fmt, alphaMode: 'premultiplied' })
    }
    if (ch !== lastCh) {
      lastCh = ch
      const heroEl = par.parentElement!
      const logoImg = heroEl.querySelector('img')
      if (logoImg) {
        const hr = heroEl.getBoundingClientRect()
        const lr = logoImg.getBoundingClientRect()
        cachedCY = 1 - 2 * (lr.top + lr.height / 2 - hr.top) * dpr / ch
      }
    }
    const aspect = cw / ch
    ud[0] = (now - t0) / 1000; ud[1] = GPU_COUNT; ud[2] = aspect
    ud[3] = cachedCY; ud[4] = Math.sqrt(aspect * aspect + 1) + 0.2
    device.queue.writeBuffer(ubuf, 0, ud)
    const enc = device.createCommandEncoder()
    const pass = enc.beginRenderPass({
      colorAttachments: [{
        view: gctx.getCurrentTexture().createView(),
        clearValue: [0, 0, 0, 0], loadOp: 'clear', storeOp: 'store',
      }],
    })
    pass.setPipeline(pipe)
    pass.setBindGroup(0, bg)
    pass.draw(6, GPU_COUNT)
    pass.end()
    device.queue.submit([enc.finish()])
  }
  rafId = requestAnimationFrame(tick)
}

function startPatternAnimation() {
  if (!useWebGPU.value) return // SVG fallback is static, nothing to start
  const canvas = canvasRef.value
  if (!canvas) return
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return

  startWebGPU(canvas).catch(() => { useWebGPU.value = false })
}

onMounted(() => {
  observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('revealed')
          observer?.unobserve(entry.target)
        }
      })
    },
    { threshold: 0.12, rootMargin: '0px 0px -60px 0px' }
  )
  pageRef.value?.querySelectorAll('.landing-reveal').forEach((el) => {
    observer?.observe(el)
  })

  // Hero visibility — pause WebGPU animation when scrolled away
  if (useWebGPU.value) {
    heroObserver = new IntersectionObserver(
      (entries) => { heroVisible = entries[0]?.isIntersecting ?? false },
      { threshold: 0 }
    )
    if (heroRef.value) heroObserver.observe(heroRef.value)
  }

  nextTick(() => startPatternAnimation())
})

onBeforeUnmount(() => {
  if (rafId !== null) cancelAnimationFrame(rafId)
  observer?.disconnect()
  heroObserver?.disconnect()
})
</script>

<style scoped>
/* Hero logo entrance — gentle scale + fade */
.hero-logo {
  animation: logoIn 2s cubic-bezier(0.16, 1, 0.3, 1) both;
}

@keyframes logoIn {
  0% { opacity: 0; transform: scale(0.6) rotate(-90deg); }
  100% { opacity: 1; transform: scale(1) rotate(0deg); }
}

/* Hero staggered cascade entrance */
.hero-stagger {
  opacity: 0;
  transform: translateY(20px);
  animation: heroFadeIn 1.4s cubic-bezier(0.16, 1, 0.3, 1) both;
  animation-delay: calc(var(--stagger, 0) * 0.2s + 0.4s);
}

@keyframes heroFadeIn {
  to { opacity: 1; transform: translateY(0); }
}

/* CTA glow pulse */
.cta-pulse {
  animation: ctaGlow 5s ease-in-out infinite;
}

@keyframes ctaGlow {
  0%, 100% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--color-primary) 30%, transparent); }
  50% { box-shadow: 0 0 28px 8px color-mix(in srgb, var(--color-primary) 12%, transparent); }
}

/* Scroll reveal for below-fold content */
.landing-reveal {
  opacity: 0;
  transform: translateY(24px);
  transition: opacity 1.2s cubic-bezier(0.16, 1, 0.3, 1),
              transform 1.2s cubic-bezier(0.16, 1, 0.3, 1);
}

.landing-reveal.revealed {
  opacity: 1;
  transform: translateY(0);
}

/* Respect user preference */
@media (prefers-reduced-motion: reduce) {
  .landing-reveal {
    transition: none;
    opacity: 1;
    transform: none;
  }
  .hero-logo,
  .hero-stagger {
    animation: none;
    opacity: 1;
    transform: none;
  }
  .cta-pulse {
    animation: none;
  }
}
</style>
