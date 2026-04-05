<template>
  <div class="w-full max-w-md mx-auto px-4">
    <!-- Logo -->
    <div class="flex justify-center mb-8">
      <NuxtLink :to="localePath('/')" class="inline-block">
        <img src="/logo.svg" alt="Parahub" class="h-12 w-auto dark:invert" />
      </NuxtLink>
    </div>

    <!-- Title -->
    <h1 class="text-2xl font-semibold text-center mb-2 text-neutral-900 dark:text-neutral-100">
      {{ $t('register.title') }}
    </h1>
    <p class="text-sm text-center text-neutral-500 dark:text-neutral-400 mb-8">
      {{ $t('register.subtitle') }}
    </p>

    <!-- Registration disabled state -->
    <div v-if="registrationDisabled" class="text-center">
      <div class="w-16 h-16 bg-neutral-100 dark:bg-neutral-800 rounded-full flex items-center justify-center mx-auto mb-4">
        <svg class="w-8 h-8 text-neutral-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
        </svg>
      </div>
      <h2 class="text-xl font-semibold mb-2 text-neutral-900 dark:text-neutral-100">{{ $t('register.disabled_title') }}</h2>
      <p class="text-neutral-500 dark:text-neutral-400 mb-6">{{ $t('register.disabled_desc') }}</p>
      <NuxtLink
        :to="localePath('/login')"
        class="inline-block w-full bg-neutral-900 dark:bg-neutral-100 text-white dark:text-neutral-900 py-2.5 px-4 rounded-lg font-medium text-center hover:bg-neutral-800 dark:hover:bg-neutral-200 transition-all"
      >
        {{ $t('register.go_to_login') }}
      </NuxtLink>
    </div>

    <!-- Success state -->
    <div v-else-if="success" class="text-center">
      <div class="w-16 h-16 bg-green-100 dark:bg-green-900/30 rounded-full flex items-center justify-center mx-auto mb-4">
        <svg class="w-8 h-8 text-green-600 dark:text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
        </svg>
      </div>
      <h2 class="text-xl font-semibold mb-2 text-neutral-900 dark:text-neutral-100">{{ $t('register.success_title') }}</h2>
      <p class="text-neutral-500 dark:text-neutral-400 mb-6">{{ $t('register.success_desc') }}</p>
      <NuxtLink
        :to="localePath('/login')"
        class="inline-block w-full bg-neutral-900 dark:bg-neutral-100 text-white dark:text-neutral-900 py-2.5 px-4 rounded-lg font-medium text-center hover:bg-neutral-800 dark:hover:bg-neutral-200 transition-all"
      >
        {{ $t('register.go_to_login') }}
      </NuxtLink>
    </div>

    <!-- Registration form -->
    <form v-else-if="!registrationDisabled && !success" @submit.prevent="handleRegister" class="space-y-4">
      <!-- Username -->
      <div>
        <label for="username" class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">
          {{ $t('register.username_label') }}
        </label>
        <input
          id="username"
          v-model="form.username"
          type="text"
          required
          :disabled="computing"
          autocomplete="username"
          class="w-full px-3 py-2.5 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-all placeholder:text-neutral-400 dark:placeholder:text-neutral-500 disabled:opacity-60"
          :placeholder="$t('register.username_placeholder')"
        />
        <p class="mt-1 text-xs text-neutral-400 dark:text-neutral-500">
          {{ $t('register.username_hint') }} {{ form.username ? `${form.username.toLowerCase()}@parahub.io` : 'username@parahub.io' }}
        </p>
      </div>

      <!-- Email (optional) -->
      <div>
        <label for="email" class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">
          {{ $t('register.email_label') }}
          <span class="text-neutral-400 dark:text-neutral-500 font-normal">({{ $t('common.optional') }})</span>
        </label>
        <input
          id="email"
          v-model="form.email"
          type="email"
          :disabled="computing"
          autocomplete="email"
          class="w-full px-3 py-2.5 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-all placeholder:text-neutral-400 dark:placeholder:text-neutral-500 disabled:opacity-60"
          :placeholder="$t('register.email_placeholder')"
        />
        <p class="mt-1 text-xs text-neutral-400 dark:text-neutral-500">
          {{ $t('register.email_hint') }}
        </p>
      </div>

      <!-- Password -->
      <div>
        <label for="password" class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">
          {{ $t('register.password_label') }}
        </label>
        <input
          id="password"
          v-model="form.password"
          type="password"
          required
          :disabled="computing"
          autocomplete="new-password"
          class="w-full px-3 py-2.5 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-all placeholder:text-neutral-400 dark:placeholder:text-neutral-500 disabled:opacity-60"
          placeholder="••••••••"
        />
      </div>

      <!-- Password confirm -->
      <div>
        <label for="password_confirm" class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">
          {{ $t('register.password_confirm_label') }}
        </label>
        <input
          id="password_confirm"
          v-model="form.password_confirm"
          type="password"
          required
          :disabled="computing"
          autocomplete="new-password"
          class="w-full px-3 py-2.5 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-all placeholder:text-neutral-400 dark:placeholder:text-neutral-500 disabled:opacity-60"
          placeholder="••••••••"
        />
      </div>

      <!-- Error -->
      <UiAlert v-if="error" variant="error">{{ error }}</UiAlert>

      <!-- PoW progress -->
      <div v-if="computing" class="bg-neutral-50 dark:bg-neutral-800/50 border border-neutral-200 dark:border-neutral-700 rounded-lg p-4 text-center">
        <div class="flex items-center justify-center gap-2 mb-1">
          <svg class="w-4 h-4 text-neutral-500 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"/>
          </svg>
          <span class="text-sm font-medium text-neutral-700 dark:text-neutral-300">{{ $t('register.pow_computing') }}</span>
        </div>
        <p class="text-xs text-neutral-400 dark:text-neutral-500">{{ $t('register.pow_hint') }}</p>
      </div>

      <!-- Submit -->
      <button
        type="submit"
        :disabled="computing || loading"
        class="w-full bg-neutral-900 dark:bg-neutral-100 text-white dark:text-neutral-900 py-2.5 px-4 rounded-lg font-medium hover:bg-neutral-800 dark:hover:bg-neutral-200 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
      >
        {{ loading ? $t('register.submitting') : $t('register.submit') }}
      </button>

      <!-- Login link -->
      <p class="text-center text-sm text-neutral-500 dark:text-neutral-400">
        {{ $t('register.have_account') }}
        <NuxtLink :to="localePath('/login')" class="text-neutral-900 dark:text-neutral-100 font-medium hover:underline">
          {{ $t('register.sign_in') }}
        </NuxtLink>
      </p>
    </form>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useAuthStore } from '~/stores/auth'
import { solvePoW } from '~/utils/pow'

const authStore = useAuthStore()
const localePath = useLocalePath()

const form = ref({
  username: '',
  email: '',
  password: '',
  password_confirm: '',
})

const loading = ref(false)
const computing = ref(false)
const error = ref('')
const success = ref(false)
const registrationDisabled = ref(false)

onMounted(async () => {
  if (authStore.isAuthenticated) {
    await navigateTo(localePath('/'))
    return
  }
  // Check if registration is enabled by probing the challenge endpoint
  try {
    await $fetch('/api/v1/auth/pow/challenge/', { credentials: 'include' })
  } catch (err: any) {
    if (err?.status === 403) registrationDisabled.value = true
  }
})

const handleRegister = async () => {
  error.value = ''

  if (form.value.password !== form.value.password_confirm) {
    error.value = 'Passwords do not match'
    return
  }

  try {
    // Step 1: get challenge
    const { challenge, params } = await $fetch<{ challenge: string; params: { N: number; r: number; p: number; dkLen: number } }>(
      '/api/v1/auth/pow/challenge/',
      { credentials: 'include' }
    )

    // Step 2: solve PoW (single scrypt call, ~1-2s on phone)
    computing.value = true
    const proof = await solvePoW(challenge, params)
    computing.value = false

    // Step 3: register
    loading.value = true
    const username = form.value.username.toLowerCase().trim()
    await $fetch('/api/v1/auth/register/', {
      method: 'POST',
      credentials: 'include',
      body: {
        username,
        ...(form.value.email ? { email: form.value.email } : {}),
        password: form.value.password,
        password_confirm: form.value.password_confirm,
        local_name: username,
        pow_proof: proof,
      },
    })

    success.value = true
  } catch (err: any) {
    computing.value = false
    loading.value = false
    const detail = err?.data?.detail || err?.data?.message || err?.message
    error.value = detail || 'Registration failed'
  } finally {
    loading.value = false
  }
}
</script>
