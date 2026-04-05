/**
 * Global SOS watcher — subscribes to realtime store for all user's SOS groups.
 * Uses the single shared WebSocket connection (no duplicate WS).
 *
 * On EMERGENCY: plays siren (Web Audio) + vibration + toast.
 * On WARNING/INFO: shows toast notification.
 */

let sirenActive = false
let _handlerRegistered = false

/**
 * Module-level handler — same function reference, safe with Set-based on().
 * Calls useToastStore() at runtime (Pinia is active by the time WS messages arrive).
 */
function _handleSosNew(data: any) {
  const alert = data.alert
  if (!alert) return

  const toastStore = useToastStore()
  const senderName = alert.sender_display_name || alert.sender_hna
  const groupName = data.group_name || ''
  const detail = alert.message || alert.category || ''
  const body = senderName ? `${senderName}: ${detail}` : detail

  if (alert.level === 'EMERGENCY') {
    playSosSiren()
    toastStore.error(body, `ParaSOS: ${groupName}`, 15000)
  } else if (alert.level === 'WARNING') {
    toastStore.warning(body, `ParaSOS: ${groupName}`, 10000)
  } else {
    toastStore.info(body, `ParaSOS: ${groupName}`, 8000)
  }
}

export const useSosWatcher = () => {
  const authStore = useAuthStore()
  const realtimeStore = useRealtimeStore()

  async function subscribeToGroups() {
    if (!authStore.isAuthenticated) return
    try {
      await authStore.ensureToken()
      const groups = await $fetch<any>('/api/v1/parasos/groups/my/', {
        credentials: 'include',
        headers: { Authorization: `Bearer ${authStore.token}` },
      })
      const groupList = Array.isArray(groups) ? groups : groups.items || []
      for (const g of groupList) {
        realtimeStore.joinRoom('parasos', g.id)
      }
    } catch { /* not authenticated or no groups */ }
  }

  function start() {
    if (!authStore.isAuthenticated) return
    if (!_handlerRegistered) {
      _handlerRegistered = true
      realtimeStore.on('sos.new', _handleSosNew)
    }
    subscribeToGroups()
  }

  return { start, subscribeToGroups }
}

/**
 * Play SOS siren via Web Audio API.
 * Two-tone sawtooth sweep 800-1200Hz, 6 seconds.
 */
export function playSosSiren() {
  if (sirenActive) return
  sirenActive = true

  try {
    const ctx = new AudioContext()
    const duration = 6
    const now = ctx.currentTime

    const oscillator = ctx.createOscillator()
    const gain = ctx.createGain()
    oscillator.connect(gain)
    gain.connect(ctx.destination)

    oscillator.type = 'sawtooth'
    gain.gain.value = 0.4

    for (let t = 0; t < duration; t += 1) {
      oscillator.frequency.setValueAtTime(800, now + t)
      oscillator.frequency.linearRampToValueAtTime(1200, now + t + 0.5)
      oscillator.frequency.linearRampToValueAtTime(800, now + t + 1)
    }

    oscillator.start(now)
    oscillator.stop(now + duration)
    oscillator.onended = () => { sirenActive = false }

    if (navigator.vibrate) {
      navigator.vibrate([500, 200, 500, 200, 500, 200, 500, 200, 500, 200, 500])
    }
  } catch (e) {
    sirenActive = false
    console.error('[SOS Siren] Failed:', e)
  }
}
