/**
 * Service Worker for Push Notifications
 * Handles incoming push events and displays notifications
 */

// Service Worker version - increment to force update
const SW_VERSION = '1.1.0'

console.log('[Service Worker] Loaded, version:', SW_VERSION)

// Handle push event
self.addEventListener('push', function(event) {
  console.log('[Service Worker] Push received:', event)

  if (!event.data) {
    console.warn('[Service Worker] Push event has no data')
    return
  }

  let data
  try {
    data = event.data.json()
  } catch (e) {
    console.error('[Service Worker] Failed to parse push data:', e)
    return
  }

  console.log('[Service Worker] Push data:', data)

  const title = data.title || 'Parahub'

  // Check if this is an incoming call notification
  const isIncomingCall = data.data?.type === 'incoming_call'

  const options = {
    body: data.body || '',
    icon: data.icon || '/logo.svg',
    badge: data.badge || '/logo.svg',
    data: {
      url: data.url || '/',
      ...data.data
    },
    // Incoming calls: require interaction (don't auto-dismiss)
    requireInteraction: isIncomingCall || data.data?.requireInteraction || false,
    // Incoming calls: longer vibration pattern
    vibrate: isIncomingCall ? [300, 100, 300, 100, 300, 100, 300] : (data.data?.vibrate || [200, 100, 200]),
    tag: data.data?.tag || data.tag || 'parahub-notification',
    // Incoming calls: renotify even with same tag (for repeated calls)
    renotify: isIncomingCall,
  }

  event.waitUntil(
    self.registration.showNotification(title, options)
  )
})

// Handle notification click
self.addEventListener('notificationclick', function(event) {
  console.log('[Service Worker] Notification click:', event)

  event.notification.close()

  // Get the URL to open from notification data
  const urlToOpen = event.notification.data?.url || '/'

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then(function(clientList) {
        // Check if there's already a window/tab open
        for (let i = 0; i < clientList.length; i++) {
          const client = clientList[i]
          if (client.url === urlToOpen && 'focus' in client) {
            return client.focus()
          }
        }

        // If no matching window, open a new one
        if (clients.openWindow) {
          return clients.openWindow(urlToOpen)
        }
      })
  )
})

// Handle notification close (for analytics)
self.addEventListener('notificationclose', function(event) {
  console.log('[Service Worker] Notification closed:', event)
})

// Install event
self.addEventListener('install', function(event) {
  console.log('[Service Worker] Installing version:', SW_VERSION)
  // Skip waiting to activate immediately
  self.skipWaiting()
})

// Activate event
self.addEventListener('activate', function(event) {
  console.log('[Service Worker] Activating version:', SW_VERSION)
  // Take control of all clients immediately
  event.waitUntil(self.clients.claim())
})
