<template>
  <div class="tm-root" :class="`tm-fill-${fill}`">
    <div v-for="g in groups" :key="g.id" class="tm-group">
      <div v-if="g.label" class="tm-label">{{ g.label }}</div>
      <div
        :ref="(el) => setFrame(g.id, el)"
        class="tm-frame"
        @mouseover="onHover(g.id, $event)"
        @mouseleave="cross = null"
      >
        <div class="tm-grid" :style="{ gridTemplateColumns: `repeat(${colsOf(g)}, minmax(0, 1fr))` }">
          <component
            :is="it.to && !it.disabled ? NuxtLink : 'button'"
            v-for="(it, i) in g.items"
            :key="it.id"
            :to="it.disabled ? undefined : it.to"
            :type="it.to && !it.disabled ? undefined : 'button'"
            data-tile
            class="tm-tile"
            :class="[{ active: it.active, disabled: it.disabled }, it.tone ? `tone-${it.tone}` : '']"
            :style="spanOf(g, i) ? { gridColumn: `span ${spanOf(g, i)}` } : undefined"
            :disabled="it.disabled || undefined"
            :aria-pressed="it.active === undefined ? undefined : it.active"
            @click="!it.disabled && !it.to && $emit('pick', it.id)"
          >
            <Loader2 v-if="it.loading" class="tm-tile-icon animate-spin" :size="18" :stroke-width="2" />
            <component :is="it.icon" v-else class="tm-tile-icon" :size="18" :stroke-width="2" />
            <span class="tm-tile-label">{{ it.label }}</span>
            <span v-if="it.dot" class="tm-dot" aria-hidden="true" />
          </component>
        </div>
        <!-- Reticle crosshair (PK/design-system.md § HUD Aesthetic): four 1px ticks
             on the frame edges, extensions cross at the hovered tile's center.
             Appears instantly, no transitions. -->
        <template v-if="cross && cross.gid === g.id">
          <span class="tm-tick bg-secondary dark:bg-primary" :style="{ left: `-${TICK}px`, top: cross.y - 0.5 + 'px', width: TICK + 'px', height: '1px' }" />
          <span class="tm-tick bg-secondary dark:bg-primary" :style="{ right: `-${TICK}px`, top: cross.y - 0.5 + 'px', width: TICK + 'px', height: '1px' }" />
          <span class="tm-tick bg-secondary dark:bg-primary" :style="{ top: `-${TICK}px`, left: cross.x - 0.5 + 'px', width: '1px', height: TICK + 'px' }" />
          <span class="tm-tick bg-secondary dark:bg-primary" :style="{ bottom: `-${TICK}px`, left: cross.x - 0.5 + 'px', width: '1px', height: TICK + 'px' }" />
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * Dense tile matrix: a bento grid of same-shape command tiles instead of a row
 * of buttons, so the layout stays rectangular whatever the locale does to the
 * labels. Hover carries the HUD reticle (§ HUD Aesthetic).
 *
 * Fill = state, and which fill depends on the surface (§ UI Patterns, Active
 * fills): `primary` (yellow) for navigation-layer consoles — map layers/tools,
 * nav — and `secondary` (indigo) for controls living inside page content.
 * Glyph tone is separate from fill: it carries semantics (success = trust) while
 * the fill stays reserved for on/off state.
 */
import { ref, resolveComponent } from 'vue'
import { Loader2 } from 'lucide-vue-next'

const NuxtLink = resolveComponent('NuxtLink')

export interface TileItem {
  id: string
  icon: any
  label: string
  active?: boolean
  disabled?: boolean
  /** Corner dot (e.g. a private note exists, a route filter is engaged) */
  dot?: boolean
  loading?: boolean
  /** Renders the tile as a link instead of a button (no `pick` emit) */
  to?: string
  /** Semantic glyph colour; the fill stays state-only */
  tone?: 'success' | 'warning'
}

export interface TileGroup {
  id: string
  label?: string
  items: TileItem[]
  /** Column count for this frame only; falls back to the `cols` prop, then 3 */
  cols?: number
}

const props = withDefaults(defineProps<{
  groups: TileGroup[]
  /** Default column count for every frame */
  cols?: number
  /** Active-tile fill: yellow for HUD/navigation surfaces, indigo inside content */
  fill?: 'primary' | 'secondary'
}>(), { fill: 'primary' })

defineEmits<{
  (e: 'pick', id: string): void
}>()

const TICK = 5 // tick length in px; thickness 1px = hairline frame weight

const colsOf = (g: TileGroup) => g.cols ?? props.cols ?? 3

// The last tile absorbs the remainder of its row, so a group whose size doesn't
// divide by the column count still renders as a full rectangle instead of
// leaving a hairline-coloured hole where a tile is missing.
function spanOf(g: TileGroup, i: number) {
  const c = colsOf(g)
  const rem = g.items.length % c
  if (rem === 0 || i !== g.items.length - 1) return 0
  return c - rem + 1
}

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
.tm-root {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.tm-label {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-muted, #737373);
  margin-bottom: 4px;
  padding-left: 2px;
}

.tm-frame {
  position: relative;
  border: 1px solid var(--color-border, #e5e5e5);
  border-radius: 10px;
}

.tm-grid {
  display: grid;
  gap: 1px;
  background: var(--color-border, #e5e5e5);
  border-radius: 9px;
  overflow: hidden;
}

.tm-tile {
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
  text-decoration: none;
}
:root.dark .tm-tile { background: #171717; }

/* The palette owns the tint: `--color-primary-100` is not a declared variable,
   so the var() form silently fell back to stock Tailwind yellow (#FEF9C3) —
   off-palette next to any surface that hovers with the real class. */
.tm-tile:hover {
  @apply bg-primary-100;
}
:root.dark .tm-tile:hover {
  @apply bg-primary-900/40;
}

/* Fill = state. Yellow on HUD/navigation surfaces, indigo inside page content.
   Dark selectors repeated after the dark hover/base rules to win the cascade. */
.tm-tile.active,
:root.dark .tm-tile.active {
  background: var(--color-primary, #ffe216);
  color: #171717;
}
.tm-fill-secondary .tm-tile.active,
:root.dark .tm-fill-secondary .tm-tile.active {
  background: var(--color-secondary, #4e4ec8);
  color: #fff;
}

/* Unavailable, but still stated: the tile keeps its slot so the reason under
   the frame has something to point at. */
.tm-tile.disabled,
.tm-tile.disabled:hover {
  cursor: not-allowed;
  color: var(--color-text-muted, #a3a3a3);
  background: var(--color-surface, #fff);
}
:root.dark .tm-tile.disabled,
:root.dark .tm-tile.disabled:hover { background: #171717; }

/* Glyph-only semantics — the fill stays reserved for state */
.tm-tile.tone-success:not(.active) .tm-tile-icon { @apply text-success; }
.tm-tile.tone-warning:not(.active) .tm-tile-icon { @apply text-warning; }
.tm-tile.disabled .tm-tile-icon { color: inherit; }

.tm-tile-icon { flex-shrink: 0; }

.tm-tile-label {
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

.tm-dot {
  position: absolute;
  top: 5px;
  right: 5px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-secondary, #4e4ec8);
}
.tm-tile.active .tm-dot { background: #171717; }
.tm-fill-secondary .tm-tile.active .tm-dot { background: #fff; }

.tm-tick {
  position: absolute;
  pointer-events: none;
}
</style>
