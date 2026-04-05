import type { IoTDevice, IoTDeviceInput, TraccarCredentials, DeviceLocation } from '~/stores/iot'

const HARDWARE_NAMES: Record<string, string> = {
  mt3000: 'GL.iNet Beryl AX',
  mt6000: 'GL.iNet Flint 2',
  axt1800: 'GL.iNet Slate AX',
  ax53u: 'Asus RT-AX53U',
ar300m16: 'GL.iNet AR300M16',
  cpe710: 'TP-Link CPE710',
}

export const useIoT = () => {
  const store = useIoTStore()
  const config = useRuntimeConfig()
  const { t, locale } = useI18n()

  // Reactive state
  const devices = computed(() => store.devices)
  const loading = computed(() => store.loading)
  const error = computed(() => store.error)
  const traccarCredentials = computed(() => store.traccarCredentials)

  // Device type labels for UI
  const getDeviceTypeLabel = (type: string): string => {
    const labels: Record<string, string> = {
      'TRACKER': 'GPS Tracker',
      'SENSOR': 'Sensor',
      'ACTUATOR': 'Actuator',
      'GATEWAY': 'Gateway',
      'MESH_ROUTER': 'Mesh Router'
    }
    return labels[type] || type
  }

  // Format device status (mesh routers: 10min threshold due to 5min heartbeat)
  const getDeviceStatus = (device: IoTDevice) => {
    if (device.last_seen) {
      const lastSeen = new Date(device.last_seen)
      const now = new Date()
      const diffMinutes = (now.getTime() - lastSeen.getTime()) / (1000 * 60)

      const onlineThreshold = device.device_type === 'MESH_ROUTER' ? 10 : 5
      if (diffMinutes < onlineThreshold) return { status: 'online', text: 'Online' }
      if (diffMinutes < 30) return { status: 'recent', text: 'Recently' }
      return { status: 'offline', text: 'Offline' }
    }
    return { status: 'never', text: 'Never connected' }
  }

  // Format uptime in human-readable form
  const formatUptime = (seconds?: number): string => {
    if (!seconds || seconds <= 0) return 'N/A'
    const d = Math.floor(seconds / 86400)
    const h = Math.floor((seconds % 86400) / 3600)
    const m = Math.floor((seconds % 3600) / 60)
    const parts: string[] = []
    if (d > 0) parts.push(`${d}d`)
    if (h > 0) parts.push(`${h}h`)
    parts.push(`${m}m`)
    return parts.join(' ')
  }

  // Format coordinates for display
  const formatCoordinates = (lat?: number, lon?: number) => {
    if (lat === undefined || lon === undefined) return 'No data'
    return `${lat.toFixed(6)}, ${lon.toFixed(6)}`
  }

  // Format date for display (locale-aware)
  const formatDate = (dateString?: string) => {
    if (!dateString) return 'Not specified'
    const localeMap: Record<string, string> = {
      en: 'en-US', ru: 'ru-RU', pt: 'pt-PT', de: 'de-DE', fr: 'fr-FR', es: 'es-ES'
    }
    return new Date(dateString).toLocaleString(localeMap[locale.value] || locale.value, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  // Load devices
  const loadDevices = async () => {
    await store.fetchDevices()
  }

  // Create new device
  const createDevice = async (deviceData: IoTDeviceInput) => {
    return await store.createDevice(deviceData)
  }

  // Delete device
  const deleteDevice = async (deviceCri: string) => {
    try {
      await store.deleteDevice(deviceCri)
      return true
    } catch (error) {
      return false
    }
  }

  // Get device details
  const getDevice = async (deviceCri: string) => {
    return await store.getDevice(deviceCri)
  }

  // Get Traccar dashboard URL for device
  const getTraccarDeviceUrl = (device: IoTDevice) => {
    if (!device.traccar_device_id) {
      return '#' // Return # instead of null to prevent navigation issues
    }
    
    // Use hardcoded URL if config is not available
    const traccarUrl = config.public?.traccarUrl || 'https://traccar.parahub.io'
    return `${traccarUrl}/#device=${device.traccar_device_id}`
  }

  // Check if device has location data
  const hasLocationData = (device: IoTDevice) => {
    return device.latitude !== undefined && device.longitude !== undefined
  }

  // Get battery level with color coding
  const getBatteryInfo = (batteryLevel?: number) => {
    if (batteryLevel === undefined) return { level: 'Unknown', color: 'gray' }
    
    let color = 'red'
    if (batteryLevel > 50) color = 'green'
    else if (batteryLevel > 20) color = 'yellow'
    
    return {
      level: `${batteryLevel}%`,
      color,
      numeric: batteryLevel
    }
  }

  // Get speed with formatting
  const getSpeedInfo = (speed?: number) => {
    if (speed === undefined || speed === null) return 'Unknown'
    return `${Math.round(speed)} km/h`
  }

  // Filter devices by type
  const filterDevicesByType = (type?: string) => {
    if (!type) return devices.value
    return devices.value.filter(device => device.device_type === type)
  }

  // Get devices with "online" status (respects per-type thresholds)
  const getActiveDevices = () => {
    return devices.value.filter(device => getDeviceStatus(device).status === 'online')
  }

  // Real-time position updates (WebSocket integration)
  const subscribeToUpdates = () => {
    // This would connect to WebSocket for real-time updates
    store.subscribeToPositionUpdates()
  }

  // Validation helpers
  const validateDeviceName = (name: string) => {
    if (!name || name.trim().length < 2) {
      return 'Name must contain at least 2 characters'
    }
    if (name.length > 100) {
      return 'Name cannot be longer than 100 characters'
    }
    return null
  }

  const validateIMEI = (imei?: string) => {
    if (!imei) return null // IMEI is optional
    
    // Basic IMEI validation (15 digits)
    if (!/^\d{15}$/.test(imei)) {
      return 'IMEI must contain exactly 15 digits'
    }
    return null
  }

  // Hardware profile slug → human name
  const getHardwareName = (slug?: string): string => {
    if (!slug || slug === 'unknown') return slug || 'Unknown'
    return HARDWARE_NAMES[slug] || slug
  }

  // Relative time formatting
  const formatRelativeTime = (dateString?: string): string => {
    if (!dateString) return ''
    const now = Date.now()
    const then = new Date(dateString).getTime()
    const diffMs = now - then
    if (diffMs < 0) return formatDate(dateString)

    const diffMin = Math.floor(diffMs / 60000)
    if (diffMin < 1) return t('iot.time_just_now')
    if (diffMin < 60) return t('iot.time_minutes_ago', { n: diffMin })

    const diffHours = Math.floor(diffMin / 60)
    if (diffHours < 24) return t('iot.time_hours_ago', { n: diffHours })

    return formatDate(dateString)
  }

  return {
    // State
    devices,
    loading,
    error,
    traccarCredentials,

    // Actions
    loadDevices,
    createDevice,
    deleteDevice,
    getDevice,
    subscribeToUpdates,

    // Formatters & Helpers
    getDeviceTypeLabel,
    getDeviceStatus,
    formatCoordinates,
    formatDate,
    formatRelativeTime,
    getTraccarDeviceUrl,
    hasLocationData,
    getBatteryInfo,
    getSpeedInfo,
    formatUptime,
    getHardwareName,
    filterDevicesByType,
    getActiveDevices,

    // Validation
    validateDeviceName,
    validateIMEI
  }
}