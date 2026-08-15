<template>
  <div class="w-full h-full flex flex-col overflow-hidden bg-neutral-50 dark:bg-neutral-900">
    <h1 class="sr-only">{{ $t('nav.chat', 'Chat') }}</h1>
    <!-- CRITICAL: Use Teleport to keep iframe in DOM outside KeepAlive scope -->
    <Teleport to="body">
      <div
        ref="iframeContainer"
        :class="['parahub-chat-iframe-container', { 'is-hidden': !isActive }]"
      >
        <!-- Only render iframe after data is cleared to avoid device_id conflicts -->
        <iframe
          v-if="isReady"
          ref="cinnyIframe"
          :src="cinnyUrl"
          class="w-full h-full border-0"
          allow="microphone; camera; display-capture; clipboard-read; clipboard-write; fullscreen"
          @load="onIframeLoad"
        />
        <div v-else class="flex items-center justify-center h-full">
          <div class="text-neutral-500">Loading chat...</div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, watch, onActivated, onDeactivated, onMounted, onBeforeUnmount } from 'vue'

definePageMeta({
  middleware: 'auth',
  order: 5,
  keepalive: true
})

useHead({
  title: 'Chat - Parahub'
})

const route = useRoute()
const authStore = useAuthStore()
const cinnyIframe = ref(null)
const iframeContainer = ref(null)
const isActive = ref(true)
const isReady = ref(false)
const iframeLoaded = ref(false)
const pendingRoomNavigation = ref(null)
const ssoClickCount = ref(0) // Track SSO clicks to prevent double-click
const masConsentClickCount = ref(0) // Track MAS consent-page confirm clicks
const hasTriedRecovery = ref(false) // Prevent infinite reload loop on error
const isRecovering = ref(false) // Prevent concurrent recovery attempts
const cinnyNavCleanup = ref(null) // Cleanup function for iframe navigation tracking
const CINNY_LAST_PATH_KEY = 'cinny_last_path'

// Recovery function to handle device_id conflicts
async function attemptDeviceIdRecovery() {
  // Prevent concurrent or repeated recovery attempts
  if (isRecovering.value || hasTriedRecovery.value) return false

  isRecovering.value = true
  hasTriedRecovery.value = true

  // CRITICAL: Destroy iframe FIRST to close IndexedDB connections
  isReady.value = false

  // Wait for connections to close (IndexedDB needs time to release)
  await new Promise(resolve => setTimeout(resolve, 500))

  // Now clear all Cinny/Matrix data (IndexedDB should be unblocked)
  await clearCinnyData()

  // Extra wait to ensure cleanup is complete
  await new Promise(resolve => setTimeout(resolve, 300))

  // Reset SSO click counters for fresh start
  ssoClickCount.value = 0
  masConsentClickCount.value = 0

  // Recreate iframe
  isReady.value = true

  isRecovering.value = false
  return true
}

// Wipe a Cinny session cached by a different Parahub account.
// Cinny silently resumes any valid cached session instead of showing the
// SSO login, so without this check an account switch (or a shared computer)
// opens the chat as the previous user. Expected Matrix ID comes from the
// backend — it is derived from the PRIMARY profile, so comparing against
// the active (possibly pseudonym) profile's local_name would misfire.
async function ensureCinnySessionOwner() {
  const cachedUserId = getCinnySessionUserId()
  if (!cachedUserId) return

  try {
    await authStore.ensureToken()
    const res = await $fetch('/api/v1/matrix/whoami', {
      credentials: 'include',
      headers: authStore.token ? { 'Authorization': `Bearer ${authStore.token}` } : {}
    })
    if (res?.user_id && res.user_id.toLowerCase() !== cachedUserId.toLowerCase()) {
      await logoutCinnySession()
      await clearCinnyData()
    }
  } catch (e) {
    // Expected user unknown (offline, API error) — keep the cached session
    console.error('[chat.vue] Session owner check failed:', e)
  }
}

// Global error handler for catching iframe errors (backup detection)
function handleGlobalError(event) {
  const message = event.message || event.reason?.message || ''
  if (message.includes('account in the store doesn\'t match')) {
    attemptDeviceIdRecovery()
  }
  if (message.includes('unpickling') || message.includes('failed to be decrypted')) {
    attemptDeviceIdRecovery()
  }
}

onMounted(async () => {
  // Listen for unhandled errors/rejections that might come from iframe
  window.addEventListener('error', handleGlobalError)
  window.addEventListener('unhandledrejection', handleGlobalError)

  // Must run BEFORE the iframe mounts: a stale session from another account
  // has to be wiped while IndexedDB connections are still closed
  await ensureCinnySessionOwner()

  // Load iframe immediately - don't clear data unless there's a conflict
  isReady.value = true

  // Save room_id to sessionStorage to survive iframe reloads
  if (route.query.room_id) {
    sessionStorage.setItem('cinny_pending_room', route.query.room_id)
  }
})

// Called when iframe finishes loading
async function onIframeLoad() {
  iframeLoaded.value = true

  // Check for errors and handle SSO
  setTimeout(async () => {
    try {
      const iframe = cinnyIframe.value
      if (!iframe || !iframe.contentDocument) {
        console.error('[chat.vue] No iframe or contentDocument access')
        return
      }

      // Check for crypto/device_id errors in body text
      const bodyText = iframe.contentDocument.body?.textContent || ''
      if (bodyText.includes('account in the store doesn\'t match')) {
        const recovered = await attemptDeviceIdRecovery()
        if (recovered) return
      }
      // Check for unpickling/decryption errors (corrupted crypto state)
      if (bodyText.includes('unpickling') || bodyText.includes('failed to be decrypted')) {
        const recovered = await attemptDeviceIdRecovery()
        if (recovered) return
      }

      // MAS consent page ("Continue to …?"), served same-origin under /mas/.
      // Confirm the compat-SSO hand-off back to Cinny automatically; the
      // second form on that page ("Use another account") is data-kind=secondary.
      const iframePath = iframe.contentWindow?.location?.pathname || ''
      if (iframePath.startsWith('/mas/')) {
        if (masConsentClickCount.value > 0) return
        const consentBtn = iframe.contentDocument.querySelector(
          'form button[type="submit"]:not([data-kind="secondary"])'
        )
        if (consentBtn) {
          masConsentClickCount.value++
          consentBtn.click()
        }
        return
      }

      // Cinny login page: auto-click the SSO button. Match by href — the
      // label ("Continue with …") is locale-dependent after the i18n rebuild.
      const ssoLink = iframe.contentDocument.querySelector('a[href*="/login/sso/redirect"]')
      if (ssoLink) {
        // Only click once
        if (ssoClickCount.value > 0) return

        ssoClickCount.value++
        ssoLink.click()

        // After SSO redirect, iframe will reload with room already in URL
        return
      }

      // No SSO link = already logged in, start tracking navigation
      startTrackingCinnyNavigation()
      const roomId = sessionStorage.getItem('cinny_pending_room')
      if (roomId) {
        sessionStorage.removeItem('cinny_pending_room')
        pendingRoomNavigation.value = null
      }
    } catch (error) {
      console.error('[chat.vue] Error in onIframeLoad:', error)
    }
  }, 1000)
}

// Track iframe navigation and save to localStorage for F5 persistence
function saveCinnyPath(path) {
  if (path && path.startsWith('/cinny/') && path !== '/cinny/' && path !== '/cinny/login') {
    localStorage.setItem(CINNY_LAST_PATH_KEY, path)
  }
}

function startTrackingCinnyNavigation() {
  stopTrackingCinnyNavigation()

  try {
    const iframeWin = cinnyIframe.value?.contentWindow
    if (!iframeWin) return

    // Save current path immediately
    saveCinnyPath(iframeWin.location.pathname)

    // Monkey-patch pushState/replaceState to catch SPA navigation
    const origPush = iframeWin.history.pushState.bind(iframeWin.history)
    const origReplace = iframeWin.history.replaceState.bind(iframeWin.history)

    iframeWin.history.pushState = function (...args) {
      origPush(...args)
      saveCinnyPath(iframeWin.location.pathname)
    }
    iframeWin.history.replaceState = function (...args) {
      origReplace(...args)
      saveCinnyPath(iframeWin.location.pathname)
    }

    // Also catch browser back/forward
    const onPopState = () => saveCinnyPath(iframeWin.location.pathname)
    iframeWin.addEventListener('popstate', onPopState)

    // Store cleanup refs
    cinnyNavCleanup.value = () => {
      iframeWin.history.pushState = origPush
      iframeWin.history.replaceState = origReplace
      iframeWin.removeEventListener('popstate', onPopState)
    }
  } catch (e) { /* iframe destroyed or cross-origin */ }
}

function stopTrackingCinnyNavigation() {
  if (cinnyNavCleanup.value) {
    try { cinnyNavCleanup.value() } catch (e) { /* iframe already gone */ }
    cinnyNavCleanup.value = null
  }
}

// Generate Cinny URL (SSO-only, no loginToken to avoid device_id conflicts)
const cinnyUrl = computed(() => {
  const roomId = route.query.room_id
  const contactAccountId = route.query.contact_account_id

  // Build base path with room navigation (default to /direct for DM list)
  let basePath = '/direct'

  if (roomId) {
    basePath = `/direct/${roomId}`
  } else if (contactAccountId) {
    const matrixUserId = `@${contactAccountId.toLowerCase()}:parahub.io`
    basePath = `/directs/${matrixUserId}`
  } else {
    // Restore last viewed room on F5 / page reload
    const lastPath = localStorage.getItem(CINNY_LAST_PATH_KEY)
    if (lastPath) return lastPath
  }

  // Always use SSO (auto-click handles login) - no loginToken to avoid device_id conflicts
  return `/cinny${basePath}`
})

// Watch for room_id changes in route query (e.g., when navigating from market to chat)
watch(() => route.query.room_id, (newRoomId) => {
  if (!newRoomId) return

  // Store in sessionStorage for persistence
  sessionStorage.setItem('cinny_pending_room', newRoomId)
  pendingRoomNavigation.value = newRoomId

  // Force iframe to load new URL with room in path
  if (cinnyIframe.value) {
    cinnyIframe.value.src = `/cinny/direct/${newRoomId}`
  }
})

onActivated(() => {
  isActive.value = true

  // Prevent page scroll (mobile keyboard fix)
  document.documentElement.style.overflow = 'hidden'
  document.body.style.overflow = 'hidden'
  document.documentElement.style.position = 'fixed'
  document.body.style.position = 'fixed'
  document.documentElement.style.width = '100%'
  document.body.style.width = '100%'
  document.documentElement.style.height = '100%'
  document.body.style.height = '100%'
})

onDeactivated(() => {
  isActive.value = false

  // Restore scroll
  document.documentElement.style.overflow = ''
  document.body.style.overflow = ''
  document.documentElement.style.position = ''
  document.body.style.position = ''
  document.documentElement.style.width = ''
  document.body.style.width = ''
  document.documentElement.style.height = ''
  document.body.style.height = ''
})

onBeforeUnmount(() => {
  // Clean up navigation tracking
  stopTrackingCinnyNavigation()

  // Clean up global error listeners
  window.removeEventListener('error', handleGlobalError)
  window.removeEventListener('unhandledrejection', handleGlobalError)

  // Restore scroll (safety)
  document.documentElement.style.overflow = ''
  document.body.style.overflow = ''
  document.documentElement.style.position = ''
  document.body.style.position = ''
  document.documentElement.style.width = ''
  document.body.style.width = ''
  document.documentElement.style.height = ''
  document.body.style.height = ''
})
</script>

<style>
.parahub-chat-iframe-container {
  position: fixed;
  /* Fills the band between the chrome bars, wherever the nav bar is docked */
  top: var(--nav-inset-top);
  left: 0;
  right: 0;
  bottom: var(--nav-inset-bottom);
  z-index: 40;
  background: rgb(250 250 250);
  overflow: hidden;
}

.dark .parahub-chat-iframe-container {
  background: rgb(23 23 23);
}

.parahub-chat-iframe-container.is-hidden {
  visibility: hidden;
  z-index: -1;
  pointer-events: none;
}
</style>
