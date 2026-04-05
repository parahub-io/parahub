export default defineNuxtPlugin((nuxtApp) => {
  // Initialize auth store on client side
  const authStore = useAuthStore()

  // Defer auth reconciliation until after hydration is completed
  nuxtApp.hook('app:mounted', async () => {
    try {
      // Use session-based reconciliation instead of localStorage
      await authStore.ensureSession()

      if (authStore.isAuthenticated) {
        // Authenticated: full realtime WS (includes feed:system + notifications)
        await authStore.ensureToken()

        const realtimeStore = useRealtimeStore()
        realtimeStore.connect()

        // Register global notification handlers
        _registerNotificationHandlers(realtimeStore)
      } else {
        // Anonymous: lightweight public WS for system broadcasts only
        _connectPublicWs()
      }
    } catch (e) {
      console.error('Client auth reconciliation error:', e)
    }
  })
})

/**
 * Register notification event handlers on the realtime store.
 * These show toasts and handle global events across all pages.
 */
function _registerNotificationHandlers(realtimeStore: ReturnType<typeof useRealtimeStore>) {
  const toastStore = useToastStore()

  realtimeStore.on('partner.added', (data: any) => {
    const name = data.partner?.display_name || data.partner?.hna
    if (name) toastStore.success(`${name} added you as partner`)
  })

  realtimeStore.on('partner.removed', (data: any) => {
    const name = data.partner?.display_name || data.partner?.hna
    if (name) toastStore.info(`${name} removed you from partners`)
  })

  realtimeStore.on('contract.created', () => {
    toastStore.info('New contract created')
  })

  realtimeStore.on('contract.updated', () => {
    toastStore.info('Contract updated')
  })

  realtimeStore.on('debt.created', () => {
    toastStore.info('New debt recorded')
  })

  realtimeStore.on('debt.updated', () => {
    toastStore.info('Debt updated')
  })

  realtimeStore.on('notification', (data: any) => {
    // Generic notification from send_notification()
    if (data.notification_type === 'success') {
      toastStore.success(data.message)
    } else if (data.notification_type === 'warning') {
      toastStore.warning(data.message)
    } else if (data.notification_type === 'error') {
      toastStore.error(data.message)
    } else {
      toastStore.info(data.message)
    }
  })

  realtimeStore.on('verification.approved', (data: any) => {
    if (data.verifier_name) {
      toastStore.success(`${data.verifier_name} verified you`)
    }
  })

  realtimeStore.on('matrix.unread_update', (data: any) => {
    if (typeof window !== 'undefined' && (window as any).__matrixUnreadHandler) {
      (window as any).__matrixUnreadHandler(data)
    }
  })

  realtimeStore.on('call.incoming', (data: any) => {
    const callStore = useCallStore()
    callStore.setIncomingCall({
      caller: data.caller,
      room_name: data.room_name,
    })
  })

  realtimeStore.on('feed.system', (data: any) => {
    if (data.event === 'new_version') {
      useState('newVersionAvailable', () => false).value = true
    }
  })
}

/**
 * Lightweight public WebSocket for anonymous users.
 * Only receives feed:system broadcasts (new_version, maintenance).
 */
function _connectPublicWs() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const url = `${protocol}//${window.location.host}/ws/v1/public/`
  let reconnectAttempts = 0
  let reconnectTimeout: ReturnType<typeof setTimeout> | null = null

  function connect() {
    const ws = new WebSocket(url)

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'feed.system' && data.event === 'new_version') {
          useState('newVersionAvailable', () => false).value = true
        }
      } catch { /* ignore */ }
    }

    ws.onopen = () => { reconnectAttempts = 0 }

    ws.onclose = (event) => {
      if (event.code !== 1000) {
        reconnectAttempts++
        const delay = Math.min(3000 * Math.pow(2, reconnectAttempts - 1), 60000)
        reconnectTimeout = setTimeout(connect, delay)
      }
    }
  }

  connect()
}
