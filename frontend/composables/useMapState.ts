/**
 * Composable for persisting map state across page navigation and browser sessions
 * Keeps map position, zoom, search query, and panel state when switching tabs or reloading
 */
import { ref, watch } from 'vue'

// Storage keys
const MAP_CENTER_KEY = 'parahub_map_center'
const MAP_ZOOM_KEY = 'parahub_map_zoom'

// Load from localStorage (client-side only)
const loadMapCenter = (): [number, number] => {
  if (process.client) {
    try {
      const saved = localStorage.getItem(MAP_CENTER_KEY)
      if (saved) {
        const parsed = JSON.parse(saved)
        if (Array.isArray(parsed) && parsed.length === 2) {
          return parsed as [number, number]
        }
      }
    } catch (e) {
      console.error('Failed to load map center from localStorage:', e)
    }
  }
  return [-9.1393, 38.7223] // Lisbon default
}

const loadMapZoom = (): number => {
  if (process.client) {
    try {
      const saved = localStorage.getItem(MAP_ZOOM_KEY)
      if (saved) {
        const parsed = parseFloat(saved)
        if (!isNaN(parsed)) {
          return parsed
        }
      }
    } catch (e) {
      console.error('Failed to load map zoom from localStorage:', e)
    }
  }
  return 11 // Default zoom
}

// Global state that persists across component unmount/mount
const mapCenter = ref<[number, number]>(loadMapCenter())
const mapZoom = ref<number>(loadMapZoom())
const searchQuery = ref<string>('')
const selectedFeature = ref<any>(null)
const clickedFeatures = ref<any[]>([])
const clickCoordinates = ref<{ lat: number; lng: number } | null>(null)
const currentMarker = ref<any>(null)

// Save to localStorage when map position changes (client-side only)
if (process.client) {
  watch(mapCenter, (newCenter) => {
    try {
      localStorage.setItem(MAP_CENTER_KEY, JSON.stringify(newCenter))
    } catch (e) {
      console.error('Failed to save map center to localStorage:', e)
    }
  })

  watch(mapZoom, (newZoom) => {
    try {
      localStorage.setItem(MAP_ZOOM_KEY, newZoom.toString())
    } catch (e) {
      console.error('Failed to save map zoom to localStorage:', e)
    }
  })
}

export const useMapState = () => {
  // Setters
  const setMapCenter = (center: [number, number]) => {
    mapCenter.value = center
  }

  const setMapZoom = (zoom: number) => {
    mapZoom.value = zoom
  }

  const setSearchQuery = (query: string) => {
    searchQuery.value = query
  }

  const setSelectedFeature = (feature: any) => {
    selectedFeature.value = feature
  }

  const setClickedFeatures = (features: any[]) => {
    clickedFeatures.value = features
  }

  const setClickCoordinates = (coords: { lat: number; lng: number } | null) => {
    clickCoordinates.value = coords
  }

  const setCurrentMarker = (marker: any) => {
    currentMarker.value = marker
  }

  // Reset all state (if needed)
  const resetMapState = () => {
    mapCenter.value = [-9.1393, 38.7223]
    mapZoom.value = 11
    searchQuery.value = ''
    selectedFeature.value = null
    clickedFeatures.value = []
    clickCoordinates.value = null
    currentMarker.value = null
  }

  return {
    // State
    mapCenter,
    mapZoom,
    searchQuery,
    selectedFeature,
    clickedFeatures,
    clickCoordinates,
    currentMarker,

    // Setters
    setMapCenter,
    setMapZoom,
    setSearchQuery,
    setSelectedFeature,
    setClickedFeatures,
    setClickCoordinates,
    setCurrentMarker,
    resetMapState
  }
}
