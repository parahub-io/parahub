/**
 * Map layer for P-Hub logistics points.
 * Shows hub markers on the map with toggle and click interaction.
 */

import { createToggleableDataLayer, roundedSquarePath } from '~/composables/useMapToggleableLayer'

// Package/box silhouette on rounded square — orange-600
function ensureHubIcon(map: any) {
  const id = 'hub-icon'
  const fill = '#ea580c'
  if (map.hasImage(id)) return
  const s = 40 // 2x for retina
  const canvas = document.createElement('canvas')
  canvas.width = s
  canvas.height = s
  const ctx = canvas.getContext('2d')!

  roundedSquarePath(ctx, s, 4)
  ctx.fillStyle = fill
  ctx.fill()

  // Package/box silhouette (white)
  ctx.fillStyle = '#ffffff'
  const cx = s / 2, cy = s / 2
  const bw = 14, bh = 12
  // Box body
  ctx.fillRect(cx - bw / 2, cy - bh / 2 + 2, bw, bh)
  // Box lid (trapezoid top)
  ctx.beginPath()
  ctx.moveTo(cx - bw / 2 - 2, cy - bh / 2 + 2)
  ctx.lineTo(cx + bw / 2 + 2, cy - bh / 2 + 2)
  ctx.lineTo(cx + bw / 2, cy - bh / 2 - 2)
  ctx.lineTo(cx - bw / 2, cy - bh / 2 - 2)
  ctx.closePath()
  ctx.fill()
  // Box tape (center line)
  ctx.fillStyle = fill
  ctx.fillRect(cx - 1.5, cy - bh / 2 - 2, 3, bh + 4)

  map.addImage(id, { width: s, height: s, data: ctx.getImageData(0, 0, s, s).data }, { pixelRatio: 2 })
}

export function useMapHubLayers() {
  return createToggleableDataLayer({
    tag: 'HubLayers',
    prefKey: 'hubs_enabled',
    source: 'hubs',
    iconLayerId: 'hubs-circle',
    labelLayerId: 'hubs-label',
    fetchItems: async () => {
      const data = await $fetch<any>('/api/v1/shipments/hubs/')
      return data?.items || []
    },
    toFeature: (h: any) => {
      if (h.lat == null || h.lon == null) return null
      return {
        type: 'Feature' as const,
        properties: {
          id: h.id,
          name: h.name,
          slug: h.slug || '',
          hub_capacity: h.hub_capacity || 0,
          hub_accepted_sizes: (h.hub_accepted_sizes || []).join(', '),
          hub_storage_fee_daily: h.hub_storage_fee_daily || '0',
          opening_hours: h.opening_hours || '',
          phone: h.phone || '',
        },
        geometry: { type: 'Point' as const, coordinates: [h.lon, h.lat] },
      }
    },
    ensureIcons: ensureHubIcon,
    iconImage: 'hub-icon',
  })
}
