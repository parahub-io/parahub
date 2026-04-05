/**
 * Churches map layer.
 * Public, no auth required.
 */

import { ref } from 'vue'

export function useMapChurchLayer() {
  const mapStore = useMapStore()

  const churchEnabled = useLocalPref('church_layer_enabled', false)
  const churchList = ref<any[]>([])
  let churchLoaded = false

  // ======== Data Loading ========

  const loadPositions = async (): Promise<any[]> => {
    try {
      const data = await $fetch<any[]>('/api/v1/geo/establishments/church-map/')
      churchList.value = data || []
      return churchList.value
    } catch (e) {
      console.warn('[ChurchLayer] Failed to fetch:', e)
      return []
    }
  }

  // ======== Canvas Icon — cross on rounded square ========

  const _ensureChurchIcon = (map: any) => {
    if (map.hasImage('church-marker')) return
    const s = 40
    const canvas = document.createElement('canvas')
    canvas.width = s
    canvas.height = s
    const ctx = canvas.getContext('2d')!

    // Rounded square background — warm rose (#9f1239)
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
    ctx.fillStyle = '#9f1239'
    ctx.fill()

    // White cross
    ctx.fillStyle = '#ffffff'
    const cx = s / 2
    const cy = s / 2
    // Vertical bar
    ctx.fillRect(cx - 2, 8, 4, 24)
    // Horizontal bar
    ctx.fillRect(cx - 8, 14, 16, 4)

    map.addImage('church-marker', { width: s, height: s, data: ctx.getImageData(0, 0, s, s).data }, { pixelRatio: 2 })
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
        denomination: p.denomination || '',
      },
      geometry: { type: 'Point' as const, coordinates: [p.longitude, p.latitude] },
    })),
  })

  // ======== Map Layers ========

  const addLayers = async (map: any) => {
    const items = await loadPositions()
    churchLoaded = true

    const geojson = _buildGeoJSON(items)

    if (map.getSource('churches')) {
      ;(map.getSource('churches') as any).setData(geojson)
      return
    }

    _ensureChurchIcon(map)
    map.addSource('churches', { type: 'geojson', data: geojson })

    const vis = churchEnabled.value ? 'visible' : 'none'

    map.addLayer({
      id: 'churches-icon',
      type: 'symbol',
      source: 'churches',
      layout: {
        'icon-image': 'church-marker',
        'icon-allow-overlap': true,
        visibility: vis,
      },
      minzoom: 12,
    })

    map.addLayer({
      id: 'churches-label',
      type: 'symbol',
      source: 'churches',
      layout: {
        'text-field': ['get', 'name'],
        'text-size': 10,
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
      minzoom: 14,
    })
  }

  // ======== Setup ========

  const setupLayers = (map: any, onReady?: () => void) => {
    if (churchEnabled.value) {
      addLayers(map).then(() => onReady?.())
    }
  }

  const setupLayersOnly = (map: any) => {
    if (!churchLoaded || churchList.value.length === 0) return
    const geojson = _buildGeoJSON(churchList.value)

    if (!map.getSource('churches')) {
      _ensureChurchIcon(map)
      map.addSource('churches', { type: 'geojson', data: geojson })
    }

    const vis = churchEnabled.value ? 'visible' : 'none'

    if (!map.getLayer('churches-icon')) {
      map.addLayer({
        id: 'churches-icon', type: 'symbol', source: 'churches',
        layout: { 'icon-image': 'church-marker', 'icon-allow-overlap': true, visibility: vis },
        minzoom: 12,
      })
    }
    if (!map.getLayer('churches-label')) {
      map.addLayer({
        id: 'churches-label', type: 'symbol', source: 'churches',
        layout: { 'text-field': ['get', 'name'], 'text-size': 10, 'text-offset': [0, 1.5], 'text-anchor': 'top', 'text-optional': true, visibility: vis },
        paint: { 'text-color': '#374151', 'text-halo-color': '#ffffff', 'text-halo-width': 1.5 },
        minzoom: 14,
      })
    }
  }

  // ======== Toggle ========

  const toggleChurches = () => {
    churchEnabled.value = !churchEnabled.value
    const map = mapStore.mapInstance
    if (!map) return

    if (churchEnabled.value && !churchLoaded) {
      addLayers(map)
      return
    }

    const vis = churchEnabled.value ? 'visible' : 'none'
    for (const id of ['churches-icon', 'churches-label']) {
      if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', vis)
    }
  }

  return {
    churchEnabled,
    churchList,
    setupLayers,
    setupLayersOnly,
    toggleChurches,
  }
}
