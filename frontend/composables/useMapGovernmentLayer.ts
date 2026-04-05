/**
 * Government establishments map layer (juntas de freguesia, etc).
 * Public, no auth required.
 */

import { ref } from 'vue'

export function useMapGovernmentLayer() {
  const mapStore = useMapStore()

  const governmentEnabled = useLocalPref('government_layer_enabled', false)
  const governmentList = ref<any[]>([])
  let governmentLoaded = false

  // ======== Data Loading ========

  const loadPositions = async (): Promise<any[]> => {
    try {
      const data = await $fetch<any[]>('/api/v1/geo/establishments/government-map/')
      governmentList.value = data || []
      return governmentList.value
    } catch (e) {
      console.warn('[GovernmentLayer] Failed to fetch:', e)
      return []
    }
  }

  // ======== Canvas Icon — flag/building with columns ========

  const _ensureGovIcon = (map: any) => {
    if (map.hasImage('gov-marker')) return
    const s = 40 // 2x for retina
    const canvas = document.createElement('canvas')
    canvas.width = s
    canvas.height = s
    const ctx = canvas.getContext('2d')!

    // Rounded square background — warm amber (#d97706)
    const pad = 3
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
    ctx.fillStyle = '#d97706'
    ctx.fill()

    // Classical building silhouette (white) — triangle roof + columns
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

  // ======== GeoJSON ========

  const _buildGeoJSON = (items: any[]) => ({
    type: 'FeatureCollection' as const,
    features: items.map((p: any) => ({
      type: 'Feature' as const,
      properties: {
        id: p.id,
        name: p.name,
        slug: p.slug || '',
        category_slug: p.category_slug || '',
      },
      geometry: { type: 'Point' as const, coordinates: [p.longitude, p.latitude] },
    })),
  })

  // ======== Map Layers ========

  const addLayers = async (map: any) => {
    const items = await loadPositions()
    governmentLoaded = true

    const geojson = _buildGeoJSON(items)

    if (map.getSource('government')) {
      ;(map.getSource('government') as any).setData(geojson)
      return
    }

    _ensureGovIcon(map)
    map.addSource('government', { type: 'geojson', data: geojson })

    const vis = governmentEnabled.value ? 'visible' : 'none'

    map.addLayer({
      id: 'government-icon',
      type: 'symbol',
      source: 'government',
      minzoom: 9,
      layout: {
        'icon-image': 'gov-marker',
        'icon-allow-overlap': true,
        visibility: vis,
      },
    })

    map.addLayer({
      id: 'government-label',
      type: 'symbol',
      source: 'government',
      minzoom: 9,
      layout: {
        'text-field': ['get', 'name'],
        'text-size': 11,
        'text-offset': [0, 1.5],
        'text-anchor': 'top',
        'text-optional': true,
        visibility: vis,
      },
      paint: {
        'text-color': '#374151',
        'text-halo-color': '#ffffff',
        'text-halo-width': 1.5,
      },
    })
  }

  // ======== Setup ========

  const setupLayers = (map: any, onReady?: () => void) => {
    if (governmentEnabled.value) {
      addLayers(map).then(() => onReady?.())
    }
  }

  const setupLayersOnly = (map: any) => {
    if (!governmentLoaded || governmentList.value.length === 0) return
    const geojson = _buildGeoJSON(governmentList.value)

    if (!map.getSource('government')) {
      _ensureGovIcon(map)
      map.addSource('government', { type: 'geojson', data: geojson })
    }

    const vis = governmentEnabled.value ? 'visible' : 'none'

    if (!map.getLayer('government-icon')) {
      map.addLayer({
        id: 'government-icon', type: 'symbol', source: 'government', minzoom: 9,
        layout: { 'icon-image': 'gov-marker', 'icon-allow-overlap': true, visibility: vis },
      })
    }
    if (!map.getLayer('government-label')) {
      map.addLayer({
        id: 'government-label', type: 'symbol', source: 'government', minzoom: 9,
        layout: { 'text-field': ['get', 'name'], 'text-size': 11, 'text-offset': [0, 1.5], 'text-anchor': 'top', 'text-optional': true, visibility: vis },
        paint: { 'text-color': '#374151', 'text-halo-color': '#ffffff', 'text-halo-width': 1.5 },
      })
    }
  }

  // ======== Toggle ========

  const toggleGovernment = () => {
    governmentEnabled.value = !governmentEnabled.value
    const map = mapStore.mapInstance
    if (!map) return

    if (governmentEnabled.value && !governmentLoaded) {
      addLayers(map)
      return
    }

    const vis = governmentEnabled.value ? 'visible' : 'none'
    for (const id of ['government-icon', 'government-label']) {
      if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', vis)
    }
  }

  return {
    governmentEnabled,
    governmentList,
    setupLayers,
    setupLayersOnly,
    toggleGovernment,
  }
}
