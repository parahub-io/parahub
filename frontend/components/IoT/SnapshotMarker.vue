<template>
  <canvas
    ref="cv"
    class="snapshot-marker"
    :style="{ width: size + 'px', height: size + 'px', opacity: stale ? 0.45 : 1 }"
    aria-hidden="true"
  />
</template>

<script setup lang="ts">
// Design-system marker over a card map snapshot (PK/design-system.md § Map
// Markers): flat-top hexagon = live device, rounded square = static place,
// fill = status/data, glyph = type. Draws with the same shared canvas
// painters as the /map GL layers so cards and map stay pixel-identical.
import {
  DEVICE_HEX_SIZE, hexagonPath, roundedSquarePath, strokeMarkerOutline,
  glyphColorFor, drawLucideGlyph,
} from '~/composables/useMapToggleableLayer'
import { drawWifiGlyph } from '~/composables/useMapMeshLayer'

interface Props {
  fill: string
  /** Lucide 24×24 path data, or 'wifi' for the mesh-router arc glyph */
  glyph?: string[] | 'wifi' | null
  shape?: 'hex' | 'square'
  /** Stale reading: whole marker dims to 0.45, same as the map layer */
  stale?: boolean
  /** CSS px at 1x; canvas draws at 2x like the GL sprites */
  size?: number
}

const props = withDefaults(defineProps<Props>(), {
  glyph: null,
  shape: 'hex',
  stale: false,
  size: DEVICE_HEX_SIZE,
})

const cv = ref<HTMLCanvasElement | null>(null)

function draw() {
  const canvas = cv.value
  if (!canvas) return
  const s = props.size * 2
  canvas.width = s
  canvas.height = s
  const ctx = canvas.getContext('2d')!
  if (props.shape === 'square') roundedSquarePath(ctx, s, 4)
  else hexagonPath(ctx, s)
  ctx.fillStyle = props.fill
  ctx.fill()
  strokeMarkerOutline(ctx)
  if (props.glyph === 'wifi') drawWifiGlyph(ctx, s)
  else if (props.glyph) drawLucideGlyph(ctx, s, props.glyph, 24, glyphColorFor(props.fill))
}

onMounted(draw)
watch(() => [props.fill, props.glyph, props.shape, props.size], draw)
</script>

<style scoped>
.snapshot-marker {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 1;
  pointer-events: none;
}
</style>
