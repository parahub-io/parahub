<template>
  <div class="py-6">
    <div class="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8">
      <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100 mb-6">
        {{ $t('civic.household.joinTitle') }}
      </h1>

      <!-- Loading -->
      <div v-if="state === 'loading'" class="py-12 text-center" role="status" aria-live="polite">
        <div class="animate-spin rounded-full h-12 w-12 mx-auto border-b-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100" aria-hidden="true"></div>
        <span class="sr-only">{{ $t('common.loading') }}</span>
      </div>

      <!-- Needs auth -->
      <div v-else-if="state === 'auth'" class="py-12 text-center">
        <div class="w-16 h-16 mx-auto rounded-full bg-secondary-100 dark:bg-secondary-900/30 flex items-center justify-center mb-4">
          <Home class="w-8 h-8 text-secondary dark:text-secondary-400" aria-hidden="true" />
        </div>
        <h2 class="text-xl font-semibold text-neutral-800 dark:text-neutral-200 mb-4">{{ $t('civic.vote.loginCta') }}</h2>
        <UiButton variant="primary" :to="localePath(`/login?redirect=${encodeURIComponent(fullPath)}`)">
          {{ $t('civic.vote.loginCta') }}
        </UiButton>
      </div>

      <!-- Success -->
      <div v-else-if="state === 'ok'" class="py-12 text-center">
        <div class="w-16 h-16 mx-auto rounded-full bg-success-100 dark:bg-success-900/30 flex items-center justify-center mb-4">
          <Home class="w-8 h-8 text-success" aria-hidden="true" />
        </div>
        <h2 class="text-xl font-semibold text-neutral-800 dark:text-neutral-200 mb-2">
          {{ $t(already ? 'civic.household.joinAlready' : 'civic.household.joinSuccess', { name: propertyName }) }}
        </h2>
        <UiButton variant="primary" class="mt-4" :to="localePath('/governance/polls?tab=household')">
          {{ $t('civic.household.toPolls') }}
        </UiButton>
      </div>

      <!-- Failure -->
      <div v-else class="py-12 text-center">
        <div class="w-16 h-16 mx-auto rounded-full bg-error-100 dark:bg-error-900/30 flex items-center justify-center mb-4">
          <Home class="w-8 h-8 text-error" aria-hidden="true" />
        </div>
        <h2 class="text-xl font-semibold text-neutral-800 dark:text-neutral-200">{{ $t('civic.household.joinFail') }}</h2>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Home } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'

const route = useRoute()
const localePath = useLocalePath()
const authStore = useAuthStore()
const { t: $t } = useI18n()

const state = ref<'loading' | 'auth' | 'ok' | 'fail'>('loading')
const propertyName = ref('')
const already = ref(false)
const fullPath = route.fullPath

onMounted(async () => {
  const token = route.query.token
  if (!token || typeof token !== 'string') {
    state.value = 'fail'
    return
  }
  if (!authStore.isAuthenticated) {
    state.value = 'auth'
    return
  }
  try {
    await authStore.ensureToken()
    const res: any = await $fetch('/api/v1/iot/properties/household/join/', {
      method: 'POST',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
      query: { token },
    })
    propertyName.value = res.property_name
    already.value = !!res.already
    state.value = 'ok'
  } catch {
    state.value = 'fail'
  }
})
</script>
