import { defineStore } from 'pinia'

export interface Assignment {
  id: string
  object_type: string
  device_id: string
  device_name: string
  route_id: string
  route_name: string
  route_color: string
  data_source_id: string
  direction_id: number
  date: string
  status: string
  display_vehicle_id: string
  notes: string
  created_at: string
  latitude?: number
  longitude?: number
  speed?: number
}

export interface DispatchRoute {
  id: string
  short_name: string
  long_name: string
  route_color: string
  route_type: number
  active_count: number
  place_slug: string
}

export interface AvailableDevice {
  id: string
  name: string
  device_id?: string
  last_seen?: string
  has_position: boolean
}

export const useDispatchStore = defineStore('dispatch', {
  state: () => ({
    assignments: [] as Assignment[],
    routes: [] as DispatchRoute[],
    availableDevices: [] as AvailableDevice[],
    loading: false,
    error: null as string | null,
    selectedDate: new Date().toISOString().slice(0, 10),
  }),

  getters: {
    activeAssignments: (state) => state.assignments.filter(a => ['ASSIGNED', 'ACTIVE'].includes(a.status)),
    completedAssignments: (state) => state.assignments.filter(a => ['COMPLETED', 'CANCELLED'].includes(a.status)),
    assignmentsByRoute: (state) => {
      const map: Record<string, Assignment[]> = {}
      for (const a of state.assignments) {
        if (!map[a.route_name]) map[a.route_name] = []
        map[a.route_name].push(a)
      }
      return map
    },
  },

  actions: {
    async getAuthHeaders() {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' }
      const authStore = useAuthStore()
      await authStore.ensureToken()
      if (authStore.token) headers.Authorization = `Bearer ${authStore.token}`
      return headers
    },

    async fetchAssignments() {
      this.loading = true
      this.error = null
      try {
        const headers = await this.getAuthHeaders()
        this.assignments = await $fetch<Assignment[]>(`/api/v1/iot/dispatch/assignments/?date=${this.selectedDate}`, {
          credentials: 'include', headers,
        })
      } catch (e: any) {
        this.error = e.data?.detail || e.message || 'Failed to load assignments'
      } finally {
        this.loading = false
      }
    },

    async fetchRoutes() {
      try {
        const headers = await this.getAuthHeaders()
        this.routes = await $fetch<DispatchRoute[]>('/api/v1/iot/dispatch/routes/', {
          credentials: 'include', headers,
        })
      } catch (e: any) {
        console.error('Failed to load dispatch routes:', e)
      }
    },

    async fetchAvailableDevices() {
      try {
        const headers = await this.getAuthHeaders()
        this.availableDevices = await $fetch<AvailableDevice[]>('/api/v1/iot/dispatch/devices/', {
          credentials: 'include', headers,
        })
      } catch (e: any) {
        console.error('Failed to load available devices:', e)
      }
    },

    async createAssignment(payload: {
      device_id: string
      route_id: string
      direction_id?: number
      date: string
      display_vehicle_id?: string
      notes?: string
    }) {
      const headers = await this.getAuthHeaders()
      const assignment = await $fetch<Assignment>('/api/v1/iot/dispatch/assignments/', {
        method: 'POST', credentials: 'include', headers, body: payload,
      })
      this.assignments.push(assignment)
      // Refresh available devices (one was just assigned)
      await this.fetchAvailableDevices()
      return assignment
    },

    async updateAssignment(id: string, payload: { status: string; notes?: string }) {
      const headers = await this.getAuthHeaders()
      const updated = await $fetch<Assignment>(`/api/v1/iot/dispatch/assignments/${id}/`, {
        method: 'PATCH', credentials: 'include', headers, body: payload,
      })
      const idx = this.assignments.findIndex(a => a.id === id)
      if (idx >= 0) this.assignments[idx] = updated
      if (['COMPLETED', 'CANCELLED'].includes(payload.status)) {
        await this.fetchAvailableDevices()
      }
      return updated
    },
  },
})
