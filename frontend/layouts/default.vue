<template>
  <div :class="['layout-container flex flex-col overflow-x-hidden overflow-y-hidden', isDashboard && 'dashboard-layout-bg']">
    <!-- Background particles on dashboard only -->
    <VfxParticles v-if="isDashboard" />
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

    <!-- Navigation -->
    <AppNavigation class="z-20" />

    <!-- Spacer for fixed navbar (matches navbar height + safe area inset for notched devices) -->
    <div class="h-14 sm:h-16 md:h-20 flex-shrink-0 relative z-10 safe-area-spacer-top"></div>

    <!-- Main content - full width and height, scroll inside -->
    <main id="main-content" role="main" class="flex-1 relative overflow-y-auto overflow-x-hidden main-content z-10">
      <slot />
    </main>

    <!-- First-time user onboarding -->
    <OnboardingWelcomeModal v-if="showOnboarding" v-model="showOnboarding" />
  </div>
</template>

<script setup>
import { useAuthStore } from '~/stores/auth'

const route = useRoute()
const authStore = useAuthStore()
const isDashboard = computed(() => {
  const name = route.name?.toString().replace(/___[a-z]{2}$/, '') || ''
  return name === 'index' && authStore.isAuthenticated
})

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
   Subtract bottom safe area so Android nav bar sits on empty space. */
.layout-container {
  height: 100vh; /* Fallback for older browsers */
  height: calc(100dvh - var(--safe-area-inset-bottom, env(safe-area-inset-bottom, 0px)));
}

/* Safety padding for scrollable content bottom */
.main-content {
  padding-bottom: 0.5rem;
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

/* Dashboard background: white for light mode, black for dark mode */
.dashboard-layout-bg {
  background: white;
}
:root.dark .dashboard-layout-bg {
  background: black;
}
</style>
