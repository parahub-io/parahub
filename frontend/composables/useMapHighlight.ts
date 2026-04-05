/**
 * Feature hover/active highlighting + interactive features + marker sync.
 *
 * Extracted from MapView.vue lines 482-487, 1688-1972.
 */

// Module-level hover/active state (survives composable re-calls)
let hoveredFeatureId: any = null
let hoveredFeatureSource: string | null = null
let hoveredFeatureSourceLayer: string | null = null
let activeFeatureId: any = null
let activeFeatureSource: string | null = null
let activeFeatureSourceLayer: string | null = null

// POI hex hover state
let poiHexVisible = false

// Track registered interactive layers to avoid duplicate event handlers
const registeredInteractiveLayers = new Set<string>()

// Markers management
const mapMarkers = new Map<string, any>()

/**
 * Attach hover hex highlight + pointer cursor to a map layer.
 * Reuses the shared `poi-hover-hex-src` source set up by useMapHighlight.
 */
export function attachHoverHex(map: any, layerId: string, iconSize = 1.2) {
  map.on('mouseenter', layerId, (e: any) => {
    map.getCanvas().style.cursor = 'pointer'
    map.setLayoutProperty('poi-hover-hex-layer', 'icon-size', iconSize)
    const coords = e.features?.[0]?.geometry?.coordinates
    const src = map.getSource('poi-hover-hex-src')
    if (src && coords) {
      src.setData({
        type: 'FeatureCollection',
        features: [{ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: coords } }],
      })
    }
  })
  map.on('mouseleave', layerId, () => {
    map.getCanvas().style.cursor = ''
    const src = map.getSource('poi-hover-hex-src')
    if (src) src.setData({ type: 'FeatureCollection', features: [] })
  })
}

export function useMapHighlight() {
  /**
   * Create a flat-top hexagon image for the POI hover indicator.
   */
  function _ensurePoiHexImage(map: any) {
    if (map.hasImage('poi-hover-hex')) return
    const s = 64
    const r = s / 2
    const canvas = (typeof OffscreenCanvas !== 'undefined')
      ? new OffscreenCanvas(s, s) : document.createElement('canvas')
    canvas.width = s
    canvas.height = s
    const ctx = (canvas as any).getContext('2d')!
    // Flat-top hexagon
    ctx.beginPath()
    for (let i = 0; i < 6; i++) {
      const angle = (Math.PI / 3) * i
      const x = r + (r - 4) * Math.cos(angle)
      const y = r + (r - 4) * Math.sin(angle)
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
    }
    ctx.closePath()
    ctx.strokeStyle = '#FFC107'
    ctx.lineWidth = 3
    ctx.stroke()
    ctx.fillStyle = 'rgba(255, 193, 7, 0.12)'
    ctx.fill()
    map.addImage('poi-hover-hex', { width: s, height: s, data: ctx.getImageData(0, 0, s, s).data }, { pixelRatio: 2 })
  }

  /**
   * Setup POI hover hex source & layer (single-point GeoJSON updated on hover).
   */
  function _setupPoiHexLayer(map: any) {
    if (map.getSource('poi-hover-hex-src')) return
    _ensurePoiHexImage(map)
    map.addSource('poi-hover-hex-src', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] }
    })
    map.addLayer({
      id: 'poi-hover-hex-layer',
      type: 'symbol',
      source: 'poi-hover-hex-src',
      layout: {
        'icon-image': 'poi-hover-hex',
        'icon-size': 1.2,
        'icon-allow-overlap': true,
        'icon-ignore-placement': true,
      },
      paint: {
        'icon-opacity': 1,
      }
    })
  }

  /**
   * Show/hide the POI hover hex at given coordinates.
   */
  function _setPoiHex(map: any, coords: [number, number] | null) {
    const src = map.getSource('poi-hover-hex-src')
    if (!src) return
    if (coords) {
      src.setData({
        type: 'FeatureCollection',
        features: [{ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: coords } }]
      })
      poiHexVisible = true
    } else {
      src.setData({ type: 'FeatureCollection', features: [] })
      poiHexVisible = false
    }
  }

  /**
   * Add highlight layers for buildings and roads.
   */
  function setupLayers(map: any) {
    // Clear interactive layer tracking (style change destroys old handlers)
    registeredInteractiveLayers.clear()

    // POI hover hex overlay
    _setupPoiHexLayer(map)

    // Buildings hover (yellow) and active (red)
    if (map.getLayer('building')) {
      const beforeLayer = map.getLayer('building-3d') ? 'building-3d' : undefined

      // Skip if layers already exist (prevents duplicates on style change)
      if (map.getLayer('building-hover')) return

      map.addLayer({
        id: 'building-hover',
        type: 'fill',
        source: 'openmaptiles',
        'source-layer': 'building',
        paint: {
          'fill-color': '#FFC107',
          'fill-opacity': ['case', ['boolean', ['feature-state', 'hover'], false], 0.5, 0],
          'fill-outline-color': '#FFA000'
        },
        minzoom: 13
      }, beforeLayer)

      map.addLayer({
        id: 'building-active',
        type: 'fill',
        source: 'openmaptiles',
        'source-layer': 'building',
        paint: {
          'fill-color': '#F44336',
          'fill-opacity': ['case', ['boolean', ['feature-state', 'active'], false], 0.7, 0],
          'fill-outline-color': '#D32F2F'
        },
        minzoom: 13
      }, beforeLayer)
    }

    // Roads hover (yellow) and active (red)
    const roadLayers = [
      'road_minor',
      'road_secondary_tertiary',
      'road_trunk_primary',
      'road_motorway',
      'road_link',
      'road_service_track'
    ]

    roadLayers.forEach(layerId => {
      if (map.getLayer(layerId)) {
        map.addLayer({
          id: `${layerId}-hover`,
          type: 'line',
          source: 'openmaptiles',
          'source-layer': 'transportation',
          filter: map.getLayer(layerId).filter,
          paint: {
            'line-color': '#FFC107',
            'line-width': ['case', ['boolean', ['feature-state', 'hover'], false], 4, 0],
            'line-opacity': ['case', ['boolean', ['feature-state', 'hover'], false], 0.8, 0]
          }
        })

        map.addLayer({
          id: `${layerId}-active`,
          type: 'line',
          source: 'openmaptiles',
          'source-layer': 'transportation',
          filter: map.getLayer(layerId).filter,
          paint: {
            'line-color': '#F44336',
            'line-width': ['case', ['boolean', ['feature-state', 'active'], false], 6, 0],
            'line-opacity': ['case', ['boolean', ['feature-state', 'active'], false], 1, 0]
          }
        })
      }
    })

    // Bridge streets
    if (map.getLayer('bridge_street')) {
      map.addLayer({
        id: 'bridge_street-hover',
        type: 'line',
        source: 'openmaptiles',
        'source-layer': 'transportation',
        filter: map.getLayer('bridge_street').filter,
        paint: {
          'line-color': '#FFC107',
          'line-width': ['case', ['boolean', ['feature-state', 'hover'], false], 4, 0],
          'line-opacity': ['case', ['boolean', ['feature-state', 'hover'], false], 0.8, 0]
        }
      })

      map.addLayer({
        id: 'bridge_street-active',
        type: 'line',
        source: 'openmaptiles',
        'source-layer': 'transportation',
        filter: map.getLayer('bridge_street').filter,
        paint: {
          'line-color': '#F44336',
          'line-width': ['case', ['boolean', ['feature-state', 'active'], false], 6, 0],
          'line-opacity': ['case', ['boolean', ['feature-state', 'active'], false], 1, 0]
        }
      })
    }
  }

  /**
   * Setup interactive layers with hover cursor and feature-state highlighting.
   */
  function setupInteractiveFeatures(map: any) {
    const poiLayers = ['poi_z14', 'poi_z15', 'poi_z16', 'poi_transit', 'government-icon', 'churches-icon']
    const interactiveLayers = [
      'building',
      'building-3d',
      ...poiLayers,
      'road_minor',
      'road_secondary_tertiary',
      'road_trunk_primary',
      'road_motorway',
      'road_link',
      'road_service_track',
      'bridge_street'
    ]

    interactiveLayers.filter(id => map.getLayer(id) && !registeredInteractiveLayers.has(id)).forEach(layer => {
      registeredInteractiveLayers.add(layer)
      map.on('mouseenter', layer, (e: any) => {
        map.getCanvas().style.cursor = 'pointer'

        if (e.features && e.features.length > 0) {
          const feature = e.features[0]

          if (feature.id !== undefined && feature.id !== null) {
            hoveredFeatureId = feature.id
            hoveredFeatureSource = feature.source
            hoveredFeatureSourceLayer = feature.sourceLayer

            map.setFeatureState(
              { source: feature.source, sourceLayer: feature.sourceLayer, id: feature.id },
              { hover: true }
            )
          }

          // Show hex overlay on POI layers
          if (poiLayers.includes(layer)) {
            const coords = feature.geometry?.coordinates
            if (coords && coords.length === 2) {
              _setPoiHex(map, coords as [number, number])
            }
          }
        }
      })

      map.on('mouseleave', layer, () => {
        map.getCanvas().style.cursor = ''

        if (hoveredFeatureId !== null && hoveredFeatureId !== undefined) {
          map.setFeatureState(
            { source: hoveredFeatureSource, sourceLayer: hoveredFeatureSourceLayer, id: hoveredFeatureId },
            { hover: false }
          )
        }
        hoveredFeatureId = null

        // Hide hex overlay when leaving POI
        if (poiLayers.includes(layer) && poiHexVisible) {
          _setPoiHex(map, null)
        }
      })
    })
  }

  /**
   * Set the active (clicked) feature — clears previous active state.
   */
  function setActiveFeature(map: any, feature: any) {
    // Clear previous active state
    clearActiveFeature(map)
    // Clear POI hex overlay on selection
    if (poiHexVisible) _setPoiHex(map, null)

    if (feature.id !== undefined && feature.id !== null) {
      activeFeatureId = feature.id
      activeFeatureSource = feature.source
      activeFeatureSourceLayer = feature.sourceLayer

      map.setFeatureState(
        { source: feature.source, sourceLayer: feature.sourceLayer, id: feature.id },
        { active: true }
      )
    }
  }

  /**
   * Clear current active feature state.
   */
  function clearActiveFeature(map: any) {
    if (activeFeatureId !== null && activeFeatureId !== undefined) {
      map.setFeatureState(
        { source: activeFeatureSource, sourceLayer: activeFeatureSourceLayer, id: activeFeatureId },
        { active: false }
      )
    }
    activeFeatureId = null
  }

  /**
   * Sync markers from mapStore to map instance.
   */
  async function syncMarkers(map: any, mapStore: any) {
    if (!map) return

    try {
      const maplibreModule = await import('maplibre-gl')
      const maplibregl = maplibreModule.default || maplibreModule

      const storeMarkers = mapStore.markers || []

      // Remove markers that are no longer in store
      for (const [markerId, markerInstance] of mapMarkers.entries()) {
        if (!storeMarkers.find((m: any) => m.id === markerId)) {
          markerInstance.remove()
          mapMarkers.delete(markerId)
        }
      }

      // Add/update markers from store
      for (const marker of storeMarkers) {
        const existingMarker = mapMarkers.get(marker.id)

        if (existingMarker) {
          existingMarker.setLngLat(marker.coordinates)
        } else {
          const el = document.createElement('div')
          el.className = `map-marker map-marker-${marker.type}`

          if (marker.type === 'item') {
            el.style.width = '12px'
            el.style.height = '12px'
            el.style.borderRadius = '50%'
            el.style.backgroundColor = '#ef4444'
            el.style.border = '2px solid white'
            el.style.boxShadow = '0 0 6px rgba(239, 68, 68, 0.6)'
          } else if (marker.type === 'user') {
            el.style.width = '12px'
            el.style.height = '12px'
            el.style.borderRadius = '50%'
            el.style.backgroundColor = '#3b82f6'
            el.style.border = '2px solid white'
            el.style.boxShadow = '0 0 6px rgba(59, 130, 246, 0.6)'
          } else {
            el.style.width = '12px'
            el.style.height = '12px'
            el.style.borderRadius = '50%'
            el.style.backgroundColor = '#8b5cf6'
            el.style.border = '2px solid white'
            el.style.boxShadow = '0 0 6px rgba(139, 92, 246, 0.6)'
          }

          const markerInstance = new maplibregl.Marker({ element: el, anchor: 'center' })
            .setLngLat(marker.coordinates)
            .addTo(map)

          mapMarkers.set(marker.id, markerInstance)
        }
      }
    } catch (error) {
      console.error('[MapHighlight] Error in syncMarkers:', error)
    }
  }

  /**
   * Remove all markers from map.
   */
  function cleanupMarkers() {
    for (const [, markerInstance] of mapMarkers.entries()) {
      markerInstance.remove()
    }
    mapMarkers.clear()
  }

  return {
    setupLayers,
    setupInteractiveFeatures,
    setActiveFeature,
    clearActiveFeature,
    syncMarkers,
    cleanupMarkers,
  }
}
