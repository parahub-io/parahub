/**
 * Public mesh network map layer.
 * Shows all mesh routers with WiFi icons.
 * No auth required — fetches from public endpoint.
 */

import { createToggleableDataLayer, roundedSquarePath } from '~/composables/useMapToggleableLayer'

// WiFi arcs on rounded square; online = blue-600, offline = grey-500
function ensureWifiIcon(map: any, id: string, fill: string) {
  if (map.hasImage(id)) return
  const s = 40 // 2x for retina
  const r = s / 2
  const canvas = document.createElement('canvas')
  canvas.width = s
  canvas.height = s
  const ctx = canvas.getContext('2d')!

  roundedSquarePath(ctx, s, 3)
  ctx.fillStyle = fill
  ctx.fill()

  // WiFi arcs (white)
  ctx.strokeStyle = '#ffffff'
  ctx.lineCap = 'round'
  const cx = r
  const cy = r + 2
  for (const arcR of [5, 9, 13]) {
    ctx.lineWidth = 2.2
    ctx.beginPath()
    ctx.arc(cx, cy, arcR, -Math.PI * 0.75, -Math.PI * 0.25)
    ctx.stroke()
  }

  // Center dot
  ctx.fillStyle = '#ffffff'
  ctx.beginPath()
  ctx.arc(cx, cy, 2, 0, Math.PI * 2)
  ctx.fill()

  map.addImage(id, { width: s, height: s, data: ctx.getImageData(0, 0, s, s).data }, { pixelRatio: 2 })
}

export function useMapMeshLayer() {
  return createToggleableDataLayer({
    tag: 'MeshLayer',
    prefKey: 'mesh_layer_enabled',
    defaultEnabled: true,
    source: 'mesh-public',
    iconLayerId: 'mesh-public-icon',
    labelLayerId: 'mesh-public-label',
    fetchItems: () => $fetch<any[]>('/api/v1/iot/mesh/public-positions'),
    toFeature: (p: any) => ({
      type: 'Feature' as const,
      properties: {
        name: p.name,
        hardware_profile: p.hardware_profile || 'unknown',
        status: p.status || 'offline',
      },
      geometry: { type: 'Point' as const, coordinates: [p.longitude, p.latitude] },
    }),
    ensureIcons: (map: any) => {
      ensureWifiIcon(map, 'mesh-wifi-online', '#2563eb')
      ensureWifiIcon(map, 'mesh-wifi-offline', '#6b7280')
    },
    iconImage: [
      'case',
      ['any', ['==', ['get', 'status'], 'online'], ['==', ['get', 'status'], 'recent']],
      'mesh-wifi-online',
      'mesh-wifi-offline',
    ],
    refreshMs: 60000,
    hoverHex: true,
  })
}
