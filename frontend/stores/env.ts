import { defineStore } from 'pinia'

export type EnvSource = 'ECOWITT' | 'AIRGRADIENT' | 'GENERIC'

export interface EnvStation {
  id: string
  object_type: string
  name: string
  source: EnvSource
  latitude: number
  longitude: number
  is_public: boolean
  show_owner: boolean
  public_url: string
  external_id: string
  ingest_token: string
  ingest_path: string
  property_id: string | null
  last_reading_at: string | null
  latest: Record<string, any>
}

export interface EnvStationInput {
  name: string
  source: EnvSource
  latitude: number
  longitude: number
  is_public?: boolean
  show_owner?: boolean
  public_url?: string
  property_id?: string | null
  external_id?: string
}

export const useEnvStore = defineStore('env', {
  state: () => ({
    stations: [] as EnvStation[],
    loading: false,
    error: null as string | null,
  }),

  actions: {
    async getAuthHeaders() {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' }
      const authStore = useAuthStore()
      await authStore.ensureToken()
      if (authStore.token) headers.Authorization = `Bearer ${authStore.token}`
      return headers
    },

    async fetchStations() {
      this.loading = true
      this.error = null
      try {
        const headers = await this.getAuthHeaders()
        this.stations = await $fetch<EnvStation[]>('/api/v1/iot/env-stations', {
          credentials: 'include',
          headers,
        })
      } catch (e: any) {
        this.error = e?.data?.detail || 'Failed to load stations'
        console.error('[env] fetchStations:', e)
      } finally {
        this.loading = false
      }
    },

    async createStation(input: EnvStationInput) {
      const headers = await this.getAuthHeaders()
      const station = await $fetch<EnvStation>('/api/v1/iot/env-stations', {
        method: 'POST',
        credentials: 'include',
        headers,
        body: input,
      })
      this.stations.push(station)
      return station
    },

    async patchStation(id: string, patch: Partial<EnvStationInput>) {
      const headers = await this.getAuthHeaders()
      const updated = await $fetch<EnvStation>(`/api/v1/iot/env-stations/${id}`, {
        method: 'PATCH',
        credentials: 'include',
        headers,
        body: patch,
      })
      const i = this.stations.findIndex(s => s.id === id)
      if (i !== -1) this.stations[i] = updated
      return updated
    },

    async setLocation(id: string, latitude: number, longitude: number) {
      return this.patchStation(id, { latitude, longitude })
    },

    async deleteStation(id: string) {
      const headers = await this.getAuthHeaders()
      await $fetch(`/api/v1/iot/env-stations/${id}`, {
        method: 'DELETE',
        credentials: 'include',
        headers,
      })
      this.stations = this.stations.filter(s => s.id !== id)
    },
  },
})
