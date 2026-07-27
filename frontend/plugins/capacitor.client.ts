import { playSosSiren } from '~/composables/useSosWatcher'
import { Capacitor, registerPlugin } from '@capacitor/core'

// Installers whose store policies forbid apps updating themselves outside the
// store's own mechanism — the self-update banner must never show for them.
const APP_STORE_INSTALLERS = [
  'com.android.vending', // Google Play
  'com.amazon.venezia',
  'com.huawei.appmarket',
]

async function checkApkUpdate(App: Awaited<typeof import('@capacitor/app')>['App']) {
  const info = await App.getInfo()
  const current = parseInt(info.build, 10) // versionCode on Android
  const res = await fetch('/parahub-apk.json', { cache: 'no-store' })
  if (!res.ok) return
  const latest = await res.json()
  if (!current || !latest?.versionCode || latest.versionCode <= current) return
  if (localStorage.getItem('apk_update_dismissed') === String(latest.versionCode)) return

  try {
    const InstallSource = registerPlugin<{
      getInstallSource(): Promise<{ installer: string }>
    }>('InstallSource')
    const { installer } = await InstallSource.getInstallSource()
    if (APP_STORE_INSTALLERS.includes(installer)) return
  } catch {
    // Shell predates the InstallSource plugin — those builds only ever
    // shipped sideloaded, so showing the banner is safe.
  }

  useState('apkUpdateVersion', () => 0).value = latest.versionCode
  useState('apkUpdateAvailable', () => false).value = true
}

export default defineNuxtPlugin(async () => {
  if (!Capacitor.isNativePlatform()) return

  // Native-only plugin modules load behind the platform gate — as static
  // imports they sat in every web visitor's entry chunk (~570 KB). Inside the
  // native app the chunk is bundled locally, so the await is instant.
  const [{ App }, { Keyboard }, { SplashScreen }, { PushNotifications }] = await Promise.all([
    import('@capacitor/app'),
    import('@capacitor/keyboard'),
    import('@capacitor/splash-screen'),
    import('@capacitor/push-notifications'),
  ])

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

  // --- Cross-origin links → Chrome Custom Tab ---
  // allowNavigation includes *.parahub.io, so foreign pages (Gitea, PeerTube,
  // status, mini-sites) would load inside the WebView: edge-to-edge under the
  // notch/gesture bar (their CSS knows nothing about our safe-area vars) and
  // no way back except the system button. Route every cross-origin http(s)
  // navigation to @capacitor/browser (CCT) instead — native insets + a close
  // button returning to the app. Same-origin links (incl. /webmail, which does
  // its own CCT handoff in-page) keep default behavior.
  const openInCustomTab = (url: string) => {
    import('@capacitor/browser').then(({ Browser }) => Browser.open({ url }))
  }
  document.addEventListener('click', (e) => {
    if (e.defaultPrevented) return // router-handled or drag-suppressed click
    const anchor = (e.target as Element | null)?.closest?.('a[href]')
    if (!anchor) return
    const href = anchor.getAttribute('href')
    if (!href) return
    let url: URL
    try { url = new URL(href, window.location.href) } catch { return }
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return
    if (url.origin === window.location.origin) return
    e.preventDefault()
    openInCustomTab(url.href)
  })
  const nativeWindowOpen = window.open.bind(window)
  window.open = ((url?: string | URL, target?: string, features?: string) => {
    try {
      if (url) {
        const u = new URL(String(url), window.location.href)
        if ((u.protocol === 'http:' || u.protocol === 'https:') && u.origin !== window.location.origin) {
          openInCustomTab(u.href)
          return null
        }
      }
    } catch { /* unparseable — let the WebView deal with it */ }
    return nativeWindowOpen(url as any, target, features)
  }) as typeof window.open

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

  // --- APK self-update check (sideloaded Android builds only) ---
  if (Capacitor.getPlatform() === 'android') {
    checkApkUpdate(App).catch(() => { /* offline / no manifest */ })
  }
})


// playSosSiren() imported from ~/composables/useSosWatcher
