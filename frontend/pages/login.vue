<template>
  <div class="w-full max-w-md mx-auto px-4">
    <!-- Logo -->
    <div class="flex justify-center mb-8">
      <NuxtLink :to="localePath('/')" class="inline-block">
        <img src="/logo.svg" alt="Parahub" class="h-12 w-auto dark:invert" />
      </NuxtLink>
    </div>

    <!-- Title -->
    <h1 class="text-2xl font-semibold text-center mb-8 text-neutral-900 dark:text-neutral-100">
      {{ $t('login.title') }}
    </h1>

    <!-- Google OAuth Login -->
    <button
      @click="loginWithGoogle"
      class="w-full bg-white dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-600 text-neutral-900 dark:text-neutral-100 py-3 px-4 rounded-lg font-medium hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors flex items-center justify-center gap-3"
    >
      <svg class="w-5 h-5" viewBox="0 0 24 24">
        <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
        <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
        <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
        <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
      </svg>
      {{ $t('login.google_signin') }}
    </button>

    <!-- Divider -->
    <div class="relative my-8">
      <div class="absolute inset-0 flex items-center">
        <div class="w-full border-t border-neutral-200 dark:border-neutral-700"></div>
      </div>
      <div class="relative flex justify-center text-sm">
        <span class="px-3 bg-neutral-50 dark:bg-neutral-900 text-neutral-500 dark:text-neutral-400">
          {{ $t('login.or') }}
        </span>
      </div>
    </div>

    <!-- Login Form -->
    <form @submit.prevent="handleLogin" class="space-y-4">
      <div>
        <label for="username" class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">
          {{ $t('login.username_label') }}
        </label>
        <input
          id="username"
          v-model="username"
          type="text"
          required
          autocomplete="username"
          class="w-full px-3 py-2.5 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-all placeholder:text-neutral-400 dark:placeholder:text-neutral-500"
          :placeholder="$t('login.username_placeholder')"
        />
      </div>

      <div>
        <label for="password" class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">
          {{ $t('login.password_label') }}
        </label>
        <input
          id="password"
          v-model="password"
          type="password"
          required
          autocomplete="current-password"
          class="w-full px-3 py-2.5 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-all placeholder:text-neutral-400 dark:placeholder:text-neutral-500"
          :placeholder="$t('login.password_placeholder')"
        />
      </div>

      <UiAlert v-if="error" variant="error">{{ error }}</UiAlert>

      <button
        type="submit"
        :disabled="loading"
        class="w-full bg-neutral-900 dark:bg-neutral-100 text-white dark:text-neutral-900 py-2.5 px-4 rounded-lg font-medium hover:bg-neutral-800 dark:hover:bg-neutral-200 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
      >
        {{ loading ? $t('login.submitting') : $t('login.submit') }}
      </button>

      <p class="text-center text-sm text-neutral-500 dark:text-neutral-400 pt-2">
        {{ $t('register.have_account_inverse') }}
        <NuxtLink :to="localePath('/register')" class="text-neutral-900 dark:text-neutral-100 font-medium hover:underline">
          {{ $t('register.create_account') }}
        </NuxtLink>
      </p>
    </form>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useAuthStore } from '~/stores/auth'
import { isNative } from '~/utils/capacitor'

const { t, locale } = useI18n()
const authStore = useAuthStore()
const router = useRouter()
const localePath = useLocalePath()

const username = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')
let pollTimer = null

const errorMessageMap: Record<string, string> = {
  invalid_credentials: 'login.error.invalid_credentials',
  account_disabled: 'login.error.account_disabled',
  rate_limited: 'login.error.rate_limited',
}

// Check if already authenticated and redirect
onMounted(async () => {
  if (authStore.isAuthenticated) {
    await navigateTo(localePath('/'))
  }
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})

const handleLogin = async () => {
  loading.value = true
  error.value = ''

  try {
    await authStore.login(username.value, password.value)
    await navigateTo(localePath('/'))
  } catch (err: any) {
    const code = err.data?.detail
    const i18nKey = errorMessageMap[code]
    error.value = i18nKey ? t(i18nKey) : t('login.error.generic')
  } finally {
    loading.value = false
  }
}

const loginWithGoogle = async () => {
  if (isNative()) {
    await loginWithGoogleNative()
  } else {
    // Pass current locale through OAuth flow so callback can redirect with correct language
    const callbackUrl = `https://parahub.io/auth/callback?provider=google&locale=${locale.value}`
    window.location.href = `https://parahub.io/accounts/google/login/?process=login&next=${encodeURIComponent(callbackUrl)}`
  }
}

const loginWithGoogleNative = async () => {
  loading.value = true
  error.value = ''

  try {
    // 1. Get a state token from backend
    const { state } = await $fetch('/api/v1/auth/mobile/init/', {
      method: 'POST'
    })

    // 2. Open OAuth in system browser (Chrome Custom Tab)
    const { Browser } = await import('@capacitor/browser')
    const next = `/auth/mobile-complete/?state=${state}`
    await Browser.open({
      url: `https://parahub.io/accounts/google/login/?process=login&next=${encodeURIComponent(next)}`
    })

    // 3. Poll for completion every 2 seconds
    pollTimer = setInterval(async () => {
      try {
        const result = await $fetch(`/api/v1/auth/mobile/poll/?state=${state}`)

        if (result.status === 'complete') {
          if (pollTimer) clearInterval(pollTimer)
          pollTimer = null

          // Close the browser
          try { await Browser.close() } catch { /* may already be closed */ }

          // Set tokens and load user
          authStore.setToken(result.access_token, result.refresh_token)
          await authStore.fetchUser()

          // Establish session cookie in WebView (CCT and WebView have separate cookie stores)
          try {
            await $fetch('/api/v1/auth/mobile/session/', {
              method: 'POST',
              credentials: 'include',
              headers: { Authorization: `Bearer ${authStore.token}` },
            })
          } catch { /* non-critical: session will be missing on restart */ }

          loading.value = false

          // Handle new OAuth users
          if (result.is_new_user) {
            await navigateTo(localePath('/choose-username'))
          } else {
            await navigateTo(localePath('/'))
          }
        }
      } catch (err) {
        // 410 = state expired
        if (err?.response?.status === 410 || err?.status === 410) {
          if (pollTimer) clearInterval(pollTimer)
          pollTimer = null
          loading.value = false
          error.value = 'Authentication timed out. Please try again.'
        }
        // Other errors: keep polling (network blip, etc.)
      }
    }, 2000)

    // 4. Also listen for browser close as a fallback timeout
    Browser.addListener('browserFinished', () => {
      // Give a few seconds for the last poll to complete
      setTimeout(() => {
        if (pollTimer) {
          clearInterval(pollTimer)
          pollTimer = null
          loading.value = false
        }
      }, 5000)
    })
  } catch (err) {
    loading.value = false
    error.value = 'Failed to start authentication'
  }
}
</script>
