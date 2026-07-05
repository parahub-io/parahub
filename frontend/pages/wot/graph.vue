<template>
  <div>
    <Head>
      <Title>{{ $t('wotGraph.pageTitle') }}</Title>
    </Head>

    <!-- Staff gate -->
    <div v-if="!isStaff" class="text-center py-20">
      <ShieldAlert class="w-12 h-12 text-neutral-400 mx-auto mb-4" />
      <p class="text-neutral-500">{{ $t('wotGraph.staffOnly') }}</p>
    </div>

    <div v-else class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-5">
      <!-- Header -->
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div class="flex items-center gap-3">
          <div class="dispatch-icon" style="background: rgba(99,102,241,0.15); color: #6366f1;">
            <Share2 class="w-5 h-5" />
          </div>
          <div>
            <h1 class="text-xl font-bold text-neutral-900 dark:text-neutral-100">{{ $t('wotGraph.title') }}</h1>
            <p class="text-xs text-neutral-500 dark:text-neutral-400">
              {{ $t('wotGraph.subtitle') }}
            </p>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <UiButton variant="outline" size="sm" :icon="RefreshCw" :loading="loading" @click="reload">
            {{ $t('wotGraph.reload') }}
          </UiButton>
          <UiButton variant="outline" size="sm" :icon="Play" @click="reheat">
            {{ $t('wotGraph.relayout') }}
          </UiButton>
        </div>
      </div>

      <!-- Stats -->
      <div v-if="data" class="flex flex-wrap gap-2">
        <UiBadge variant="neutral" type="soft">{{ $t('wotGraph.stats.profilesTotal', data.total_profiles) }}</UiBadge>
        <UiBadge variant="success" type="soft">{{ $t('wotGraph.stats.verified', data.verified_profiles) }}</UiBadge>
        <UiBadge variant="info" type="soft">{{ $t('wotGraph.stats.inGraph', data.connected_profiles) }}</UiBadge>
        <UiBadge variant="primary" type="soft">{{ $t('wotGraph.stats.verifications', data.edges.length) }}</UiBadge>
        <UiBadge v-if="mutualPairCount" variant="warning" type="soft">{{ $t('wotGraph.stats.mutualPairs', mutualPairCount) }}</UiBadge>
        <UiBadge v-if="sameAccountPairs.length" variant="error" type="soft">
          {{ $t('wotGraph.stats.sameAccount', sameAccountPairs.length) }}
        </UiBadge>
      </div>

      <!-- Loading / error / empty -->
      <div v-if="loading" class="flex justify-center py-20">
        <div class="animate-spin rounded-full h-12 w-12 border-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100" />
      </div>
      <UiAlert v-else-if="error" variant="error" :title="error" />
      <div v-else-if="data && data.nodes.length === 0" class="py-12 text-center">
        <Share2 class="w-12 h-12 text-neutral-400 mx-auto mb-4" />
        <h3 class="font-semibold text-neutral-700 dark:text-neutral-300">{{ $t('wotGraph.emptyTitle') }}</h3>
        <p class="text-sm text-neutral-500 mt-1">{{ $t('wotGraph.emptyText') }}</p>
      </div>

      <!-- Graph + side panel -->
      <div v-else-if="data" class="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4">
        <!-- Canvas -->
        <div class="card p-0 overflow-hidden relative" style="background: var(--graph-bg, #fafafa);">
          <svg
            ref="svgEl"
            :viewBox="`0 0 ${W} ${H}`"
            class="w-full select-none touch-none"
            style="aspect-ratio: 900 / 620; display: block;"
            @pointermove="onPointerMove"
            @pointerup="onPointerUp"
            @pointerleave="onPointerUp"
          >
            <defs>
              <marker id="wot-arrow" viewBox="0 0 10 10" refX="9" refY="5"
                      markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M0,0 L10,5 L0,10 z" fill="#94a3b8" />
              </marker>
            </defs>

            <!-- Same-account links (Sybil signal) — behind everything -->
            <line
              v-for="(p, i) in sameAccountPairs" :key="`sa-${i}`"
              :x1="p.a.x" :y1="p.a.y" :x2="p.b.x" :y2="p.b.y"
              stroke="#ef4444" stroke-width="2" stroke-dasharray="2 4" opacity="0.7"
            />

            <!-- Verification edges -->
            <g v-for="(l, i) in renderLinks" :key="`e-${i}`">
              <line
                :x1="l.x1" :y1="l.y1" :x2="l.x2" :y2="l.y2"
                :stroke="edgeHighlighted(l) ? '#6366f1' : '#cbd5e1'"
                :stroke-width="l.mutual ? 2.5 : 1.5"
                :stroke-dasharray="l.method === 'VOUCHED' ? '5 3' : undefined"
                marker-end="url(#wot-arrow)"
                :marker-start="l.mutual ? 'url(#wot-arrow)' : undefined"
                :opacity="dimmed(l.sourceId, l.targetId) ? 0.15 : 0.85"
              />
            </g>

            <!-- Nodes -->
            <g
              v-for="n in nodes" :key="n.id"
              :transform="`translate(${n.x},${n.y})`"
              style="cursor: grab;"
              @pointerdown="onPointerDown(n, $event)"
              @mouseenter="hovered = n.id"
              @mouseleave="hovered = null"
              @click="selected = n"
            >
              <circle
                :r="radius(n)"
                :fill="trustColor(n.trust_level)"
                :stroke="n.id === selected?.id ? '#111827' : (n.is_verified ? '#10b981' : '#ffffff')"
                :stroke-width="n.id === selected?.id ? 3 : (n.is_verified ? 2.5 : 1.5)"
                :opacity="dimNode(n.id) ? 0.2 : 1"
              />
              <!-- pseudonymous marker -->
              <circle
                v-if="n.profile_type !== 'PERSONAL'"
                :r="radius(n) + 3" fill="none" stroke="#a855f7" stroke-width="1"
                stroke-dasharray="2 2" :opacity="dimNode(n.id) ? 0.2 : 0.9"
              />
              <text
                :y="radius(n) + 12" text-anchor="middle"
                class="fill-neutral-700 dark:fill-neutral-300"
                style="font-size: 10px; pointer-events: none;"
                :opacity="dimNode(n.id) ? 0.2 : 1"
              >{{ shortName(n.hna) }}</text>
            </g>
          </svg>

          <!-- Tooltip -->
          <div
            v-if="hoveredNode"
            class="absolute pointer-events-none bg-neutral-900 text-white text-xs rounded px-2 py-1 shadow-lg"
            style="top: 8px; left: 8px; max-width: 240px;"
          >
            <div class="font-semibold">{{ hoveredNode.hna }}</div>
            <div class="text-neutral-300">
              {{ $t('wotGraph.tooltip.rep') }} {{ hoveredNode.reputation.toFixed(1) }} ·
              {{ $t('wotGraph.tooltip.in') }} {{ hoveredNode.received }} ·
              {{ $t('wotGraph.tooltip.out') }} {{ hoveredNode.given }}
            </div>
          </div>
        </div>

        <!-- Side panel: legend + selection -->
        <div class="space-y-4">
          <div class="card p-4 space-y-2">
            <h3 class="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-1">{{ $t('wotGraph.legend.title') }}</h3>
            <div v-for="lvl in legendLevels" :key="lvl.key" class="flex items-center gap-2 text-xs text-neutral-600 dark:text-neutral-400">
              <span class="inline-block w-3 h-3 rounded-full" :style="{ background: lvl.color }" />
              {{ $t(`wotGraph.legend.${lvl.key.toLowerCase()}`) }}
            </div>
            <div class="border-t border-neutral-200 dark:border-neutral-700 my-2" />
            <div class="flex items-center gap-2 text-xs text-neutral-600 dark:text-neutral-400">
              <span class="inline-block w-3 h-3 rounded-full border-2" style="border-color:#10b981" /> {{ $t('wotGraph.legend.verified') }}
            </div>
            <div class="flex items-center gap-2 text-xs text-neutral-600 dark:text-neutral-400">
              <span class="inline-block w-3 h-3 rounded-full border border-dashed" style="border-color:#a855f7" /> {{ $t('wotGraph.legend.pseudonymous') }}
            </div>
            <div class="flex items-center gap-2 text-xs text-neutral-600 dark:text-neutral-400">
              <svg width="22" height="8"><line x1="0" y1="4" x2="22" y2="4" stroke="#94a3b8" stroke-width="2" marker-end="url(#wot-arrow)" /></svg> {{ $t('wotGraph.legend.oneway') }}
            </div>
            <div class="flex items-center gap-2 text-xs text-neutral-600 dark:text-neutral-400">
              <svg width="22" height="8"><line x1="0" y1="4" x2="22" y2="4" stroke="#cbd5e1" stroke-width="2.5" /></svg> {{ $t('wotGraph.legend.mutual') }}
            </div>
            <div class="flex items-center gap-2 text-xs text-neutral-600 dark:text-neutral-400">
              <svg width="22" height="8"><line x1="0" y1="4" x2="22" y2="4" stroke="#ef4444" stroke-width="2" stroke-dasharray="2 4" /></svg> {{ $t('wotGraph.legend.sameAccount') }} ⚠
            </div>
          </div>

          <div v-if="selected" class="card p-4 space-y-2">
            <div class="flex items-center justify-between">
              <h3 class="text-sm font-semibold text-neutral-900 dark:text-neutral-100 truncate">{{ selected.hna }}</h3>
              <button class="text-neutral-400 hover:text-neutral-700" @click="selected = null"><X class="w-4 h-4" /></button>
            </div>
            <dl class="text-xs space-y-1 text-neutral-600 dark:text-neutral-400">
              <div class="flex justify-between"><dt>{{ $t('wotGraph.detail.reputation') }}</dt><dd class="font-mono">{{ selected.reputation.toFixed(1) }}</dd></div>
              <div class="flex justify-between"><dt>{{ $t('wotGraph.detail.received') }}</dt><dd class="font-mono">{{ selected.received }}</dd></div>
              <div class="flex justify-between"><dt>{{ $t('wotGraph.detail.given') }}</dt><dd class="font-mono">{{ selected.given }}</dd></div>
              <div class="flex justify-between"><dt>{{ $t('wotGraph.detail.trust') }}</dt><dd>{{ selected.trust_level }}</dd></div>
              <div class="flex justify-between"><dt>{{ $t('wotGraph.detail.type') }}</dt><dd>{{ selected.profile_type }}</dd></div>
              <div class="flex justify-between"><dt>{{ $t('wotGraph.detail.joined') }}</dt><dd>{{ selected.joined ? new Date(selected.joined).toLocaleDateString() : '—' }}</dd></div>
              <div class="flex justify-between gap-2"><dt>{{ $t('wotGraph.detail.account') }}</dt><dd class="font-mono truncate">{{ selected.account_id.slice(0, 10) }}</dd></div>
            </dl>
            <div v-if="accountSiblings(selected).length" class="text-xs text-error mt-2">
              ⚠ {{ $t('wotGraph.detail.sharesAccount', { names: accountSiblings(selected).map(s => shortName(s.hna)).join(', ') }) }}
            </div>
            <NuxtLink :to="localePath(`/u/${shortName(selected.hna)}`)" class="btn-sm btn-outline w-full mt-1">
              {{ $t('wotGraph.detail.openProfile') }}
            </NuxtLink>
          </div>
          <p v-else class="text-xs text-neutral-400 text-center px-2">{{ $t('wotGraph.hint') }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ShieldAlert, Share2, RefreshCw, Play, X } from 'lucide-vue-next'

definePageMeta({ middleware: 'auth' })

const { t } = useI18n()
const localePath = useLocalePath()
const authStore = useAuthStore()
const isStaff = computed(() => authStore.user?.is_staff ?? false)

interface GNode {
  id: string; hna: string | null; reputation: number; received: number; given: number
  trust_level: string; is_verified: boolean; profile_type: string; account_id: string
  joined: string | null
}
interface GEdge { source: string; target: string; method: string; verified_at: string | null; mutual: boolean }
interface GraphData { nodes: GNode[]; edges: GEdge[]; total_profiles: number; verified_profiles: number; connected_profiles: number }

type SimNode = GNode & { x: number; y: number; vx: number; vy: number; fixed: boolean }

const W = 900
const H = 620

const loading = ref(false)
const error = ref('')
const data = ref<GraphData | null>(null)
const nodes = ref<SimNode[]>([])
const hovered = ref<string | null>(null)
const selected = ref<SimNode | null>(null)
const svgEl = ref<SVGSVGElement | null>(null)

const nodeById = computed(() => {
  const m = new Map<string, SimNode>()
  for (const n of nodes.value) m.set(n.id, n)
  return m
})

const hoveredNode = computed(() => (hovered.value ? nodeById.value.get(hovered.value) ?? null : null))

// label comes from i18n (wotGraph.legend.<key lowercased>); key drives color lookup
const legendLevels = [
  { key: 'HIGH', color: '#6366f1' },
  { key: 'MEDIUM', color: '#0ea5e9' },
  { key: 'BASIC', color: '#10b981' },
  { key: 'LOW', color: '#f59e0b' },
  { key: 'NONE', color: '#9ca3af' },
]
function trustColor(level: string): string {
  return legendLevels.find(l => l.key === level)?.color ?? '#9ca3af'
}
function radius(n: SimNode): number {
  return 8 + Math.sqrt(n.received) * 4
}
function shortName(hna: string | null): string {
  return (hna ?? '?').split('@')[0]
}

// ── Edge rendering: collapse A→B + B→A into a single mutual link ──────
const renderLinks = computed(() => {
  if (!data.value) return [] as Array<{ x1: number; y1: number; x2: number; y2: number; mutual: boolean; method: string; sourceId: string; targetId: string }>
  const seen = new Set<string>()
  const out: Array<{ x1: number; y1: number; x2: number; y2: number; mutual: boolean; method: string; sourceId: string; targetId: string }> = []
  for (const e of data.value.edges) {
    const s = nodeById.value.get(e.source)
    const t = nodeById.value.get(e.target)
    if (!s || !t) continue
    const key = e.mutual ? [e.source, e.target].sort().join('|') : `${e.source}>${e.target}`
    if (seen.has(key)) continue
    seen.add(key)
    const dx = t.x - s.x, dy = t.y - s.y
    const len = Math.hypot(dx, dy) || 1
    const ux = dx / len, uy = dy / len
    const r1 = radius(s), r2 = radius(t) + (e.mutual ? 6 : 8)
    out.push({
      x1: s.x + ux * (r1 + (e.mutual ? 6 : 0)), y1: s.y + uy * (r1 + (e.mutual ? 6 : 0)),
      x2: t.x - ux * r2, y2: t.y - uy * r2,
      mutual: e.mutual, method: e.method, sourceId: e.source, targetId: e.target,
    })
  }
  return out
})

const mutualPairCount = computed(() => renderLinks.value.filter(l => l.mutual).length)

// ── Same-account clusters (Sybil signal) ─────────────────────────────
const sameAccountPairs = computed(() => {
  const groups = new Map<string, SimNode[]>()
  for (const n of nodes.value) {
    if (!n.account_id) continue
    const g = groups.get(n.account_id) ?? []
    g.push(n); groups.set(n.account_id, g)
  }
  const pairs: Array<{ a: SimNode; b: SimNode }> = []
  for (const g of groups.values()) {
    if (g.length < 2) continue
    for (let i = 0; i < g.length; i++)
      for (let j = i + 1; j < g.length; j++) pairs.push({ a: g[i], b: g[j] })
  }
  return pairs
})
function accountSiblings(n: SimNode): SimNode[] {
  if (!n.account_id) return []
  return nodes.value.filter(o => o.id !== n.id && o.account_id === n.account_id)
}

// ── Hover/selection highlighting ─────────────────────────────────────
const focusId = computed(() => hovered.value ?? selected.value?.id ?? null)
const neighborIds = computed(() => {
  const f = focusId.value
  if (!f || !data.value) return null
  const set = new Set<string>([f])
  for (const e of data.value.edges) {
    if (e.source === f) set.add(e.target)
    if (e.target === f) set.add(e.source)
  }
  return set
})
function dimNode(id: string): boolean {
  return !!neighborIds.value && !neighborIds.value.has(id)
}
function dimmed(s: string, t: string): boolean {
  return !!neighborIds.value && !(neighborIds.value.has(s) && neighborIds.value.has(t))
}
function edgeHighlighted(l: { sourceId: string; targetId: string }): boolean {
  const f = focusId.value
  return !!f && (l.sourceId === f || l.targetId === f)
}

// ── Force simulation (self-contained, no deps) ───────────────────────
let alpha = 0
let raf = 0
const REPULSION = 9000
const SPRING = 0.04
const LINK_LEN = 110
const CENTER = 0.02
const DAMP = 0.85

function step() {
  const ns = nodes.value
  const n = ns.length
  // repulsion (O(n^2) — fine for a staff tool on <1k nodes)
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      const a = ns[i], b = ns[j]
      let dx = a.x - b.x, dy = a.y - b.y
      let d2 = dx * dx + dy * dy
      if (d2 < 1) { dx = (i - j) || 1; dy = 1; d2 = dx * dx + dy * dy }
      const f = (REPULSION / d2) * alpha
      const d = Math.sqrt(d2)
      const fx = (dx / d) * f, fy = (dy / d) * f
      a.vx += fx; a.vy += fy; b.vx -= fx; b.vy -= fy
    }
  }
  // springs along edges
  if (data.value) {
    for (const e of data.value.edges) {
      const a = nodeById.value.get(e.source), b = nodeById.value.get(e.target)
      if (!a || !b) continue
      const dx = b.x - a.x, dy = b.y - a.y
      const d = Math.hypot(dx, dy) || 1
      const f = ((d - LINK_LEN) * SPRING) * alpha
      const fx = (dx / d) * f, fy = (dy / d) * f
      a.vx += fx; a.vy += fy; b.vx -= fx; b.vy -= fy
    }
  }
  // centering + integrate
  for (const p of ns) {
    if (p.fixed) { p.vx = 0; p.vy = 0; continue }
    p.vx += (W / 2 - p.x) * CENTER * alpha
    p.vy += (H / 2 - p.y) * CENTER * alpha
    p.vx *= DAMP; p.vy *= DAMP
    p.x += p.vx; p.y += p.vy
    p.x = Math.max(24, Math.min(W - 24, p.x))
    p.y = Math.max(24, Math.min(H - 36, p.y))
  }
  alpha *= 0.985
  if (alpha > 0.02 || dragging) {
    raf = requestAnimationFrame(step)
  } else {
    raf = 0
  }
}
function reheat() {
  alpha = 1
  if (!raf) raf = requestAnimationFrame(step)
}

function seedPositions() {
  const n = nodes.value.length
  nodes.value.forEach((p, i) => {
    const ang = (i / Math.max(1, n)) * Math.PI * 2
    p.x = W / 2 + Math.cos(ang) * 160
    p.y = H / 2 + Math.sin(ang) * 160
    p.vx = 0; p.vy = 0
  })
}

// ── Drag ─────────────────────────────────────────────────────────────
let dragging: SimNode | null = null
function toSvg(ev: PointerEvent): { x: number; y: number } {
  const el = svgEl.value
  if (!el) return { x: 0, y: 0 }
  const r = el.getBoundingClientRect()
  return { x: ((ev.clientX - r.left) / r.width) * W, y: ((ev.clientY - r.top) / r.height) * H }
}
function onPointerDown(n: SimNode, ev: PointerEvent) {
  dragging = n; n.fixed = true
  ;(ev.target as Element).setPointerCapture?.(ev.pointerId)
  reheat()
}
function onPointerMove(ev: PointerEvent) {
  if (!dragging) return
  const p = toSvg(ev)
  dragging.x = p.x; dragging.y = p.y
}
function onPointerUp() {
  if (dragging) { dragging.fixed = false; dragging = null; reheat() }
}

// ── Load ─────────────────────────────────────────────────────────────
async function reload() {
  loading.value = true
  error.value = ''
  try {
    await authStore.ensureToken()
    const res = await $fetch<GraphData>('/api/v1/wot/graph/', {
      credentials: 'include',
      headers: authStore.token ? { Authorization: `Bearer ${authStore.token}` } : {},
    })
    data.value = res
    nodes.value = res.nodes.map(n => ({ ...n, x: W / 2, y: H / 2, vx: 0, vy: 0, fixed: false }))
    selected.value = null
    seedPositions()
    reheat()
  } catch (e: any) {
    error.value = e?.data?.detail || e?.message || t('wotGraph.loadError')
  } finally {
    loading.value = false
  }
}

onMounted(() => { if (isStaff.value) reload() })
onBeforeUnmount(() => { if (raf) cancelAnimationFrame(raf) })
</script>

<style scoped>
.dispatch-icon {
  display: flex; align-items: center; justify-content: center;
  width: 2.5rem; height: 2.5rem; border-radius: 0.75rem;
}
.dark svg { --graph-bg: #18181b; }
</style>
