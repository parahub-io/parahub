import { defineStore } from 'pinia'

export interface IoTDevice {
  id: string
  name: string
  device_type: 'TRACKER' | 'SENSOR' | 'ACTUATOR' | 'GATEWAY' | 'MESH_ROUTER'
  imei?: string
  device_id?: string
  traccar_device_id?: number
  property_id?: string | null
  last_seen?: string
  latitude?: number
  longitude?: number
  speed?: number
  battery_level?: number
  last_update?: string
  latest_firmware_version?: string
  connection_info?: {
    yggdrasil_address?: string
    hostname?: string
    firmware_version?: string
    hardware_profile?: string
    uptime?: number
    private_ssid?: string
    firmware_role?: string
    mesh_ip?: string
    vpn_mode?: string
    latitude?: number
    longitude?: number
  }
}

export interface WifiConfigResult {
  device_id: string
  name: string
  success: boolean
  error?: string
}

export interface WifiConfigResponse {
  updated: number
  failed: number
  results: WifiConfigResult[]
}

export interface IoTDeviceInput {
  name: string
  device_type: string
  imei?: string
  property_id?: string
}

export interface TraccarCredentials {
  username: string
  password_hint: string
  traccar_url: string
  has_account: boolean
}

export interface DeviceLocation {
  lat: number
  lon: number
  speed?: number
  altitude?: number
  battery_level?: number
  device_timestamp: string
}

export const useIoTStore = defineStore('iot', {
  state: () => ({
    devices: [] as IoTDevice[],
    loading: false,
    error: null as string | null,
    traccarCredentials: null as TraccarCredentials | null,
    realTimePositions: new Map<string, DeviceLocation>(),
  }),

  getters: {
    getDeviceByType: (state) => (type: string) => {
      return state.devices.filter(device => device.device_type === type)
    },
    
    trackerDevices: (state) => {
      return state.devices.filter(device => device.device_type === 'TRACKER')
    },
    
    onlineDevices: (state) => {
      return state.devices.filter(device => device.last_seen)
    },
    
    getDeviceById: (state) => (id: string) => {
      return state.devices.find(device => device.id === id)
    }
  },

  actions: {
    async fetchDevices(opts?: { propertyId?: string; unassigned?: boolean }) {
      this.loading = true
      this.error = null

      try {
        const headers = await this.getAuthHeaders()
        const params: Record<string, string> = {}
        if (opts?.propertyId) params.property_id = opts.propertyId
        if (opts?.unassigned) params.unassigned = 'true'

        const data = await $fetch<IoTDevice[]>('/api/v1/iot/devices', {
          credentials: 'include',
          headers,
          params,
        })

        this.devices = data || []
      } catch (error: any) {
        this.error = error.data?.detail || error.message || 'Error loading devices. You may not be authorized.'
        console.error('Error fetching IoT devices:', error)
        
        // If unauthorized, might need to refresh token or redirect to login
        if (error.status === 401 || error.statusCode === 401) {
          this.error = 'Authorization error. Please log in.'
        }
      } finally {
        this.loading = false
      }
    },

    async createDevice(deviceData: IoTDeviceInput) {
      this.loading = true
      this.error = null
      
      try {
        const headers = await this.getAuthHeaders()

        const device = await $fetch<IoTDevice>('/api/v1/iot/devices', {
          method: 'POST',
          credentials: 'include',
          headers,
          body: deviceData
        })
        
        this.devices.push(device)
        return device
      } catch (error: any) {
        this.error = error.message || 'Error creating device'
        console.error('Error creating IoT device:', error)
        throw error
      } finally {
        this.loading = false
      }
    },

    async deleteDevice(deviceId: string) {
      this.loading = true
      this.error = null

      try {
        const headers = await this.getAuthHeaders()

        await $fetch(`/api/v1/iot/devices/${deviceId}`, {
          method: 'DELETE',
          credentials: 'include',
          headers
        })

        // Remove from local state
        this.devices = this.devices.filter(device => device.id !== deviceId)
        this.realTimePositions.delete(deviceId)
      } catch (error: any) {
        this.error = error.message || 'Error deleting device'
        console.error('Error deleting IoT device:', error)
        throw error
      } finally {
        this.loading = false
      }
    },

    async renameDevice(deviceId: string, name: string) {
      try {
        const headers = await this.getAuthHeaders()
        const data = await $fetch<{ status: string; name: string }>(`/api/v1/iot/devices/${deviceId}/rename`, {
          method: 'PATCH',
          credentials: 'include',
          headers,
          body: { name },
        })
        // Update local state
        const device = this.devices.find(d => d.id === deviceId)
        if (device) {
          device.name = data.name
        }
        return data
      } catch (error: any) {
        throw new Error(error.data?.detail || 'Failed to rename device')
      }
    },

    async getDevice(deviceId: string) {
      try {
        const device = await $fetch<IoTDevice>(`/api/v1/iot/devices/${deviceId}`, {
          credentials: 'include',
          headers: await this.getAuthHeaders()
        })

        // Update device in local state
        const index = this.devices.findIndex(d => d.id === deviceId)
        if (index >= 0) {
          this.devices[index] = device
        } else {
          this.devices.push(device)
        }

        return device
      } catch (error: any) {
        this.error = error.message || 'Error loading device'
        console.error('Error fetching IoT device:', error)
        throw error
      }
    },

    async getWifiPassword(deviceId: string) {
      try {
        const headers = await this.getAuthHeaders()
        const data = await $fetch<{ wifi_password: string; ssid: string }>(`/api/v1/iot/devices/${deviceId}/wifi-password`, {
          credentials: 'include',
          headers
        })
        return data
      } catch (error: any) {
        const status = error.status || error.statusCode
        if (status === 503) throw new Error('Router is offline')
        if (status === 504) throw new Error('Connection timed out')
        throw new Error(error.data?.detail || 'Failed to get WiFi password')
      }
    },

    async getRootPassword(deviceId: string) {
      try {
        const headers = await this.getAuthHeaders()
        const data = await $fetch<{ root_password: string; hostname: string }>(`/api/v1/iot/devices/${deviceId}/root-password`, {
          credentials: 'include',
          headers
        })
        return data
      } catch (error: any) {
        const status = error.status || error.statusCode
        if (status === 503) throw new Error('Router is offline')
        if (status === 504) throw new Error('Connection timed out')
        throw new Error(error.data?.detail || 'Failed to get root password')
      }
    },

    async updateWifiConfig(deviceId: string, config: { wifi_ssid?: string; wifi_password?: string; apply_to_all?: boolean }) {
      try {
        const headers = await this.getAuthHeaders()
        const data = await $fetch<WifiConfigResponse>(`/api/v1/iot/devices/${deviceId}/wifi-config`, {
          method: 'PATCH',
          credentials: 'include',
          headers,
          body: config,
        })

        // Update local state for successful devices
        if (config.wifi_ssid) {
          for (const r of data.results) {
            if (r.success) {
              const device = this.devices.find(d => d.id === r.device_id)
              if (device?.connection_info) {
                device.connection_info.private_ssid = config.wifi_ssid
              }
            }
          }
        }

        return data
      } catch (error: any) {
        const status = error.status || error.statusCode
        if (status === 503) throw new Error('Router is offline')
        if (status === 504) throw new Error('Connection timed out')
        throw new Error(error.data?.detail || 'Failed to update WiFi config')
      }
    },

    async getMullvadStatus(deviceId: string) {
      try {
        const headers = await this.getAuthHeaders()
        return await $fetch<{
          mode: string
          account?: string
          country?: string
          server?: string
          server_ip?: string
          local_ip?: string
        }>(`/api/v1/iot/devices/${deviceId}/mullvad-status`, {
          credentials: 'include',
          headers,
        })
      } catch (error: any) {
        const status = error.status || error.statusCode
        if (status === 503) throw new Error('Router is offline')
        if (status === 504) throw new Error('Connection timed out')
        throw new Error(error.data?.detail || 'Failed to get Mullvad status')
      }
    },

    async setupMullvad(deviceId: string, accountKey: string, country: string = '') {
      try {
        const headers = await this.getAuthHeaders()
        return await $fetch<{
          status: string
          mode: string
          country?: string
          server?: string
        }>(`/api/v1/iot/devices/${deviceId}/mullvad-setup`, {
          method: 'POST',
          credentials: 'include',
          headers,
          body: { account_key: accountKey, country },
        })
      } catch (error: any) {
        const status = error.status || error.statusCode
        if (status === 504) throw new Error('Setup timed out — network restart may still be in progress')
        throw new Error(error.data?.detail || 'Failed to setup Mullvad')
      }
    },

    async removeMullvad(deviceId: string) {
      try {
        const headers = await this.getAuthHeaders()
        return await $fetch<{ status: string; mode: string }>(`/api/v1/iot/devices/${deviceId}/mullvad-remove`, {
          method: 'POST',
          credentials: 'include',
          headers,
        })
      } catch (error: any) {
        const status = error.status || error.statusCode
        if (status === 504) throw new Error('Remove timed out')
        throw new Error(error.data?.detail || 'Failed to remove Mullvad')
      }
    },

    async getSpeedLimitStatus(deviceId: string) {
      try {
        const headers = await this.getAuthHeaders()
        return await $fetch<{ enabled: boolean }>(`/api/v1/iot/devices/${deviceId}/speed-limit-status`, {
          credentials: 'include',
          headers,
        })
      } catch (error: any) {
        const status = error.status || error.statusCode
        if (status === 503) throw new Error('Router is offline')
        if (status === 504) throw new Error('Connection timed out')
        throw new Error(error.data?.detail || 'Failed to get speed limit status')
      }
    },

    async toggleSpeedLimit(deviceId: string, enabled: boolean) {
      try {
        const headers = await this.getAuthHeaders()
        return await $fetch<{ status: string; enabled: boolean }>(`/api/v1/iot/devices/${deviceId}/speed-limit-toggle`, {
          method: 'POST',
          credentials: 'include',
          headers,
          body: { enabled },
        })
      } catch (error: any) {
        const status = error.status || error.statusCode
        if (status === 504) throw new Error('Toggle timed out')
        throw new Error(error.data?.detail || 'Failed to toggle speed limit')
      }
    },

    async getLanVpnStatus(deviceId: string) {
      try {
        const headers = await this.getAuthHeaders()
        return await $fetch<{ enabled: boolean }>(`/api/v1/iot/devices/${deviceId}/lan-vpn-status`, {
          credentials: 'include',
          headers,
        })
      } catch (error: any) {
        const status = error.status || error.statusCode
        if (status === 503) throw new Error('Router is offline')
        if (status === 504) throw new Error('Connection timed out')
        throw new Error(error.data?.detail || 'Failed to get LAN VPN status')
      }
    },

    async toggleLanVpn(deviceId: string, enabled: boolean) {
      try {
        const headers = await this.getAuthHeaders()
        return await $fetch<{ status: string; enabled: boolean }>(`/api/v1/iot/devices/${deviceId}/lan-vpn-toggle`, {
          method: 'POST',
          credentials: 'include',
          headers,
          body: { enabled },
        })
      } catch (error: any) {
        const status = error.status || error.statusCode
        if (status === 504) throw new Error('Toggle timed out')
        throw new Error(error.data?.detail || 'Failed to toggle LAN VPN')
      }
    },

    async getWiredMeshStatus(deviceId: string) {
      try {
        const headers = await this.getAuthHeaders()
        return await $fetch<{ enabled: boolean }>(`/api/v1/iot/devices/${deviceId}/wired-mesh-status`, {
          credentials: 'include',
          headers,
        })
      } catch (error: any) {
        const status = error.status || error.statusCode
        if (status === 503) throw new Error('Router is offline')
        if (status === 504) throw new Error('Connection timed out')
        throw new Error(error.data?.detail || 'Failed to get wired mesh status')
      }
    },

    async toggleWiredMesh(deviceId: string, enabled: boolean) {
      try {
        const headers = await this.getAuthHeaders()
        return await $fetch<{ status: string; enabled: boolean }>(`/api/v1/iot/devices/${deviceId}/wired-mesh-toggle`, {
          method: 'POST',
          credentials: 'include',
          headers,
          body: { enabled },
        })
      } catch (error: any) {
        const status = error.status || error.statusCode
        if (status === 504) throw new Error('Toggle timed out')
        throw new Error(error.data?.detail || 'Failed to toggle wired mesh')
      }
    },

    async getYggAccess(deviceId: string) {
      const headers = await this.getAuthHeaders()
      return await $fetch<{ ygg_allowed_ips: string[] }>(`/api/v1/iot/devices/${deviceId}/ygg-access`, {
        credentials: 'include',
        headers,
      })
    },

    async addYggAccess(deviceId: string, ip: string) {
      const headers = await this.getAuthHeaders()
      return await $fetch<{ ygg_allowed_ips: string[] }>(`/api/v1/iot/devices/${deviceId}/ygg-access`, {
        method: 'POST',
        credentials: 'include',
        headers,
        body: { ip },
      })
    },

    async removeYggAccess(deviceId: string, ip: string) {
      const headers = await this.getAuthHeaders()
      return await $fetch<{ ygg_allowed_ips: string[] }>(`/api/v1/iot/devices/${deviceId}/ygg-access`, {
        method: 'DELETE',
        credentials: 'include',
        headers,
        body: { ip },
      })
    },

    async getDiagnostics(deviceId: string, tab: string) {
      try {
        const headers = await this.getAuthHeaders()
        return await $fetch<{ tab: string; sections: Array<{ title: string; output: string }> }>(
          `/api/v1/iot/devices/${deviceId}/diagnostics/${tab}`,
          { credentials: 'include', headers },
        )
      } catch (error: any) {
        const status = error.status || error.statusCode
        if (status === 503) throw new Error('Router is offline')
        if (status === 504) throw new Error('Connection timed out')
        throw new Error(error.data?.detail || 'Failed to get diagnostics')
      }
    },

    async setDeviceLocation(deviceId: string, latitude: number, longitude: number) {
      try {
        const headers = await this.getAuthHeaders()
        await $fetch(`/api/v1/iot/devices/${deviceId}/location`, {
          method: 'PUT',
          credentials: 'include',
          headers,
          body: { latitude, longitude },
        })

        // Update local state
        const device = this.devices.find(d => d.id === deviceId)
        if (device) {
          if (!device.connection_info) device.connection_info = {}
          device.connection_info.latitude = latitude
          device.connection_info.longitude = longitude
          device.latitude = latitude
          device.longitude = longitude
        }
      } catch (error: any) {
        throw new Error(error.data?.detail || 'Failed to set device location')
      }
    },

    updateDeviceLocation(deviceId: string, location: DeviceLocation) {
      // Update real-time position cache
      this.realTimePositions.set(deviceId, location)

      // Update device in main array if exists
      const device = this.devices.find(d => d.id === deviceId)
      if (device) {
        device.latitude = location.lat
        device.longitude = location.lon
        device.speed = location.speed
        device.battery_level = location.battery_level
        device.last_update = location.device_timestamp
        device.last_seen = location.device_timestamp
      }
    },

    subscribeToPositionUpdates() {
      const realtimeStore = useRealtimeStore()
      realtimeStore.connect()

      const trackerIds = this.trackerDevices.map(d => d.id)
      if (trackerIds.length > 0) {
        realtimeStore.subscribe(trackerIds)
      }
    },

    unsubscribeFromPositionUpdates() {
      const realtimeStore = useRealtimeStore()
      const trackerIds = this.trackerDevices.map(d => d.id)
      if (trackerIds.length > 0) {
        realtimeStore.unsubscribe(trackerIds)
      }
    },

    // Helper method to get authentication headers
    async getAuthHeaders() {
      const headers: Record<string, string> = {
        'Content-Type': 'application/json'
      }

      const authStore = useAuthStore()
      await authStore.ensureToken()

      if (authStore.token) {
        headers.Authorization = `Bearer ${authStore.token}`
      }

      return headers
    }
  }
})