<template>
  <div class="w-full h-full flex flex-col overflow-hidden bg-neutral-50 dark:bg-neutral-900">
    <!-- Mobile hamburger button (only visible on mobile) -->
    <button
      v-if="isMobile"
      @click="toggleElementPanel"
      class="fixed top-20 left-3 z-50 w-11 h-11 bg-emerald-600 text-white rounded-lg shadow-lg flex items-center justify-center text-2xl hover:bg-emerald-700 transition-colors md:hidden"
      aria-label="Toggle room list"
    >
      ☰
    </button>

    <!-- CRITICAL: Use Teleport to keep iframe in DOM outside KeepAlive scope -->
    <!-- This prevents iframe from being removed when component is deactivated -->
    <!-- Teleport to body to bypass KeepAlive component swapping -->
    <Teleport to="body">
      <div
        ref="iframeContainer"
        :class="['parahub-chat-iframe-container', { 'is-hidden': !isActive }]"
      >
        <iframe
          ref="elementIframe"
          :src="elementUrl"
          class="w-full h-full border-0"
          allow="microphone; camera; display-capture; clipboard-read; clipboard-write; fullscreen"
        />
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, onActivated, onDeactivated, onMounted, onBeforeUnmount, watch } from 'vue'

definePageMeta({
  middleware: 'auth',
  order: 3,
  keepalive: true  // Enable KeepAlive caching for instant switching
})

// Page title
useHead({
  title: 'Chat - Parahub'
})

const route = useRoute()
const elementIframe = ref(null)
const iframeContainer = ref(null)
const isActive = ref(true)  // Track active state for KeepAlive
const isMobile = ref(false)

// Detect mobile on mount
onMounted(() => {
  isMobile.value = window.innerWidth <= 768
  window.addEventListener('resize', () => {
    isMobile.value = window.innerWidth <= 768
  })

  // Auto-close left panel when room is selected on mobile
  if (isMobile.value) {
    setupAutoClosePanelOnRoomSelect()
  }
})

// Auto-close left panel when user selects a room (mobile only)
function setupAutoClosePanelOnRoomSelect() {
  // Wait for iframe to load
  const checkIframe = setInterval(() => {
    if (!elementIframe.value?.contentWindow) return

    try {
      // Monitor hash changes in iframe (when user navigates to a room)
      let lastHash = ''

      const checkHashChange = () => {
        try {
          const currentHash = elementIframe.value.contentWindow.location.hash

          // If hash changed to a room URL, close the panel
          if (currentHash !== lastHash && currentHash.includes('/room/')) {
            closeLeftPanel()
          }

          lastHash = currentHash
        } catch (e) {
          // Cross-origin, can't access hash
        }
      }

      // Check hash every 300ms
      setInterval(checkHashChange, 300)

      clearInterval(checkIframe)
    } catch (e) {
      // Cross-origin, can't access - skip
      clearInterval(checkIframe)
    }
  }, 500)

  // Stop trying after 10 seconds
  setTimeout(() => clearInterval(checkIframe), 10000)
}

// Close left panel (mobile)
function closeLeftPanel() {
  if (!elementIframe.value?.contentWindow) return

  try {
    const iframe = elementIframe.value
    const iframeDoc = iframe.contentDocument || iframe.contentWindow.document

    const leftPanel = iframeDoc.querySelector('.mx_LeftPanel_outerWrapper')
    if (leftPanel) {
      leftPanel.removeAttribute('data-parahub-open')
      leftPanel.classList.remove('mx_LeftPanel--opened')
    }

    // CRITICAL: Also remove overlay that was created when panel was opened
    const overlay = iframeDoc.getElementById('parahub-overlay')
    if (overlay) {
      overlay.remove()
    }

    // Also update hamburger button icon if it exists
    const hamburgerBtn = iframeDoc.getElementById('parahub-hamburger-btn')
    if (hamburgerBtn) {
      hamburgerBtn.innerHTML = '☰'
    }
  } catch (e) {
    // Cross-origin, can't close panel
  }
}

// Toggle left panel in Element iframe
function toggleElementPanel() {
  if (!elementIframe.value?.contentWindow) return

  try {
    // Try direct DOM access (works if same-origin)
    const iframe = elementIframe.value
    const iframeDoc = iframe.contentDocument || iframe.contentWindow.document

    // Find hamburger button inside Element
    const elementButton = iframeDoc.querySelector('#parahub-hamburger-btn')
    if (elementButton) {
      elementButton.click()
      return
    }
  } catch (e) {
    // Cross-origin, fall through to postMessage
  }

  // Fallback: Use postMessage for cross-origin
  elementIframe.value.contentWindow.postMessage({
    type: 'parahub-toggle-panel'
  }, '*')
}

// Generate Element URL based on query params (only once on mount)
const elementUrl = computed(() => {
  const roomId = route.query.room_id
  const contactAccountId = route.query.contact_account_id

  if (roomId) {
    // Open existing room directly
    return `/element/#/room/${encodeURIComponent(roomId)}`
  }

  if (contactAccountId) {
    // Legacy: Generate Matrix user ID and open user profile
    // @{account_id.lower().replace('-', '_')}:parahub.io
    const matrixUserId = `@${contactAccountId.toLowerCase().replace(/-/g, '_')}:parahub.io`

    // Open DM with user (Element will create room if needed)
    return `/element/#/user/${encodeURIComponent(matrixUserId)}?action=chat`
  }

  // Default: home screen
  return '/element/#/home'
})


// KeepAlive: Component is now visible again
onActivated(() => {
  isActive.value = true

  // If navigating to chat with new contact, update iframe src
  const newUrl = elementUrl.value
  if (elementIframe.value) {
    const currentUrl = elementIframe.value.src
    // Only update if URL actually changed (avoid unnecessary navigation)
    if (currentUrl && !currentUrl.endsWith(newUrl.split('#')[1])) {
      // Use hash navigation instead of full reload to preserve Element state
      const hash = newUrl.split('#')[1]
      if (hash && elementIframe.value.contentWindow) {
        elementIframe.value.contentWindow.location.hash = `#${hash}`
      }
    }
  }
})

// KeepAlive: Component is being hidden
onDeactivated(() => {
  isActive.value = false
  // iframe stays in body DOM, just hidden via CSS
})

// Clean up on component destroy (not just deactivation)
onBeforeUnmount(() => {
  // iframe will be removed by Teleport cleanup
})
</script>

<style>
/* Global styles for teleported iframe container */
.parahub-chat-iframe-container {
  position: fixed;
  /* Match navbar responsive height (h-14/sm:h-16/md:h-20) + safe area for notched devices */
  top: calc(3.5rem + var(--safe-area-inset-top, env(safe-area-inset-top, 0px)));
  left: 0;
  right: 0;
  bottom: var(--safe-area-inset-bottom, env(safe-area-inset-bottom, 0px));
  z-index: 40; /* Above most content, below modals */
  background: rgb(250 250 250); /* bg-neutral-50 */
}

@media (min-width: 640px) {
  .parahub-chat-iframe-container {
    top: calc(4rem + var(--safe-area-inset-top, env(safe-area-inset-top, 0px)));
  }
}

@media (min-width: 768px) {
  .parahub-chat-iframe-container {
    top: calc(5rem + var(--safe-area-inset-top, env(safe-area-inset-top, 0px)));
  }
}

/* Dark mode support */
.dark .parahub-chat-iframe-container {
  background: rgb(23 23 23); /* bg-neutral-900 */
}

/* Hidden state - use visibility + z-index to keep iframe alive */
.parahub-chat-iframe-container.is-hidden {
  visibility: hidden;
  z-index: -1;
  pointer-events: none;
}
</style>
