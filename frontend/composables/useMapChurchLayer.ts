/**
 * Churches map layer.
 * Public, no auth required.
 */

import { createToggleableDataLayer, roundedSquarePath } from '~/composables/useMapToggleableLayer'

// Cross on rounded square — warm rose (#9f1239)
function ensureChurchIcon(map: any) {
  if (map.hasImage('church-marker')) return
  const s = 40
  const canvas = document.createElement('canvas')
  canvas.width = s
  canvas.height = s
  const ctx = canvas.getContext('2d')!

  roundedSquarePath(ctx, s, 3)
  ctx.fillStyle = '#9f1239'
  ctx.fill()

  // White cross
  ctx.fillStyle = '#ffffff'
  const cx = s / 2
  ctx.fillRect(cx - 2, 8, 4, 24) // vertical bar
  ctx.fillRect(cx - 8, 14, 16, 4) // horizontal bar

  map.addImage('church-marker', { width: s, height: s, data: ctx.getImageData(0, 0, s, s).data }, { pixelRatio: 2 })
}

export function useMapChurchLayer() {
  return createToggleableDataLayer({
    tag: 'ChurchLayer',
    prefKey: 'church_layer_enabled',
    source: 'churches',
    iconLayerId: 'churches-icon',
    labelLayerId: 'churches-label',
    fetchItems: () => $fetch<any[]>('/api/v1/geo/establishments/church-map/'),
    toFeature: (p: any) => ({
      type: 'Feature' as const,
      properties: {
        id: p.id,
        name: p.name,
        slug: p.slug || '',
        denomination: p.denomination || '',
      },
      geometry: { type: 'Point' as const, coordinates: [p.longitude, p.latitude] },
    }),
    ensureIcons: ensureChurchIcon,
    iconImage: 'church-marker',
    iconMinzoom: 12,
    labelMinzoom: 14,
    labelTextSize: 10,
  })
}
