<template>
  <div>
    <Head>
      <Title>{{ $t('invite.title') }} - Parahub</Title>
    </Head>

    <div class="max-w-2xl mx-auto">
      <div class="bg-neutral-100 dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-8">
        <!-- Username Selection (for new users) -->
        <div v-if="status === 'choosing_username'" class="text-center">
          <div class="w-16 h-16 bg-primary rounded-full flex items-center justify-center mx-auto mb-4">
            <User class="w-10 h-10 text-white" />
          </div>
          <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100 mb-2">
            {{ $t('invite.choose_username') }}
          </h1>
          <p class="text-neutral-600 dark:text-neutral-400 mb-6">
            {{ $t('invite.username_description') }}
          </p>

          <!-- Username Selection Form -->
          <div class="space-y-4 text-left">
            <!-- Radio: Random -->
            <label
              class="flex items-center gap-3 p-4 rounded-lg border-2 cursor-pointer transition-all"
              :class="usernameMode === 'random'
                ? 'border-primary bg-primary/10'
                : 'border-neutral-300 dark:border-neutral-600 hover:border-primary/50'"
            >
              <input
                type="radio"
                v-model="usernameMode"
                value="random"
                class="w-5 h-5 text-primary"
              />
              <div class="flex-1">
                <div class="font-medium text-neutral-900 dark:text-neutral-100">
                  {{ $t('invite.random_username') }}
                </div>
                <div class="text-sm text-neutral-600 dark:text-neutral-400">
                  @{{ generatedUsername }}:parahub.io
                </div>
              </div>
              <button
                @click.prevent="regenerateUsername"
                class="p-2 hover:bg-neutral-200 dark:hover:bg-neutral-700 rounded-lg transition-colors"
                :disabled="isGenerating"
                :title="$t('invite.regenerate')"
              >
                <RefreshCw class="w-5 h-5" :class="{ 'animate-spin': isGenerating }" />
              </button>
            </label>

            <!-- Radio: Custom -->
            <label
              class="flex flex-col p-4 rounded-lg border-2 cursor-pointer transition-all"
              :class="usernameMode === 'custom'
                ? 'border-primary bg-primary/10'
                : 'border-neutral-300 dark:border-neutral-600 hover:border-primary/50'"
            >
              <div class="flex items-center gap-3">
                <input
                  type="radio"
                  v-model="usernameMode"
                  value="custom"
                  class="w-5 h-5 text-primary"
                />
                <div class="font-medium text-neutral-900 dark:text-neutral-100">
                  {{ $t('invite.custom_username') }}
                </div>
              </div>

              <!-- Custom username input -->
              <div v-if="usernameMode === 'custom'" class="mt-3 pl-8">
                <div class="flex items-center gap-2">
                  <span class="text-neutral-500">@</span>
                  <input
                    v-model="customUsername"
                    type="text"
                    :placeholder="$t('invite.username_placeholder')"
                    class="flex-1 px-3 py-2 bg-white dark:bg-neutral-900 border border-neutral-300 dark:border-neutral-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
                    @input="checkCustomUsername"
                    :disabled="isCheckingUsername"
                  />
                  <span class="text-neutral-500">:parahub.io</span>
                </div>

                <!-- Availability status -->
                <div class="mt-2 text-sm">
                  <span v-if="isCheckingUsername" class="text-neutral-500 flex items-center gap-1">
                    <Loader2 class="w-4 h-4 animate-spin" />
                    {{ $t('invite.checking') }}
                  </span>
                  <span v-else-if="customUsernameStatus === 'available'" class="text-green-600 flex items-center gap-1">
                    <CheckCircle class="w-4 h-4" />
                    {{ $t('invite.username_available') }}
                  </span>
                  <span v-else-if="customUsernameStatus === 'taken'" class="text-red-600 flex items-center gap-1">
                    <XCircle class="w-4 h-4" />
                    {{ customUsernameError || $t('invite.username_taken') }}
                  </span>
                  <span v-else-if="customUsernameStatus === 'invalid'" class="text-red-600 flex items-center gap-1">
                    <XCircle class="w-4 h-4" />
                    {{ customUsernameError }}
                  </span>
                </div>
              </div>
            </label>
          </div>

          <!-- Continue button -->
          <button
            @click="proceedWithSignup"
            class="mt-6 w-full btn-primary py-3 text-lg"
            :disabled="!canProceed || isSigningUp"
          >
            <span v-if="isSigningUp" class="flex items-center justify-center gap-2">
              <Loader2 class="w-5 h-5 animate-spin" />
              {{ $t('invite.creating_account') }}
            </span>
            <span v-else>
              {{ $t('invite.continue') }}
            </span>
          </button>
        </div>

        <!-- Success - New Account -->
        <div v-else-if="status === 'success' && accountCreated" class="text-center">
          <div class="w-16 h-16 bg-green-500 rounded-full flex items-center justify-center mx-auto mb-4">
            <Check class="w-10 h-10 text-white" />
          </div>
          <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100 mb-2">
            {{ $t('invite.welcome') }}
          </h1>
          <p class="text-neutral-600 dark:text-neutral-400 mb-6">
            {{ $t('invite.success_message', { inviter: inviterName }) }}
          </p>

          <!-- Credentials -->
          <div class="bg-white dark:bg-neutral-700 rounded-lg p-6 mb-6 text-left">
            <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-4">
              {{ $t('invite.your_credentials') }}
            </h3>
            <div class="space-y-3">
              <div>
                <label class="block text-sm text-neutral-600 dark:text-neutral-400 mb-1">Email / HNA:</label>
                <div class="flex items-center gap-2">
                  <input
                    :value="credentials.email"
                    readonly
                    class="flex-1 px-3 py-2 bg-neutral-50 dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-600 rounded font-mono text-sm"
                  />
                  <button
                    @click="(e) => copyText(e, credentials.email)"
                    class="px-3 py-2 bg-neutral-200 dark:bg-neutral-700 hover:bg-neutral-300 dark:hover:bg-neutral-600 rounded"
                  >
                    <ClipboardCopy class="w-4 h-4" />
                  </button>
                </div>
              </div>
              <div>
                <label class="block text-sm text-neutral-600 dark:text-neutral-400 mb-1">{{ $t('invite.password') }}:</label>
                <div class="flex items-center gap-2">
                  <input
                    :value="credentials.password"
                    readonly
                    class="flex-1 px-3 py-2 bg-neutral-50 dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-600 rounded font-mono text-sm"
                  />
                  <button
                    @click="(e) => copyText(e, credentials.password)"
                    class="px-3 py-2 bg-neutral-200 dark:bg-neutral-700 hover:bg-neutral-300 dark:hover:bg-neutral-600 rounded"
                  >
                    <ClipboardCopy class="w-4 h-4" />
                  </button>
                </div>
              </div>
              <div>
                <label class="block text-sm text-neutral-600 dark:text-neutral-400 mb-1">Matrix ID:</label>
                <div class="flex items-center gap-2">
                  <input
                    :value="`@${credentials.username}:parahub.io`"
                    readonly
                    class="flex-1 px-3 py-2 bg-neutral-50 dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-600 rounded font-mono text-sm"
                  />
                  <button
                    @click="(e) => copyText(e, `@${credentials.username}:parahub.io`)"
                    class="px-3 py-2 bg-neutral-200 dark:bg-neutral-700 hover:bg-neutral-300 dark:hover:bg-neutral-600 rounded"
                  >
                    <ClipboardCopy class="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
            <UiAlert variant="warning" class="mt-4">
              <p class="font-semibold text-center">{{ $t('invite.save_credentials_warning') }}</p>
            </UiAlert>
          </div>

          <div class="flex gap-3 justify-center">
            <NuxtLink :to="localePath('/profile')" class="btn-primary">
              {{ $t('invite.go_to_profile') }}
            </NuxtLink>
            <NuxtLink :to="localePath('/directory?tab=users')" class="btn-secondary">
              {{ $t('invite.view_partners') }}
            </NuxtLink>
          </div>
        </div>

        <!-- Success - Existing User -->
        <div v-else-if="status === 'success' && !accountCreated" class="text-center">
          <div class="w-16 h-16 bg-green-500 rounded-full flex items-center justify-center mx-auto mb-4">
            <Check class="w-10 h-10 text-white" />
          </div>
          <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100 mb-2">
            {{ $t('invite.partner_added') }}
          </h1>
          <p class="text-neutral-600 dark:text-neutral-400 mb-6">
            {{ $t('invite.partner_added_message', { inviter: inviterName }) }}
          </p>
          <div class="flex gap-3 justify-center">
            <NuxtLink :to="localePath('/directory?tab=users')" class="btn-primary">
              {{ $t('invite.view_partners') }}
            </NuxtLink>
            <NuxtLink :to="localePath('/profile')" class="btn-secondary">
              {{ $t('invite.go_to_profile') }}
            </NuxtLink>
          </div>
        </div>

        <!-- Error -->
        <div v-else-if="status === 'error'" class="text-center">
          <div class="w-16 h-16 bg-red-500 rounded-full flex items-center justify-center mx-auto mb-4">
            <X class="w-10 h-10 text-white" />
          </div>
          <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100 mb-2">
            {{ $t('common.error') }}
          </h1>
          <p class="text-neutral-600 dark:text-neutral-400 mb-6">
            {{ errorMessage }}
          </p>
          <NuxtLink :to="localePath('/profile')" class="btn-primary">
            {{ $t('invite.go_to_profile') }}
          </NuxtLink>
        </div>

        <!-- Loading -->
        <div v-else-if="status === 'loading'" class="text-center py-8">
          <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4"></div>
          <p class="text-neutral-600 dark:text-neutral-400">
            {{ $t('invite.processing') }}
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Check, X, ClipboardCopy, User, RefreshCw, Loader2, CheckCircle, XCircle } from 'lucide-vue-next'

definePageMeta({
})

const { $t } = useNuxtApp()
const route = useRoute()
const localePath = useLocalePath()
const authStore = useAuthStore()
const token = route.params.token as string

const status = ref<'loading' | 'choosing_username' | 'success' | 'error'>('loading')
const errorMessage = ref('')
const inviterName = ref('')
const accountCreated = ref(false)
const credentials = ref({
  email: '',
  password: '',
  username: ''
})

// Username selection state
const usernameMode = ref<'random' | 'custom'>('random')
const generatedUsername = ref('')
const customUsername = ref('')
const customUsernameStatus = ref<'idle' | 'available' | 'taken' | 'invalid'>('idle')
const customUsernameError = ref('')
const isGenerating = ref(false)
const isCheckingUsername = ref(false)
const isSigningUp = ref(false)

// Debounce timer for username check
let checkUsernameTimer: ReturnType<typeof setTimeout> | null = null

const canProceed = computed(() => {
  if (usernameMode.value === 'random') {
    return generatedUsername.value.length > 0
  } else {
    return customUsernameStatus.value === 'available' && customUsername.value.length >= 3
  }
})

onMounted(async () => {
  await processInvite()
})

const processInvite = async () => {
  // Check if user is authenticated
  await authStore.ensureToken()

  if (authStore.token) {
    // User is logged in - just add partner
    await acceptInviteForLoggedInUser()
  } else {
    // User is not logged in - show username selection
    await generateRandomUsername()
    status.value = 'choosing_username'
  }
}

const generateRandomUsername = async () => {
  isGenerating.value = true
  try {
    const response = await $fetch<{ username: string; available: boolean }>('/api/v1/auth/generate-username/')
    generatedUsername.value = response.username
  } catch (error) {
    console.error('Failed to generate username:', error)
    // Fallback to simple random
    generatedUsername.value = `user-${Date.now() % 100000}`
  } finally {
    isGenerating.value = false
  }
}

const regenerateUsername = async () => {
  await generateRandomUsername()
}

const checkCustomUsername = () => {
  // Clear previous timer
  if (checkUsernameTimer) {
    clearTimeout(checkUsernameTimer)
  }

  const username = customUsername.value.toLowerCase().trim()

  // Basic validation
  if (username.length < 3) {
    customUsernameStatus.value = 'invalid'
    customUsernameError.value = $t('invite.username_too_short')
    return
  }

  if (username.length > 30) {
    customUsernameStatus.value = 'invalid'
    customUsernameError.value = $t('invite.username_too_long')
    return
  }

  if (!/^[a-z0-9][a-z0-9._-]*[a-z0-9]$/.test(username) && !/^[a-z0-9]$/.test(username)) {
    customUsernameStatus.value = 'invalid'
    customUsernameError.value = $t('invite.username_invalid_chars')
    return
  }

  // Debounced API check
  customUsernameStatus.value = 'idle'
  isCheckingUsername.value = true

  checkUsernameTimer = setTimeout(async () => {
    try {
      const response = await $fetch<{ available: boolean; reason?: string }>(
        `/api/v1/auth/check-username/${encodeURIComponent(username)}/`
      )

      if (response.available) {
        customUsernameStatus.value = 'available'
        customUsernameError.value = ''
      } else {
        customUsernameStatus.value = 'taken'
        customUsernameError.value = response.reason || $t('invite.username_taken')
      }
    } catch (error) {
      console.error('Failed to check username:', error)
      customUsernameStatus.value = 'invalid'
      customUsernameError.value = $t('invite.check_failed')
    } finally {
      isCheckingUsername.value = false
    }
  }, 500) // 500ms debounce
}

const proceedWithSignup = async () => {
  const selectedUsername = usernameMode.value === 'random'
    ? generatedUsername.value
    : customUsername.value.toLowerCase().trim()

  await quickSignup(selectedUsername)
}

const quickSignup = async (selectedUsername?: string) => {
  isSigningUp.value = true
  try {
    const body: { invite_token: string; local_name?: string } = {
      invite_token: token
    }

    if (selectedUsername) {
      body.local_name = selectedUsername
    }

    const response = await $fetch<{
      email: string
      password: string
      username: string
      inviter_hna: string
      access_token: string
      refresh_token: string
    }>('/api/v1/partners/quick-signup/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body
    })

    // Store credentials (for display)
    credentials.value = {
      email: response.email,
      password: response.password,
      username: response.username
    }

    inviterName.value = response.inviter_hna
    accountCreated.value = true

    // Auto-login: set JWT tokens in auth store
    authStore.setToken(response.access_token, response.refresh_token)

    // Fetch user data
    await authStore.loadUser()

    status.value = 'success'
  } catch (error: any) {
    console.error('Quick signup failed:', error)
    status.value = 'error'

    if (error.data?.error) {
      const backendError = error.data.error
      switch (backendError) {
        case 'Invalid or inactive invite token':
          errorMessage.value = $t('invite.error_invalid_token')
          break
        case 'Username already taken':
          errorMessage.value = $t('invite.error_username_taken')
          break
        case 'Username already taken in chat system':
          errorMessage.value = $t('invite.error_username_taken_matrix')
          break
        default:
          errorMessage.value = `${$t('invite.error_server')}: ${backendError}`
      }
    } else if (error.statusCode === 400) {
      errorMessage.value = $t('invite.error_bad_request')
    } else if (error.statusCode === 500) {
      errorMessage.value = $t('invite.error_internal')
    } else {
      errorMessage.value = $t('invite.error_unknown')
    }

    console.error('Full error details:', error)
  } finally {
    isSigningUp.value = false
  }
}

const acceptInviteForLoggedInUser = async () => {
  try {
    const response = await $fetch<{ partner?: { display_name?: string; hna?: string } }>('/api/v1/partners/accept/', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`,
        'Content-Type': 'application/json'
      },
      body: {
        invite_token: token
      }
    })

    if (response.partner) {
      inviterName.value = response.partner.display_name || response.partner.hna || ''
    }

    accountCreated.value = false
    status.value = 'success'
  } catch (error: any) {
    console.error('Failed to accept invite:', error)
    status.value = 'error'

    if (error.data?.error) {
      errorMessage.value = error.data.error === 'Invalid or inactive invite token'
        ? $t('invite.error_invalid_token')
        : error.data.error === 'Already in your partners'
        ? $t('invite.error_already_partner')
        : error.data.error
    } else {
      errorMessage.value = $t('invite.error_accept_failed')
    }
  }
}

const copyText = async (event: any, text: string) => {
  try {
    await navigator.clipboard.writeText(text)
    const button = event.target.closest('button')
    const originalHTML = button.innerHTML
    button.innerHTML = '<span class="text-green-600">✓</span>'
    setTimeout(() => {
      button.innerHTML = originalHTML
    }, 2000)
  } catch (error) {
    console.error('Failed to copy:', error)
  }
}
</script>
