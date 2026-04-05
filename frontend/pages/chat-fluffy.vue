<template>
  <div class="w-full h-full flex flex-col overflow-hidden bg-neutral-50 dark:bg-neutral-900">
    <!-- CRITICAL: Use Teleport to keep iframe in DOM outside KeepAlive scope -->
    <!-- This prevents iframe from being removed when component is deactivated -->
    <!-- Teleport to body to bypass KeepAlive component swapping -->
    <Teleport to="body">
      <div
        ref="iframeContainer"
        :class="['parahub-chat-iframe-container', { 'is-hidden': !isActive }]"
      >
        <iframe
          ref="fluffychatIframe"
          :src="fluffychatUrl"
          class="w-full h-full border-0"
          allow="microphone; camera; display-capture; clipboard-read; clipboard-write; fullscreen"
        />
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, onActivated, onDeactivated, onMounted, onBeforeUnmount } from 'vue'

definePageMeta({
  middleware: 'auth',
  order: 4,
  keepalive: true  // Enable KeepAlive caching for instant switching
})

// Page title
useHead({
  title: 'Chat (Mobile) - Parahub'
})

const route = useRoute()
const fluffychatIframe = ref(null)
const iframeContainer = ref(null)
const isActive = ref(true)  // Track active state for KeepAlive

onMounted(() => {})

// Generate FluffyChat URL based on query params
// Note: FluffyChat will auto-detect homeserver from .well-known/matrix/client
const fluffychatUrl = computed(() => {
  const roomId = route.query.room_id
  const contactAccountId = route.query.contact_account_id

  // FluffyChat should use SSO login automatically
  // Set homeserver in URL to skip manual selection
  const baseUrl = '/fluffychat/#/'

  if (roomId) {
    // Open existing room directly
    // FluffyChat routing: /rooms/{roomId}
    return `/fluffychat/#/rooms/${encodeURIComponent(roomId)}`
  }

  if (contactAccountId) {
    // Generate Matrix user ID and open DM
    const matrixUserId = `@${contactAccountId.toLowerCase()}:parahub.io`

    // FluffyChat: open user profile or DM
    return `/fluffychat/#/newprivatechat/${encodeURIComponent(matrixUserId)}`
  }

  // Default: home screen with homeserver pre-filled
  // FluffyChat will detect parahub.io from .well-known and offer SSO login
  return baseUrl
})

// KeepAlive: Component is now visible again
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

  // If navigating to chat with new room, update iframe src
  const newUrl = fluffychatUrl.value
  if (fluffychatIframe.value) {
    const currentUrl = fluffychatIframe.value.src
    // Only update if URL actually changed (avoid unnecessary navigation)
    if (currentUrl && !currentUrl.endsWith(newUrl.split('#')[1])) {
      // Use hash navigation instead of full reload
      const hash = newUrl.split('#')[1]
      if (hash && fluffychatIframe.value.contentWindow) {
        fluffychatIframe.value.contentWindow.location.hash = `#${hash}`
      }
    }
  }
})

// KeepAlive: Component is being hidden
onDeactivated(() => {
  isActive.value = false

  // Restore normal scroll behavior
  document.documentElement.style.overflow = ''
  document.body.style.overflow = ''
  document.documentElement.style.position = ''
  document.body.style.position = ''
  document.documentElement.style.width = ''
  document.body.style.width = ''
  document.documentElement.style.height = ''
  document.body.style.height = ''

  // iframe stays in body DOM, just hidden via CSS
})

// Clean up on component destroy (not just deactivation)
onBeforeUnmount(() => {
  // Restore normal scroll behavior (safety cleanup)
  document.documentElement.style.overflow = ''
  document.body.style.overflow = ''
  document.documentElement.style.position = ''
  document.body.style.position = ''
  document.documentElement.style.width = ''
  document.body.style.width = ''
  document.documentElement.style.height = ''
  document.body.style.height = ''

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
  overflow: hidden; /* Prevent iframe container scroll */
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
