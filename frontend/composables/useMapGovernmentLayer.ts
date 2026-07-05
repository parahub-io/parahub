/**
 * Government establishments map layer (juntas de freguesia, etc).
 * Public, no auth required.
 */

import { createToggleableDataLayer, roundedSquarePath } from '~/composables/useMapToggleableLayer'

// Classical building (roof + columns) on rounded square — warm amber (#d97706)
function ensureGovIcon(map: any) {
  if (map.hasImage('gov-marker')) return
  const s = 40 // 2x for retina
  const canvas = document.createElement('canvas')
  canvas.width = s
  canvas.height = s
  const ctx = canvas.getContext('2d')!

  roundedSquarePath(ctx, s, 3)
  ctx.fillStyle = '#d97706'
  ctx.fill()

  ctx.strokeStyle = '#ffffff'
  ctx.fillStyle = '#ffffff'
  ctx.lineWidth = 1.5
  const cx = s / 2

  // Roof triangle
  ctx.beginPath()
  ctx.moveTo(cx, 8)
  ctx.lineTo(cx + 12, 17)
  ctx.lineTo(cx - 12, 17)
  ctx.closePath()
  ctx.fill()

  // Four columns
  const colW = 2
  const colTop = 18
  const colBot = 30
  for (const x of [cx - 9, cx - 3, cx + 3, cx + 9]) {
    ctx.fillRect(x - colW / 2, colTop, colW, colBot - colTop)
  }

  // Base
  ctx.fillRect(cx - 12, colBot, 24, 3)

  map.addImage('gov-marker', { width: s, height: s, data: ctx.getImageData(0, 0, s, s).data }, { pixelRatio: 2 })
}

export function useMapGovernmentLayer() {
  return createToggleableDataLayer({
    tag: 'GovernmentLayer',
    prefKey: 'government_layer_enabled',
    source: 'government',
    iconLayerId: 'government-icon',
    labelLayerId: 'government-label',
    fetchItems: () => $fetch<any[]>('/api/v1/geo/establishments/government-map/'),
    toFeature: (p: any) => ({
      type: 'Feature' as const,
      properties: {
        id: p.id,
        name: p.name,
        slug: p.slug || '',
        category_slug: p.category_slug || '',
      },
      geometry: { type: 'Point' as const, coordinates: [p.longitude, p.latitude] },
    }),
    ensureIcons: ensureGovIcon,
    iconImage: 'gov-marker',
    iconMinzoom: 9,
    labelMinzoom: 9,
  })
}
