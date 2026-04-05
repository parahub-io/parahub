/**
 * Public mesh network map layer.
 * Shows all mesh routers with WiFi icons.
 * No auth required — fetches from public endpoint.
 */

import { ref } from 'vue'
import { attachHoverHex } from '~/composables/useMapHighlight'

export function useMapMeshLayer() {
  const mapStore = useMapStore()

  const meshEnabled = useLocalPref('mesh_layer_enabled', true)
  const meshList = ref<any[]>([])
  let meshLoaded = false
  let refreshInterval: ReturnType<typeof setInterval> | null = null

  // ======== Data Loading ========

  const loadMeshPositions = async (): Promise<any[]> => {
    try {
      const data = await $fetch<any[]>('/api/v1/iot/mesh/public-positions')
      meshList.value = data || []
      return meshList.value
    } catch (e) {
      console.warn('[MeshLayer] Failed to fetch mesh positions:', e)
      return []
    }
  }

  // ======== Canvas WiFi Icon ========

  const _ensureWifiIcon = (map: any, id: string, fill: string, size = 20) => {
    if (map.hasImage(id)) return
    const s = size * 2 // 2x for retina
    const r = s / 2
    const canvas = document.createElement('canvas')
    canvas.width = s
    canvas.height = s
    const ctx = canvas.getContext('2d')!

    // Rounded square background
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
    ctx.fillStyle = fill
    ctx.fill()

    // WiFi arcs (white)
    ctx.strokeStyle = '#ffffff'
    ctx.lineCap = 'round'
    const cx = r
    const cy = r + 2

    // Three arcs from small to large
    const arcs = [5, 9, 13]
    for (const arcR of arcs) {
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

  // ======== GeoJSON Builders ========

  const _buildPointGeoJSON = (positions: any[]) => ({
    type: 'FeatureCollection' as const,
    features: positions.map((p: any) => ({
      type: 'Feature' as const,
      properties: {
        name: p.name,
        hardware_profile: p.hardware_profile || 'unknown',
        status: p.status || 'offline',
      },
      geometry: { type: 'Point' as const, coordinates: [p.longitude, p.latitude] },
    })),
  })

  // ======== Map Layers ========

  const addMeshLayers = async (map: any) => {
    const positions = await loadMeshPositions()
    meshLoaded = true

    const pointGeoJSON = _buildPointGeoJSON(positions)

    if (map.getSource('mesh-public')) {
      ;(map.getSource('mesh-public') as any).setData(pointGeoJSON)
      return
    }

    map.addSource('mesh-public', { type: 'geojson', data: pointGeoJSON })

    const vis = meshEnabled.value ? 'visible' : 'none'

    // WiFi icons
    _ensureWifiIcon(map, 'mesh-wifi-online', '#2563eb')  // blue-600
    _ensureWifiIcon(map, 'mesh-wifi-offline', '#6b7280') // grey-500

    map.addLayer({
      id: 'mesh-public-icon',
      type: 'symbol',
      source: 'mesh-public',
      layout: {
        'icon-image': [
          'case',
          ['any', ['==', ['get', 'status'], 'online'], ['==', ['get', 'status'], 'recent']],
          'mesh-wifi-online',
          'mesh-wifi-offline',
        ],
        'icon-allow-overlap': true,
        visibility: vis,
      },
    })

    // Labels
    map.addLayer({
      id: 'mesh-public-label',
      type: 'symbol',
      source: 'mesh-public',
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

  // ======== Refresh ========

  const refreshMesh = async () => {
    const map = mapStore.mapInstance
    if (!map || !map.getSource('mesh-public')) return
    const positions = await loadMeshPositions()
    ;(map.getSource('mesh-public') as any).setData(_buildPointGeoJSON(positions))
  }

  // ======== Setup ========

  const setupLayers = (map: any) => {
    if (meshEnabled.value) {
      addMeshLayers(map)
      refreshInterval = setInterval(refreshMesh, 60000)
    }
  }

  const setupLayersOnly = (map: any) => {
    if (!meshLoaded || meshList.value.length === 0) return
    const pointGeoJSON = _buildPointGeoJSON(meshList.value)

    if (!map.getSource('mesh-public')) {
      map.addSource('mesh-public', { type: 'geojson', data: pointGeoJSON })
    }

    const vis = meshEnabled.value ? 'visible' : 'none'

    _ensureWifiIcon(map, 'mesh-wifi-online', '#2563eb')
    _ensureWifiIcon(map, 'mesh-wifi-offline', '#6b7280')

    if (!map.getLayer('mesh-public-icon')) {
      map.addLayer({
        id: 'mesh-public-icon', type: 'symbol', source: 'mesh-public',
        layout: {
          'icon-image': ['case', ['any', ['==', ['get', 'status'], 'online'], ['==', ['get', 'status'], 'recent']], 'mesh-wifi-online', 'mesh-wifi-offline'],
          'icon-allow-overlap': true, visibility: vis,
        },
      })
    }
    if (!map.getLayer('mesh-public-label')) {
      map.addLayer({
        id: 'mesh-public-label', type: 'symbol', source: 'mesh-public',
        layout: { 'text-field': ['get', 'name'], 'text-size': 11, 'text-offset': [0, 1.5], 'text-anchor': 'top', 'text-optional': true, visibility: vis },
        paint: { 'text-color': '#374151', 'text-halo-color': '#ffffff', 'text-halo-width': 1.5 },
      })
    }

    attachHoverHex(map, 'mesh-public-icon')
  }

  // ======== Toggle ========

  const toggleMesh = () => {
    meshEnabled.value = !meshEnabled.value
    const map = mapStore.mapInstance
    if (!map) return

    if (meshEnabled.value && !meshLoaded) {
      addMeshLayers(map)
      refreshInterval = setInterval(refreshMesh, 60000)
      return
    }

    const vis = meshEnabled.value ? 'visible' : 'none'
    for (const id of ['mesh-public-icon', 'mesh-public-label']) {
      if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', vis)
    }

    if (meshEnabled.value && !refreshInterval) {
      refreshInterval = setInterval(refreshMesh, 60000)
    } else if (!meshEnabled.value && refreshInterval) {
      clearInterval(refreshInterval)
      refreshInterval = null
    }
  }

  const pauseRefresh = () => {
    if (refreshInterval) { clearInterval(refreshInterval); refreshInterval = null }
  }

  const resumeRefresh = () => {
    if (meshEnabled.value && !refreshInterval) {
      refreshInterval = setInterval(refreshMesh, 60000)
      refreshMesh()
    }
  }

  return {
    meshEnabled,
    meshList,
    setupLayers,
    setupLayersOnly,
    toggleMesh,
    pauseRefresh,
    resumeRefresh,
  }
}
