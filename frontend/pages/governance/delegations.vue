<template>
  <div class="py-6">
    <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
      <button @click="router.push(localePath('/governance/polls'))" class="text-link mb-4 flex items-center gap-1">
        <ArrowLeft class="w-4 h-4" aria-hidden="true" />
        {{ $t('governance.polls') }}
      </button>
      <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100 mb-2">
        {{ $t('civic.delegations.title') }}
      </h1>
      <p class="text-sm text-neutral-500 dark:text-neutral-400 mb-6">{{ $t('civic.delegations.hint') }}</p>

      <UiAlert v-if="data && data.voice_used_in_polls > 0" variant="info" :icon="GitBranch" class="mb-6">
        {{ $t('civic.delegations.voiceUsed', { n: data.voice_used_in_polls }) }}
      </UiAlert>

      <!-- Create -->
      <div class="card p-4 mb-6">
        <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-3 flex items-center gap-2">
          <UserPlus class="w-5 h-5" aria-hidden="true" />
          {{ $t('civic.delegations.create') }}
        </h2>
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-3">
          <div class="relative">
            <input
              v-model="delegateQuery"
              :placeholder="$t('civic.delegations.delegatePlaceholder')"
              class="w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 px-3 py-2 text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
              @input="searchDelegates"
            />
            <div v-if="delegateResults.length" class="absolute z-10 mt-1 w-full bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg shadow-lg overflow-hidden">
              <button
                v-for="p in delegateResults" :key="p.id"
                class="w-full text-left px-3 py-2 text-sm hover:bg-primary-100 dark:hover:bg-primary-900/40 text-neutral-800 dark:text-neutral-200"
                @click="pickDelegate(p)"
              >
                {{ p.display_name || p.hna }}
              </button>
            </div>
          </div>

          <select v-model="scopeType" class="w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 px-3 py-2 text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent">
            <option value="topic">{{ $t('civic.delegations.scopeTopic') }}</option>
            <option value="territory">{{ $t('civic.delegations.scopeTerritory') }}</option>
          </select>

          <select v-if="scopeType === 'topic'" v-model="topicSlug" class="w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 px-3 py-2 text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent">
            <option value="" disabled>—</option>
            <option v-for="t in topics" :key="t.slug" :value="t.slug">{{ t.icon }} {{ topicName(t) }}</option>
          </select>
          <select v-else v-model="territoryId" class="w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 px-3 py-2 text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent">
            <option value="" disabled>—</option>
            <option v-for="t in myChain" :key="t.id" :value="t.id">{{ $t(`civic.level.${t.level}`) }} · {{ t.name }}</option>
          </select>
        </div>
        <div class="flex items-center gap-3">
          <UiButton variant="primary" size="sm" :loading="creating"
                    :disabled="!delegateId || (scopeType === 'topic' ? !topicSlug : !territoryId)"
                    @click="createDelegation">
            {{ $t('civic.delegations.create') }}
          </UiButton>
          <span v-if="createdMsg" class="text-sm text-success">{{ createdMsg }}</span>
          <span v-if="createError" class="text-sm text-error">{{ createError }}</span>
        </div>
      </div>

      <!-- Loading -->
      <div v-if="!data" class="py-12 text-center" role="status" aria-live="polite">
        <div class="animate-spin rounded-full h-12 w-12 mx-auto border-b-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100" aria-hidden="true"></div>
        <span class="sr-only">{{ $t('common.loading') }}</span>
      </div>

      <template v-else>
        <!-- Requests to me -->
        <div v-if="data.received_pending.length" class="card p-4 mb-6">
          <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-1">
            {{ $t('civic.delegations.receivedPending') }}
          </h2>
          <p class="text-xs text-neutral-500 dark:text-neutral-400 mb-3">{{ $t('civic.delegations.acceptHint') }}</p>
          <div class="divide-y divide-neutral-200 dark:divide-neutral-700">
            <div v-for="d in data.received_pending" :key="d.id" class="py-3 flex flex-wrap items-center justify-between gap-2">
              <DelegationLine :d="d" />
              <div class="flex gap-2">
                <UiButton variant="success" size="sm" @click="act(d.id, 'accept')">{{ $t('civic.delegations.accept') }}</UiButton>
                <UiButton variant="ghost" size="sm" @click="act(d.id, 'decline')">{{ $t('civic.delegations.decline') }}</UiButton>
              </div>
            </div>
          </div>
        </div>

        <!-- Given -->
        <div class="card p-4 mb-6">
          <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-3">
            {{ $t('civic.delegations.given') }}
          </h2>
          <div v-if="data.given.length === 0" class="py-6 text-center text-sm text-neutral-500 dark:text-neutral-400">
            {{ $t('civic.delegations.empty') }}
          </div>
          <div v-else class="divide-y divide-neutral-200 dark:divide-neutral-700">
            <div v-for="d in data.given" :key="d.id" class="py-3 flex flex-wrap items-center justify-between gap-2">
              <DelegationLine :d="d" direction="given" />
              <UiButton
                :variant="pendingRevoke === d.id ? 'error' : 'outline-error'" size="sm"
                @click="revoke(d.id)"
              >
                {{ pendingRevoke === d.id ? $t('civic.delegations.revokeSure') : $t('civic.delegations.revoke') }}
              </UiButton>
            </div>
          </div>
        </div>

        <!-- I represent -->
        <div v-if="data.received_active.length" class="card p-4">
          <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-3">
            {{ $t('civic.delegations.receivedActive') }}
          </h2>
          <div class="divide-y divide-neutral-200 dark:divide-neutral-700">
            <div v-for="d in data.received_active" :key="d.id" class="py-3 flex flex-wrap items-center justify-between gap-2">
              <DelegationLine :d="d" direction="received" />
              <UiButton
                :variant="pendingRevoke === d.id ? 'error' : 'ghost'" size="sm"
                @click="revoke(d.id)"
              >
                {{ pendingRevoke === d.id ? $t('civic.delegations.revokeSure') : $t('civic.delegations.revoke') }}
              </UiButton>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, h, onMounted } from 'vue'
import { ArrowLeft, GitBranch, UserPlus } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'
import { usePGP } from '~/composables/usePGP'

definePageMeta({ middleware: 'auth' })

const router = useRouter()
const localePath = useLocalePath()
const authStore = useAuthStore()
const { t: $t, locale } = useI18n()
const { loadKeys, hasKeys, signCanonicalPayload } = usePGP()

const data = ref<any>(null)
const topics = ref<any[]>([])
const myChain = ref<any[]>([])

const delegateQuery = ref('')
const delegateId = ref('')
const delegateResults = ref<any[]>([])
const scopeType = ref<'topic' | 'territory'>('topic')
const topicSlug = ref('')
const territoryId = ref('')
const creating = ref(false)
const createdMsg = ref('')
const createError = ref('')
const pendingRevoke = ref<string | null>(null)
let revokeTimer: ReturnType<typeof setTimeout> | null = null
let searchTimer: ReturnType<typeof setTimeout> | null = null

// Inline row renderer: «topic/territory → @delegate» in either direction
const DelegationLine = (props: { d: any; direction?: string }) => {
  const d = props.d
  const scope = d.scope_type === 'topic'
    ? (d.topic_name || d.topic_slug)
    : `${$t(`civic.level.${d.territory_level}`)} · ${d.territory_name}`
  const other = props.direction === 'received'
    ? (d.delegator_display_name || d.delegator_hna.split('@')[0])
    : (d.delegate_display_name || d.delegate_hna.split('@')[0])
  const arrow = props.direction === 'received' ? '←' : '→'
  return h('div', { class: 'text-sm text-neutral-800 dark:text-neutral-200 min-w-0' }, [
    h('span', { class: 'font-medium' }, scope || ''),
    h('span', { class: 'text-neutral-500 dark:text-neutral-400' }, ` ${arrow} `),
    h('span', {}, `@${other}`),
    d.operational ? null : h('span', { class: 'ml-2 text-xs text-warning-600 dark:text-warning-400' }, '⏳'),
  ])
}

async function authed(): Promise<Record<string, string>> {
  await authStore.ensureToken()
  return { Authorization: `Bearer ${authStore.token}` }
}

async function load() {
  try {
    const headers = await authed()
    data.value = await $fetch('/api/v1/governance/civic/delegations/', { credentials: 'include', headers })
  } catch { /* auth middleware guards the page */ }
}

function topicName(t: any): string {
  return t.name_i18n?.[locale.value] || t.name
}

function searchDelegates() {
  delegateId.value = ''
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(async () => {
    const q = delegateQuery.value.trim().replace(/^@/, '')
    if (q.length < 2) { delegateResults.value = []; return }
    try {
      const headers = await authed()
      const res: any = await $fetch('/api/v1/profiles/search/', {
        credentials: 'include', headers, query: { q, page_size: 5 },
      })
      delegateResults.value = res?.items || res || []
    } catch { delegateResults.value = [] }
  }, 300)
}

function pickDelegate(p: any) {
  delegateId.value = p.id
  delegateQuery.value = p.display_name || p.hna
  delegateResults.value = []
}

async function createDelegation() {
  creating.value = true
  createdMsg.value = ''
  createError.value = ''
  try {
    const headers = await authed()
    await loadKeys()
    const timestamp = new Date().toISOString()
    let signature = ''
    if (hasKeys.value) {
      signature = await signCanonicalPayload({
        action: 'standing_delegation',
        delegate_id: delegateId.value,
        scope_type: scopeType.value,
        scope: scopeType.value === 'topic' ? topicSlug.value : territoryId.value,
        timestamp,
      })
    }
    await $fetch('/api/v1/governance/civic/delegations/', {
      method: 'POST', credentials: 'include', headers,
      body: {
        delegate_id: delegateId.value,
        scope_type: scopeType.value,
        topic_slug: scopeType.value === 'topic' ? topicSlug.value : null,
        territory_id: scopeType.value === 'territory' ? territoryId.value : null,
        pgp_signature: signature,
        signed_timestamp: timestamp,
      },
    })
    createdMsg.value = $t('civic.delegations.created')
    delegateQuery.value = ''
    delegateId.value = ''
    await load()
  } catch (e: any) {
    createError.value = e?.response?._data?.detail || e?.data?.detail || String(e?.message || e)
  } finally {
    creating.value = false
  }
}

async function act(id: string, action: 'accept' | 'decline') {
  try {
    const headers = await authed()
    await $fetch(`/api/v1/governance/civic/delegations/${id}/${action}/`, {
      method: 'POST', credentials: 'include', headers,
    })
    await load()
  } catch { /* keep list */ }
}

// Two-tap destructive confirmation (design-system pattern)
async function revoke(id: string) {
  if (pendingRevoke.value !== id) {
    pendingRevoke.value = id
    if (revokeTimer) clearTimeout(revokeTimer)
    revokeTimer = setTimeout(() => { pendingRevoke.value = null }, 3000)
    return
  }
  pendingRevoke.value = null
  try {
    const headers = await authed()
    await $fetch(`/api/v1/governance/civic/delegations/${id}/revoke/`, {
      method: 'POST', credentials: 'include', headers,
    })
    await load()
  } catch { /* keep list */ }
}

onMounted(async () => {
  load()
  try { topics.value = await $fetch('/api/v1/governance/civic/topics/') } catch { /* empty */ }
  try {
    const headers = await authed()
    const res: any = await $fetch('/api/v1/governance/civic/residency/', { credentials: 'include', headers })
    myChain.value = res.chain || []
  } catch { /* no residency */ }
})
</script>
