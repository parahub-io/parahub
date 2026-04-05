/**
 * WebSocket composable for real-time tracker device updates.
 *
 * Wraps useWebSocket to subscribe to a single tracker device via
 * the TrackerConsumer (ws/v1/trackers/) subscribe_device protocol.
 *
 * Automatically re-subscribes after reconnection (e.g. signal loss).
 */

import { ref } from 'vue'

export const useTrackerDeviceWs = () => {
  const _onUpdate = ref<((tracker: any) => void) | null>(null)
  const _currentDeviceId = ref<string | null>(null)

  const { isConnected, connect: wsConnect, disconnect, send } = useWebSocket({
    path: '/ws/v1/trackers/',
    skipCleanup: true,
    onMessage: (data) => {
      if (data.type === 'device_update' && data.tracker && _onUpdate.value) {
        _onUpdate.value(data.tracker)
      }
    },
    onOpen: () => {
      // Re-subscribe after reconnection if we have an active subscription
      if (_currentDeviceId.value && _onUpdate.value) {
        send({ type: 'subscribe_device', device_id: _currentDeviceId.value })
      }
    },
  })

  const subscribeDevice = async (deviceId: string, onUpdate: (tracker: any) => void) => {
    _onUpdate.value = onUpdate
    _currentDeviceId.value = deviceId
    if (!isConnected.value) await wsConnect()
    // Wait for connection (up to 3s)
    let waited = 0
    while (!isConnected.value && waited < 3000) {
      await new Promise(r => setTimeout(r, 100))
      waited += 100
    }
    if (isConnected.value) {
      send({ type: 'subscribe_device', device_id: deviceId })
    }
  }

  const unsubscribe = () => {
    _onUpdate.value = null
    _currentDeviceId.value = null
    if (isConnected.value) send({ type: 'unsubscribe' })
  }

  return { isConnected, subscribeDevice, unsubscribe, disconnect }
}
