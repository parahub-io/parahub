import { defineStore } from 'pinia'

export interface ManagedAgency {
  id: string
  name: string
  timezone: string
  lang: string
  url: string
  data_source_id: string
  data_source_slug: string
  routes_count: number
  stops_count: number
}

export interface ManagedStop {
  id: string
  source_id: string
  name: string
  lat: number
  lon: number
  agency_id: string
}

export interface RouteStopItem {
  stop_id: string
  stop_name: string
  lat: number
  lon: number
  sequence: number
}

export interface ManagedRoute {
  id: string
  source_id: string
  short_name: string
  long_name: string
  route_type: number
  route_color: string
  description: string
  agency_id: string
  agency_name: string
  stops_outbound: RouteStopItem[]
  stops_inbound: RouteStopItem[]
  has_shape: boolean
}

export const useTransitManageStore = defineStore('transitManage', {
  state: () => ({
    agencies: [] as ManagedAgency[],
    stops: [] as ManagedStop[],
    routes: [] as ManagedRoute[],
    selectedAgency: null as ManagedAgency | null,
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

    // --- Agencies ---
    async fetchAgencies() {
      this.loading = true
      this.error = null
      try {
        const headers = await this.getAuthHeaders()
        this.agencies = await $fetch<ManagedAgency[]>('/api/v1/geo/transit/manage/agencies/', {
          credentials: 'include', headers,
        })
        if (this.agencies.length && !this.selectedAgency) {
          this.selectedAgency = this.agencies[0]
        }
      } catch (e: any) {
        this.error = e.data?.detail || e.message || 'Failed to load agencies'
      } finally {
        this.loading = false
      }
    },

    async createAgency(payload: { name: string; timezone?: string; lang?: string; url?: string }) {
      const headers = await this.getAuthHeaders()
      const agency = await $fetch<ManagedAgency>('/api/v1/geo/transit/manage/agencies/', {
        method: 'POST', credentials: 'include', headers, body: payload,
      })
      this.agencies.push(agency)
      this.selectedAgency = agency
      return agency
    },

    // --- Stops ---
    async fetchStops(agencyId: string, q: string = '') {
      const headers = await this.getAuthHeaders()
      const params = new URLSearchParams({ agency_id: agencyId })
      if (q) params.set('q', q)
      this.stops = await $fetch<ManagedStop[]>(`/api/v1/geo/transit/manage/stops/?${params}`, {
        credentials: 'include', headers,
      })
    },

    async fetchNearbyStops(lat: number, lon: number, radius: number = 500) {
      const headers = await this.getAuthHeaders()
      return await $fetch<ManagedStop[]>(`/api/v1/geo/transit/manage/stops/nearby/?lat=${lat}&lon=${lon}&radius=${radius}`, {
        credentials: 'include', headers,
      })
    },

    async createStop(payload: { agency_id: string; name: string; lat: number; lon: number }) {
      const headers = await this.getAuthHeaders()
      const stop = await $fetch<ManagedStop>('/api/v1/geo/transit/manage/stops/', {
        method: 'POST', credentials: 'include', headers, body: payload,
      })
      this.stops.push(stop)
      return stop
    },

    async updateStop(stopId: string, payload: { name?: string; lat?: number; lon?: number }) {
      const headers = await this.getAuthHeaders()
      const updated = await $fetch<ManagedStop>(`/api/v1/geo/transit/manage/stops/${stopId}/`, {
        method: 'PATCH', credentials: 'include', headers, body: payload,
      })
      const idx = this.stops.findIndex(s => s.id === stopId)
      if (idx >= 0) this.stops[idx] = updated
      return updated
    },

    async deleteStop(stopId: string) {
      const headers = await this.getAuthHeaders()
      await $fetch(`/api/v1/geo/transit/manage/stops/${stopId}/`, {
        method: 'DELETE', credentials: 'include', headers,
      })
      this.stops = this.stops.filter(s => s.id !== stopId)
    },

    // --- Routes ---
    async fetchRoutes(agencyId: string) {
      const headers = await this.getAuthHeaders()
      this.routes = await $fetch<ManagedRoute[]>(`/api/v1/geo/transit/manage/routes/?agency_id=${agencyId}`, {
        credentials: 'include', headers,
      })
    },

    async createRoute(payload: {
      agency_id: string
      short_name: string
      long_name?: string
      route_type?: number
      route_color?: string
    }) {
      const headers = await this.getAuthHeaders()
      const route = await $fetch<ManagedRoute>('/api/v1/geo/transit/manage/routes/', {
        method: 'POST', credentials: 'include', headers, body: payload,
      })
      this.routes.push(route)
      return route
    },

    async updateRoute(routeId: string, payload: {
      short_name?: string
      long_name?: string
      route_type?: number
      route_color?: string
      description?: string
    }) {
      const headers = await this.getAuthHeaders()
      const updated = await $fetch<ManagedRoute>(`/api/v1/geo/transit/manage/routes/${routeId}/`, {
        method: 'PATCH', credentials: 'include', headers, body: payload,
      })
      const idx = this.routes.findIndex(r => r.id === routeId)
      if (idx >= 0) this.routes[idx] = updated
      return updated
    },

    async updateRouteStops(routeId: string, directionId: number, stops: { stop_id: string; sequence: number }[]) {
      const headers = await this.getAuthHeaders()
      const updated = await $fetch<ManagedRoute>(`/api/v1/geo/transit/manage/routes/${routeId}/stops/`, {
        method: 'PUT', credentials: 'include', headers,
        body: { direction_id: directionId, stops },
      })
      const idx = this.routes.findIndex(r => r.id === routeId)
      if (idx >= 0) this.routes[idx] = updated
      return updated
    },

    async deleteRoute(routeId: string) {
      const headers = await this.getAuthHeaders()
      await $fetch(`/api/v1/geo/transit/manage/routes/${routeId}/`, {
        method: 'DELETE', credentials: 'include', headers,
      })
      this.routes = this.routes.filter(r => r.id !== routeId)
    },

    async previewShape(stops: { lat: number; lon: number }[], costing: string = 'bus') {
      const headers = await this.getAuthHeaders()
      return await $fetch<{ type: string; coordinates: number[][]; fallback?: boolean }>('/api/v1/geo/transit/manage/routes/preview-shape/', {
        method: 'POST', credentials: 'include', headers,
        body: { stops, costing },
      })
    },
  },
})
