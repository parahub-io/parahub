/**
 * Map layer for condominium buildings.
 * Shows building markers on the map, with toggle and click interaction.
 */

import { ref } from 'vue'

export function useMapCondoLayers() {
  const mapStore = useMapStore()

  const condosEnabled = useLocalPref('condos_enabled', false)
  const condosList = ref<any[]>([])
  let condosLoaded = false

  // ======== Data Loading ========

  const loadCondos = async (): Promise<any[]> => {
    try {
      const data = await $fetch<any[]>('/api/v1/geo/condominiums/map/')
      condosList.value = data || []
      return condosList.value
    } catch (e) {
      console.warn('[CondoLayers] Failed to fetch condominiums:', e)
      return []
    }
  }

  // ======== Canvas Icon ========

  const _ensureCondoIcon = (map: any, id: string, fill: string, size = 20) => {
    if (map.hasImage(id)) return
    const s = size * 2 // 2x for retina
    const r = s / 2
    const canvas = document.createElement('canvas')
    canvas.width = s
    canvas.height = s
    const ctx = canvas.getContext('2d')!

    // Rounded square with building silhouette
    const pad = 4
    const cr = 6 // corner radius
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

    // Building silhouette (white)
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

  // ======== Map Layers ========

  const addCondoLayers = async (map: any) => {
    const condos = await loadCondos()
    condosLoaded = true

    const geojson = {
      type: 'FeatureCollection' as const,
      features: condos.map((c: any) => ({
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
      })),
    }

    if (map.getSource('condos')) {
      ;(map.getSource('condos') as any).setData(geojson)
      return
    }

    _ensureCondoIcon(map, 'condo-icon', '#7c3aed') // purple-600

    map.addSource('condos', { type: 'geojson', data: geojson })

    map.addLayer({
      id: 'condos-circle',
      type: 'symbol',
      source: 'condos',
      layout: {
        'icon-image': 'condo-icon',
        'icon-allow-overlap': true,
        visibility: condosEnabled.value ? 'visible' : 'none',
      },
    })

    map.addLayer({
      id: 'condos-label',
      type: 'symbol',
      source: 'condos',
      layout: {
        'text-field': ['get', 'name'],
        'text-size': 11,
        'text-offset': [0, 1.5],
        'text-anchor': 'top',
        'text-optional': true,
        visibility: condosEnabled.value ? 'visible' : 'none',
      },
      paint: {
        'text-color': '#374151',
        'text-halo-color': '#ffffff',
        'text-halo-width': 1.5,
      },
    })
  }

  // ======== Setup (called from MapView on map load) ========

  const setupLayers = (map: any) => {
    if (condosEnabled.value) {
      addCondoLayers(map)
    }
  }

  /** Re-add layers after style change (no data reload). */
  const setupLayersOnly = (map: any) => {
    if (!condosLoaded || condosList.value.length === 0) return
    const geojson = {
      type: 'FeatureCollection' as const,
      features: condosList.value.map((c: any) => ({
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
      })),
    }

    if (!map.getSource('condos')) {
      _ensureCondoIcon(map, 'condo-icon', '#7c3aed')
      map.addSource('condos', { type: 'geojson', data: geojson })
    }

    if (!map.getLayer('condos-circle')) {
      map.addLayer({
        id: 'condos-circle',
        type: 'symbol',
        source: 'condos',
        layout: {
          'icon-image': 'condo-icon',
          'icon-allow-overlap': true,
          visibility: condosEnabled.value ? 'visible' : 'none',
        },
      })
    }

    if (!map.getLayer('condos-label')) {
      map.addLayer({
        id: 'condos-label',
        type: 'symbol',
        source: 'condos',
        layout: {
          'text-field': ['get', 'name'],
          'text-size': 11,
          'text-offset': [0, 1.5],
          'text-anchor': 'top',
          'text-optional': true,
          visibility: condosEnabled.value ? 'visible' : 'none',
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

  const toggleCondos = () => {
    condosEnabled.value = !condosEnabled.value
    const map = mapStore.mapInstance
    if (!map) return

    if (condosEnabled.value && !condosLoaded) {
      addCondoLayers(map)
      return
    }

    const vis = condosEnabled.value ? 'visible' : 'none'
    if (map.getLayer('condos-circle')) map.setLayoutProperty('condos-circle', 'visibility', vis)
    if (map.getLayer('condos-label')) map.setLayoutProperty('condos-label', 'visibility', vis)
  }

  return {
    condosEnabled,
    condosList,
    setupLayers,
    setupLayersOnly,
    toggleCondos,
  }
}
