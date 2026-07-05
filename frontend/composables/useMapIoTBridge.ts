/**
 * IoT popover / panel bridge: opens the IoT device panel from popover items
 * (trackers, "My Homes" properties), flies the camera with the lock-on
 * animation, and forwards trail controls from the panel back to the map.
 */
import type { Ref } from 'vue'

export function useMapIoTBridge(opts: {
  selectedIoTDevice: Ref<any>
  clearEntityPanels: () => void
  iot: {
    iotPopoverOpen: Ref<boolean>
    showIoTLockOn: (lat: number, lon: number) => void
    replayIoTLockOn: (lat: number, lon: number) => void
    hideIoTPreview: () => void
    flyToTracker: (lat: number, lon: number, name: string) => void
    enableFollow: () => void
    getPanelPadding: () => any
    showTrail: (map: any, geojson: any) => void
    clearTrail: (map: any) => void
    updateTrailCursor: (map: any, lng: number, lat: number, heading: number | null) => void
  }
  animationEnabled: Ref<boolean>
}) {
  const { selectedIoTDevice, clearEntityPanels, iot, animationEnabled } = opts
  const mapStore = useMapStore()

  const selectIoTDevice = (deviceType: string, data: any) => {
    clearEntityPanels()
    selectedIoTDevice.value = {
      deviceType,
      device_id: data.device_id || data.id || '',
      name: data.name || '',
      status: data.status || 'unknown',
      speed: data.speed ? `${Math.round(data.speed)} km/h` : '',
      firmware_role: data.firmware_role || '',
      hardware_profile: data.hardware_profile || '',
      price: data.price || '',
      lngLat: data.latitude != null ? { lat: data.latitude, lng: data.longitude } : null,
      last_update: data.last_update || null,
    }
    // Show lock-on animation
    if (data.latitude != null) iot.showIoTLockOn(data.latitude, data.longitude)
  }

  const selectAndFlyToTracker = (t: any) => {
    selectIoTDevice('tracker', { ...t, status: t.traccar_status })
    iot.flyToTracker(t.latitude, t.longitude, t.name)
    iot.enableFollow()
  }

  const selectAndFlyToProperty = (p: any) => {
    clearEntityPanels()
    iot.showIoTLockOn(p.latitude, p.longitude)
    iot.hideIoTPreview()
    const map = mapStore.mapInstance
    if (map) {
      const padding = iot.getPanelPadding()
      if (animationEnabled.value !== false) {
        map.flyTo({ center: [p.longitude, p.latitude], zoom: 17, essential: true, speed: 4.5, padding })
      } else {
        map.jumpTo({ center: [p.longitude, p.latitude], zoom: 17, padding })
      }
    }
    iot.iotPopoverOpen.value = false
  }

  const handleShowTrail = (geojson: any) => {
    const map = mapStore.mapInstance
    if (!map) return
    iot.showTrail(map, geojson)
    const coords = geojson?.features?.find((f: any) => f.properties?.role === 'trail')?.geometry?.coordinates
    if (coords && coords.length >= 2) {
      let minLng = Infinity, maxLng = -Infinity, minLat = Infinity, maxLat = -Infinity
      for (const [lng, lat] of coords) {
        if (lng < minLng) minLng = lng
        if (lng > maxLng) maxLng = lng
        if (lat < minLat) minLat = lat
        if (lat > maxLat) maxLat = lat
      }
      map.fitBounds([[minLng, minLat], [maxLng, maxLat]], { padding: 80, maxZoom: 16 })
    }
  }

  const handleClearTrail = () => {
    const map = mapStore.mapInstance
    if (map) iot.clearTrail(map)
  }

  const handleTrailCursor = (data: { lng: number; lat: number; heading: number | null }) => {
    const map = mapStore.mapInstance
    if (map) iot.updateTrailCursor(map, data.lng, data.lat, data.heading)
  }

  const handleRecenterIoT = () => {
    const dev = selectedIoTDevice.value
    if (!dev?.lngLat) return
    iot.enableFollow()
    iot.flyToTracker(dev.lngLat.lat, dev.lngLat.lng, dev.name || '')
    iot.replayIoTLockOn(dev.lngLat.lat, dev.lngLat.lng)
  }

  return {
    selectAndFlyToTracker,
    selectAndFlyToProperty,
    handleShowTrail,
    handleClearTrail,
    handleTrailCursor,
    handleRecenterIoT,
  }
}
