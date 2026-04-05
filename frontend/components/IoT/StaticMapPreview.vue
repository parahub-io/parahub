<template>
  <div ref="container" class="static-map" :style="{ height: height + 'px' }">
    <!-- MapLibre renders here when visible -->
    <div ref="mapEl" class="map-inner" />
    <!-- Centered marker (always visible, even while map loads) -->
    <div class="marker">
      <div class="marker-pulse" />
      <div class="marker-dot" />
    </div>
  </div>
</template>

<script setup lang="ts">
interface Props {
  latitude: number
  longitude: number
  zoom?: number
  height?: number
  interactive?: boolean
}

const emit = defineEmits<{
  (e: 'update:center', lat: number, lon: number): void
}>()

const props = withDefaults(defineProps<Props>(), {
  zoom: 15,
  height: 150,
  interactive: false,
})

const colorMode = useColorMode()
const container = ref<HTMLElement | null>(null)
const mapEl = ref<HTMLElement | null>(null)

let map: any = null
let observer: IntersectionObserver | null = null
let created = false

const getStyleUrl = () =>
  colorMode.value === 'dark'
    ? '/map-styles/dark-liberty-parahub.json'
    : '/map-styles/liberty-parahub.json'

async function createMap() {
  if (created || !mapEl.value) return
  created = true

  const mod = await import('maplibre-gl')
  const maplibregl = mod.default || mod
  await import('maplibre-gl/dist/maplibre-gl.css')

  map = new maplibregl.Map({
    container: mapEl.value,
    style: getStyleUrl(),
    center: [props.longitude, props.latitude],
    zoom: props.zoom,
    interactive: props.interactive,
    attributionControl: false,
    trackResize: props.interactive,
    fadeDuration: 0,
    pixelRatio: Math.min(window.devicePixelRatio || 1, 2),
  })

  map.once('load', () => map.resize())

  if (props.interactive) {
    map.on('moveend', () => {
      const c = map.getCenter()
      emit('update:center', Math.round(c.lat * 100000) / 100000, Math.round(c.lng * 100000) / 100000)
    })
  }
}

// Lazy: only create map when container enters viewport
onMounted(() => {
  if (!container.value) return

  observer = new IntersectionObserver(
    (entries) => {
      if (entries[0].isIntersecting && !created) {
        createMap()
      }
    },
    { rootMargin: '200px' } // start loading slightly before visible
  )
  observer.observe(container.value)
})

// Theme switch
watch(() => colorMode.value, () => {
  if (map) map.setStyle(getStyleUrl())
})

// Coordinates change (skip if map already at target — prevents loop when interactive)
watch(
  () => [props.latitude, props.longitude],
  ([lat, lon]) => {
    if (!map) return
    const c = map.getCenter()
    if (Math.abs(c.lat - lat) < 0.00001 && Math.abs(c.lng - lon) < 0.00001) return
    map.jumpTo({ center: [lon, lat], zoom: props.zoom })
  }
)

onUnmounted(() => {
  observer?.disconnect()
  observer = null
  if (map) {
    map.remove()
    map = null
  }
})
</script>

<style scoped>
.static-map {
  position: relative;
  width: 100%;
  overflow: hidden;
  border-radius: 0.5rem;
  background: #e5e7eb;
}

:deep(.dark) .static-map,
.dark .static-map {
  background: #374151;
}

.map-inner {
  position: absolute;
  inset: 0;
}

/* Hide MapLibre logo and attribution for tiny previews */
.map-inner :deep(.maplibregl-ctrl-bottom-left),
.map-inner :deep(.maplibregl-ctrl-bottom-right) {
  display: none;
}

.marker {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 1;
  pointer-events: none;
}

.marker-dot {
  width: 12px;
  height: 12px;
  background: #6366f1;
  border: 2px solid white;
  border-radius: 50%;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.3);
  position: relative;
  z-index: 2;
}

.marker-pulse {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 24px;
  height: 24px;
  background: rgba(99, 102, 241, 0.3);
  border-radius: 50%;
  animation: pulse 2s ease-out infinite;
  z-index: 1;
}

@keyframes pulse {
  0% { transform: translate(-50%, -50%) scale(1); opacity: 0.6; }
  100% { transform: translate(-50%, -50%) scale(2.5); opacity: 0; }
}
</style>
