/**
 * Map layer for condominium buildings.
 * Shows building markers on the map, with toggle and click interaction.
 */

import { createToggleableDataLayer, roundedSquarePath } from '~/composables/useMapToggleableLayer'

// Building silhouette with windows on rounded square — purple-600
function ensureCondoIcon(map: any) {
  const id = 'condo-icon'
  const fill = '#7c3aed'
  if (map.hasImage(id)) return
  const s = 40 // 2x for retina
  const r = s / 2
  const canvas = document.createElement('canvas')
  canvas.width = s
  canvas.height = s
  const ctx = canvas.getContext('2d')!

  roundedSquarePath(ctx, s, 4)
  ctx.fillStyle = fill
  ctx.fill()

  // Building silhouette (white)
  const pad = 4
  ctx.fillStyle = '#ffffff'
  const bx = r - 7, by = pad + 8, bw = 14, bh = s - pad * 2 - 8
  ctx.fillRect(bx, by, bw, bh)
  // Windows
  ctx.fillStyle = fill
  for (let row = 0; row < 3; row++) {
    for (let col = 0; col < 2; col++) {
      ctx.fillRect(bx + 2 + col * 7, by + 2 + row * 5, 4, 3)
    }
  }

  map.addImage(id, { width: s, height: s, data: ctx.getImageData(0, 0, s, s).data }, { pixelRatio: 2 })
}

export function useMapCondoLayers() {
  return createToggleableDataLayer({
    tag: 'CondoLayers',
    prefKey: 'condos_enabled',
    source: 'condos',
    iconLayerId: 'condos-circle',
    labelLayerId: 'condos-label',
    fetchItems: () => $fetch<any[]>('/api/v1/geo/condominiums/map/'),
    toFeature: (c: any) => ({
      type: 'Feature' as const,
      properties: {
        id: c.id,
        name: c.name,
        slug: c.slug || '',
        full_address: c.full_address || '',
        fraction_count: c.fraction_count || 0,
        member_count: c.member_count || 0,
      },
      geometry: { type: 'Point' as const, coordinates: [c.longitude, c.latitude] },
    }),
    ensureIcons: ensureCondoIcon,
    iconImage: 'condo-icon',
  })
}
