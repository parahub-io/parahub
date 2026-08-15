<template>
  <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
    <NuxtLink
      :to="localePath('/iot?tab=infra')"
      class="inline-flex items-center gap-1.5 text-sm text-neutral-500 dark:text-neutral-400 hover:text-secondary dark:hover:text-secondary-400 mb-4"
    >
      <ArrowLeft class="w-4 h-4" />
      Infrastructure
    </NuxtLink>

    <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100">Platform capabilities</h1>
    <p class="text-sm text-neutral-500 dark:text-neutral-400 mt-1 mb-6">
      Node-level authority over surfaces no organization owns. Authority inside an
      organization is handed out on that organization's own members page.
    </p>

    <!-- Loading -->
    <div v-if="loading" class="py-12 text-center" role="status" aria-live="polite">
      <div class="inline-block animate-spin rounded-full h-12 w-12 border-4 border-neutral-300 dark:border-neutral-600 border-t-neutral-900 dark:border-t-neutral-100" />
      <span class="sr-only">{{ $t('common.loading') }}</span>
    </div>

    <!-- No access -->
    <div v-else-if="accessDenied" class="py-12 text-center">
      <ShieldOff class="w-12 h-12 mx-auto text-neutral-400 mb-3" />
      <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100">Not permitted</h3>
      <p class="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
        Holding a capability does not include handing it out — only the node owner appoints.
      </p>
    </div>

    <template v-else>
      <div v-for="cap in capabilities" :key="cap.key" class="card p-4 mb-4">
        <div class="flex flex-wrap items-baseline gap-2">
          <h2 class="text-base font-semibold text-neutral-900 dark:text-neutral-100">{{ cap.label }}</h2>
          <span class="text-xs font-mono text-neutral-500 dark:text-neutral-400">{{ cap.key }}</span>
          <span class="ml-auto text-xs font-mono text-neutral-400 dark:text-neutral-500">
            group: {{ cap.group }}
          </span>
        </div>
        <p class="text-sm text-neutral-500 dark:text-neutral-400 mt-1 mb-3">{{ cap.description }}</p>

        <!-- Holders -->
        <div
          v-if="cap.holders.length"
          class="border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700 mb-3"
        >
          <div
            v-for="h in cap.holders"
            :key="h.username"
            class="flex flex-wrap items-center gap-2 px-3 py-2.5"
          >
            <!-- A stored avatar whose file is gone falls back to initials rather
                 than a broken-image glyph (media/ is not carried between servers) -->
            <img
              v-if="h.avatar_url"
              :src="h.avatar_url"
              alt=""
              class="w-7 h-7 rounded-full object-cover"
              @error="h.avatar_url = ''"
            >
            <div v-else class="w-7 h-7 rounded-full bg-neutral-200 dark:bg-neutral-700 flex items-center justify-center text-xs font-semibold text-neutral-600 dark:text-neutral-300">
              {{ (h.display_name || h.username).slice(0, 1).toUpperCase() }}
            </div>
            <div class="min-w-0">
              <div class="text-sm font-medium text-neutral-900 dark:text-neutral-100 truncate">
                {{ h.display_name || h.username }}
              </div>
              <div class="text-xs font-mono text-neutral-500 dark:text-neutral-400 truncate">{{ h.username }}</div>
            </div>
            <div class="ml-auto flex items-center gap-2">
              <!-- Staff pass every check by override; a revoke here would change nothing -->
              <UiBadge v-if="h.implicit" variant="neutral" type="soft" size="sm">staff · implicit</UiBadge>
              <UiButton
                v-else
                :variant="revokeArmed === armKey(cap, h) ? 'error' : 'outline-error'"
                size="sm"
                :loading="busy === armKey(cap, h)"
                @click="revoke(cap, h)"
              >
                {{ revokeArmed === armKey(cap, h) ? 'Sure?' : 'Revoke' }}
              </UiButton>
            </div>
          </div>
        </div>
        <p v-else class="text-sm text-neutral-500 dark:text-neutral-400 mb-3">Nobody holds this yet.</p>

        <!-- Grant -->
        <div class="relative">
          <div class="flex flex-wrap gap-2">
            <input
              v-model="search[cap.key]"
              type="text"
              placeholder="Find a login by name or username"
              class="flex-1 min-w-[12rem] px-3 py-2 text-sm rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 focus:ring-2 focus:ring-primary focus:border-transparent"
              @input="onSearch(cap.key)"
              @blur="closeResults(cap.key)"
            >
          </div>
          <div
            v-if="(results[cap.key] || []).length"
            class="absolute z-20 mt-1 w-full max-w-md rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 shadow-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700"
          >
            <button
              v-for="a in results[cap.key]"
              :key="a.username"
              type="button"
              class="w-full text-left px-3 py-2 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors"
              @click="grant(cap, a)"
            >
              <span class="text-sm text-neutral-900 dark:text-neutral-100">{{ a.display_name || a.username }}</span>
              <span class="ml-2 text-xs font-mono text-neutral-500 dark:text-neutral-400">{{ a.username }}</span>
            </button>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ArrowLeft, ShieldOff } from 'lucide-vue-next'
import { useToastStore } from '~/stores/toast'

definePageMeta({ middleware: 'auth' })

const localePath = useLocalePath()
const authStore = useAuthStore()
const toast = useToastStore()

useHead({ title: 'Platform capabilities' })

const loading = ref(true)
const accessDenied = ref(false)
const capabilities = ref<any[]>([])
const search = reactive<Record<string, string>>({})
const results = reactive<Record<string, any[]>>({})
const busy = ref('')
const revokeArmed = ref('')
let armTimer: any = null
const searchTimers: Record<string, any> = {}

const armKey = (cap: any, holder: any) => `${cap.key}:${holder.username}`

async function authed() {
  await authStore.ensureToken()
  return { Authorization: `Bearer ${authStore.token}` }
}

async function load() {
  loading.value = true
  try {
    capabilities.value = await $fetch<any[]>('/api/v1/platform/capabilities/', {
      credentials: 'include', headers: await authed(),
    })
  } catch (e: any) {
    if ((e?.response?.status ?? e?.statusCode) === 403) accessDenied.value = true
    else toast.error('Failed to load capabilities')
  } finally {
    loading.value = false
  }
}

function onSearch(key: string) {
  clearTimeout(searchTimers[key])
  searchTimers[key] = setTimeout(async () => {
    const q = (search[key] || '').trim()
    if (q.length < 2) { results[key] = []; return }
    try {
      results[key] = await $fetch<any[]>('/api/v1/platform/accounts/', {
        credentials: 'include', headers: await authed(), params: { q },
      })
    } catch {
      results[key] = []
    }
  }, 250)
}

// Late enough for a click on a result to land first.
function closeResults(key: string) {
  setTimeout(() => { results[key] = [] }, 200)
}

async function grant(cap: any, account: any) {
  busy.value = armKey(cap, account)
  try {
    await $fetch(`/api/v1/platform/capabilities/${cap.key}/holders/`, {
      method: 'POST',
      credentials: 'include',
      headers: await authed(),
      body: { username: account.username },
    })
    toast.success(`${account.display_name || account.username} now holds ${cap.key}`)
    search[cap.key] = ''
    results[cap.key] = []
    await load()
  } catch {
    toast.error('Failed to grant')
  } finally {
    busy.value = ''
  }
}

async function revoke(cap: any, holder: any) {
  const key = armKey(cap, holder)
  if (revokeArmed.value !== key) {
    revokeArmed.value = key
    clearTimeout(armTimer)
    armTimer = setTimeout(() => { revokeArmed.value = '' }, 3000)
    return
  }
  revokeArmed.value = ''
  busy.value = key
  try {
    await $fetch(`/api/v1/platform/capabilities/${cap.key}/holders/${holder.username}/`, {
      method: 'DELETE', credentials: 'include', headers: await authed(),
    })
    toast.success(`${cap.key} withdrawn from ${holder.username}`)
    await load()
  } catch {
    toast.error('Failed to revoke')
  } finally {
    busy.value = ''
  }
}

onMounted(load)

let firstActivation = true
onActivated(() => {
  if (firstActivation) { firstActivation = false; return }
  load()
})
</script>
