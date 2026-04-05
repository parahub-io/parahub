/**
 * Browse panel markers + handlers for MapBrowsePanel.
 *
 * Extracted from MapView.vue lines 376-381, 3095-3270.
 */

import { ref } from 'vue'

interface BrowseOptions {
  setSelectedFeature: (f: any) => void
  setClickedFeatures: (f: any[]) => void
  setClickCoordinates: (c: any) => void
  animationEnabled: { value: boolean }
}

export function useMapBrowse(opts: BrowseOptions) {
  const mapStore = useMapStore()

  // Browse panel state
  const browseVisible = ref(false)
  const browseWasOpen = ref(false)
  const browseCategoryId = ref<string | null>(null)
  const browseCategoryName = ref<string | null>(null)
  const browseCategoryIcon = ref<string | null>(null)

  /** Add browse establishment GeoJSON source + layers. */
  function setupLayers(map: any) {
    if (map.getSource('browse-establishments')) return

    map.addSource('browse-establishments', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] }
    })

    map.addLayer({
      id: 'browse-establishments-circle',
      type: 'circle',
      source: 'browse-establishments',
      paint: {
        'circle-radius': 7,
        'circle-color': '#ffe216',
        'circle-stroke-color': '#333',
        'circle-stroke-width': 1.5
      }
    })

    map.addLayer({
      id: 'browse-establishments-label',
      type: 'symbol',
      source: 'browse-establishments',
      layout: {
        'text-field': ['get', 'name'],
        'text-size': 11,
        'text-offset': [0, 1.5],
        'text-anchor': 'top',
        'text-optional': true,
        'text-max-width': 10
      },
      paint: {
        'text-color': '#333',
        'text-halo-color': '#fff',
        'text-halo-width': 1.5
      }
    })

    // Click handler on browse markers
    map.on('click', 'browse-establishments-circle', (e: any) => {
      if (!e.features || !e.features.length) return
      const props = e.features[0].properties
      if (!props) return

      const coords = e.features[0].geometry.coordinates
      if (opts.animationEnabled.value) {
        map.flyTo({ center: coords, zoom: 18, essential: true, speed: 4.5 })
      } else {
        map.jumpTo({ center: coords, zoom: 18 })
      }

      // If the establishment has a building_osm_way_id, simulate building click
      if (props.building_osm_way_id) {
        setTimeout(() => {
          const point = map.project(coords)
          const features = map.queryRenderedFeatures(point)
          if (features && features.length > 0) {
            const buildingFeature = features.find((f: any) => f.sourceLayer === 'building') || features[0]
            opts.setClickedFeatures(features)
            opts.setSelectedFeature(buildingFeature)
            opts.setClickCoordinates({ lat: coords[1], lng: coords[0] })
          }
        }, 500)
      }
    })

    map.on('mouseenter', 'browse-establishments-circle', () => {
      map.getCanvas().style.cursor = 'pointer'
    })
    map.on('mouseleave', 'browse-establishments-circle', () => {
      map.getCanvas().style.cursor = ''
    })
  }

  function updateMarkers(establishments: any[]) {
    const map = mapStore.mapInstance
    if (!map) return

    const features = establishments
      .filter((e: any) => e.location)
      .map((e: any) => ({
        type: 'Feature' as const,
        geometry: {
          type: 'Point' as const,
          coordinates: [e.location.lon, e.location.lat]
        },
        properties: {
          id: e.id,
          name: e.name,
          building_osm_way_id: e.building_osm_way_id || ''
        }
      }))

    const source = map.getSource('browse-establishments')
    if (source) {
      source.setData({ type: 'FeatureCollection', features })
    }
  }

  function clearMarkers() {
    const map = mapStore.mapInstance
    if (!map) return
    const source = map.getSource('browse-establishments')
    if (source) {
      source.setData({ type: 'FeatureCollection', features: [] })
    }
  }

  function closePanel() {
    browseVisible.value = false
    browseWasOpen.value = false
    browseCategoryId.value = null
    browseCategoryName.value = null
    browseCategoryIcon.value = null
    clearMarkers()
  }

  function handleCategorySelect(cat: any) {
    browseCategoryId.value = cat.id
    browseCategoryName.value = cat.name
    browseCategoryIcon.value = cat.icon || null
    browseVisible.value = true
  }

  function handleEstablishmentSelect(est: any) {
    handleSelect(est)
  }

  function handleCategoryCleared() {
    browseCategoryId.value = null
    browseCategoryName.value = null
    browseCategoryIcon.value = null
  }

  function handleSelect(est: any) {
    const map = mapStore.mapInstance
    if (!est.location || !map) return

    const coords = [est.location.lon, est.location.lat]
    if (opts.animationEnabled.value) {
      map.flyTo({ center: coords, zoom: 18, essential: true, speed: 4.5 })
    } else {
      map.jumpTo({ center: coords, zoom: 18 })
    }

    // Hide browse panel, remember it was open for back navigation
    browseWasOpen.value = true
    browseVisible.value = false

    // If establishment has a building, open building panel after map settles
    if (est.building_osm_way_id) {
      setTimeout(() => {
        const point = map.project(coords)
        const features = map.queryRenderedFeatures(point)
        if (features && features.length > 0) {
          const buildingFeature = features.find((f: any) => f.sourceLayer === 'building') || features[0]
          opts.setClickedFeatures(features)
          opts.setSelectedFeature(buildingFeature)
          opts.setClickCoordinates({ lat: est.location.lat, lng: est.location.lon })

          if (typeof window !== 'undefined') {
            window._pendingEstablishmentId = est.id
          }
        }
      }, 600)
    }
  }

  return {
    browseVisible,
    browseWasOpen,
    browseCategoryId,
    browseCategoryName,
    browseCategoryIcon,
    setupLayers,
    updateMarkers,
    clearMarkers,
    closePanel,
    handleCategorySelect,
    handleEstablishmentSelect,
    handleCategoryCleared,
    handleSelect,
  }
}
