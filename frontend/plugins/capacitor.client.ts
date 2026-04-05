import { playSosSiren } from '~/composables/useSosWatcher'
import { Capacitor } from '@capacitor/core'
import { App } from '@capacitor/app'
import { Keyboard } from '@capacitor/keyboard'
import { SplashScreen } from '@capacitor/splash-screen'
import { PushNotifications } from '@capacitor/push-notifications'

export default defineNuxtPlugin(async () => {
  if (!Capacitor.isNativePlatform()) return

  // --- SystemBars safe area (Android) ---
  // Capacitor 8's SystemBars plugin (insetsHandling: 'css') injects
  // --safe-area-inset-* CSS vars. Trigger onDOMReady manually as backup
  // in case the bridge's DOMContentLoaded listener missed in server mode.
  if (Capacitor.getPlatform() === 'android') {
    try {
      const iface = (window as any).CapacitorSystemBarsAndroidInterface
      if (iface?.onDOMReady) iface.onDOMReady()
    } catch {}
  }

  // --- Keyboard (push content up on iOS) ---
  try {
    Keyboard.addListener('keyboardWillShow', (info) => {
      document.documentElement.style.setProperty(
        '--keyboard-height',
        `${info.keyboardHeight}px`
      )
    })
    Keyboard.addListener('keyboardWillHide', () => {
      document.documentElement.style.setProperty('--keyboard-height', '0px')
    })
  } catch { /* Android handles this natively */ }

  // --- Hardware back button (Android) ---
  App.addListener('backButton', ({ canGoBack }) => {
    if (canGoBack) {
      window.history.back()
    } else {
      App.minimizeApp()
    }
  })

  // --- Deep links ---
  App.addListener('appUrlOpen', (event) => {
    // Handle https://parahub.io/... deep links
    const url = new URL(event.url)
    if (url.hostname === 'parahub.io') {
      // Skip Django-only paths (OAuth callbacks, admin, etc.) — let the browser handle them
      if (url.pathname.startsWith('/accounts/') || url.pathname.startsWith('/admin/')) return

      const path = url.pathname + url.search + url.hash
      const localePath = useLocalePath()
      navigateTo(localePath(path))
    }
  })

  // --- FCM Push Notifications ---
  try {
    const permResult = await PushNotifications.requestPermissions()
    if (permResult.receive === 'granted') {
      await PushNotifications.register()
    }

    // FCM token received — send to backend
    PushNotifications.addListener('registration', async (token) => {
      console.log('[FCM] Token:', token.value)
      try {
        const authStore = useAuthStore()
        await authStore.ensureToken()
        await $fetch('/api/v1/notifications/fcm/register/', {
          method: 'POST',
          credentials: 'include',
          headers: { Authorization: `Bearer ${authStore.token}` },
          body: {
            token: token.value,
            platform: Capacitor.getPlatform(),
          },
        })
        console.log('[FCM] Token registered with backend')
      } catch (e) {
        console.error('[FCM] Failed to register token:', e)
      }
    })

    PushNotifications.addListener('registrationError', (err) => {
      console.error('[FCM] Registration error:', err)
    })

    // FCM data message received (foreground) — handle SOS siren
    PushNotifications.addListener('pushNotificationReceived', (notification) => {
      console.log('[FCM] Push received:', notification)
      const data = notification.data
      if (data?.type === 'sos_alert' && data?.level === 'EMERGENCY') {
        playSosSiren()
      }
    })

    // Notification tapped — navigate to SOS group
    PushNotifications.addListener('pushNotificationActionPerformed', (action) => {
      const data = action.notification.data
      if (data?.type === 'sos_alert' && data?.group_id) {
        const localePath = useLocalePath()
        navigateTo(localePath(`/sos/${data.group_id}`))
      } else if (data?.url) {
        navigateTo(data.url)
      }
    })
  } catch (e) {
    console.error('[FCM] Setup error:', e)
  }

  // --- Hardware panic button (volume down × 3) ---
  window.addEventListener('sos-panic-button', async () => {
    console.log('[SOS] Hardware panic button triggered!')
    try {
      const authStore = useAuthStore()
      if (!authStore.isAuthenticated) return

      await authStore.ensureToken()
      // Get user's first group to send EMERGENCY
      const groups = await $fetch<any>('/api/v1/parasos/groups/my/', {
        credentials: 'include',
        headers: { Authorization: `Bearer ${authStore.token}` },
      })
      const groupList = Array.isArray(groups) ? groups : groups.items || []
      if (!groupList.length) return

      // Get current location
      let location: { latitude: number; longitude: number } | undefined
      try {
        const pos = await new Promise<GeolocationPosition>((resolve, reject) => {
          navigator.geolocation.getCurrentPosition(resolve, reject, { enableHighAccuracy: true, timeout: 3000 })
        })
        location = { latitude: pos.coords.latitude, longitude: pos.coords.longitude }
      } catch { /* location optional */ }

      // Send EMERGENCY to first group
      await $fetch(`/api/v1/parasos/groups/${groupList[0].id}/sos/`, {
        method: 'POST',
        credentials: 'include',
        headers: { Authorization: `Bearer ${authStore.token}` },
        body: { level: 'EMERGENCY', category: 'OTHER', message: 'Hardware panic button', location },
      })
      console.log('[SOS] Emergency sent via panic button')
      playSosSiren() // Confirm to sender
    } catch (e) {
      console.error('[SOS] Panic button failed:', e)
    }
  })

  // --- Hide splash screen after app is ready ---
  try {
    await SplashScreen.hide()
  } catch { /* already hidden */ }
})


// playSosSiren() imported from ~/composables/useSosWatcher
