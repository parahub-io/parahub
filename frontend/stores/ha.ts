import { defineStore } from 'pinia'

export interface HAHome {
  id: string
  object_type: string
  name: string
  url: string
  ha_version: string
  location_name: string
  latitude: number | null
  longitude: number | null
  status: 'online' | 'offline' | 'error'
  last_seen: string | null
  last_error: string
  entity_count: number
  sync_interval_seconds: number
  auto_import: boolean
  property_id: string | null
}

export type EnergySignalRole = 'SURPLUS_BOOL' | 'SURPLUS_POWER' | 'SURPLUS_PRICE'

export interface HAEntity {
  id: string
  object_type: string
  entity_id: string
  domain: string
  friendly_name: string
  state: string
  attributes: Record<string, any>
  is_controllable: boolean
  last_changed: string | null
  last_synced: string | null
  home_id: string
  home_name: string
  device_id: string | null
  energy_signal_role: EnergySignalRole | null
}

export interface HAEntityDiscover {
  entity_id: string
  domain: string
  friendly_name: string
  state: string
  is_controllable: boolean
  already_imported: boolean
}

export interface HATestResult {
  ok: boolean
  ha_version?: string
  location_name?: string
  latitude?: number
  longitude?: number
  error?: string
}

export const useHAStore = defineStore('ha', {
  state: () => ({
    homes: [] as HAHome[],
    entities: new Map<string, HAEntity[]>(), // homeId → entities
    loading: false,
    error: null as string | null,
  }),

  getters: {
    getHomeById: (state) => (id: string) => state.homes.find(h => h.id === id),
    homeEntities: (state) => (homeId: string) => state.entities.get(homeId) || [],
    totalEntities: (state) => state.homes.reduce((sum, h) => sum + h.entity_count, 0),
  },

  actions: {
    async fetchHomes(opts?: { propertyId?: string }) {
      this.loading = true
      this.error = null
      try {
        const headers = await this.getAuthHeaders()
        const params: Record<string, string> = {}
        if (opts?.propertyId) params.property_id = opts.propertyId
        this.homes = await $fetch<HAHome[]>('/api/v1/iot/ha/homes', {
          credentials: 'include',
          headers,
          params,
        })
      } catch (e: any) {
        this.error = e.data?.detail || e.message || 'Failed to load HA homes'
      } finally {
        this.loading = false
      }
    },

    async createHome(name: string, url: string, accessToken: string, propertyId?: string): Promise<HAHome> {
      const headers = await this.getAuthHeaders()
      const body: Record<string, any> = { name, url, access_token: accessToken }
      if (propertyId) body.property_id = propertyId
      const home = await $fetch<HAHome>('/api/v1/iot/ha/homes', {
        method: 'POST',
        credentials: 'include',
        headers,
        body,
      })
      this.homes.push(home)
      return home
    },

    async updateHome(homeId: string, data: Partial<{ name: string; url: string; access_token: string; sync_interval_seconds: number; auto_import: boolean }>) {
      const headers = await this.getAuthHeaders()
      const home = await $fetch<HAHome>(`/api/v1/iot/ha/homes/${homeId}`, {
        method: 'PATCH',
        credentials: 'include',
        headers,
        body: data,
      })
      const idx = this.homes.findIndex(h => h.id === homeId)
      if (idx >= 0) this.homes[idx] = home
      return home
    },

    async deleteHome(homeId: string) {
      const headers = await this.getAuthHeaders()
      await $fetch(`/api/v1/iot/ha/homes/${homeId}`, {
        method: 'DELETE',
        credentials: 'include',
        headers,
      })
      this.homes = this.homes.filter(h => h.id !== homeId)
      this.entities.delete(homeId)
    },

    async testConnection(homeId: string): Promise<HATestResult> {
      const headers = await this.getAuthHeaders()
      return await $fetch<HATestResult>(`/api/v1/iot/ha/homes/${homeId}/test`, {
        method: 'POST',
        credentials: 'include',
        headers,
      })
    },

    async listEntities(homeId: string): Promise<HAEntity[]> {
      const headers = await this.getAuthHeaders()
      const entities = await $fetch<HAEntity[]>(`/api/v1/iot/ha/homes/${homeId}/entities`, {
        credentials: 'include',
        headers,
      })
      this.entities.set(homeId, entities)
      return entities
    },

    async discoverEntities(homeId: string): Promise<HAEntityDiscover[]> {
      const headers = await this.getAuthHeaders()
      return await $fetch<HAEntityDiscover[]>(`/api/v1/iot/ha/homes/${homeId}/discover`, {
        credentials: 'include',
        headers,
      })
    },

    async importEntities(homeId: string, entityIds: string[]): Promise<{ imported: number }> {
      const headers = await this.getAuthHeaders()
      const result = await $fetch<{ imported: number }>(`/api/v1/iot/ha/homes/${homeId}/import`, {
        method: 'POST',
        credentials: 'include',
        headers,
        body: { entity_ids: entityIds },
      })
      // Refresh home to update entity count
      await this.fetchHomes()
      return result
    },

    async deleteEntity(entityId: string, homeId: string) {
      const headers = await this.getAuthHeaders()
      await $fetch(`/api/v1/iot/ha/entities/${entityId}`, {
        method: 'DELETE',
        credentials: 'include',
        headers,
      })
      const entities = this.entities.get(homeId)
      if (entities) {
        this.entities.set(homeId, entities.filter(e => e.id !== entityId))
      }
      // Refresh home for entity count
      await this.fetchHomes()
    },

    async getEntityState(entityId: string): Promise<HAEntity> {
      const headers = await this.getAuthHeaders()
      return await $fetch<HAEntity>(`/api/v1/iot/ha/entities/${entityId}/state`, {
        credentials: 'include',
        headers,
      })
    },

    async controlEntity(entityId: string, service: string, data?: Record<string, any>) {
      const headers = await this.getAuthHeaders()
      return await $fetch<{ status: string; new_state: string }>(`/api/v1/iot/ha/entities/${entityId}/control`, {
        method: 'POST',
        credentials: 'include',
        headers,
        body: { service, data },
      })
    },

    async setEnergySignalRole(entityId: string, homeId: string, role: EnergySignalRole | null): Promise<HAEntity> {
      const headers = await this.getAuthHeaders()
      const entity = await $fetch<HAEntity>(`/api/v1/iot/ha/entities/${entityId}`, {
        method: 'PATCH',
        credentials: 'include',
        headers,
        body: { energy_signal_role: role },
      })
      // Update local cache
      const entities = this.entities.get(homeId)
      if (entities) {
        const idx = entities.findIndex(e => e.id === entityId)
        if (idx >= 0) entities[idx] = entity
      }
      return entity
    },

    async syncHome(homeId: string): Promise<{ updated: number; errors: number; offline: string[] }> {
      const headers = await this.getAuthHeaders()
      return await $fetch(`/api/v1/iot/ha/homes/${homeId}/sync`, {
        method: 'POST',
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
