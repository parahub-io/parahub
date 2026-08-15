<template>
  <div class="layout-container flex flex-col overflow-x-hidden overflow-y-hidden">
    <!-- Skip navigation link -->
    <a
      href="#main-content"
      class="skip-link sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 bg-primary text-black px-4 py-2 rounded-md z-50 font-medium"
    >
      {{ $t('skipToContent') }}
    </a>

    <!-- ARIA live regions for screen reader announcements -->
    <div id="announcements" aria-live="polite" aria-atomic="true" class="sr-only"></div>
    <div id="urgent-announcements" aria-live="assertive" aria-atomic="true" class="sr-only"></div>

    <!-- Navigation (multi-root component — the header inside carries its own fixed z-50) -->
    <AppNavigation />

    <!-- Chrome spacers: one band per edge, each the size of whatever occupies
         that edge (nav bar on one, bare safe area on the other — the bar docks
         bottom on phones and top on md+). Symmetric by design, so <main> gets
         exactly the space between them in both modes. -->
    <div class="flex-shrink-0 relative z-10 nav-spacer-top"></div>

    <!-- Main content - full width and height, scroll inside -->
    <main id="main-content" role="main" class="flex-1 relative overflow-y-auto overflow-x-hidden main-content z-10">
      <slot />
    </main>

    <div class="flex-shrink-0 relative z-10 nav-spacer-bottom"></div>

    <!-- First-time user onboarding -->
    <OnboardingWelcomeModal v-if="showOnboarding" v-model="showOnboarding" />
  </div>
</template>

<script setup>
import { useAuthStore } from '~/stores/auth'

const authStore = useAuthStore()

// Onboarding modal for first-time authenticated users
// Uses watch instead of onMounted because auth state resolves asynchronously
// (dashboard's ensureSession() completes after layout mounts)
const showOnboarding = ref(false)

// Global SOS watcher — siren on EMERGENCY alerts (browser Web Audio)
const sosWatcher = useSosWatcher()

onMounted(() => {
  const unwatch = watch(() => authStore.isAuthenticated, (isAuth) => {
    if (isAuth && !localStorage.getItem('parahub_onboarding_seen')) {
      showOnboarding.value = true
      nextTick(() => unwatch())
    }
    // Start SOS watcher when authenticated
    if (isAuth) sosWatcher.start()
  }, { immediate: true })
})
</script>

<style scoped>
/* Dynamic viewport height - fixes mobile browser UI (address bar) issues.
   Full height here: the safe areas are carved out by the two chrome spacers,
   whichever edge each one lands on. */
.layout-container {
  height: 100vh; /* Fallback for older browsers */
  height: 100dvh;
}

/* Both resolve to "nav bar + its safe area" on the docked edge and to the bare
   safe area on the other — see main.css § Navigation dock insets. */
.nav-spacer-top {
  height: var(--nav-inset-top);
}
.nav-spacer-bottom {
  height: var(--nav-inset-bottom);
  transition: height 0.18s ease-out; /* tracks the keyboard slide-out */
}

/* Safety padding for scrollable content bottom */
.main-content {
  padding-bottom: 0.5rem;
  /* Reserve the scrollbar gutter permanently so the layout width never shifts
     when a page's content height briefly collapses (e.g. tab switch loading
     empties a list → scrollbar disappears → centered content reflows). No-op
     on overlay-scrollbar platforms (macOS/mobile). */
  scrollbar-gutter: stable;
}

.skip-link {
  position: absolute;
  top: -40px;
  left: 6px;
  background: var(--color-primary);
  color: black;
  padding: 8px;
  border-radius: 4px;
  text-decoration: none;
  font-weight: 600;
  z-index: 100;
}

.skip-link:focus {
  top: 6px;
}
</style>
