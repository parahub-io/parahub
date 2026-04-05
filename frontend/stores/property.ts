import { defineStore } from 'pinia'

export interface Property {
  id: string
  object_type: string
  name: string
  property_type: string
  address: string
  latitude: number
  longitude: number
  has_territory: boolean
  world_object_id: string | null
  building_address: string | null
  device_count: number
  ha_home_count: number
  ha_entity_count: number
  mesh_count: number
  tracker_count: number
  energy_producer_count: number
  energy_consumer_count: number
  created_at: string
}

export interface PropertyMapItem {
  id: string
  name: string
  property_type: string
  latitude: number
  longitude: number
  territory: GeoJSON.Polygon | null
}

export const usePropertyStore = defineStore('property', {
  state: () => ({
    properties: [] as Property[],
    loading: false,
    error: null as string | null,
  }),

  getters: {
    getById: (state) => (id: string) => state.properties.find(p => p.id === id),
  },

  actions: {
    async fetchProperties() {
      this.loading = true
      this.error = null
      try {
        const headers = await this.getAuthHeaders()
        this.properties = await $fetch<Property[]>('/api/v1/iot/properties/', {
          credentials: 'include',
          headers,
        })
      } catch (e: any) {
        this.error = e.data?.detail || e.message || 'Failed to load properties'
      } finally {
        this.loading = false
      }
    },

    async createProperty(data: {
      name: string
      property_type: string
      world_object_id?: string
      latitude?: number
      longitude?: number
      territory?: object
      address?: string
    }): Promise<Property> {
      const headers = await this.getAuthHeaders()
      const prop = await $fetch<Property>('/api/v1/iot/properties/', {
        method: 'POST',
        credentials: 'include',
        headers,
        body: data,
      })
      this.properties.push(prop)
      return prop
    },

    async updateProperty(id: string, data: Partial<{
      name: string
      property_type: string
      world_object_id: string
      latitude: number
      longitude: number
      territory: object
      address: string
    }>): Promise<Property> {
      const headers = await this.getAuthHeaders()
      const prop = await $fetch<Property>(`/api/v1/iot/properties/${id}/`, {
        method: 'PATCH',
        credentials: 'include',
        headers,
        body: data,
      })
      const idx = this.properties.findIndex(p => p.id === id)
      if (idx >= 0) this.properties[idx] = prop
      return prop
    },

    async deleteProperty(id: string) {
      const headers = await this.getAuthHeaders()
      await $fetch(`/api/v1/iot/properties/${id}/`, {
        method: 'DELETE',
        credentials: 'include',
        headers,
      })
      this.properties = this.properties.filter(p => p.id !== id)
    },

    async fetchMapData(): Promise<PropertyMapItem[]> {
      const headers = await this.getAuthHeaders()
      return await $fetch<PropertyMapItem[]>('/api/v1/iot/properties/map/', {
        credentials: 'include',
        headers,
      })
    },

    async getAuthHeaders() {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' }
      const authStore = useAuthStore()
      await authStore.ensureToken()
      if (authStore.token) headers.Authorization = `Bearer ${authStore.token}`
      return headers
    },
  },
})
