<template>
  <div class="min-h-screen bg-neutral-50 dark:bg-neutral-900 pb-24 pt-24">
    <div class="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
      <!-- Header -->
      <div class="mb-6">
        <button @click="router.push(localePath(`/governance/polls/${pollId}`))" class="text-link mb-4 flex items-center gap-1">
          <ArrowLeft class="w-4 h-4" />
          {{ $t('governance.pollDetail.backToPoll') }}
        </button>

        <h1 class="text-3xl font-bold text-neutral-900 dark:text-neutral-100">
          {{ $t('governance.auditLog.title') }}
        </h1>
        <p class="text-neutral-600 dark:text-neutral-400 mt-2">
          {{ $t('governance.auditLog.description') }}
        </p>
      </div>

      <!-- Merkle Root -->
      <div v-if="poll" class="bg-gradient-to-r from-secondary-50 to-secondary-100 dark:from-secondary-900/20 dark:to-secondary-900/10 border border-secondary-200 dark:border-secondary-800 rounded-lg p-6 mb-6">
        <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-3 flex items-center gap-2">
          <Shield class="w-5 h-5" />
          {{ $t('governance.auditLog.merkleRoot') }}
        </h2>
        <div class="font-mono text-sm bg-white dark:bg-neutral-800 rounded px-3 py-2 break-all">
          {{ poll.merkle_root || $t('governance.auditLog.notCalculated') }}
        </div>
        <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-2">
          {{ $t('governance.auditLog.merkleRootHint') }}
        </p>
        <div v-if="poll.status === 'ended'" class="mt-3 flex gap-3">
          <button class="btn-secondary text-sm">
            🔍 {{ $t('governance.auditLog.verifyIntegrity') }}
          </button>
          <button class="btn-secondary btn-sm">
            📥 {{ $t('governance.auditLog.exportLog') }}
          </button>
        </div>
      </div>

      <!-- Loading State -->
      <div v-if="loading" class="flex justify-center py-12">
        <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100"></div>
      </div>

      <!-- Error State -->
      <UiAlert v-else-if="error" variant="error">{{ error }}</UiAlert>

      <!-- Empty State -->
      <div v-else-if="!logs || logs.length === 0" class="text-center py-12">
        <FileText class="w-12 h-12 mx-auto mb-4 text-neutral-300 dark:text-neutral-600" />
        <h3 class="text-xl font-semibold text-neutral-700 dark:text-neutral-300 mb-2">
          {{ $t('governance.auditLog.noEvents') }}
        </h3>
        <p class="text-neutral-600 dark:text-neutral-400">
          {{ $t('governance.auditLog.noEventsDescription') }}
        </p>
      </div>

      <!-- Audit Log Entries -->
      <div v-else class="space-y-4">
        <!-- Summary -->
        <div class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-6 mb-6">
          <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4">{{ $t('governance.pollDetail.statistics') }}</h2>
          <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div class="text-center">
              <div class="text-2xl font-bold text-secondary dark:text-secondary-400">{{ logs.length }}</div>
              <div class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('governance.auditLog.totalEvents') }}</div>
            </div>
            <div class="text-center">
              <div class="text-2xl font-bold text-success dark:text-success-400">{{ voteCount }}</div>
              <div class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('governance.auditLog.voteEvents') }}</div>
            </div>
            <div class="text-center">
              <div class="text-2xl font-bold text-secondary dark:text-secondary-400">{{ delegationCount }}</div>
              <div class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('governance.auditLog.delegationEvents') }}</div>
            </div>
            <div class="text-center">
              <div class="text-2xl font-bold text-neutral-700 dark:text-neutral-300">{{ chainVerified ? '✓' : '?' }}</div>
              <div class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('governance.auditLog.integrity') }}</div>
            </div>
          </div>
        </div>

        <!-- Log Entries -->
        <div
          v-for="(log, index) in paginatedLogs"
          :key="log.id || index"
          class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-6"
        >
          <!-- Entry Header -->
          <div class="flex justify-between items-start mb-4">
            <div>
              <div class="flex items-center gap-2">
                <component :is="getActionIcon(log.action)" class="w-5 h-5" :class="getActionColor(log.action)" />
                <span class="font-semibold text-neutral-900 dark:text-neutral-100">
                  {{ getActionLabel(log.action) }}
                </span>
              </div>
              <div class="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
                {{ formatDate(log.timestamp) }}
              </div>
            </div>
            <div class="text-right">
              <div class="text-xs text-neutral-500 dark:text-neutral-400">
                #{{ logs.length - index }}
              </div>
            </div>
          </div>

          <!-- Payload -->
          <div class="mb-4 p-3 bg-neutral-50 dark:bg-neutral-900 rounded-lg">
            <div class="text-xs font-semibold text-neutral-500 dark:text-neutral-400 mb-2">{{ $t('governance.auditLog.payload') }}:</div>
            <pre class="text-xs font-mono text-neutral-700 dark:text-neutral-300 whitespace-pre-wrap break-all">{{ JSON.stringify(log.payload, null, 2) }}</pre>
          </div>

          <!-- Crypto Info -->
          <div class="space-y-2">
            <div>
              <div class="text-xs font-semibold text-neutral-500 dark:text-neutral-400 mb-1">{{ $t('governance.auditLog.currentHash') }}:</div>
              <div class="font-mono text-xs bg-neutral-50 dark:bg-neutral-900 rounded px-2 py-1 break-all text-neutral-700 dark:text-neutral-300">
                {{ log.current_log_hash }}
              </div>
            </div>
            <div v-if="log.previous_log_hash">
              <div class="text-xs font-semibold text-neutral-500 dark:text-neutral-400 mb-1">{{ $t('governance.auditLog.previousHash') }}:</div>
              <div class="font-mono text-xs bg-neutral-50 dark:bg-neutral-900 rounded px-2 py-1 break-all text-neutral-700 dark:text-neutral-300">
                {{ log.previous_log_hash }}
              </div>
            </div>
            <div>
              <div class="text-xs font-semibold text-neutral-500 dark:text-neutral-400 mb-1">{{ $t('governance.auditLog.pgpSignature') }}:</div>
              <div class="font-mono text-xs bg-neutral-50 dark:bg-neutral-900 rounded px-2 py-1 break-all text-neutral-700 dark:text-neutral-300 max-h-20 overflow-y-auto">
                {{ log.pgp_signature }}
              </div>
            </div>
          </div>
        </div>

        <!-- Pagination -->
        <div v-if="totalPages > 1" class="flex justify-center gap-2 mt-6">
          <button
            v-for="page in totalPages"
            :key="page"
            @click="currentPage = page"
            class="px-4 py-2 rounded-lg transition-colors"
            :class="currentPage === page
              ? 'bg-secondary text-white'
              : 'bg-white dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-700'"
          >
            {{ page }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ArrowLeft, Shield, FileText, Vote, UserPlus, UserMinus, Play, Square, AlertCircle } from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()
const localePath = useLocalePath()
const { t, locale } = useI18n()

const pollId = computed(() => route.params.id as string)

// State
const logs = ref<any[]>([])
const poll = ref<any>(null)
const loading = ref(false)
const error = ref('')
const currentPage = ref(1)
const pageSize = 10
const chainVerified = ref<boolean | null>(null)

// Fetch audit log
async function fetchAuditLog() {
  loading.value = true
  error.value = ''

  try {
    // Fetch poll
    poll.value = await $fetch(`/api/v1/governance/polls/${pollId.value}/`, {
      credentials: 'include',
    })

    // Fetch audit log
    const logsResponse = await $fetch<any[]>(`/api/v1/governance/polls/${pollId.value}/audit-log/`, {
      credentials: 'include',
    })
    logs.value = logsResponse

  } catch (e: any) {
    console.error('Failed to fetch audit log:', e)
    error.value = e.data?.message || e.message || t('governance.errors.loadingAuditLog')
  } finally {
    loading.value = false
  }
}

// Computed
const paginatedLogs = computed(() => {
  const start = (currentPage.value - 1) * pageSize
  const end = start + pageSize
  return logs.value.slice(start, end)
})

const totalPages = computed(() => {
  return Math.ceil(logs.value.length / pageSize)
})

const voteCount = computed(() => {
  return logs.value.filter(log => log.action === 'vote_cast').length
})

const delegationCount = computed(() => {
  return logs.value.filter(log => log.action === 'delegation_created' || log.action === 'delegation_revoked').length
})

// Helpers
function getActionIcon(action: string) {
  switch (action) {
    case 'poll_created':
    case 'poll_started':
      return Play
    case 'vote_cast':
      return Vote
    case 'delegation_created':
      return UserPlus
    case 'delegation_revoked':
      return UserMinus
    case 'poll_ended':
      return Square
    default:
      return AlertCircle
  }
}

function getActionColor(action: string) {
  switch (action) {
    case 'poll_created':
    case 'poll_started':
      return 'text-secondary dark:text-secondary-400'
    case 'vote_cast':
      return 'text-success dark:text-success-400'
    case 'delegation_created':
      return 'text-secondary dark:text-secondary-400'
    case 'delegation_revoked':
      return 'text-warning dark:text-warning-400'
    case 'poll_ended':
      return 'text-neutral-600 dark:text-neutral-400'
    default:
      return 'text-neutral-600 dark:text-neutral-400'
  }
}

function getActionLabel(action: string) {
  return t(`governance.auditLog.actions.${action}`, action)
}

function formatDate(dateString: string): string {
  const date = new Date(dateString)
  return date.toLocaleString(locale.value, {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

// Lifecycle
onMounted(() => {
  fetchAuditLog()
})

definePageMeta({})
</script>
