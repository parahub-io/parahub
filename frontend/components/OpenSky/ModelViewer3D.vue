<template>
  <div ref="viewerRef" class="relative w-full bg-neutral-900" :style="{ height: isFullscreen ? '100vh' : '70vh' }">
    <!-- Size warning -->
    <div v-if="glbSizeMb > 100 && !loadStarted" class="absolute inset-0 flex items-center justify-center z-10 bg-neutral-900/80 rounded-lg">
      <div class="text-center p-6">
        <AlertTriangle class="w-12 h-12 text-warning mx-auto mb-3" />
        <p class="text-white text-lg mb-2">{{ $t('opensky.large_model_warning', 'Large 3D model') }}</p>
        <p class="text-neutral-400 mb-4">{{ glbSizeMb.toFixed(0) }} MB</p>
        <button
          @click="startLoading"
          class="btn-primary"
        >
          {{ $t('opensky.load_anyway', 'Load anyway') }}
        </button>
      </div>
    </div>

    <!-- Loading overlay -->
    <div v-if="isLoading" class="absolute inset-0 flex items-center justify-center z-10 bg-neutral-900/80 rounded-lg">
      <div class="text-center">
        <Loader2 class="w-10 h-10 animate-spin text-primary mx-auto mb-3" />
        <p class="text-white">{{ $t('opensky.loading_3d', 'Loading 3D model...') }}</p>
        <p v-if="loadProgress > 0" class="text-neutral-400 text-sm mt-1">{{ loadProgress }}%</p>
      </div>
    </div>

    <!-- Error -->
    <div v-if="loadError" class="absolute inset-0 flex items-center justify-center z-10 bg-neutral-900/80 rounded-lg">
      <div class="text-center p-6">
        <AlertTriangle class="w-12 h-12 text-error mx-auto mb-3" />
        <p class="text-white">{{ loadError }}</p>
      </div>
    </div>

    <!-- Controls hint -->
    <div v-if="modelLoaded && !isLoading" class="absolute bottom-3 left-3 z-10 text-xs text-neutral-400 bg-neutral-900/60 px-2 py-1 rounded">
      <div>{{ $t('opensky.viewer_controls', 'Drag to rotate, scroll to zoom, right-click to pan') }}</div>
      <div :class="{ 'text-primary': demoMode > 0 }">{{ $t('opensky.viewer_demo_hint', '1/2/3 — auto-rotate demo (same key stops)') }}</div>
    </div>

    <!-- Demo rotation buttons — touch-friendly mirror of keys 1/2/3 -->
    <div v-if="modelLoaded && !isLoading" class="absolute bottom-3 right-3 z-10 flex gap-1.5">
      <button
        @click="setDemoMode(1)"
        class="p-2 rounded transition-colors"
        :class="demoMode === 1 ? 'bg-primary text-neutral-900' : 'bg-neutral-900/60 text-neutral-300 hover:bg-neutral-900/90 hover:text-white'"
        :title="$t('opensky.demo_spin', 'Slow spin (key 1)')"
      >
        <RotateCcw class="w-4 h-4" />
      </button>
      <button
        @click="setDemoMode(2)"
        class="p-2 rounded transition-colors"
        :class="demoMode === 2 ? 'bg-primary text-neutral-900' : 'bg-neutral-900/60 text-neutral-300 hover:bg-neutral-900/90 hover:text-white'"
        :title="$t('opensky.demo_spin_reverse', 'Slow spin, opposite direction (key 2)')"
      >
        <RotateCw class="w-4 h-4" />
      </button>
      <button
        @click="setDemoMode(3)"
        class="p-2 rounded transition-colors"
        :class="demoMode === 3 ? 'bg-primary text-neutral-900' : 'bg-neutral-900/60 text-neutral-300 hover:bg-neutral-900/90 hover:text-white'"
        :title="$t('opensky.demo_random', 'Random direction & center every 30 s (key 3)')"
      >
        <Shuffle class="w-4 h-4" />
      </button>
    </div>

    <!-- Fullscreen button -->
    <button
      v-if="modelLoaded && !isLoading"
      @click="toggleFullscreen"
      class="absolute top-3 right-3 z-10 p-2 bg-neutral-900/60 hover:bg-neutral-900/90 text-neutral-300 hover:text-white rounded transition-colors"
      :title="isFullscreen ? $t('opensky.exit_fullscreen', 'Exit fullscreen') : $t('opensky.fullscreen', 'Fullscreen')"
    >
      <Minimize v-if="isFullscreen" class="w-5 h-5" />
      <Maximize v-else class="w-5 h-5" />
    </button>

    <!-- Three.js canvas -->
    <div ref="containerRef" class="w-full h-full rounded-lg overflow-hidden bg-neutral-900"></div>
  </div>
</template>

<script setup lang="ts">
import { Loader2, AlertTriangle, Maximize, Minimize, RotateCcw, RotateCw, Shuffle } from 'lucide-vue-next'
import { ref, nextTick, onMounted, onBeforeUnmount, watch } from 'vue'

const props = defineProps<{
  glbUrl: string
  authToken: string
  glbSizeMb?: number
}>()

const viewerRef = ref<HTMLElement | null>(null)
const containerRef = ref<HTMLElement | null>(null)
const isLoading = ref(false)
const loadProgress = ref(0)
const loadError = ref<string | null>(null)
const modelLoaded = ref(false)
const loadStarted = ref(false)
const isFullscreen = ref(false)

// Three.js objects (kept as plain vars, not reactive)
let renderer: any = null
let scene: any = null
let camera: any = null
let controls: any = null
let animationId: number | null = null

const startLoading = () => {
  loadStarted.value = true
  loadModel()
}

const toggleFullscreen = async () => {
  if (!viewerRef.value) return
  if (!document.fullscreenElement) {
    await viewerRef.value.requestFullscreen()
  } else {
    await document.exitFullscreen()
  }
}

// ===== Demo auto-rotation (keys 1/2/3) =====
// 1 — slow spin around the model's own center; 2 — same, opposite direction;
// 3 — every 30 s pick a random direction AND a random pivot point on the map.
// The MODEL rotates (not the camera), so zoom/pan/rotate stay usable during demo.
const DEMO_ROT_SPEED = 0.08 // rad/s ≈ full turn in ~80 s
const DEMO_SHUFFLE_MS = 30000
const demoMode = ref<0 | 1 | 2 | 3>(0)
let demoTHREE: any = null
let demoModel: any = null
let demoBounds: { x: number; z: number; maxDim: number } | null = null // footprint at load
let demoDir = 1
let demoPivot: any = null
let demoQuat: any = null
let demoAxis: any = null
let demoShuffleTimer: ReturnType<typeof setInterval> | null = null

const currentModelCenter = () => {
  const box = new demoTHREE.Box3().setFromObject(demoModel)
  return box.getCenter(new demoTHREE.Vector3())
}

const shuffleDemo = () => {
  // Random direction + random pivot near the viewport center (the model starts
  // centered at the origin, so this is a random point on the map). Sampling in a
  // FIXED region — not around the model's current center — keeps the action in
  // frame; the leash below stops the residual drift once it exceeds one model size.
  demoDir = Math.random() < 0.5 ? 1 : -1
  const center = currentModelCenter()
  if (!demoBounds || center.length() > demoBounds.maxDim) {
    demoPivot = center // wandered too far: spin in place, no further drift
  } else {
    demoPivot = new demoTHREE.Vector3(
      (Math.random() - 0.5) * demoBounds.x * 0.7,
      center.y,
      (Math.random() - 0.5) * demoBounds.z * 0.7,
    )
  }
}

const setDemoMode = (mode: 1 | 2 | 3) => {
  if (!demoModel || !demoTHREE) return
  if (demoShuffleTimer) { clearInterval(demoShuffleTimer); demoShuffleTimer = null }
  if (demoMode.value === mode) { demoMode.value = 0; return } // same key again = stop
  demoMode.value = mode
  demoAxis = demoAxis || new demoTHREE.Vector3(0, 1, 0)
  demoQuat = demoQuat || new demoTHREE.Quaternion()
  if (mode === 3) {
    shuffleDemo()
    demoShuffleTimer = setInterval(shuffleDemo, DEMO_SHUFFLE_MS)
  } else {
    demoDir = mode === 1 ? 1 : -1
    demoPivot = currentModelCenter()
  }
}

const updateDemoRotation = (dt: number) => {
  if (!demoMode.value || !demoModel || !demoPivot) return
  // Clamp: after rAF throttling (backgrounded tab) the first delta spans the
  // whole pause — without the cap the model snaps tens of degrees at once.
  const q = demoQuat.setFromAxisAngle(demoAxis, demoDir * DEMO_ROT_SPEED * Math.min(dt, 0.1))
  // Rotate the model around a vertical axis through the pivot (world space)
  demoModel.position.sub(demoPivot).applyQuaternion(q).add(demoPivot)
  demoModel.applyQuaternion(q)
}

const onKeyDown = (e: KeyboardEvent) => {
  if (!modelLoaded.value) return
  if (e.key === '1' || e.key === '2' || e.key === '3') {
    setDemoMode(Number(e.key) as 1 | 2 | 3)
  }
}

const onFullscreenChange = () => {
  isFullscreen.value = !!document.fullscreenElement
  // Trigger resize after fullscreen transition
  nextTick(() => {
    if (containerRef.value && renderer && camera) {
      const w = containerRef.value.clientWidth
      const h = containerRef.value.clientHeight
      camera.aspect = w / h
      camera.updateProjectionMatrix()
      renderer.setSize(w, h)
    }
  })
}

const loadModel = async () => {
  if (!containerRef.value) return

  isLoading.value = true
  loadError.value = null
  loadProgress.value = 0

  try {
    // Dynamic import three.js (client-side only)
    const THREE = await import('three')
    const { TrackballControls } = await import('three/examples/jsm/controls/TrackballControls.js')
    const { GLTFLoader } = await import('three/examples/jsm/loaders/GLTFLoader.js')
    const { DRACOLoader } = await import('three/examples/jsm/loaders/DRACOLoader.js')

    const container = containerRef.value
    const width = container.clientWidth
    const height = container.clientHeight

    // Scene
    scene = new THREE.Scene()
    scene.background = new THREE.Color(0x1a1a2e)

    // Camera
    camera = new THREE.PerspectiveCamera(60, width / height, 0.1, 10000)
    camera.position.set(5, 5, 5)

    // Renderer
    renderer = new THREE.WebGLRenderer({ antialias: true })
    renderer.setSize(width, height)
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure = 1.0
    container.appendChild(renderer.domElement)

    // Lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6)
    scene.add(ambientLight)

    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8)
    directionalLight.position.set(10, 20, 10)
    scene.add(directionalLight)

    const directionalLight2 = new THREE.DirectionalLight(0xffffff, 0.3)
    directionalLight2.position.set(-10, 10, -10)
    scene.add(directionalLight2)

// Controls (TrackballControls — free 3-axis rotation)
    controls = new TrackballControls(camera, renderer.domElement)
    controls.rotateSpeed = 1.0
    controls.zoomSpeed = 0.8
    controls.panSpeed = 0.4
    controls.dynamicDampingFactor = 0.15
    controls.staticMoving = false
    controls.minDistance = 0.5
    controls.maxDistance = 500

    // Fetch GLB with auth headers and progress tracking
    const response = await fetch(props.glbUrl, {
      headers: { 'Authorization': `Bearer ${props.authToken}` },
      credentials: 'include'
    })

    if (!response.ok) {
      throw new Error(`Failed to load model: ${response.status}`)
    }

    const contentLength = response.headers.get('content-length')
    const total = contentLength ? parseInt(contentLength, 10) : 0
    const reader = response.body!.getReader()
    const chunks: Uint8Array[] = []
    let received = 0

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      chunks.push(value)
      received += value.length
      if (total > 0) {
        loadProgress.value = Math.round((received / total) * 100)
      }
    }

    // Combine chunks into ArrayBuffer
    const blob = new Blob(chunks)
    const arrayBuffer = await blob.arrayBuffer()

    // Load GLB (with Draco decoder for compressed geometry)
    const loader = new GLTFLoader()
    const dracoLoader = new DRACOLoader()
    dracoLoader.setDecoderPath('/draco/')
    loader.setDRACOLoader(dracoLoader)

    const gltf = await new Promise<any>((resolve, reject) => {
      loader.parse(arrayBuffer, '', resolve, reject)
    })

    dracoLoader.dispose()

    const model = gltf.scene
    scene.add(model)

    // ODM meshes are Z-up (local ENU frame passed through obj2gltf as-is);
    // three.js is Y-up — without this the terrain plane stands vertical.
    model.rotation.x = -Math.PI / 2

    // Auto-center and scale model to fit viewport (bbox computed after the
    // up-axis rotation so centering and camera framing see the upright model)
    const box = new THREE.Box3().setFromObject(model)
    const boxCenter = box.getCenter(new THREE.Vector3())
    const boxSize = box.getSize(new THREE.Vector3())
    const maxDim = Math.max(boxSize.x, boxSize.y, boxSize.z)

    // Center model
    model.position.sub(boxCenter)

    // Position camera to see the whole model
    const fov = camera.fov * (Math.PI / 180)
    const cameraDistance = maxDim / (2 * Math.tan(fov / 2)) * 1.5
    camera.position.set(cameraDistance, cameraDistance * 0.7, cameraDistance)
    camera.lookAt(0, 0, 0)

    controls.target.set(0, 0, 0)
    controls.update()

    modelLoaded.value = true
    isLoading.value = false

    // Wire up demo auto-rotation (keys 1/2/3) — needs THREE + the model root
    demoTHREE = THREE
    demoModel = model
    demoBounds = { x: boxSize.x, z: boxSize.z, maxDim }

    // Animation loop
    const clock = new THREE.Clock()
    const animate = () => {
      animationId = requestAnimationFrame(animate)
      updateDemoRotation(clock.getDelta())
      controls.update()
      renderer.render(scene, camera)
    }
    animate()

    // Handle resize
    const onResize = () => {
      if (!container || !renderer || !camera) return
      const w = container.clientWidth
      const h = container.clientHeight
      camera.aspect = w / h
      camera.updateProjectionMatrix()
      renderer.setSize(w, h)
    }
    window.addEventListener('resize', onResize)

    // Store cleanup ref
    ;(container as any).__resizeHandler = onResize

  } catch (err: any) {
    console.error('Failed to load 3D model:', err)
    loadError.value = err.message || 'Failed to load 3D model'
    isLoading.value = false
  }
}

onMounted(() => {
  document.addEventListener('fullscreenchange', onFullscreenChange)
  document.addEventListener('keydown', onKeyDown)
  // Open maximized right away — the "View 3D" click's transient activation is
  // still valid here; if the browser refuses, the viewer just stays in the modal.
  try { viewerRef.value?.requestFullscreen?.()?.catch(() => {}) } catch {}
  // Auto-start loading for small models
  if (!props.glbSizeMb || props.glbSizeMb <= 100) {
    loadStarted.value = true
    loadModel()
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('fullscreenchange', onFullscreenChange)
  document.removeEventListener('keydown', onKeyDown)
  if (demoShuffleTimer) { clearInterval(demoShuffleTimer); demoShuffleTimer = null }
  demoModel = null
  demoTHREE = null
  // Cleanup three.js resources
  if (animationId !== null) {
    cancelAnimationFrame(animationId)
    animationId = null
  }

  if (containerRef.value) {
    const handler = (containerRef.value as any).__resizeHandler
    if (handler) {
      window.removeEventListener('resize', handler)
    }
  }

  if (controls) {
    controls.dispose()
    controls = null
  }

  if (renderer) {
    renderer.dispose()
    if (renderer.domElement?.parentNode) {
      renderer.domElement.parentNode.removeChild(renderer.domElement)
    }
    renderer = null
  }

  // Dispose scene objects
  if (scene) {
    scene.traverse((obj: any) => {
      if (obj.geometry) obj.geometry.dispose()
      if (obj.material) {
        if (Array.isArray(obj.material)) {
          obj.material.forEach((m: any) => {
            if (m.map) m.map.dispose()
            m.dispose()
          })
        } else {
          if (obj.material.map) obj.material.map.dispose()
          obj.material.dispose()
        }
      }
    })
    scene = null
  }

  camera = null
})
</script>
