<template>
  <div class="min-h-screen flex items-center justify-center bg-neutral-50 dark:bg-neutral-900 px-4">
    <div class="w-full max-w-md text-center">
      <div v-if="loading" class="space-y-4">
        <Loader2 class="h-10 w-10 animate-spin mx-auto text-neutral-900 dark:text-neutral-100" />
        <p class="text-neutral-600 dark:text-neutral-400 text-sm">{{ $t('auth.loading') }}</p>
      </div>

      <div v-else-if="error" class="space-y-4">
        <div class="text-red-600 dark:text-red-400">
          <AlertTriangle class="w-12 h-12 mx-auto" />
        </div>
        <h2 class="text-xl font-semibold text-neutral-900 dark:text-neutral-100">{{ $t('auth.error.authorization') }}</h2>
        <p class="text-neutral-600 dark:text-neutral-400">{{ error }}</p>
        <NuxtLink :to="localePath('/login')" class="inline-block px-4 py-2 bg-neutral-900 dark:bg-neutral-100 text-white dark:text-neutral-900 rounded-lg hover:bg-neutral-800 dark:hover:bg-neutral-200 transition-colors">
          {{ $t('auth.back_to_login') }}
        </NuxtLink>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { AlertTriangle, Loader2 } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'

const authStore = useAuthStore()
const router = useRouter()
const localePath = useLocalePath()
const route = useRoute()
const { t } = useI18n()

const loading = ref(true)
const error = ref('')

// Determine the user's locale for redirect. The callback page has no locale prefix,
// so localePath() defaults to 'en' without explicit locale.
// Priority: 1) query param (passed from login page), 2) cookie, 3) default (en)
const preferredLangCookie = useCookie('preferred_language')
const userLocale = String(route.query.locale || '') || preferredLangCookie.value || undefined

onMounted(async () => {
  try {
    // Check if user is authenticated after OAuth callback
    const isAuthenticated = await authStore.checkAuthStatus()

    if (isAuthenticated) {
      // OAuth authentication successful - session cookie already set by backend

      // Check if this is a new OAuth user with generated credentials
      try {
        const response = await $fetch('/api/v1/auth/generated-credentials/', {
          credentials: 'include'
        })

        if (response.hna && response.password) {
          // New user with generated credentials, redirect to choose username page
          await navigateTo(localePath('/choose-username', userLocale))
          return
        }
      } catch (err) {
        // No generated credentials or error, continue to normal redirect
      }

      // Redirect to home or intended page, preserving user's browsing locale
      const redirectTo = route.query.redirect || '/'
      await navigateTo(localePath(String(redirectTo), userLocale))
    } else {
      error.value = t('auth.failed')
    }
  } catch (err) {
    console.error('Auth callback error:', err)
    error.value = t('auth.error.generic')
  } finally {
    loading.value = false
  }
})
</script>