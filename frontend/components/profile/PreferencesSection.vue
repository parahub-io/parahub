<template>
  <div class="bg-white dark:bg-neutral-800 rounded-xl border border-neutral-200 dark:border-neutral-700 p-4">
    <div class="space-y-4">
      <!-- Display Name -->
      <div>
        <label for="pref-display-name" class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
          {{ $t('profile.preferences.display_name_label') }}
        </label>
        <div class="flex items-center gap-2">
          <input
            id="pref-display-name"
            v-model="displayName"
            type="text"
            maxlength="100"
            class="flex-1 px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
            :placeholder="$t('profile.preferences.display_name_placeholder')"
            @keyup.enter="saveDisplayName"
          />
          <button
            @click="saveDisplayName"
            :disabled="displayNameSaving || displayName === originalDisplayName"
            class="px-4 py-2 bg-primary hover:bg-primary/90 disabled:bg-neutral-300 dark:disabled:bg-neutral-600 rounded-lg text-black disabled:text-neutral-500 font-medium transition-colors"
          >
            <span v-if="!displayNameSaving">{{ $t('common.save') }}</span>
            <span v-else>...</span>
          </button>
        </div>
        <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-2">
          {{ $t('profile.preferences.display_name_hint') }}
        </p>
      </div>

      <!-- Name Visibility (privacy opt-out) -->
      <div>
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
          {{ $t('profile.preferences.name_public_label') }}
        </label>
        <div class="flex items-center gap-3">
          <button
            @click="toggleNamePublic"
            class="relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
            :class="namePublic ? 'bg-primary' : 'bg-neutral-300 dark:bg-neutral-600'"
            :aria-label="$t('profile.preferences.name_public_label')"
            :aria-pressed="namePublic"
          >
            <span
              class="inline-block h-4 w-4 transform rounded-full bg-white transition-transform"
              :class="namePublic ? 'translate-x-6' : 'translate-x-1'"
            />
          </button>
          <span class="text-sm text-neutral-700 dark:text-neutral-300">
            {{ namePublic ? $t('profile.preferences.name_public_enabled') : $t('profile.preferences.name_public_disabled') }}
          </span>
        </div>
        <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-2">
          {{ $t('profile.preferences.name_public_hint') }}
        </p>
      </div>

      <!-- Push Notifications -->
      <div>
        <PushNotificationToggle />
      </div>

      <!-- Notification Categories (only when push is enabled) -->
      <div v-if="pushSubscribed" role="group" :aria-labelledby="notifGroupId">
        <label :id="notifGroupId" class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
          {{ $t('profile.preferences.notifications_label') }}
        </label>
        <p class="text-xs text-neutral-500 dark:text-neutral-400 mb-3">
          {{ $t('profile.preferences.notifications_hint') }}
        </p>
        <div class="space-y-3">
          <div v-for="cat in notifCategories" :key="cat.key" class="flex items-center justify-between gap-3">
            <div class="flex-1 min-w-0">
              <span class="text-sm text-neutral-700 dark:text-neutral-300">{{ cat.label }}</span>
              <span class="text-xs text-neutral-500 dark:text-neutral-400 ml-1">— {{ cat.hint }}</span>
            </div>
            <button
              @click="toggleNotifCategory(cat.key)"
              class="relative inline-flex h-6 w-11 flex-shrink-0 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
              :class="notifPrefs[cat.key] ? 'bg-primary' : 'bg-neutral-300 dark:bg-neutral-600'"
              :aria-label="cat.label"
              :aria-pressed="notifPrefs[cat.key]"
            >
              <span
                class="inline-block h-4 w-4 transform rounded-full bg-white transition-transform"
                :class="notifPrefs[cat.key] ? 'translate-x-6' : 'translate-x-1'"
              />
            </button>
          </div>
        </div>
        <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-3">
          {{ $t('profile.preferences.notify_sos_managed') }} ·
          <NuxtLink :to="localePath('/sos')" class="text-link">{{ $t('profile.preferences.notify_sos_link') }}</NuxtLink>
        </p>
      </div>

      <!-- Theme Preference -->
      <div>
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
          {{ $t('profile.preferences.theme_label') || 'Theme' }}
        </label>
        <div class="flex items-center gap-3">
          <button
            @click="cycleColorMode"
            :key="'theme-btn-' + colorMode.preference"
            class="flex items-center gap-2 px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 hover:bg-neutral-50 dark:hover:bg-neutral-600 transition-colors text-neutral-900 dark:text-neutral-100"
            :aria-label="$t('profile.preferences.theme_label')"
          >
            <component :is="themeIcon" class="w-5 h-5" />
            <span class="text-sm font-medium">{{ themeLabel }}</span>
          </button>
        </div>
        <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-2">
          {{ $t('profile.preferences.theme_hint') || 'Choose your preferred color theme' }}
        </p>
      </div>

      <!-- Map Animation Preference -->
      <div>
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
          {{ $t('profile.preferences.animation_label') }}
        </label>
        <div class="flex items-center gap-3">
          <button
            @click="toggleAnimation"
            class="relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
            :class="animationEnabled ? 'bg-primary' : 'bg-neutral-300 dark:bg-neutral-600'"
            :aria-label="$t('profile.preferences.animation_label')"
            :aria-pressed="animationEnabled"
          >
            <span
              class="inline-block h-4 w-4 transform rounded-full bg-white transition-transform"
              :class="animationEnabled ? 'translate-x-6' : 'translate-x-1'"
            />
          </button>
          <span class="text-sm text-neutral-700 dark:text-neutral-300">
            {{ animationEnabled ? $t('profile.preferences.animation_enabled') : $t('profile.preferences.animation_disabled') }}
          </span>
        </div>
        <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-2">
          {{ $t('profile.preferences.animation_hint') }}
        </p>
      </div>

      <!-- Chat Client Preference - DISABLED: Cinny is default, no selection available yet -->
      <!--
      <div>
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
          {{ $t('profile.preferences.chat_client_label') }}
        </label>
        <select
          v-model="selectedChatClient"
          @change="updateChatClient"
          class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100"
          :aria-label="$t('profile.preferences.chat_client_label')"
        >
          <option value="element">Element (Desktop)</option>
          <option value="fluffy">FluffyChat (Mobile)</option>
          <option value="cinny">Cinny (Lightweight)</option>
        </select>
        <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-2">
          {{ $t('profile.preferences.chat_client_hint') }}
        </p>
      </div>
      -->

      <!-- Advanced settings → dedicated page (keeps this page uncluttered) -->
      <NuxtLink
        :to="localePath('/profile/advanced')"
        class="flex items-center justify-between gap-3 -mx-4 -mb-4 mt-2 px-4 py-3 min-h-[44px] border-t border-neutral-200 dark:border-neutral-700 rounded-b-xl hover:bg-neutral-50 dark:hover:bg-neutral-700/50 transition-colors"
      >
        <span class="inline-flex items-center gap-2 text-sm font-medium text-neutral-700 dark:text-neutral-300">
          <SlidersHorizontal class="w-4 h-4 text-neutral-400" />
          {{ $t('profile.preferences.advanced_title') }}
        </span>
        <ChevronRight class="w-4 h-4 text-neutral-400" />
      </NuxtLink>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { Sun, Moon, Monitor, SlidersHorizontal, ChevronRight } from 'lucide-vue-next'
import { useNotification } from '~/composables/useNotification'
import { useAuthStore } from '~/stores/auth'
import { savePrefToBackend } from '~/composables/usePreferencesSync'

const props = defineProps<{
  animationEnabled: boolean
}>()

const emit = defineEmits<{
  'update:animationEnabled': [enabled: boolean]
}>()

const { t } = useI18n()
const localePath = useLocalePath()
const colorMode = useColorMode()
const { showSuccess, showError } = useNotification()
const authStore = useAuthStore()

// Push subscription state (to conditionally show notification categories)
const { isSubscribed: pushSubscribed } = usePushNotifications()

// Notification category preferences
const notifGroupId = useId()
type NotifCategory = 'social' | 'contracts' | 'governance' | 'calls' | 'rental'

const notifPrefs = reactive<Record<NotifCategory, boolean>>({
  social: true,
  contracts: true,
  governance: true,
  calls: true,
  rental: true,
})

const notifCategories = computed(() => [
  { key: 'social' as NotifCategory, label: t('profile.preferences.notify_social'), hint: t('profile.preferences.notify_social_hint') },
  { key: 'contracts' as NotifCategory, label: t('profile.preferences.notify_contracts'), hint: t('profile.preferences.notify_contracts_hint') },
  { key: 'rental' as NotifCategory, label: t('profile.preferences.notify_rental'), hint: t('profile.preferences.notify_rental_hint') },
  { key: 'governance' as NotifCategory, label: t('profile.preferences.notify_governance'), hint: t('profile.preferences.notify_governance_hint') },
  { key: 'calls' as NotifCategory, label: t('profile.preferences.notify_calls'), hint: t('profile.preferences.notify_calls_hint') },
])

let notifPatchTimer: ReturnType<typeof setTimeout> | null = null

const toggleNotifCategory = (key: NotifCategory) => {
  notifPrefs[key] = !notifPrefs[key]

  // Debounced save to backend
  if (notifPatchTimer) clearTimeout(notifPatchTimer)
  notifPatchTimer = setTimeout(async () => {
    try {
      await authStore.ensureToken()
      await $fetch('/api/v1/profiles/me/preferences/', {
        method: 'PATCH',
        credentials: 'include',
        headers: {
          'Authorization': `Bearer ${authStore.token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          notification_prefs: { ...notifPrefs }
        })
      })
      if (authStore.profile) {
        authStore.profile.notification_prefs = { ...notifPrefs }
      }
    } catch (e) {
      console.warn('[prefs] Failed to save notification prefs:', e)
    }
  }, 500)
}

// Display name
const displayName = ref('')
const originalDisplayName = ref('')
const displayNameSaving = ref(false)

// Name visibility (privacy opt-out): when false, only the @handle is public
const namePublic = ref(false)

const toggleNamePublic = async () => {
  const next = !namePublic.value
  namePublic.value = next
  try {
    await authStore.ensureToken()
    await $fetch('/api/v1/profiles/me/preferences/', {
      method: 'PATCH',
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ name_public: next })
    })
    if (authStore.profile) authStore.profile.name_public = next
    showSuccess(next
      ? t('profile.preferences.name_public_enabled')
      : t('profile.preferences.name_public_disabled'))
  } catch (error) {
    namePublic.value = !next // revert on failure
    console.error('Failed to update name visibility:', error)
    showError(t('profile.preferences.display_name_update_failed'))
  }
}

onMounted(() => {
  // Load display name from profile
  displayName.value = authStore.profile?.display_name || ''
  originalDisplayName.value = displayName.value

  // Load name visibility preference
  namePublic.value = Boolean(authStore.profile?.name_public)

  // Load notification preferences (empty object = all enabled by default)
  const saved = authStore.profile?.notification_prefs
  if (saved && typeof saved === 'object') {
    for (const key of ['social', 'contracts', 'governance', 'calls', 'rental'] as NotifCategory[]) {
      if (key in saved) {
        notifPrefs[key] = Boolean(saved[key])
      }
    }
  }
})

const saveDisplayName = async () => {
  if (displayNameSaving.value || displayName.value === originalDisplayName.value) return

  displayNameSaving.value = true
  try {
    await authStore.ensureToken()
    await $fetch('/api/v1/profiles/me/preferences/', {
      method: 'PATCH',
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        display_name: displayName.value
      })
    })
    originalDisplayName.value = displayName.value
    // Update store
    if (authStore.profile) {
      authStore.profile.display_name = displayName.value
    }
    showSuccess(t('profile.preferences.display_name_updated'))
  } catch (error) {
    console.error('Failed to update display name:', error)
    showError(t('profile.preferences.display_name_update_failed'))
  } finally {
    displayNameSaving.value = false
  }
}

// Animation enabled preference (localStorage, shared with useMapIoTLayers)
const localAnimationEnabled = useLocalPref('animation_enabled', true)

// Use cookie for chat client preference
const selectedChatClient = useCookie('preferred_chat_client', {
  default: () => 'cinny',
  maxAge: 365 * 24 * 60 * 60, // 1 year
  sameSite: 'lax',
  watch: true
})

const toggleAnimation = () => {
  localAnimationEnabled.value = !localAnimationEnabled.value
  emit('update:animationEnabled', localAnimationEnabled.value)
  savePrefToBackend('animation_enabled', localAnimationEnabled.value)
  showSuccess(
    localAnimationEnabled.value
      ? t('profile.preferences.animation_enabled')
      : t('profile.preferences.animation_disabled')
  )
}

// Theme computed properties for stable rendering
const themeIcon = computed(() => {
  switch (colorMode.preference) {
    case 'light': return Sun
    case 'dark': return Moon
    default: return Monitor
  }
})

const themeLabel = computed(() => {
  switch (colorMode.preference) {
    case 'light': return t('profile.preferences.theme_light') || 'Light'
    case 'dark': return t('profile.preferences.theme_dark') || 'Dark'
    default: return t('profile.preferences.theme_system') || 'System'
  }
})

const cycleColorMode = () => {
  const modes = ['system', 'light', 'dark'] as const
  const currentIndex = modes.indexOf(colorMode.preference as any)
  const nextIndex = (currentIndex + 1) % modes.length
  colorMode.preference = modes[nextIndex]
}

// DISABLED: Chat client selection temporarily disabled (Cinny is default)
/*
const updateChatClient = () => {
  const clientNames = {
    'element': 'Element',
    'fluffy': 'FluffyChat',
    'cinny': 'Cinny'
  }
  const clientName = clientNames[selectedChatClient.value] || 'Element'
  showSuccess(t('profile.preferences.chat_client_updated', { client: clientName }))
}
*/
</script>
