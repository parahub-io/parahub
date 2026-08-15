// Self-contained 2D force simulation for SVG graph pages (WoT graph, mesh graph).
// Owns physics, layout seeding and pointer-drag state; rendering, colors and
// edge semantics stay in the page. No external dependencies.

import type { Ref } from 'vue'

export type SimNode<T> = T & { x: number; y: number; vx: number; vy: number; fixed: boolean }

export interface ForceLink { source: string; target: string }

export interface ForceGraphOptions {
  width?: number
  height?: number
  linkLen?: number
  repulsion?: number
  spring?: number
  center?: number
  damp?: number
}

export function useForceGraph<T extends { id: string }>(opts: ForceGraphOptions = {}) {
  const W = opts.width ?? 900
  const H = opts.height ?? 620
  const REPULSION = opts.repulsion ?? 9000
  const SPRING = opts.spring ?? 0.04
  const LINK_LEN = opts.linkLen ?? 110
  const CENTER = opts.center ?? 0.02
  const DAMP = opts.damp ?? 0.85

  const nodes = ref([]) as Ref<SimNode<T>[]>
  const links = ref<ForceLink[]>([])
  const svgEl = ref<SVGSVGElement | null>(null)

  const nodeById = computed(() => {
    const m = new Map<string, SimNode<T>>()
    for (const n of nodes.value) m.set(n.id, n)
    return m
  })

  let alpha = 0
  let raf = 0
  let dragging: SimNode<T> | null = null

  function step() {
    const ns = nodes.value
    const n = ns.length
    // repulsion (O(n^2) — fine for staff tools on <1k nodes)
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
    // springs along links
    for (const e of links.value) {
      const a = nodeById.value.get(e.source), b = nodeById.value.get(e.target)
      if (!a || !b) continue
      const dx = b.x - a.x, dy = b.y - a.y
      const d = Math.hypot(dx, dy) || 1
      const f = ((d - LINK_LEN) * SPRING) * alpha
      const fx = (dx / d) * f, fy = (dy / d) * f
      a.vx += fx; a.vy += fy; b.vx -= fx; b.vy -= fy
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

  function setGraph(ns: T[], edges: ForceLink[]) {
    nodes.value = ns.map(n => ({ ...n, x: W / 2, y: H / 2, vx: 0, vy: 0, fixed: false })) as SimNode<T>[]
    links.value = edges.map(e => ({ source: e.source, target: e.target }))
    seedPositions()
    reheat()
  }

  function toSvg(ev: PointerEvent): { x: number; y: number } {
    const el = svgEl.value
    if (!el) return { x: 0, y: 0 }
    const r = el.getBoundingClientRect()
    return { x: ((ev.clientX - r.left) / r.width) * W, y: ((ev.clientY - r.top) / r.height) * H }
  }

  function onPointerDown(n: SimNode<T>, ev: PointerEvent) {
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

  onBeforeUnmount(() => { if (raf) cancelAnimationFrame(raf) })

  return { W, H, nodes, nodeById, svgEl, setGraph, reheat, onPointerDown, onPointerMove, onPointerUp }
}
