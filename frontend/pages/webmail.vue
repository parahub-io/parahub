<template>
  <div class="min-h-screen flex items-center justify-center bg-neutral-50 dark:bg-neutral-900">
    <div class="text-center">
      <div v-if="error" class="text-red-500">
        <p class="font-medium">{{ error }}</p>
        <a href="https://mail.parahub.io" target="_blank" class="mt-2 text-sm text-link">
          {{ $t('webmail.open_manually') }}
        </a>
      </div>
      <div v-else class="flex flex-col items-center gap-3 text-neutral-500 dark:text-neutral-400">
        <div class="w-8 h-8 border-2 border-neutral-300 border-t-secondary rounded-full animate-spin" />
        <p class="text-sm">{{ $t('webmail.loading') }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useAuthStore } from '~/stores/auth'
import { isNative } from '~/utils/capacitor'

const { t } = useI18n()
const authStore = useAuthStore()
const router = useRouter()
const localePath = useLocalePath()
const error = ref('')

useHead({ title: t('webmail.loading') })

onMounted(async () => {
  try {
    await authStore.ensureToken()
    const data = await $fetch('/api/v1/profiles/me/mail-credentials/', {
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    // Encode as base64(username\npassword) and hand off to same-origin relay page
    const payload = btoa(`${data.email}\n${data.password}`)
    const url = `https://mail.parahub.io/ph-autologin#${payload}`
    if (isNative()) {
      // Native shell: SOGo in the app WebView draws edge-to-edge under the
      // notch/gesture bar (its CSS knows nothing about our safe-area vars) and
      // has no way back. A Chrome Custom Tab handles insets natively and has a
      // close button returning to the app.
      const { Browser } = await import('@capacitor/browser')
      await Browser.open({ url })
      // Leave the spinner page so closing the tab lands back where the user was
      if (window.history.length > 1) router.back()
      else router.replace(localePath('/'))
    } else {
      window.location.href = url
    }
  } catch (e) {
    error.value = t('webmail.error')
  }
})

definePageMeta({
  middleware: 'auth',
})
</script>
