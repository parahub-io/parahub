/**
 * Map layer for P-Hub logistics points.
 * Shows hub markers on the map with toggle and click interaction.
 */

import { ref } from 'vue'

export function useMapHubLayers() {
  const mapStore = useMapStore()

  const hubsEnabled = useLocalPref('hubs_enabled', false)
  const hubsList = ref<any[]>([])
  let hubsLoaded = false

  // ======== Data Loading ========

  const loadHubs = async (): Promise<any[]> => {
    try {
      const data = await $fetch<any>('/api/v1/shipments/hubs/')
      hubsList.value = data?.items || []
      return hubsList.value
    } catch (e) {
      console.warn('[HubLayers] Failed to fetch hubs:', e)
      return []
    }
  }

  // ======== Canvas Icon ========

  const _ensureHubIcon = (map: any, id: string, fill: string, size = 20) => {
    if (map.hasImage(id)) return
    const s = size * 2 // 2x for retina
    const canvas = document.createElement('canvas')
    canvas.width = s
    canvas.height = s
    const ctx = canvas.getContext('2d')!

    // Rounded square background
    const pad = 4
    const cr = 6
    ctx.beginPath()
    ctx.moveTo(pad + cr, pad)
    ctx.lineTo(s - pad - cr, pad)
    ctx.quadraticCurveTo(s - pad, pad, s - pad, pad + cr)
    ctx.lineTo(s - pad, s - pad - cr)
    ctx.quadraticCurveTo(s - pad, s - pad, s - pad - cr, s - pad)
    ctx.lineTo(pad + cr, s - pad)
    ctx.quadraticCurveTo(pad, s - pad, pad, s - pad - cr)
    ctx.lineTo(pad, pad + cr)
    ctx.quadraticCurveTo(pad, pad, pad + cr, pad)
    ctx.closePath()
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

  // ======== GeoJSON Builder ========

  const _buildGeoJSON = (hubs: any[]) => ({
    type: 'FeatureCollection' as const,
    features: hubs
      .filter((h: any) => h.lat != null && h.lon != null)
      .map((h: any) => ({
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
      })),
  })

  // ======== Map Layers ========

  const addHubLayers = async (map: any) => {
    const hubs = await loadHubs()
    hubsLoaded = true

    const geojson = _buildGeoJSON(hubs)

    if (map.getSource('hubs')) {
      ;(map.getSource('hubs') as any).setData(geojson)
      return
    }

    _ensureHubIcon(map, 'hub-icon', '#ea580c') // orange-600

    map.addSource('hubs', { type: 'geojson', data: geojson })

    map.addLayer({
      id: 'hubs-circle',
      type: 'symbol',
      source: 'hubs',
      layout: {
        'icon-image': 'hub-icon',
        'icon-allow-overlap': true,
        visibility: hubsEnabled.value ? 'visible' : 'none',
      },
    })

    map.addLayer({
      id: 'hubs-label',
      type: 'symbol',
      source: 'hubs',
      layout: {
        'text-field': ['get', 'name'],
        'text-size': 11,
        'text-offset': [0, 1.5],
        'text-anchor': 'top',
        'text-optional': true,
        visibility: hubsEnabled.value ? 'visible' : 'none',
      },
      paint: {
        'text-color': '#374151',
        'text-halo-color': '#ffffff',
        'text-halo-width': 1.5,
      },
    })
  }

  // ======== Setup ========

  const setupLayers = (map: any) => {
    if (hubsEnabled.value) {
      addHubLayers(map)
    }
  }

  /** Re-add layers after style change (no data reload). */
  const setupLayersOnly = (map: any) => {
    if (!hubsLoaded || hubsList.value.length === 0) return
    const geojson = _buildGeoJSON(hubsList.value)

    if (!map.getSource('hubs')) {
      _ensureHubIcon(map, 'hub-icon', '#ea580c')
      map.addSource('hubs', { type: 'geojson', data: geojson })
    }

    if (!map.getLayer('hubs-circle')) {
      map.addLayer({
        id: 'hubs-circle',
        type: 'symbol',
        source: 'hubs',
        layout: {
          'icon-image': 'hub-icon',
          'icon-allow-overlap': true,
          visibility: hubsEnabled.value ? 'visible' : 'none',
        },
      })
    }

    if (!map.getLayer('hubs-label')) {
      map.addLayer({
        id: 'hubs-label',
        type: 'symbol',
        source: 'hubs',
        layout: {
          'text-field': ['get', 'name'],
          'text-size': 11,
          'text-offset': [0, 1.5],
          'text-anchor': 'top',
          'text-optional': true,
          visibility: hubsEnabled.value ? 'visible' : 'none',
        },
        paint: {
          'text-color': '#374151',
          'text-halo-color': '#ffffff',
          'text-halo-width': 1.5,
        },
      })
    }
  }

  // ======== Toggle ========

  const toggleHubs = () => {
    hubsEnabled.value = !hubsEnabled.value
    const map = mapStore.mapInstance
    if (!map) return

    if (hubsEnabled.value && !hubsLoaded) {
      addHubLayers(map)
      return
    }

    const vis = hubsEnabled.value ? 'visible' : 'none'
    if (map.getLayer('hubs-circle')) map.setLayoutProperty('hubs-circle', 'visibility', vis)
    if (map.getLayer('hubs-label')) map.setLayoutProperty('hubs-label', 'visibility', vis)
  }

  return {
    hubsEnabled,
    hubsList,
    setupLayers,
    setupLayersOnly,
    toggleHubs,
  }
}
