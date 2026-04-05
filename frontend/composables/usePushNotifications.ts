/**
 * Composable for managing push notifications
 * Handles service worker registration, subscription, and permission management
 */

export const usePushNotifications = () => {
  const config = useRuntimeConfig()
  const authStore = useAuthStore()

  const isSupported = ref(false)
  const isSubscribed = ref(false)
  const permission = ref<NotificationPermission>('default')
  const isLoading = ref(false)

  // Check if push notifications are supported
  onMounted(() => {
    isSupported.value =
      'serviceWorker' in navigator &&
      'PushManager' in window &&
      'Notification' in window

    if (isSupported.value) {
      permission.value = Notification.permission
      checkSubscription()
    }
  })

  /**
   * Request permission and subscribe to push notifications
   */
  const subscribe = async () => {
    if (!isSupported.value) return false
    if (!authStore.isAuthenticated) return false

    isLoading.value = true

    try {
      const perm = await Notification.requestPermission()
      permission.value = perm

      if (perm !== 'granted') {
        alert('Please enable notifications in your browser settings:\n1. Tap the lock icon in address bar\n2. Enable Notifications\n3. Refresh the page and try again')
        return false
      }

      // Register service worker
      const registration = await navigator.serviceWorker.register('/sw.js', {
        scope: '/'
      })

      await navigator.serviceWorker.ready

      // Check for existing subscription and unsubscribe first
      const existingSubscription = await registration.pushManager.getSubscription()
      if (existingSubscription) {
        await existingSubscription.unsubscribe()
      }

      // Get VAPID public key from backend
      const { data: vapidData } = await useFetch('/api/v1/notifications/vapid-public-key/')

      if (!vapidData.value || !vapidData.value.public_key) {
        throw new Error('Failed to get VAPID public key')
      }

      const vapidPublicKey = vapidData.value.public_key

      // Convert VAPID public key from base64 to Uint8Array
      const convertedVapidKey = urlBase64ToUint8Array(vapidPublicKey)

      // Try subscription with 30s timeout (push services can be slow)
      const subscribePromise = registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: convertedVapidKey
      })

      const timeoutPromise = new Promise((_, reject) =>
        setTimeout(() => {
          reject(new Error('Push subscription timeout. This may be due to:\n1. Network/VPN blocking push service\n2. Browser push service unavailable\n3. Try different browser or network'))
        }, 30000)
      )

      const subscription = await Promise.race([subscribePromise, timeoutPromise])

      // Send subscription to backend
      await authStore.ensureToken()
      await $fetch('/api/v1/notifications/subscribe/', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Authorization': `Bearer ${authStore.token}`,
          'Content-Type': 'application/json'
        },
        body: {
          endpoint: subscription.endpoint,
          keys: {
            p256dh: arrayBufferToBase64(subscription.getKey('p256dh')),
            auth: arrayBufferToBase64(subscription.getKey('auth'))
          }
        }
      })

      isSubscribed.value = true
      return true

    } catch (error) {
      console.error('[Push] Failed to subscribe:', error)
      return false
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Unsubscribe from push notifications
   */
  const unsubscribe = async () => {
    if (!isSupported.value || !authStore.isAuthenticated) {
      return false
    }

    isLoading.value = true

    try {
      const registration = await navigator.serviceWorker.ready
      const subscription = await registration.pushManager.getSubscription()

      if (!subscription) {
        isSubscribed.value = false
        return true
      }

      // Unsubscribe from push manager
      await subscription.unsubscribe()

      // Remove from backend
      await authStore.ensureToken()
      await $fetch('/api/v1/notifications/unsubscribe/', {
        method: 'DELETE',
        credentials: 'include',
        headers: {
          'Authorization': `Bearer ${authStore.token}`
        },
        query: {
          endpoint: subscription.endpoint
        }
      })

      isSubscribed.value = false
      return true

    } catch (error) {
      console.error('[Push] Failed to unsubscribe:', error)
      return false
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Check if user is currently subscribed
   */
  const checkSubscription = async () => {
    if (!isSupported.value || !authStore.isAuthenticated) {
      return
    }

    try {
      const registration = await navigator.serviceWorker.getRegistration()
      if (!registration) {
        isSubscribed.value = false
        return
      }

      const subscription = await registration.pushManager.getSubscription()
      isSubscribed.value = !!subscription
    } catch (error) {
      console.error('[Push] Failed to check subscription:', error)
      isSubscribed.value = false
    }
  }

  /**
   * Convert URL-safe base64 string to Uint8Array
   */
  function urlBase64ToUint8Array(base64String: string): Uint8Array {
    const padding = '='.repeat((4 - base64String.length % 4) % 4)
    const base64 = (base64String + padding)
      .replace(/-/g, '+')
      .replace(/_/g, '/')

    const rawData = window.atob(base64)
    const outputArray = new Uint8Array(rawData.length)

    for (let i = 0; i < rawData.length; ++i) {
      outputArray[i] = rawData.charCodeAt(i)
    }
    return outputArray
  }

  /**
   * Convert ArrayBuffer to base64 string
   */
  function arrayBufferToBase64(buffer: ArrayBuffer | null): string {
    if (!buffer) return ''
    const bytes = new Uint8Array(buffer)
    let binary = ''
    for (let i = 0; i < bytes.byteLength; i++) {
      binary += String.fromCharCode(bytes[i])
    }
    return window.btoa(binary)
  }

  return {
    isSupported,
    isSubscribed,
    permission,
    isLoading,
    subscribe,
    unsubscribe,
    checkSubscription
  }
}
