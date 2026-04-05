import { defineStore } from 'pinia'
import type { Map as MaplibreMap } from 'maplibre-gl'

export interface MapMarker {
  id: string
  coordinates: [number, number]
  type: 'user' | 'item' | 'custom'
  data?: any
}

export interface HighlightedItem {
  id: string
  coordinates: [number, number]
  title?: string
  animate?: boolean
}

export const useMapStore = defineStore('map', {
  state: () => ({
    // Maplibre instance (singleton)
    mapInstance: null as MaplibreMap | null,

    // Map state
    center: [-9.1393, 38.7223] as [number, number], // Lisbon default
    zoom: 13,
    userLocation: null as [number, number] | null,

    // Markers and highlights
    markers: [] as MapMarker[],
    highlightedItem: null as HighlightedItem | null,

    // UI state
    animationsEnabled: true,
  }),

  getters: {
    hasUserLocation: (state) => state.userLocation !== null,
    hasMap: (state) => state.mapInstance !== null,

    // Check if specific item is highlighted
    isItemHighlighted: (state) => (itemId: string) => {
      return state.highlightedItem?.id === itemId
    },
  },

  actions: {
    // Map instance management
    setMapInstance(map: MaplibreMap) {
      this.mapInstance = map

      // Sync map events to store
      map.on('move', () => {
        const center = map.getCenter()
        this.center = [center.lng, center.lat]
      })

      map.on('zoom', () => {
        this.zoom = map.getZoom()
      })
    },

    clearMapInstance() {
      if (this.mapInstance) {
        // Remove all event listeners
        this.mapInstance.remove()
        this.mapInstance = null
      }
    },

    // Position management
    updateCenter(coordinates: [number, number], animate = true) {
      this.center = coordinates

      if (this.mapInstance) {
        if (animate) {
          this.mapInstance.flyTo({
            center: coordinates,
            essential: true,
            speed: 4.5
          })
        } else {
          this.mapInstance.setCenter(coordinates)
        }
      }
    },

    updateZoom(zoom: number, animate = true) {
      this.zoom = zoom

      if (this.mapInstance) {
        if (animate) {
          this.mapInstance.flyTo({
            zoom,
            essential: true,
            speed: 4.5
          })
        } else {
          this.mapInstance.setZoom(zoom)
        }
      }
    },

    updateUserLocation(coordinates: [number, number]) {
      this.userLocation = coordinates

      // Auto-add user marker
      this.addMarker({
        id: 'user-location',
        coordinates,
        type: 'user'
      })
    },

    // Marker management
    addMarker(marker: MapMarker) {
      const existingIndex = this.markers.findIndex(m => m.id === marker.id)

      if (existingIndex >= 0) {
        this.markers[existingIndex] = marker
      } else {
        this.markers.push(marker)
      }
    },

    removeMarker(markerId: string) {
      const index = this.markers.findIndex(m => m.id === markerId)
      if (index >= 0) {
        this.markers.splice(index, 1)
      }
    },

    clearMarkers(type?: 'user' | 'item' | 'custom') {
      if (type) {
        this.markers = this.markers.filter(m => m.type !== type)
      } else {
        this.markers = []
      }
    },

    // Highlight management (for selected items)
    highlightItem(item: HighlightedItem) {
      this.highlightedItem = item

      // Fly to item location
      if (item.coordinates && this.mapInstance) {
        this.mapInstance.flyTo({
          center: item.coordinates,
          zoom: Math.max(this.zoom, 15), // Zoom in if too far
          essential: true,
          speed: 4.5
        })
      }
    },

    clearHighlight() {
      this.highlightedItem = null
    },

    // UI controls
    setAnimationsEnabled(enabled: boolean) {
      this.animationsEnabled = enabled
    },
  }
})
