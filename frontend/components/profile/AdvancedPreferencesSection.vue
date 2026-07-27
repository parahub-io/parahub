<template>
  <div class="bg-white dark:bg-neutral-800 rounded-xl border border-neutral-200 dark:border-neutral-700 p-4">
    <div class="space-y-4">
      <!-- Transit comet trails -->
      <div>
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
          {{ $t('profile.preferences.trails_label') }}
        </label>
        <div class="flex items-center gap-3">
          <button
            @click="toggleTransitTrails"
            class="relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
            :class="transitTrailsEnabled ? 'bg-primary' : 'bg-neutral-300 dark:bg-neutral-600'"
            :aria-label="$t('profile.preferences.trails_label')"
            :aria-pressed="transitTrailsEnabled"
          >
            <span
              class="inline-block h-4 w-4 transform rounded-full bg-white transition-transform"
              :class="transitTrailsEnabled ? 'translate-x-6' : 'translate-x-1'"
            />
          </button>
          <span class="text-sm text-neutral-700 dark:text-neutral-300">
            {{ transitTrailsEnabled ? $t('profile.preferences.trails_enabled') : $t('profile.preferences.trails_disabled') }}
          </span>
        </div>
        <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-2">
          {{ $t('profile.preferences.trails_hint') }}
        </p>
      </div>

      <!-- Map Avatar (MMORPG presence) -->
      <div>
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
          {{ $t('profile.preferences.map_presence_label') }}
        </label>
        <div class="flex items-center gap-3">
          <button
            @click="toggleMapPresence"
            class="relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
            :class="mapPresenceEnabled ? 'bg-primary' : 'bg-neutral-300 dark:bg-neutral-600'"
            :aria-label="$t('profile.preferences.map_presence_label')"
            :aria-pressed="mapPresenceEnabled"
          >
            <span
              class="inline-block h-4 w-4 transform rounded-full bg-white transition-transform"
              :class="mapPresenceEnabled ? 'translate-x-6' : 'translate-x-1'"
            />
          </button>
          <span class="text-sm text-neutral-700 dark:text-neutral-300">
            {{ mapPresenceEnabled ? $t('profile.preferences.map_presence_enabled') : $t('profile.preferences.map_presence_disabled') }}
          </span>
        </div>
        <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-2">
          {{ $t('profile.preferences.map_presence_hint') }}
        </p>
      </div>

      <!-- Dev Server Toggle (only visible to developers) -->
      <div v-if="showDevToggle" class="border-t border-neutral-200 dark:border-neutral-700 pt-4 mt-4">
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
          <span class="inline-flex items-center gap-2">
            <Code class="w-4 h-4 text-orange-500" />
            {{ $t('profile.preferences.dev_mode_label') || 'Developer Mode' }}
          </span>
        </label>
        <div class="flex items-center gap-3">
          <button
            @click="toggleDevMode"
            class="relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
            :class="devModeEnabled ? 'bg-orange-500' : 'bg-neutral-300 dark:bg-neutral-600'"
            :aria-label="$t('profile.preferences.dev_mode_label') || 'Developer Mode'"
            :aria-pressed="devModeEnabled"
          >
            <span
              class="inline-block h-4 w-4 transform rounded-full bg-white transition-transform"
              :class="devModeEnabled ? 'translate-x-6' : 'translate-x-1'"
            />
          </button>
          <span class="text-sm text-neutral-700 dark:text-neutral-300">
            {{ devModeEnabled
               ? ($t('profile.preferences.dev_mode_enabled') || 'Using dev server')
               : ($t('profile.preferences.dev_mode_disabled') || 'Using production server') }}
          </span>
        </div>
        <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-2">
          {{ $t('profile.preferences.dev_mode_hint') || 'Switch between development and production servers. Page will reload.' }}
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Code } from 'lucide-vue-next'
import { useNotification } from '~/composables/useNotification'
import { useAuthStore } from '~/stores/auth'

const { t } = useI18n()
const { showSuccess } = useNotification()
const authStore = useAuthStore()

// Transit comet trails preference (localStorage, shared with useMapTransitLayers)
const transitTrailsEnabled = useLocalPref('transit_trails_enabled', true)

// Map presence (MMORPG avatar) preference (localStorage, shared with useMapAvatarPanel)
const mapPresenceEnabled = useLocalPref('map_presence_enabled', false)

const toggleTransitTrails = () => {
  transitTrailsEnabled.value = !transitTrailsEnabled.value
  showSuccess(
    transitTrailsEnabled.value
      ? t('profile.preferences.trails_enabled')
      : t('profile.preferences.trails_disabled')
  )
}

const toggleMapPresence = () => {
  mapPresenceEnabled.value = !mapPresenceEnabled.value
  showSuccess(
    mapPresenceEnabled.value
      ? t('profile.preferences.map_presence_enabled')
      : t('profile.preferences.map_presence_disabled')
  )
}

// Dev mode cookie
// nginx reads this cookie RAW ($cookie_parahub_dev map) — Nuxt's default encode
// JSON-quotes numeric-looking strings ('1' → %221%22), breaking routing. The
// explicit decode must stay paired with it: the default decode destr's '1'
// into a number, breaking the === '1' checks.
const devModeCookie = useCookie('parahub_dev', {
  default: () => '',
  maxAge: 86400 * 400, // 400 days — browser-max ("indefinite"); Chrome/Edge clamp any longer lifetime to 400 days
  sameSite: 'lax',
  watch: true,
  encode: (v: any) => encodeURIComponent(String(v ?? '')),
  decode: (v: string) => v ? decodeURIComponent(v) : v
})

const devModeEnabled = ref(false)
const clientHasCookie = ref(false)

// Show dev toggle only if:
// 1. User is staff/superuser (admin), OR
// 2. Cookie is already set (developer already enabled it via console)
const showDevToggle = computed(() => {
  // is_staff comes from API in profile object
  const isAdmin = authStore.user?.is_staff || authStore.user?.profile?.is_staff
  const hasCookie = devModeCookie.value === '1' || clientHasCookie.value
  return isAdmin || hasCookie
})

onMounted(() => {
  // Check cookie on client side (SSR might not see browser cookies)
  if (typeof document !== 'undefined') {
    clientHasCookie.value = document.cookie.includes('parahub_dev=1')
  }
  devModeEnabled.value = devModeCookie.value === '1' || clientHasCookie.value
})

const toggleDevMode = () => {
  devModeEnabled.value = !devModeEnabled.value
  if (devModeEnabled.value) {
    devModeCookie.value = '1'
    showSuccess(t('profile.preferences.dev_mode_enabled') || 'Switched to dev server')
  } else {
    devModeCookie.value = null // Remove cookie
    showSuccess(t('profile.preferences.dev_mode_disabled') || 'Switched to production server')
  }
  // Reload page to apply new server
  setTimeout(() => {
    window.location.reload()
  }, 500)
}
</script>
