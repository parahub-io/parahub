<template>
  <div class="mcm-root">
    <div v-for="g in groups" :key="g.id" class="mcm-group">
      <div v-if="g.label" class="mcm-label">{{ g.label }}</div>
      <div
        :ref="(el) => setFrame(g.id, el)"
        class="mcm-frame"
        @mouseover="onHover(g.id, $event)"
        @mouseleave="cross = null"
      >
        <div class="mcm-grid" :style="cols ? { gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` } : undefined">
          <button
            v-for="it in g.items"
            :key="it.id"
            data-tile
            class="mcm-tile"
            :class="{ active: it.active }"
            :aria-pressed="it.active"
            @click="$emit('pick', it.id)"
          >
            <Loader2 v-if="it.loading" class="mcm-tile-icon animate-spin" :size="18" :stroke-width="2" />
            <component :is="it.icon" v-else class="mcm-tile-icon" :size="18" :stroke-width="2" />
            <span class="mcm-tile-label">{{ it.label }}</span>
            <span v-if="it.dot && it.active" class="mcm-dot" aria-hidden="true" />
          </button>
        </div>
        <!-- Reticle crosshair (PK/design-system.md § HUD Aesthetic): four 1px ticks
             on the frame edges, extensions cross at the hovered tile's center.
             Appears instantly, no transitions. -->
        <template v-if="cross && cross.gid === g.id">
          <span class="mcm-tick bg-secondary dark:bg-primary" :style="{ left: `-${TICK}px`, top: cross.y - 0.5 + 'px', width: TICK + 'px', height: '1px' }" />
          <span class="mcm-tick bg-secondary dark:bg-primary" :style="{ right: `-${TICK}px`, top: cross.y - 0.5 + 'px', width: TICK + 'px', height: '1px' }" />
          <span class="mcm-tick bg-secondary dark:bg-primary" :style="{ top: `-${TICK}px`, left: cross.x - 0.5 + 'px', width: '1px', height: TICK + 'px' }" />
          <span class="mcm-tick bg-secondary dark:bg-primary" :style="{ bottom: `-${TICK}px`, left: cross.x - 0.5 + 'px', width: '1px', height: TICK + 'px' }" />
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * Tile matrix for map control popovers (layers / tools): a dense bento grid
 * instead of a row list. Fill = state (active tile fills primary yellow with
 * dark text, same grammar as the active top-nav item), hover carries the HUD
 * reticle.
 */
import { ref } from 'vue'
import { Loader2 } from 'lucide-vue-next'

export interface MatrixItem {
  id: string
  icon: any
  label: string
  active: boolean
  /** Corner dot on the active tile (e.g. transit route filter engaged) */
  dot?: boolean
  loading?: boolean
}

export interface MatrixGroup {
  id: string
  label?: string
  items: MatrixItem[]
}

defineProps<{
  groups: MatrixGroup[]
  /** Fixed column count; omit for responsive default (3 desktop / 4 phones) */
  cols?: number
}>()

defineEmits<{
  (e: 'pick', id: string): void
}>()

const TICK = 5 // tick length in px; thickness 1px = hairline frame weight

const frameEls: Record<string, HTMLElement | null> = {}
function setFrame(id: string, el: any) {
  frameEls[id] = el as HTMLElement | null
}

const cross = ref<{ gid: string; x: number; y: number } | null>(null)

function onHover(gid: string, e: MouseEvent) {
  const tile = (e.target as HTMLElement).closest?.('[data-tile]') as HTMLElement | null
  const frame = frameEls[gid]
  // Ignore hovers over hairline gaps — keep last position, clear only on frame leave
  if (!tile || !frame?.contains(tile)) return
  const f = frame.getBoundingClientRect()
  const r = tile.getBoundingClientRect()
  cross.value = {
    gid,
    x: r.left - f.left + r.width / 2,
    y: r.top - f.top + r.height / 2,
  }
}
</script>

<style scoped>
.mcm-root {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.mcm-label {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-muted, #737373);
  margin-bottom: 4px;
  padding-left: 2px;
}

.mcm-frame {
  position: relative;
  border: 1px solid var(--color-border, #e5e5e5);
  border-radius: 10px;
}

/* 3 columns everywhere: every group (3 imagery / 9 data / 6 tools) fills its
   rows exactly — no dangling empty cells, wider tap targets on the sheet */
.mcm-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1px;
  background: var(--color-border, #e5e5e5);
  border-radius: 9px;
  overflow: hidden;
}

.mcm-tile {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  height: 56px;
  padding: 4px 2px;
  border: none;
  background: var(--color-surface, #fff);
  color: var(--color-text);
  cursor: pointer;
  font-size: 10px;
  line-height: 1.15;
  text-align: center;
}
:root.dark .mcm-tile { background: #171717; }

.mcm-tile:hover {
  background: var(--color-primary-100, #fef9c3);
}
:root.dark .mcm-tile:hover {
  background: var(--color-primary-900, #422006);
}

/* Fill = state, same yellow-on-dark grammar as the active top-nav item.
   Dark selector repeated after the dark hover/base rules to win the cascade. */
.mcm-tile.active,
:root.dark .mcm-tile.active {
  background: var(--color-primary, #ffe216);
  color: #171717;
}

.mcm-tile-icon { flex-shrink: 0; }

.mcm-tile-label {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  max-width: 100%;
  /* Long single words (RU/DE labels) wrap to the second line instead of
     truncating on the first */
  word-break: break-word;
  overflow-wrap: anywhere;
}

/* Renders only on active (yellow) tiles — dark for contrast */
.mcm-dot {
  position: absolute;
  top: 5px;
  right: 5px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #171717;
}

.mcm-tick {
  position: absolute;
  pointer-events: none;
}
</style>
