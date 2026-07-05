/**
 * Live tracker → IoT panel bridge: subscribes to the selected tracker's WS
 * stream, throttles panel reactivity, and keeps the map dot / lock-on /
 * follow-camera updates immediate.
 */
import { watch } from 'vue'
import type { Ref } from 'vue'

const LOCK_ON_MIN_INTERVAL = 30000 // 30s between animations
const LOCK_ON_MIN_DISTANCE = 0.0001 // ~11m — skip if barely moved
const PANEL_UPDATE_INTERVAL = 2000 // min ms between panel reactive updates

export function useMapTrackerPanelWs(opts: {
  selectedIoTDevice: Ref<any>
  iot: {
    updateSingleTracker: (deviceId: string, lat: number, lon: number, speed: number, status: string) => void
    moveIoTLockOn: (lat: number, lon: number) => void
    followToPosition: (lat: number, lon: number) => void
    replayIoTLockOn: (lat: number, lon: number) => void
  }
}) {
  const { selectedIoTDevice, iot } = opts
  const trackerWs = useTrackerDeviceWs()

  let lastLockOnTime = 0
  let lastLockOnLat = 0
  let lastLockOnLon = 0
  let panelUpdateTimer: ReturnType<typeof setTimeout> | null = null
  let pendingPanelUpdate: { speed: string; lat: number; lon: number; status: string; last_update: string | null } | null = null
  let lastPanelFlush = 0

  function flushPanelUpdate() {
    if (pendingPanelUpdate && selectedIoTDevice.value) {
      selectedIoTDevice.value = {
        ...selectedIoTDevice.value,
        speed: pendingPanelUpdate.speed,
        status: pendingPanelUpdate.status,
        lngLat: { lat: pendingPanelUpdate.lat, lng: pendingPanelUpdate.lon },
        last_update: pendingPanelUpdate.last_update,
      }
      pendingPanelUpdate = null
    }
  }

  // Watch only device_id changes — NOT every position update from WS callback.
  // Without this, the WS callback setting selectedIoTDevice.value triggers
  // the watcher, which re-subscribes, which gets an update, which triggers
  // the watcher again → infinite loop (2-5MB/s memory growth, 130% CPU).
  watch(() => selectedIoTDevice.value?.device_id, (newId, oldId) => {
    // Unsubscribe from previous
    if (oldId) {
      trackerWs.unsubscribe()
      if (panelUpdateTimer) { clearTimeout(panelUpdateTimer); panelUpdateTimer = null }
      pendingPanelUpdate = null
    }
    // Subscribe to new tracker
    const dev = selectedIoTDevice.value
    if (dev?.deviceType === 'tracker' && newId) {
      lastLockOnTime = Date.now()
      lastLockOnLat = dev.lngLat?.lat || 0
      lastLockOnLon = dev.lngLat?.lng || 0

      lastPanelFlush = 0

      trackerWs.subscribeDevice(newId, (tracker) => {
        // tracker: { dev, name, lat, lon, spd, hdg, bat, t, owner }
        if (!selectedIoTDevice.value || selectedIoTDevice.value.device_id !== tracker.dev) return
        const newLat = tracker.lat
        const newLon = tracker.lon
        const newSpeed = tracker.spd || 0
        // Derive status from tracker timestamp age
        const trackerEpoch = tracker.t || 0
        const ageSec = Math.floor(Date.now() / 1000) - trackerEpoch
        const wsStatus = ageSec < 120 ? 'online' : ageSec < 600 ? 'unknown' : 'offline'
        const wsLastUpdate = trackerEpoch ? new Date(trackerEpoch * 1000).toISOString() : null
        // Throttled panel update — only trigger Vue reactivity at most every PANEL_UPDATE_INTERVAL
        pendingPanelUpdate = {
          speed: newSpeed > 1 ? `${Math.round(newSpeed)} km/h` : '',
          lat: newLat,
          lon: newLon,
          status: wsStatus,
          last_update: wsLastUpdate,
        }
        const now2 = Date.now()
        if (now2 - lastPanelFlush >= PANEL_UPDATE_INTERVAL) {
          flushPanelUpdate()
          lastPanelFlush = now2
        } else if (!panelUpdateTimer) {
          panelUpdateTimer = setTimeout(() => {
            flushPanelUpdate()
            lastPanelFlush = Date.now()
            panelUpdateTimer = null
          }, PANEL_UPDATE_INTERVAL - (now2 - lastPanelFlush))
        }
        // Update map dot (immediate, no reactivity cost)
        iot.updateSingleTracker(tracker.dev, newLat, newLon, newSpeed, wsStatus)
        // Move lock-on marker (immediate, just setLngLat)
        iot.moveIoTLockOn(newLat, newLon)
        // Follow mode: smoothly pan camera to new position
        iot.followToPosition(newLat, newLon)
        // Replay full lock-on animation only if moved significantly AND throttle interval passed
        const now = Date.now()
        const moved = Math.abs(newLat - lastLockOnLat) + Math.abs(newLon - lastLockOnLon) > LOCK_ON_MIN_DISTANCE
        if (moved && now - lastLockOnTime >= LOCK_ON_MIN_INTERVAL) {
          iot.replayIoTLockOn(newLat, newLon)
          lastLockOnTime = now
          lastLockOnLat = newLat
          lastLockOnLon = newLon
        }
      })
    } else if (!newId) {
      trackerWs.unsubscribe()
      if (panelUpdateTimer) { clearTimeout(panelUpdateTimer); panelUpdateTimer = null }
      pendingPanelUpdate = null
    }
  })

  return {
    disconnect: () => trackerWs.disconnect(),
  }
}
