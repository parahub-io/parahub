<template>
  <div class="flex items-center gap-1" role="radiogroup" :aria-label="$t('nav.language') || 'Language'">
    <Globe class="w-3.5 h-3.5 text-neutral-400 dark:text-neutral-500 flex-shrink-0" aria-hidden="true" />
    <button
      v-for="lang in locales"
      :key="lang.code"
      role="radio"
      :aria-checked="locale === lang.code"
      :aria-label="lang.nativeName"
      :title="lang.nativeName"
      @click="switchLocale(lang.code)"
      class="px-1.5 py-1 rounded text-xs font-medium transition-colors min-w-[28px] text-center"
      :class="locale === lang.code
        ? 'bg-primary text-neutral-900'
        : variant === 'dark'
          ? 'text-neutral-400 hover:text-white hover:bg-neutral-700'
          : 'text-neutral-500 dark:text-neutral-400 hover:text-neutral-800 dark:hover:text-neutral-200 hover:bg-neutral-200 dark:hover:bg-neutral-700'"
    >
      {{ lang.code.toUpperCase() }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { Globe } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'

const props = defineProps<{
  variant?: 'light' | 'dark'
}>()

const { locale } = useI18n()
const switchLocalePath = useSwitchLocalePath()
const authStore = useAuthStore()

const saving = ref(false)
const locales = [
  { code: 'en', nativeName: 'English' },
  { code: 'pt', nativeName: 'Português' },
  { code: 'es', nativeName: 'Español' },
  { code: 'fr', nativeName: 'Français' },
  { code: 'de', nativeName: 'Deutsch' },
]

const switchLocale = async (code: string) => {
  if (saving.value || code === locale.value) return

  const path = switchLocalePath(code)
  if (path) {
    await navigateTo(path)
  }

  // Save to backend if authenticated
  if (authStore.isAuthenticated) {
    saving.value = true
    try {
      await authStore.ensureToken()
      if (authStore.token) {
        await $fetch('/api/v1/profiles/me/preferences/', {
          method: 'PATCH',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${authStore.token}`,
          },
          body: { preferred_language: code },
        })
      }
    } catch (error) {
      console.error('Failed to save language preference:', error)
    } finally {
      saving.value = false
    }
  }
}
</script>
