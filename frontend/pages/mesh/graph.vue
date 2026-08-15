<template>
  <div>
    <Head>
      <Title>{{ $t('meshGraph.pageTitle') }}</Title>
    </Head>

    <!-- Staff gate -->
    <div v-if="!isStaff" class="text-center py-20">
      <ShieldAlert class="w-12 h-12 text-neutral-400 mx-auto mb-4" />
      <p class="text-neutral-500">{{ $t('meshGraph.staffOnly') }}</p>
    </div>

    <div v-else class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-5">
      <!-- Header -->
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div class="flex items-center gap-3">
          <div class="graph-icon" style="background: rgba(78,78,200,0.15); color: #4E4EC8;">
            <Network class="w-5 h-5" />
          </div>
          <div>
            <h1 class="text-xl font-bold text-neutral-900 dark:text-neutral-100">{{ $t('meshGraph.title') }}</h1>
            <p class="text-xs text-neutral-500 dark:text-neutral-400">
              {{ $t('meshGraph.subtitle') }}
            </p>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <UiButton variant="outline" size="sm" :icon="RefreshCw" :loading="loading" @click="reload">
            {{ $t('meshGraph.reload') }}
          </UiButton>
          <UiButton variant="outline" size="sm" :icon="Play" @click="reheat">
            {{ $t('meshGraph.relayout') }}
          </UiButton>
        </div>
      </div>

      <!-- Stats -->
      <div v-if="data" class="flex flex-wrap gap-2">
        <UiBadge variant="neutral" type="soft">{{ $t('meshGraph.stats.nodes', data.nodes.length) }}</UiBadge>
        <UiBadge variant="success" type="soft">{{ $t('meshGraph.stats.fresh', data.fresh_nodes) }}</UiBadge>
        <UiBadge variant="info" type="soft">{{ $t('meshGraph.stats.islands', data.islands) }}</UiBadge>
        <UiBadge variant="primary" type="soft">{{ $t('meshGraph.stats.links', directCount) }}</UiBadge>
        <UiBadge v-if="inferredCount" variant="warning" type="soft">{{ $t('meshGraph.stats.inferred', inferredCount) }}</UiBadge>
      </div>

      <!-- Loading / error / empty -->
      <div v-if="loading" class="flex justify-center py-20" role="status">
        <div class="animate-spin rounded-full h-12 w-12 border-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100" />
        <span class="sr-only">{{ $t('meshGraph.reload') }}</span>
      </div>
      <UiAlert v-else-if="error" variant="error" :title="error" />
      <div v-else-if="data && data.nodes.length === 0" class="py-12 text-center">
        <Network class="w-12 h-12 text-neutral-400 mx-auto mb-4" />
        <h3 class="font-semibold text-neutral-700 dark:text-neutral-300">{{ $t('meshGraph.emptyTitle') }}</h3>
        <p class="text-sm text-neutral-500 mt-1">{{ $t('meshGraph.emptyText') }}</p>
      </div>

      <!-- Graph + side panel -->
      <div v-else-if="data" class="grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-4">
        <!-- Canvas -->
        <div class="card p-0 overflow-hidden relative graph-canvas" style="background: var(--graph-bg, #fafafa);">
          <svg
            ref="svgEl"
            :viewBox="`0 0 ${W} ${H}`"
            class="w-full select-none touch-none"
            style="aspect-ratio: 900 / 620; display: block;"
            @pointermove="onPointerMove"
            @pointerup="onPointerUp"
            @pointerleave="onPointerUp"
          >
            <!-- Edges -->
            <g v-for="(l, i) in renderLinks" :key="`e-${i}`">
              <line
                :x1="l.x1" :y1="l.y1" :x2="l.x2" :y2="l.y2"
                :stroke="edgeHighlighted(l) ? '#4E4EC8' : l.color"
                :stroke-width="l.width"
                :stroke-dasharray="l.inferred ? '4 4' : undefined"
                :opacity="dimmed(l.sourceId, l.targetId) ? 0.12 : 0.8"
              />
              <text
                v-if="l.tp !== null"
                :x="(l.x1 + l.x2) / 2" :y="(l.y1 + l.y2) / 2 - 4"
                text-anchor="middle"
                class="fill-neutral-500 dark:fill-neutral-400"
                style="font-size: 8px; pointer-events: none;"
                :opacity="dimmed(l.sourceId, l.targetId) ? 0.12 : 1"
              >{{ formatTp(l.tp) }}</text>
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
              <!-- terminator ring -->
              <polygon
                v-if="n.is_terminator"
                :points="hexPoints(radius(n) + 5)"
                fill="none" stroke="#FFE216" stroke-width="3"
                :opacity="dimNode(n.id) ? 0.2 : 1"
              />
              <polygon
                :points="hexPoints(radius(n))"
                :fill="nodeFill(n)"
                :stroke="n.id === selected?.id ? '#111827' : '#1f2937'"
                :stroke-width="n.id === selected?.id ? 3 : 1"
                :opacity="dimNode(n.id) ? 0.2 : 1"
              />
              <text
                :y="radius(n) + (n.is_terminator ? 18 : 13)" text-anchor="middle"
                class="fill-neutral-700 dark:fill-neutral-300"
                style="font-size: 10px; pointer-events: none;"
                :opacity="dimNode(n.id) ? 0.2 : 1"
              >{{ shortName(n) }}</text>
            </g>
          </svg>

          <!-- Tooltip -->
          <div
            v-if="hoveredNode"
            class="absolute pointer-events-none bg-neutral-900 text-white text-xs rounded px-2 py-1 shadow-lg"
            style="top: 8px; left: 8px; max-width: 260px;"
          >
            <div class="font-semibold">{{ hoveredNode.hostname }}</div>
            <div class="text-neutral-300">
              {{ hoveredNode.role }} · {{ hoveredNode.firmware_version }}
              <template v-if="hoveredNode.wifi_clients !== null">
                · {{ (hoveredNode.wifi_clients ?? 0) + (hoveredNode.guest_clients ?? 0) }} {{ $t('meshGraph.tooltip.clients') }}
              </template>
            </div>
          </div>
        </div>

        <!-- Side panel: legend + selection -->
        <div class="space-y-4">
          <div class="card p-4 space-y-2">
            <h3 class="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-1">{{ $t('meshGraph.legend.title') }}</h3>
            <div class="flex items-center gap-2 text-xs text-neutral-600 dark:text-neutral-400">
              <svg width="18" height="18" viewBox="-9 -9 18 18"><polygon :points="hexPoints(7)" fill="#4E4EC8" stroke="#1f2937" stroke-width="1" /></svg>
              {{ $t('meshGraph.legend.bumblebee') }}
            </div>
            <div class="flex items-center gap-2 text-xs text-neutral-600 dark:text-neutral-400">
              <svg width="18" height="18" viewBox="-9 -9 18 18"><polygon :points="hexPoints(5)" fill="#4E4EC8" stroke="#1f2937" stroke-width="1" /></svg>
              {{ $t('meshGraph.legend.bee') }}
            </div>
            <div class="flex items-center gap-2 text-xs text-neutral-600 dark:text-neutral-400">
              <svg width="18" height="18" viewBox="-9 -9 18 18"><polygon :points="hexPoints(6)" fill="none" stroke="#FFE216" stroke-width="2.5" /></svg>
              {{ $t('meshGraph.legend.terminator') }}
            </div>
            <div class="flex items-center gap-2 text-xs text-neutral-600 dark:text-neutral-400">
              <svg width="18" height="18" viewBox="-9 -9 18 18"><polygon :points="hexPoints(6)" fill="#a3a3a3" stroke="#1f2937" stroke-width="1" /></svg>
              {{ $t('meshGraph.legend.stale') }}
            </div>
            <div class="border-t border-neutral-200 dark:border-neutral-700 my-2" />
            <div v-for="tier in TP_TIERS" :key="tier.label" class="flex items-center gap-2 text-xs text-neutral-600 dark:text-neutral-400">
              <svg width="22" height="8"><line x1="0" y1="4" x2="22" y2="4" :stroke="tier.color" :stroke-width="tier.legendWidth" /></svg>
              {{ tier.label }}
            </div>
            <div class="flex items-center gap-2 text-xs text-neutral-600 dark:text-neutral-400">
              <svg width="22" height="8"><line x1="0" y1="4" x2="22" y2="4" stroke="#cbd5e1" stroke-width="1.5" stroke-dasharray="4 4" /></svg>
              {{ $t('meshGraph.legend.inferred') }}
            </div>
          </div>

          <div v-if="selected" class="card p-4 space-y-2">
            <div class="flex items-center justify-between">
              <h3 class="text-sm font-semibold text-neutral-900 dark:text-neutral-100 truncate">{{ selected.hostname }}</h3>
              <button class="text-neutral-400 hover:text-neutral-700" @click="selected = null"><X class="w-4 h-4" /></button>
            </div>
            <UiBadge v-if="selected.is_terminator" variant="primary" type="soft" size="sm">
              {{ $t('meshGraph.detail.terminator') }}
            </UiBadge>
            <dl class="text-xs space-y-1 text-neutral-600 dark:text-neutral-400">
              <div class="flex justify-between"><dt>{{ $t('meshGraph.detail.role') }}</dt><dd>{{ selected.role }}</dd></div>
              <div class="flex justify-between"><dt>{{ $t('meshGraph.detail.firmware') }}</dt><dd class="font-mono">{{ selected.firmware_version }}</dd></div>
              <div class="flex justify-between"><dt>{{ $t('meshGraph.detail.vpn') }}</dt><dd>{{ selected.vpn_mode }}</dd></div>
              <div class="flex justify-between"><dt>{{ $t('meshGraph.detail.uptime') }}</dt><dd>{{ formatUptime(selected.uptime) }}</dd></div>
              <div class="flex justify-between"><dt>{{ $t('meshGraph.detail.lastSeen') }}</dt><dd>{{ selected.last_seen ? new Date(selected.last_seen).toLocaleString() : '—' }}</dd></div>
              <div class="flex justify-between"><dt>{{ $t('meshGraph.detail.island') }}</dt><dd class="font-mono">#{{ selected.island + 1 }}</dd></div>
              <div v-if="selected.wifi_clients !== null" class="flex justify-between">
                <dt>{{ $t('meshGraph.detail.wifiClients') }}</dt><dd class="font-mono">{{ selected.wifi_clients }}</dd>
              </div>
              <div v-if="selected.guest_clients !== null" class="flex justify-between">
                <dt>{{ $t('meshGraph.detail.guestClients') }}</dt><dd class="font-mono">{{ selected.guest_clients }}</dd>
              </div>
            </dl>
            <div v-if="selectedLinks.length" class="pt-1">
              <div class="text-xs font-semibold text-neutral-700 dark:text-neutral-300 mb-1">{{ $t('meshGraph.detail.links') }}</div>
              <div v-for="sl in selectedLinks" :key="sl.otherId" class="flex justify-between text-xs text-neutral-600 dark:text-neutral-400">
                <span class="truncate">{{ sl.name }}</span>
                <span class="font-mono">{{ sl.inferred ? '~' : formatTp(sl.tp) }}</span>
              </div>
            </div>
            <NuxtLink :to="localePath('/iot')" class="btn-sm btn-outline w-full mt-1">
              {{ $t('meshGraph.detail.openDevice') }}
            </NuxtLink>
          </div>
          <p v-else class="text-xs text-neutral-400 text-center px-2">{{ $t('meshGraph.hint') }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ShieldAlert, Network, RefreshCw, Play, X } from 'lucide-vue-next'
import type { SimNode } from '~/composables/useForceGraph'

definePageMeta({ middleware: 'auth' })

const { t } = useI18n()
const localePath = useLocalePath()
const authStore = useAuthStore()
const isStaff = computed(() => authStore.user?.is_staff ?? false)

interface MNode {
  id: string; mac: string; hostname: string; name: string; role: string
  firmware_version: string; vpn_mode: string; fresh: boolean
  last_seen: string | null; uptime: number; island: number
  is_terminator: boolean; reports_links: boolean
  wifi_clients: number | null; guest_clients: number | null
}
interface MEdge { source: string; target: string; tp_ab: number | null; tp_ba: number | null; inferred: boolean }
interface GraphData { nodes: MNode[]; edges: MEdge[]; islands: number; fresh_nodes: number }

type MeshSimNode = SimNode<MNode>

const { W, H, nodes, nodeById, svgEl, setGraph, reheat, onPointerDown, onPointerMove, onPointerUp } =
  useForceGraph<MNode>({ linkLen: 150 })

const loading = ref(false)
const error = ref('')
const data = ref<GraphData | null>(null)
const hovered = ref<string | null>(null)
const selected = ref<MeshSimNode | null>(null)

const hoveredNode = computed(() => (hovered.value ? nodeById.value.get(hovered.value) ?? null : null))

const directCount = computed(() => data.value?.edges.filter(e => !e.inferred).length ?? 0)
const inferredCount = computed(() => data.value?.edges.filter(e => e.inferred).length ?? 0)

// ── Rendering helpers ────────────────────────────────────────────────
function radius(n: MNode): number {
  return n.role === 'bumblebee' ? 15 : 11
}
function hexPoints(r: number): string {
  // flat-top hexagon (map-marker device grammar)
  const pts: string[] = []
  for (let i = 0; i < 6; i++) {
    const a = (Math.PI / 3) * i + Math.PI / 6
    pts.push(`${(r * Math.cos(a)).toFixed(2)},${(r * Math.sin(a)).toFixed(2)}`)
  }
  return pts.join(' ')
}
function nodeFill(n: MNode): string {
  return n.fresh ? '#4E4EC8' : '#a3a3a3'
}
function shortName(n: MNode): string {
  return n.hostname.replace(/^Parahub-/, '')
}
function formatTp(tp: number | null): string {
  if (tp === null) return ''
  return tp >= 100 ? `${Math.round(tp)}M` : `${tp.toFixed(1)}M`
}
function formatUptime(s: number): string {
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600)
  return d > 0 ? `${d}d ${h}h` : `${h}h ${Math.floor((s % 3600) / 60)}m`
}

// Link-quality tiers: color says whether a hop is healthy at a glance
const TP_TIERS = [
  { min: 200, color: '#059669', legendWidth: 3.5, label: '≥200 Mbit/s' },
  { min: 50, color: '#0ea5e9', legendWidth: 2.5, label: '50–200 Mbit/s' },
  { min: 5, color: '#D97706', legendWidth: 2, label: '5–50 Mbit/s' },
  { min: 0, color: '#DC2626', legendWidth: 1.5, label: '<5 Mbit/s' },
]
function tpTier(tp: number) {
  return TP_TIERS.find(t2 => tp >= t2.min) ?? TP_TIERS[TP_TIERS.length - 1]
}

// ── Edge geometry ────────────────────────────────────────────────────
const renderLinks = computed(() => {
  if (!data.value) return [] as Array<{
    x1: number; y1: number; x2: number; y2: number
    color: string; width: number; tp: number | null; inferred: boolean
    sourceId: string; targetId: string
  }>
  const out = []
  for (const e of data.value.edges) {
    const s = nodeById.value.get(e.source)
    const tn = nodeById.value.get(e.target)
    if (!s || !tn) continue
    const dx = tn.x - s.x, dy = tn.y - s.y
    const len = Math.hypot(dx, dy) || 1
    const ux = dx / len, uy = dy / len
    const r1 = radius(s) + 2, r2 = radius(tn) + 2
    const tp = e.inferred ? null : Math.max(e.tp_ab ?? 0, e.tp_ba ?? 0)
    const tier = tp === null ? null : tpTier(tp)
    out.push({
      x1: s.x + ux * r1, y1: s.y + uy * r1,
      x2: tn.x - ux * r2, y2: tn.y - uy * r2,
      color: tier ? tier.color : '#cbd5e1',
      width: tier ? 1.5 + Math.min(3, Math.sqrt(tp!) / 9) : 1.5,
      tp, inferred: e.inferred,
      sourceId: e.source, targetId: e.target,
    })
  }
  return out
})

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
function dimmed(s: string, t2: string): boolean {
  return !!neighborIds.value && !(neighborIds.value.has(s) && neighborIds.value.has(t2))
}
function edgeHighlighted(l: { sourceId: string; targetId: string }): boolean {
  const f = focusId.value
  return !!f && (l.sourceId === f || l.targetId === f)
}

// Selected node's radio links for the side panel
const selectedLinks = computed(() => {
  const sel = selected.value
  if (!sel || !data.value) return []
  const out: Array<{ otherId: string; name: string; tp: number | null; inferred: boolean }> = []
  for (const e of data.value.edges) {
    const otherId = e.source === sel.id ? e.target : (e.target === sel.id ? e.source : null)
    if (!otherId) continue
    const other = nodeById.value.get(otherId)
    if (!other) continue
    out.push({
      otherId,
      name: shortName(other),
      tp: e.inferred ? null : Math.max(e.tp_ab ?? 0, e.tp_ba ?? 0),
      inferred: e.inferred,
    })
  }
  return out.sort((a, b) => (b.tp ?? -1) - (a.tp ?? -1))
})

// ── Load ─────────────────────────────────────────────────────────────
async function reload() {
  loading.value = true
  error.value = ''
  try {
    await authStore.ensureToken()
    const res = await $fetch<GraphData>('/api/v1/iot/mesh/graph', {
      credentials: 'include',
      headers: authStore.token ? { Authorization: `Bearer ${authStore.token}` } : {},
    })
    data.value = res
    setGraph(res.nodes, res.edges)
    selected.value = null
  } catch (e: any) {
    error.value = e?.data?.detail || e?.message || t('meshGraph.loadError')
  } finally {
    loading.value = false
  }
}

onMounted(() => { if (isStaff.value) reload() })
</script>

<style scoped>
.graph-icon {
  display: flex; align-items: center; justify-content: center;
  width: 2.5rem; height: 2.5rem; border-radius: 0.75rem;
}
.dark .graph-canvas { --graph-bg: #18181b; }
</style>
