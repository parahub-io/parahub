<template>
  <div class="py-6 w-full">
    <div class="w-full px-4 sm:px-6 lg:px-8">
      <div class="max-w-4xl mx-auto w-full">
        <!-- Page title -->
        <Head>
          <Title>{{ $t('zenith.title') }} - Parahub</Title>
        </Head>

        <!-- Auth required -->
        <div v-if="!authStore.isAuthenticated" class="bg-yellow-100 dark:bg-yellow-900/20 border border-yellow-300 dark:border-yellow-800 rounded-lg p-6 text-center">
          <Bot class="w-16 h-16 text-yellow-500 mx-auto mb-4" />
          <h2 class="text-xl font-semibold text-yellow-800 dark:text-yellow-200 mb-2">{{ $t('zenith.auth_required') }}</h2>
          <p class="text-yellow-700 dark:text-yellow-300 mb-4">{{ $t('zenith.auth_required_desc') }}</p>
          <NuxtLink :to="localePath('/login')" class="btn-primary">
            {{ $t('zenith.sign_in') }}
          </NuxtLink>
        </div>

        <!-- Main content -->
        <div v-else class="space-y-6">
          <!-- Header -->
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
              <Bot class="w-8 h-8 text-primary" />
              <div>
                <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100">{{ $t('zenith.title') }}</h1>
                <p class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t('zenith.subtitle') }}</p>
              </div>
            </div>
            <button
              @click="showSettings = !showSettings"
              class="btn-secondary flex items-center gap-2"
            >
              <Settings class="w-4 h-4" />
              {{ $t('zenith.settings') }}
            </button>
          </div>

          <!-- Settings Panel -->
          <div v-if="showSettings" class="bg-neutral-100 dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4 sm:p-6 space-y-4">
            <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
              <Settings class="w-5 h-5" />
              {{ $t('zenith.settings_title') }}
            </h3>

            <!-- Enable toggle -->
            <div class="flex items-center justify-between">
              <div>
                <p class="font-medium text-neutral-900 dark:text-neutral-100">{{ $t('zenith.enable_zenith') }}</p>
                <p class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t('zenith.enable_desc') }}</p>
              </div>
              <button
                @click="toggleEnabled"
                :disabled="settingsLoading"
                class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
                :class="settings.enabled ? 'bg-primary' : 'bg-neutral-300 dark:bg-neutral-600'"
              >
                <span
                  class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out"
                  :class="settings.enabled ? 'translate-x-5' : 'translate-x-0'"
                />
              </button>
            </div>

            <!-- Repository name -->
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                {{ $t('zenith.repo_name') }}
              </label>
              <input
                v-model="settings.gitea_repo_name"
                type="text"
                class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100"
                placeholder="zenith-knowledge"
              />
              <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
                {{ $t('zenith.repo_name_desc') }}
              </p>
            </div>

            <!-- API Key -->
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                {{ $t('zenith.api_key') }}
              </label>
              <div class="flex gap-2">
                <input
                  v-model="newApiKey"
                  type="password"
                  class="flex-1 px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100"
                  :placeholder="settings.has_api_key ? $t('zenith.api_key_set') : $t('zenith.api_key_placeholder')"
                />
              </div>
              <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
                {{ $t('zenith.api_key_desc') }}
              </p>
            </div>

            <!-- Allow contacts -->
            <div class="flex items-center justify-between">
              <div>
                <p class="font-medium text-neutral-900 dark:text-neutral-100">{{ $t('zenith.allow_contacts') }}</p>
                <p class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t('zenith.allow_contacts_desc') }}</p>
              </div>
              <button
                @click="toggleContactsAccess"
                :disabled="settingsLoading"
                class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
                :class="settings.allow_contacts_access ? 'bg-primary' : 'bg-neutral-300 dark:bg-neutral-600'"
              >
                <span
                  class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out"
                  :class="settings.allow_contacts_access ? 'translate-x-5' : 'translate-x-0'"
                />
              </button>
            </div>

            <!-- Save button -->
            <div class="flex justify-end">
              <button
                @click="saveSettings"
                :disabled="settingsLoading"
                class="btn-primary flex items-center gap-2"
              >
                <Loader2 v-if="settingsLoading" class="w-4 h-4 animate-spin" />
                <Save v-else class="w-4 h-4" />
                {{ $t('zenith.save_settings') }}
              </button>
            </div>
          </div>

          <!-- Not enabled warning -->
          <UiAlert v-if="!settings.enabled && !showSettings" variant="warning" :title="$t('zenith.not_enabled')">
            <p class="mt-1">{{ $t('zenith.not_enabled_desc') }}</p>
            <button @click="showSettings = true" class="text-sm text-primary hover:underline mt-2">
              {{ $t('zenith.open_settings') }}
            </button>
          </UiAlert>

          <!-- Chat interface -->
          <div v-if="settings.enabled" class="bg-neutral-100 dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 overflow-hidden">
            <!-- Chat messages -->
            <div ref="messagesContainer" class="h-96 overflow-y-auto p-4 space-y-4">
              <!-- Welcome message -->
              <div v-if="messages.length === 0" class="text-center py-8">
                <Bot class="w-16 h-16 text-neutral-400 mx-auto mb-4" />
                <p class="text-neutral-600 dark:text-neutral-400">{{ $t('zenith.welcome') }}</p>
                <p class="text-sm text-neutral-500 dark:text-neutral-500 mt-2">{{ $t('zenith.welcome_desc') }}</p>
              </div>

              <!-- Messages -->
              <div
                v-for="(message, index) in messages"
                :key="index"
                class="flex"
                :class="message.role === 'user' ? 'justify-end' : 'justify-start'"
              >
                <div
                  class="max-w-[80%] rounded-lg px-4 py-2"
                  :class="message.role === 'user'
                    ? 'bg-primary text-black'
                    : 'bg-neutral-200 dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100'"
                >
                  <div class="flex items-center gap-2 mb-1">
                    <User v-if="message.role === 'user'" class="w-4 h-4" />
                    <Bot v-else class="w-4 h-4" />
                    <span class="text-xs opacity-75">
                      {{ message.role === 'user' ? $t('zenith.you') : 'Zenith' }}
                    </span>
                  </div>
                  <div class="whitespace-pre-wrap">{{ message.content }}</div>
                  <div v-if="message.usage" class="text-xs opacity-50 mt-1">
                    {{ message.usage.input_tokens + message.usage.output_tokens }} tokens | ${{ message.usage.cost_usd.toFixed(4) }}
                  </div>
                </div>
              </div>

              <!-- Loading indicator -->
              <div v-if="asking" class="flex justify-start">
                <div class="bg-neutral-200 dark:bg-neutral-700 rounded-lg px-4 py-2">
                  <div class="flex items-center gap-2">
                    <Loader2 class="w-4 h-4 animate-spin" />
                    <span class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t('zenith.thinking') }}</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- Input -->
            <div class="border-t border-neutral-200 dark:border-neutral-700 p-4">
              <form @submit.prevent="sendMessage" class="flex gap-2">
                <input
                  v-model="question"
                  type="text"
                  :placeholder="$t('zenith.ask_placeholder')"
                  :disabled="asking"
                  class="flex-1 px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
                />
                <button
                  type="submit"
                  :disabled="!question.trim() || asking"
                  class="btn-primary flex items-center gap-2"
                >
                  <Send class="w-4 h-4" />
                  {{ $t('zenith.send') }}
                </button>
              </form>
            </div>
          </div>

          <!-- Query logs -->
          <div v-if="settings.enabled && settings.total_queries > 0" class="bg-neutral-100 dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4 sm:p-6">
            <div class="flex items-center justify-between mb-4">
              <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
                <History class="w-5 h-5" />
                {{ $t('zenith.query_history') }}
              </h3>
              <span class="text-sm text-neutral-600 dark:text-neutral-400">
                {{ settings.total_queries }} {{ $t('zenith.total_queries') }}
              </span>
            </div>

            <button
              v-if="!logsLoaded"
              @click="loadLogs"
              class="btn-secondary w-full"
            >
              {{ $t('zenith.load_history') }}
            </button>

            <div v-else class="space-y-3 max-h-96 overflow-y-auto">
              <div
                v-for="log in logs"
                :key="log.id"
                class="border border-neutral-200 dark:border-neutral-700 rounded-lg p-3"
              >
                <div class="flex items-center justify-between mb-2">
                  <span class="text-xs text-neutral-500 dark:text-neutral-400">
                    {{ formatDate(log.created_at) }}
                    <span v-if="log.querier_hna" class="ml-2 text-secondary">
                      {{ $t('zenith.asked_by') }} {{ log.querier_hna }}
                    </span>
                    <span v-else class="ml-2 text-neutral-400">
                      ({{ $t('zenith.you') }})
                    </span>
                  </span>
                  <span v-if="log.success" class="text-xs text-green-600 dark:text-green-400">
                    {{ log.processing_time_ms }}ms
                  </span>
                  <span v-else class="text-xs text-red-600 dark:text-red-400">
                    {{ $t('zenith.failed') }}
                  </span>
                </div>
                <p class="text-sm font-medium text-neutral-900 dark:text-neutral-100 mb-1">
                  {{ log.question }}
                </p>
                <p v-if="log.success" class="text-sm text-neutral-700 dark:text-neutral-300 line-clamp-2">
                  {{ log.answer }}
                </p>
                <p v-else class="text-sm text-red-600 dark:text-red-400">
                  {{ log.error_message }}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Bot, Settings, Send, User, Loader2, Save, History } from 'lucide-vue-next'

const { t } = useI18n()
const authStore = useAuthStore()
const localePath = useLocalePath()
const toastStore = useToastStore()

// State
const showSettings = ref(false)
const settingsLoading = ref(false)
const settings = ref({
  enabled: false,
  gitea_repo_name: 'zenith-knowledge',
  allow_contacts_access: true,
  has_api_key: false,
  total_queries: 0,
  system_prompt: null
})
const newApiKey = ref('')

// Chat state
const messages = ref<Array<{role: 'user' | 'assistant', content: string, usage?: any}>>([])
const question = ref('')
const asking = ref(false)
const messagesContainer = ref<HTMLElement | null>(null)

// Logs state
const logs = ref<any[]>([])
const logsLoaded = ref(false)

// Load settings on mount
onMounted(async () => {
  if (authStore.isAuthenticated) {
    await loadSettings()
  }
})

// Watch for auth changes
watch(() => authStore.isAuthenticated, async (isAuth) => {
  if (isAuth) {
    await loadSettings()
  }
})

async function loadSettings() {
  try {
    await authStore.ensureToken()
    const response = await $fetch('/api/v1/zenith/settings', {
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`
      }
    })
    settings.value = response as any
  } catch (error) {
    console.error('Failed to load Zenith settings:', error)
  }
}

async function saveSettings() {
  settingsLoading.value = true
  try {
    await authStore.ensureToken()

    const updateData: any = {
      gitea_repo_name: settings.value.gitea_repo_name,
      allow_contacts_access: settings.value.allow_contacts_access
    }

    if (newApiKey.value) {
      updateData.gemini_api_key = newApiKey.value
    }

    const response = await $fetch('/api/v1/zenith/settings', {
      method: 'PUT',
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`,
        'Content-Type': 'application/json'
      },
      body: updateData
    })

    settings.value = response as any
    newApiKey.value = ''
    toastStore.success(t('zenith.settings_saved'))
  } catch (error: any) {
    console.error('Failed to save settings:', error)
    toastStore.error(error.data?.error || t('zenith.settings_save_failed'))
  } finally {
    settingsLoading.value = false
  }
}

async function toggleEnabled() {
  settingsLoading.value = true
  try {
    await authStore.ensureToken()
    const response = await $fetch('/api/v1/zenith/settings', {
      method: 'PUT',
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`,
        'Content-Type': 'application/json'
      },
      body: {
        enabled: !settings.value.enabled
      }
    })
    settings.value = response as any
  } catch (error: any) {
    console.error('Failed to toggle enabled:', error)
    toastStore.error(error.data?.error || t('zenith.settings_save_failed'))
  } finally {
    settingsLoading.value = false
  }
}

async function toggleContactsAccess() {
  settingsLoading.value = true
  try {
    await authStore.ensureToken()
    const response = await $fetch('/api/v1/zenith/settings', {
      method: 'PUT',
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`,
        'Content-Type': 'application/json'
      },
      body: {
        allow_contacts_access: !settings.value.allow_contacts_access
      }
    })
    settings.value = response as any
  } catch (error: any) {
    console.error('Failed to toggle contacts access:', error)
    toastStore.error(error.data?.error || t('zenith.settings_save_failed'))
  } finally {
    settingsLoading.value = false
  }
}

async function sendMessage() {
  if (!question.value.trim() || asking.value) return

  const userQuestion = question.value.trim()
  question.value = ''

  // Add user message
  messages.value.push({
    role: 'user',
    content: userQuestion
  })

  // Scroll to bottom
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })

  asking.value = true

  try {
    await authStore.ensureToken()
    const response = await $fetch('/api/v1/zenith/ask', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`,
        'Content-Type': 'application/json'
      },
      body: {
        question: userQuestion
      }
    }) as any

    // Add assistant message
    messages.value.push({
      role: 'assistant',
      content: response.answer,
      usage: response.usage
    })

    // Update total queries
    settings.value.total_queries++

  } catch (error: any) {
    console.error('Failed to ask Zenith:', error)
    const errorMsg = error.data?.error || t('zenith.ask_failed')
    messages.value.push({
      role: 'assistant',
      content: `Error: ${errorMsg}`
    })
    toastStore.error(errorMsg)
  } finally {
    asking.value = false

    // Scroll to bottom
    nextTick(() => {
      if (messagesContainer.value) {
        messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
      }
    })
  }
}

async function loadLogs() {
  try {
    await authStore.ensureToken()
    const response = await $fetch('/api/v1/zenith/logs', {
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`
      }
    })
    logs.value = response as any[]
    logsLoaded.value = true
  } catch (error) {
    console.error('Failed to load logs:', error)
    toastStore.error(t('zenith.logs_load_failed'))
  }
}

function formatDate(dateString: string) {
  return new Date(dateString).toLocaleString()
}

definePageMeta({
  middleware: 'auth',
})
</script>
