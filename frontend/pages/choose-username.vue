<template>
  <div class="min-h-screen flex items-center justify-center bg-neutral-50 dark:bg-neutral-900 px-4 py-8">
    <div class="w-full max-w-lg">
      <!-- Logo -->
      <div class="flex justify-center mb-6">
        <NuxtLink :to="localePath('/')" class="inline-block">
          <img src="/logo.svg" alt="Parahub" class="h-10 w-auto dark:invert" />
        </NuxtLink>
      </div>

      <div class="bg-white dark:bg-neutral-800 rounded-2xl p-6 md:p-8">
        <h1 class="text-2xl font-bold text-center mb-2 text-neutral-900 dark:text-neutral-100">
          {{ $t('choose_username.title') }}
        </h1>
        <p class="text-center text-neutral-600 dark:text-neutral-400 mb-6">
          {{ $t('choose_username.subtitle') }}
        </p>

        <!-- Username Selection -->
        <div class="space-y-4 mb-6">
          <div>
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">
              {{ $t('choose_username.username_label') }}
            </label>
            <div class="flex gap-2">
              <input
                v-model="username"
                type="text"
                :class="[
                  'flex-1 px-3 py-2.5 border rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-all',
                  usernameError ? 'border-red-500 dark:border-red-500' : 'border-neutral-300 dark:border-neutral-600'
                ]"
                :placeholder="$t('choose_username.username_placeholder')"
                @input="debouncedCheckAvailability"
              />
              <button
                @click="generateNewUsername"
                :disabled="generatingUsername"
                class="px-3 py-2.5 bg-neutral-100 dark:bg-neutral-700 hover:bg-neutral-200 dark:hover:bg-neutral-600 border border-neutral-300 dark:border-neutral-600 rounded-lg transition-colors disabled:opacity-50"
                :title="$t('choose_username.generate_new')"
              >
                <RefreshCw :class="['w-5 h-5 text-neutral-600 dark:text-neutral-400', { 'animate-spin': generatingUsername }]" />
              </button>
            </div>

            <!-- Availability indicator -->
            <div v-if="checkingAvailability" class="mt-1.5 flex items-center gap-1.5 text-sm text-neutral-500">
              <Loader2 class="w-4 h-4 animate-spin" />
              {{ $t('choose_username.checking') }}
            </div>
            <div v-else-if="usernameError" class="mt-1.5 text-sm text-red-600 dark:text-red-400">
              {{ usernameError }}
            </div>
            <div v-else-if="usernameAvailable && username" class="mt-1.5 flex items-center gap-1.5 text-sm text-green-600 dark:text-green-400">
              <CheckCircle class="w-4 h-4" />
              {{ $t('choose_username.available') }}
            </div>
          </div>

          <!-- HNA Preview -->
          <div class="bg-neutral-50 dark:bg-neutral-700/50 rounded-lg p-3">
            <div class="text-xs text-neutral-500 dark:text-neutral-400 mb-1">{{ $t('choose_username.your_hna') }}</div>
            <div class="font-mono text-neutral-900 dark:text-neutral-100">{{ username }}@parahub.io</div>
          </div>
        </div>

        <!-- Credentials Section -->
        <div v-if="credentials" class="space-y-4 mb-6">
          <UiAlert variant="warning" :title="$t('choose_username.save_credentials')">
            <p class="text-xs">{{ $t('choose_username.save_credentials_desc') }}</p>
          </UiAlert>

          <div class="bg-neutral-50 dark:bg-neutral-700/50 rounded-lg p-3">
            <div class="flex items-center justify-between mb-1">
              <div class="text-xs text-neutral-500 dark:text-neutral-400">{{ $t('choose_username.password_label') }}</div>
              <div class="flex gap-1">
                <button
                  @click="showPassword = !showPassword"
                  class="p-1 hover:bg-neutral-200 dark:hover:bg-neutral-600 rounded transition-colors"
                >
                  <Eye v-if="!showPassword" class="w-4 h-4 text-neutral-500" />
                  <EyeOff v-else class="w-4 h-4 text-neutral-500" />
                </button>
                <button
                  @click="copyPassword"
                  class="p-1 hover:bg-neutral-200 dark:hover:bg-neutral-600 rounded transition-colors"
                >
                  <Check v-if="passwordCopied" class="w-4 h-4 text-green-500" />
                  <Copy v-else class="w-4 h-4 text-neutral-500" />
                </button>
              </div>
            </div>
            <div class="font-mono text-neutral-900 dark:text-neutral-100">
              {{ showPassword ? credentials.password : '••••••••••••' }}
            </div>
          </div>
        </div>

        <!-- Error message -->
        <UiAlert v-if="submitError" variant="error" class="mb-4">{{ submitError }}</UiAlert>

        <!-- Continue Button -->
        <button
          @click="saveAndContinue"
          :disabled="!canContinue || saving"
          class="w-full bg-neutral-900 dark:bg-neutral-100 text-white dark:text-neutral-900 py-3 px-4 rounded-lg font-medium hover:bg-neutral-800 dark:hover:bg-neutral-200 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2"
        >
          <Loader2 v-if="saving" class="w-5 h-5 animate-spin" />
          {{ saving ? $t('choose_username.saving') : $t('choose_username.continue') }}
        </button>

        <!-- Skip link -->
        <div class="mt-4 text-center">
          <button
            @click="skipAndContinue"
            class="text-sm text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300 underline"
          >
            {{ $t('choose_username.keep_generated') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { RefreshCw, Loader2, CheckCircle, Eye, EyeOff, Copy, Check } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'

const authStore = useAuthStore()
const baseLocalePath = useLocalePath()

// This page is reached via OAuth callback at /choose-username (no locale prefix).
// Read the user's locale from cookie so localePath redirects preserve their language.
const preferredLangCookie = useCookie('preferred_language')
const userLocale = preferredLangCookie.value || undefined
const localePath = (path) => baseLocalePath(path, userLocale)

const username = ref('')
const originalUsername = ref('')
const credentials = ref(null)
const showPassword = ref(false)
const passwordCopied = ref(false)

const checkingAvailability = ref(false)
const usernameAvailable = ref(false)
const usernameError = ref('')
const generatingUsername = ref(false)
const saving = ref(false)
const submitError = ref('')

let checkTimeout = null

const canContinue = computed(() => {
  return username.value &&
         !checkingAvailability.value &&
         !usernameError.value &&
         (usernameAvailable.value || username.value === originalUsername.value)
})

onMounted(async () => {
  // Check if user is authenticated
  const isAuthenticated = await authStore.checkAuthStatus()
  if (!isAuthenticated) {
    await navigateTo(localePath('/login'))
    return
  }

  // Fetch generated credentials
  try {
    const response = await $fetch('/api/v1/auth/generated-credentials/', {
      credentials: 'include'
    })

    if (response.hna && response.password) {
      credentials.value = response
      // Extract username from HNA (e.g., "happy-fox@parahub.io" → "happy-fox")
      const hna = response.hna
      const atIndex = hna.indexOf('@')
      if (atIndex > 0) {
        username.value = hna.substring(0, atIndex)
        originalUsername.value = username.value
        usernameAvailable.value = true // Original username is already taken by this user
      }
    } else {
      // No credentials means not a new OAuth user, redirect to home
      await navigateTo(localePath('/'))
    }
  } catch (error) {
    console.error('Failed to fetch credentials:', error)
    await navigateTo(localePath('/'))
  }
})

const debouncedCheckAvailability = () => {
  if (checkTimeout) clearTimeout(checkTimeout)

  usernameError.value = ''
  usernameAvailable.value = false

  if (!username.value) return

  // If same as original, it's available for this user
  if (username.value === originalUsername.value) {
    usernameAvailable.value = true
    return
  }

  checkingAvailability.value = true

  checkTimeout = setTimeout(async () => {
    await checkAvailability()
  }, 500)
}

const checkAvailability = async () => {
  if (!username.value) {
    checkingAvailability.value = false
    return
  }

  try {
    const response = await $fetch(`/api/v1/auth/check-username/${encodeURIComponent(username.value)}/`, {
      credentials: 'include'
    })

    if (response.available) {
      usernameAvailable.value = true
      usernameError.value = ''
    } else {
      usernameAvailable.value = false
      usernameError.value = response.reason || 'Username not available'
    }
  } catch (error) {
    usernameError.value = error.data?.error || 'Failed to check availability'
    usernameAvailable.value = false
  } finally {
    checkingAvailability.value = false
  }
}

const generateNewUsername = async () => {
  generatingUsername.value = true
  usernameError.value = ''

  try {
    const response = await $fetch('/api/v1/auth/generate-username/', {
      credentials: 'include'
    })

    username.value = response.username
    usernameAvailable.value = true
  } catch (error) {
    usernameError.value = 'Failed to generate username'
  } finally {
    generatingUsername.value = false
  }
}

const copyPassword = async () => {
  if (!credentials.value?.password) return

  try {
    await navigator.clipboard.writeText(credentials.value.password)
    passwordCopied.value = true
    setTimeout(() => {
      passwordCopied.value = false
    }, 2000)
  } catch (error) {
    console.error('Failed to copy:', error)
  }
}

const saveAndContinue = async () => {
  if (!canContinue.value) return

  saving.value = true
  submitError.value = ''

  try {
    // If username changed, update it first
    if (username.value !== originalUsername.value) {
      await $fetch('/api/v1/auth/set-username/', {
        method: 'POST',
        credentials: 'include',
        body: { username: username.value }
      })
    }

    // Confirm username selection (clears new user flag)
    await $fetch('/api/v1/auth/confirm-username/', {
      method: 'POST',
      credentials: 'include'
    })

    // Clear the flag in store and refresh user data
    authStore.needsUsernameConfirmation = false
    await authStore.fetchUser()

    await navigateTo(localePath('/chat'))
  } catch (err) {
    submitError.value = err?.data?.error || 'Failed to update username'
  } finally {
    saving.value = false
  }
}

const skipAndContinue = async () => {
  try {
    // Confirm username selection with generated username (clears new user flag)
    await $fetch('/api/v1/auth/confirm-username/', {
      method: 'POST',
      credentials: 'include'
    })

    // Clear the flag in store
    authStore.needsUsernameConfirmation = false

    await navigateTo(localePath('/chat'))
  } catch (error) {
    console.error('Failed to confirm username:', error)
    // Navigate anyway - user chose to skip
    await navigateTo(localePath('/chat'))
  }
}
</script>
