/**
 * Public mesh network map layer.
 * Shows all mesh routers with WiFi icons.
 * No auth required — fetches from public endpoint.
 */

import {
  createToggleableDataLayer, DEVICE_HEX_SIZE, DEVICE_MINZOOM, DEVICE_LABEL_MINZOOM,
  hexagonPath, strokeMarkerOutline,
} from '~/composables/useMapToggleableLayer'

/** WiFi arcs + center dot on an s×s (2x) marker canvas — the mesh-router glyph. */
export function drawWifiGlyph(ctx: CanvasRenderingContext2D, s: number, color = '#ffffff') {
  const r = s / 2
  ctx.strokeStyle = color
  ctx.lineCap = 'round'
  const cx = r
  const cy = r + 3
  for (const arcR of [5, 9.5, 14]) {
    ctx.lineWidth = 2.4
    ctx.beginPath()
    ctx.arc(cx, cy, arcR, -Math.PI * 0.75, -Math.PI * 0.25)
    ctx.stroke()
  }
  ctx.fillStyle = color
  ctx.beginPath()
  ctx.arc(cx, cy, 2.2, 0, Math.PI * 2)
  ctx.fill()
}

// WiFi arcs on the standard device hexagon; status fill per the marker grammar
// (PK/design-system.md § Map Markers): online indigo, recent/stale grey, offline red
function ensureWifiIcon(map: any, id: string, fill: string) {
  if (map.hasImage(id)) return
  const s = DEVICE_HEX_SIZE * 2 // 2x for retina
  const canvas = document.createElement('canvas')
  canvas.width = s
  canvas.height = s
  const ctx = canvas.getContext('2d')!

  hexagonPath(ctx, s)
  ctx.fillStyle = fill
  ctx.fill()
  strokeMarkerOutline(ctx)
  drawWifiGlyph(ctx, s)

  map.addImage(id, { width: s, height: s, data: ctx.getImageData(0, 0, s, s).data }, { pixelRatio: 2 })
}

/** Compact uptime for the HUD readout: 45M / 6H / 3D. */
function _uptimeShort(seconds: number): string {
  if (seconds < 3600) return `${Math.max(1, Math.round(seconds / 60))}M`
  if (seconds < 172800) return `${Math.round(seconds / 3600)}H`
  return `${Math.round(seconds / 86400)}D`
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
        device_id: p.device_id,
        name: p.name,
        hardware_profile: p.hardware_profile || 'unknown',
        status: p.status || 'offline',
        owner_name: p.owner_name || '',
        owner_cri: p.owner_cri || '',
      },
      geometry: { type: 'Point' as const, coordinates: [p.longitude, p.latitude] },
    }),
    ensureIcons: (map: any) => {
      ensureWifiIcon(map, 'mesh-wifi-online', '#4E4EC8')
      ensureWifiIcon(map, 'mesh-wifi-recent', '#a3a3a3')
      ensureWifiIcon(map, 'mesh-wifi-offline', '#ef4444')
    },
    iconImage: [
      'case',
      ['==', ['get', 'status'], 'online'], 'mesh-wifi-online',
      ['==', ['get', 'status'], 'recent'], 'mesh-wifi-recent',
      'mesh-wifi-offline',
    ],
    refreshMs: 60000,
    hoverHex: true,
    iconMinzoom: DEVICE_MINZOOM,
    labelMinzoom: DEVICE_LABEL_MINZOOM,
    // Routers are static devices — they compose with co-located env stations
    // and energy cells. A live router reads out its public heartbeat subset
    // (shared-wifi SSID + WLAN clients / mesh links / uptime) as an
    // instrument column that replaces the name label; offline routers keep
    // the plain hex + name.
    ensemble: {
      segment: 'mesh',
      toMember: (p: any) => ({
        id: p.device_id,
        lat: p.latitude,
        lon: p.longitude,
        role: 'infra' as const,
        hud: !!p.guest_ssid,
        // Co-located routers broadcast the same shared wifi — one column
        // represents the spot, the rest keep their name labels
        hudDedupeKey: 'wifi',
      }),
      hudView: (p: any) => {
        if (!p.guest_ssid) return null
        const rows: Array<[string, string]> = []
        if (p.wifi_clients != null) rows.push(['WLAN', String(p.wifi_clients)])
        if (p.mesh_links != null) rows.push(['LINKS', String(p.mesh_links)])
        if (p.uptime != null) rows.push(['UP', _uptimeShort(p.uptime)])
        // 'recent' (10–30 min since the last heartbeat) dims like a stale
        // env station — the counters are aging
        return { primary: p.guest_ssid, rows, windDir: null, stale: p.status !== 'online' }
      },
    },
  })
}
