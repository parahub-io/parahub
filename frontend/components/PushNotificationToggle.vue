<template>
  <div class="p-4 border border-neutral-200 dark:border-neutral-700 rounded-lg">
    <div class="flex items-center justify-between gap-4">
      <div class="flex-1">
        <h3 class="font-medium text-neutral-900 dark:text-neutral-100">{{ $t('profile.preferences.push_notifications_title') }}</h3>
        <p class="text-sm text-neutral-600 dark:text-neutral-400">
          {{ $t('profile.preferences.push_notifications_description') }}
        </p>
      </div>

      <div class="flex items-center gap-2">
        <button
          v-if="!isSupported"
          disabled
          class="px-4 py-2 text-sm text-neutral-500 bg-neutral-100 dark:bg-neutral-700 rounded cursor-not-allowed"
        >
          {{ $t('profile.preferences.push_not_supported') }}
        </button>

        <button
          v-else-if="permission === 'denied'"
          disabled
          class="px-4 py-2 text-sm text-error bg-error-50 dark:bg-error-900/20 rounded cursor-not-allowed"
        >
          {{ $t('profile.preferences.push_permission_denied') }}
        </button>

        <button
          v-else-if="isSubscribed"
          @click="handleUnsubscribe"
          :disabled="isLoading"
          class="btn-secondary btn-sm rounded"
        >
          {{ isLoading ? $t('profile.preferences.push_loading') : $t('profile.preferences.push_enabled') }}
        </button>

        <button
          v-else
          @click="handleSubscribe"
          :disabled="isLoading"
          class="px-4 py-2 text-sm text-white bg-neutral-600 rounded hover:bg-neutral-700 disabled:opacity-50"
        >
          {{ isLoading ? $t('profile.preferences.push_loading') : $t('profile.preferences.push_enable') }}
        </button>
      </div>
    </div>

    <!-- Permission hint -->
    <div v-if="permission === 'denied'" class="mt-2 text-sm text-error">
      {{ $t('profile.preferences.push_permission_hint') }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { useNotification } from '~/composables/useNotification'

const { t } = useI18n()
const { showError, showSuccess } = useNotification()

const {
  isSupported,
  isSubscribed,
  permission,
  isLoading,
  subscribe,
  unsubscribe
} = usePushNotifications()

const handleSubscribe = async () => {
  const success = await subscribe()
  if (success) {
    showSuccess(t('profile.preferences.push_subscribed', 'Push notifications enabled'))
  } else if (permission.value === 'denied') {
    showError(t('profile.preferences.push_permission_denied_hint', 'Please enable notifications in browser settings'))
  } else {
    showError(t('profile.preferences.push_subscription_failed', 'Failed to enable push notifications. Check your network or try a different browser.'))
  }
}

const handleUnsubscribe = async () => {
  const success = await unsubscribe()
  if (success) {
    showSuccess(t('profile.preferences.push_unsubscribed', 'Push notifications disabled'))
  }
}
</script>

