<template>
  <div class="min-h-screen bg-neutral-50 dark:bg-neutral-900 pb-24 pt-24">
    <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
      <!-- Loading State -->
      <div v-if="loading" class="flex justify-center py-12">
        <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>

      <!-- Error State -->
      <UiAlert v-else-if="loadError" variant="error">
        {{ loadError }}
        <button @click="router.push(localePath('/governance/polls'))" class="mt-2 text-sm text-error-700 dark:text-error-300 hover:underline">
          ← {{ $t('governance.pollDetail.backToList') }}
        </button>
      </UiAlert>

      <!-- Poll Detail -->
      <div v-else-if="poll">
        <!-- Header -->
        <div class="mb-6">
          <button @click="router.push(localePath('/governance/polls'))" class="text-link mb-4 flex items-center gap-1">
            <ArrowLeft class="w-4 h-4" />
            {{ $t('governance.pollDetail.backToList') }}
          </button>

          <div class="flex justify-between items-start mb-4">
            <div>
              <div class="flex items-center gap-2 mb-3">
                <DemoBadge :is-demo="poll.is_demo" />
                <span
                  class="inline-block px-3 py-1 rounded-full text-xs font-semibold"
                  :class="getStatusClass(poll.status)"
                >
                  {{ getStatusLabel(poll.status) }}
                </span>
              </div>
              <h1 class="text-3xl font-bold text-neutral-900 dark:text-neutral-100">
                {{ poll.title }}
              </h1>
            </div>
          </div>

          <div class="flex items-center gap-4 text-sm text-neutral-500 dark:text-neutral-400">
            <div class="flex items-center gap-1">
              <User class="w-4 h-4" />
              <span>{{ poll.created_by_display_name || formatAuthor(poll.created_by_hna) }}</span>
            </div>
            <div class="flex items-center gap-1">
              <Calendar class="w-4 h-4" />
              <span>{{ formatDate(poll.created_at) }}</span>
            </div>
            <div v-if="poll.end_time" class="flex items-center gap-1">
              <Clock class="w-4 h-4" />
              <span>{{ getTimeRemaining(poll.end_time) }}</span>
            </div>
          </div>
        </div>

        <!-- Description -->
        <div class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-6 mb-6">
          <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-3">{{ $t('governance.pollDetail.description') }}</h2>
          <p class="text-neutral-700 dark:text-neutral-300 whitespace-pre-wrap">{{ poll.description }}</p>
        </div>

        <!-- Statistics -->
        <div class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-6 mb-6">
          <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4">{{ $t('governance.pollDetail.statistics') }}</h2>

          <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <div class="text-center">
              <div class="text-2xl font-bold text-secondary dark:text-secondary-400">{{ poll.total_voted }}</div>
              <div class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('governance.pollDetail.totalVoted') }}</div>
            </div>
            <div class="text-center">
              <div class="text-2xl font-bold text-neutral-700 dark:text-neutral-300">{{ poll.total_eligible }}</div>
              <div class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('governance.pollDetail.totalEligible') }}</div>
            </div>
            <div class="text-center">
              <div class="text-2xl font-bold" :class="poll.quorum_met ? 'text-success dark:text-success-400' : 'text-error dark:text-error-400'">
                {{ getProgressPercent(poll) }}%
              </div>
              <div class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('governance.pollDetail.turnout') }}</div>
            </div>
            <div class="text-center">
              <div class="text-2xl font-bold text-neutral-700 dark:text-neutral-300">{{ poll.quorum_percent }}%</div>
              <div class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('governance.quorum') }}</div>
            </div>
          </div>

          <!-- Progress Bar -->
          <div class="w-full bg-neutral-200 dark:bg-neutral-700 rounded-full h-3">
            <div
              class="h-3 rounded-full transition-all"
              :class="poll.quorum_met ? 'bg-success' : 'bg-secondary'"
              :style="`width: ${getProgressPercent(poll)}%`"
            ></div>
          </div>
          <div v-if="poll.quorum_met" class="flex items-center gap-2 mt-2 text-success dark:text-success-400">
            <CheckCircle class="w-4 h-4" />
            <span class="text-sm font-medium">{{ $t('governance.quorumReached') }}</span>
          </div>
        </div>

        <!-- User Status Card (if authenticated) -->
        <div v-if="authStore.isAuthenticated && myStatus" class="bg-secondary-50 dark:bg-secondary-900/20 border border-secondary-200 dark:border-secondary-800 rounded-lg p-6 mb-6">
          <h2 class="text-lg font-semibold text-secondary-900 dark:text-secondary-100 mb-4">{{ $t('governance.pollDetail.yourStatus') }}</h2>

          <!-- Already Voted -->
          <div v-if="myStatus.has_voted" class="flex items-start gap-3">
            <CheckCircle class="w-6 h-6 text-success dark:text-success-400 flex-shrink-0 mt-0.5" />
            <div>
              <div class="font-medium text-success-700 dark:text-success-300">{{ $t('governance.pollDetail.youVoted') }}</div>
              <div class="text-sm text-neutral-700 dark:text-neutral-300 mt-1">
                {{ $t('governance.pollDetail.yourChoice') }}: <span class="font-semibold">{{ myStatus.vote_option_text }}</span>
              </div>
              <div class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
                {{ $t('governance.pollDetail.voteId') }}: {{ myStatus.vote_option_id?.substring(0, 8) }}...
              </div>
            </div>
          </div>

          <!-- Has Delegation -->
          <div v-else-if="myStatus.has_delegation" class="flex items-start gap-3">
            <UserPlus class="w-6 h-6 text-secondary dark:text-secondary-400 flex-shrink-0 mt-0.5" />
            <div class="flex-1">
              <div class="font-medium text-secondary-700 dark:text-secondary-300">{{ $t('governance.pollDetail.youDelegated') }}</div>
              <div class="text-sm text-neutral-700 dark:text-neutral-300 mt-1">
                {{ $t('governance.pollDetail.delegate') }}: <span class="font-semibold">{{ myStatus.delegate_hna }}</span>
              </div>
              <div v-if="myStatus.delegate_voted" class="text-sm text-success-700 dark:text-success-300 mt-1">
                ✓ {{ $t('governance.delegateHasVoted') }}
              </div>
              <div v-else class="text-sm text-warning-700 dark:text-warning-300 mt-1">
                ⏳ {{ $t('governance.delegateNotVoted') }}
              </div>
              <button
                @click="revokeDelegation"
                :disabled="revokingDelegation"
                class="mt-3 px-3 py-1.5 text-sm bg-error-100 dark:bg-error-900/30 text-error-700 dark:text-error-300 rounded-lg hover:bg-error-200 dark:hover:bg-error-900/50 transition-colors disabled:opacity-50"
              >
                {{ revokingDelegation ? $t('governance.revoking') : $t('governance.revokeDelegation') }}
              </button>
            </div>
          </div>

          <!-- Can Vote -->
          <div v-else-if="myStatus.can_vote">
            <div class="flex items-center gap-2 text-secondary-700 dark:text-secondary-300 mb-3">
              <Vote class="w-5 h-5" />
              <span class="font-medium">{{ $t('governance.pollDetail.canVote') }}</span>
            </div>
          </div>

          <!-- Cannot Vote -->
          <div v-else class="flex items-start gap-3">
            <AlertCircle class="w-6 h-6 text-error dark:text-error-400 flex-shrink-0 mt-0.5" />
            <div>
              <div class="font-medium text-error-700 dark:text-error-300">{{ $t('governance.pollDetail.cannotVote') }}</div>
              <div class="text-sm text-neutral-700 dark:text-neutral-300 mt-1">
                {{ myStatus.vote_error }}
              </div>
            </div>
          </div>
        </div>

        <!-- Voting Section -->
        <div v-if="authStore.isAuthenticated && myStatus?.can_vote && poll.status === 'active'" class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-6 mb-6">
          <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4">{{ $t('governance.pollDetail.yourChoice') }}</h2>

          <div class="space-y-3 mb-6">
            <label
              v-for="option in poll.options"
              :key="option.id"
              class="flex items-start gap-3 p-4 border-2 rounded-lg cursor-pointer transition-all"
              :class="selectedOption === option.id
                ? 'border-secondary bg-secondary-50 dark:bg-secondary-900/20'
                : 'border-neutral-200 dark:border-neutral-700 hover:border-secondary-300 dark:hover:border-secondary-700'"
            >
              <input
                type="radio"
                :value="option.id"
                v-model="selectedOption"
                class="mt-1"
              />
              <div class="flex-1">
                <div class="font-medium text-neutral-900 dark:text-neutral-100">{{ option.text }}</div>
                <div v-if="option.description" class="text-sm text-neutral-600 dark:text-neutral-400 mt-1">
                  {{ option.description }}
                </div>
              </div>
            </label>
          </div>

          <div
            v-if="voteError"
            class="mb-4 p-4 rounded-lg border"
            :class="voteNeedsKeys
              ? 'border-warning-300 bg-warning-50 dark:border-warning-700 dark:bg-warning-900/20'
              : 'border-error-300 bg-error-50 dark:border-error-700 dark:bg-error-900/20'"
          >
            <div class="flex items-start gap-3">
              <AlertCircle
                class="w-5 h-5 flex-shrink-0 mt-0.5"
                :class="voteNeedsKeys ? 'text-warning-600 dark:text-warning-400' : 'text-error-600 dark:text-error-400'"
              />
              <div class="flex-1">
                <div
                  class="text-sm"
                  :class="voteNeedsKeys ? 'text-warning-800 dark:text-warning-200' : 'text-error-800 dark:text-error-200'"
                >
                  {{ voteError }}
                </div>
                <NuxtLink
                  v-if="voteNeedsKeys"
                  :to="localePath('/seed-restore')"
                  class="inline-flex items-center gap-1 mt-2 text-sm font-medium text-warning-700 dark:text-warning-300 hover:underline"
                >
                  <KeyRound class="w-4 h-4" />
                  {{ $t('governance.errors.restoreKeys') }}
                </NuxtLink>
              </div>
            </div>
          </div>

          <div class="flex gap-3">
            <button
              @click="castVote"
              :disabled="!selectedOption || voting"
              class="btn-secondary flex-1 gap-2"
            >
              <Vote class="w-5 h-5" />
              {{ voting ? $t('governance.voting_in_progress') : $t('governance.voteFor') }}
            </button>

            <button
              v-if="poll.allow_delegation"
              @click="showDelegateModal = true"
              class="px-6 py-3 bg-secondary hover:bg-secondary-600 text-white rounded-lg font-medium transition-colors flex items-center gap-2"
            >
              <UserPlus class="w-5 h-5" />
              {{ $t('governance.delegate') }}
            </button>
          </div>
        </div>

        <!-- Results Section -->
        <div v-if="poll.results && (poll.public_results || poll.status === 'ended')" class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-6 mb-6">
          <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4">
            {{ poll.status === 'ended' ? $t('governance.results') : $t('governance.intermediateResults') }}
          </h2>

          <div class="space-y-4">
            <div
              v-for="result in sortedResults"
              :key="result.option_id"
              class="relative"
            >
              <div class="flex justify-between items-center mb-2">
                <div class="flex items-center gap-2">
                  <span
                    v-if="result.option_id === poll.winning_option_id"
                    class="text-primary"
                  >
                    🏆
                  </span>
                  <span class="font-medium text-neutral-900 dark:text-neutral-100">
                    {{ result.option_text }}
                  </span>
                </div>
                <div class="text-right">
                  <div class="font-semibold text-neutral-900 dark:text-neutral-100">
                    {{ result.percentage.toFixed(1) }}%
                  </div>
                  <div class="text-xs text-neutral-500 dark:text-neutral-400">
                    {{ $t('governance.nVotes', result.voter_count) }}
                  </div>
                </div>
              </div>

              <div class="w-full bg-neutral-200 dark:bg-neutral-700 rounded-full h-3 overflow-hidden">
                <div
                  class="h-3 rounded-full transition-all"
                  :class="result.option_id === poll.winning_option_id ? 'bg-primary' : 'bg-secondary'"
                  :style="`width: ${result.percentage}%`"
                ></div>
              </div>
            </div>
          </div>

          <UiAlert v-if="poll.status === 'ended' && poll.winning_option_id" variant="warning" :icon="Trophy" class="mt-6">
            <span class="font-semibold">
              {{ $t('governance.winner') }}: {{ poll.results.find((r: any) => r.option_id === poll.winning_option_id)?.option_text }}
            </span>
          </UiAlert>
        </div>

        <!-- Actions -->
        <div class="flex gap-3">
          <button
            v-if="poll.results"
            @click="router.push(localePath(`/governance/polls/delegations-${poll.id}`))"
            class="px-4 py-2 bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 text-neutral-700 dark:text-neutral-300 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors flex items-center gap-2"
          >
            <GitBranch class="w-4 h-4" />
            {{ $t('governance.delegationChains.title') }}
          </button>

          <button
            @click="router.push(localePath(`/governance/polls/audit-${poll.id}`))"
            class="px-4 py-2 bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 text-neutral-700 dark:text-neutral-300 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors flex items-center gap-2"
          >
            <Shield class="w-4 h-4" />
            {{ $t('governance.auditLog.title') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Delegate Modal -->
    <Teleport to="body">
      <div
        v-if="showDelegateModal"
        class="fixed inset-0 bg-black/50 flex items-center justify-center z-[100]"
        @click="showDelegateModal = false"
      >
        <div
          class="bg-white dark:bg-neutral-900 rounded-lg shadow-xl max-w-md w-full mx-4 p-6"
          @click.stop
        >
          <h3 class="text-lg font-semibold mb-4 text-neutral-900 dark:text-neutral-100">
            {{ $t('governance.delegateVote') }}
          </h3>

          <p class="text-sm text-neutral-600 dark:text-neutral-400 mb-4">
            {{ $t('governance.delegateModal.description') }}
          </p>

          <div class="mb-4">
            <label class="block text-sm font-medium mb-2 text-neutral-700 dark:text-neutral-300">
              {{ $t('governance.delegateModal.delegateHna') }}
            </label>
            <input
              v-model="delegateHna"
              type="text"
              :placeholder="$t('governance.delegateModal.delegateHnaPlaceholder')"
              class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100"
            />
          </div>

          <div v-if="delegateError" class="mb-4 text-sm text-error dark:text-error-400">
            {{ delegateError }}
          </div>

          <div class="flex gap-3 justify-end">
            <button
              @click="showDelegateModal = false"
              class="px-4 py-2 text-sm text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded-lg transition-colors"
            >
              {{ $t('governance.delegateModal.cancel') }}
            </button>
            <button
              @click="createDelegation"
              :disabled="!delegateHna || delegating"
              class="px-4 py-2 text-sm bg-secondary hover:bg-secondary-600 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {{ delegating ? $t('governance.delegating') : $t('governance.delegate') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ArrowLeft, User, Calendar, Clock, CheckCircle, Vote, UserPlus, AlertCircle, Trophy, GitBranch, Shield, KeyRound } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'
import { usePollWebSocket } from '~/composables/usePollWebSocket'
import { usePGP } from '~/composables/usePGP'

const route = useRoute()
const router = useRouter()
const localePath = useLocalePath()
const authStore = useAuthStore()
const { loadKeys, signCanonicalPayload, hasKeys } = usePGP()
const { t: $t, locale } = useI18n()
const pollId = computed(() => route.params.id as string)

// SSR-ready fetch (public data for SEO title)
const { data: poll, pending: loading, error: fetchError } = await useAsyncData(
  `poll-${route.params.id}`,
  () => $fetch(`/api/v1/governance/polls/${route.params.id}/`, {
    credentials: 'include',
  })
)
const myStatus = ref<any>(null)
const loadError = computed(() => {
  if (!fetchError.value) return null
  const err = fetchError.value as any
  return err.data?.message || err.message || $t('governance.errors.loadingPoll')
})
const voteError = ref<string>('')
const voteNeedsKeys = ref(false)

// SEO meta
useSeoMeta({
  title: () => poll.value?.title ? `${poll.value.title} — Parahub` : 'Parahub',
})

// WebSocket for real-time updates
const ws = usePollWebSocket(pollId.value)

// Real-time object field updates
useObjectSubscription(poll)
const selectedOption = ref<string | null>(null)
const voting = ref(false)
const showDelegateModal = ref(false)
const delegateHna = ref('')
const delegating = ref(false)
const delegateError = ref('')
const revokingDelegation = ref(false)

// Setup WebSocket event handlers
ws.onVoteCast.value = (data) => {
  fetchPoll()
}

ws.onDelegationCreated.value = (data) => {
  fetchPoll()
}

ws.onDelegationRevoked.value = (data) => {
  fetchPoll()
}

ws.onResultsUpdated.value = (data) => {
  // Update results directly without full refresh
  if (poll.value && poll.value.results) {
    poll.value.results = data.results
    poll.value.quorum_met = data.quorum_met
  }
}

// Refresh poll details (client-side, after votes/delegations)
async function fetchPoll() {
  try {
    poll.value = await $fetch(`/api/v1/governance/polls/${pollId.value}/`, {
      credentials: 'include',
    })

    // Fetch user status if authenticated
    if (authStore.isAuthenticated) {
      await fetchMyStatus()
    }
  } catch (e: any) {
    console.error('Failed to fetch poll:', e)
  }
}

// Fetch user status
async function fetchMyStatus() {
  try {
    await authStore.ensureToken()

    myStatus.value = await $fetch(`/api/v1/governance/polls/${pollId.value}/my-status/`, {
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`
      }
    })
  } catch (e: any) {
    console.error('Failed to fetch user status:', e)
  }
}

// Cast vote
async function castVote() {
  if (!selectedOption.value) return

  voting.value = true
  voteError.value = ''
  voteNeedsKeys.value = false

  await loadKeys()
  if (!hasKeys.value) {
    voteNeedsKeys.value = true
    voteError.value = $t('governance.errors.pgpKeysRequired')
    voting.value = false
    return
  }

  try {
    await authStore.ensureToken()

    const timestamp = new Date().toISOString()
    const signature = await signCanonicalPayload({
      option_id: selectedOption.value,
      poll_id: pollId.value,
      timestamp,
    })

    await $fetch(`/api/v1/governance/polls/${pollId.value}/vote/`, {
      method: 'POST',
      body: {
        option_id: selectedOption.value,
        pgp_signature: signature,
        signed_timestamp: timestamp,
      },
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`
      }
    })

    await fetchPoll()
    selectedOption.value = null
  } catch (e: any) {
    console.error('Failed to cast vote:', e)
    voteError.value = e.data?.detail || e.data?.message || e.message || $t('governance.errors.voting')
  } finally {
    voting.value = false
  }
}

// Create delegation
async function createDelegation() {
  if (!delegateHna.value) return

  delegating.value = true
  delegateError.value = ''

  try {
    await authStore.ensureToken()

    // Resolve HNA (e.g. "alice@parahub.io" or "alice") to profile ULID
    const localName = delegateHna.value.replace(/^@/, '').split('@')[0]
    let delegateId: string
    try {
      const profile = await $fetch<{ id: string }>(`/api/v1/profiles/${localName}/`, {
        credentials: 'include',
        headers: { 'Authorization': `Bearer ${authStore.token}` }
      })
      delegateId = profile.id
    } catch {
      delegateError.value = $t('governance.errors.delegateNotFound')
      delegating.value = false
      return
    }

    const timestamp = new Date().toISOString()
    const signature = await signCanonicalPayload({
      delegate_id: delegateId,
      poll_id: pollId.value,
      timestamp,
    })

    await $fetch(`/api/v1/governance/polls/${pollId.value}/delegate/`, {
      method: 'POST',
      body: {
        delegate_id: delegateId,
        pgp_signature: signature,
        signed_timestamp: timestamp,
      },
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`
      }
    })

    showDelegateModal.value = false
    delegateHna.value = ''
    await fetchPoll()
  } catch (e: any) {
    console.error('Failed to create delegation:', e)
    delegateError.value = e.data?.message || e.message || $t('governance.errors.delegating')
  } finally {
    delegating.value = false
  }
}

// Revoke delegation
async function revokeDelegation() {
  revokingDelegation.value = true

  try {
    await authStore.ensureToken()

    const timestamp = new Date().toISOString()
    const signature = await signCanonicalPayload({
      action: 'revoke_delegation',
      poll_id: pollId.value,
      timestamp,
    })

    await $fetch(`/api/v1/governance/polls/${pollId.value}/delegate/revoke/`, {
      method: 'POST',
      body: {
        pgp_signature: signature,
        signed_timestamp: timestamp,
      },
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`
      }
    })

    await fetchPoll()
  } catch (e: any) {
    console.error('Failed to revoke delegation:', e)
    voteError.value = e.data?.detail || e.data?.message || e.message || $t('governance.errors.revokingDelegation')
  } finally {
    revokingDelegation.value = false
  }
}

// Computed
const sortedResults = computed(() => {
  if (!poll.value?.options) return []
  const resultsMap = new Map(
    (poll.value.results || []).map((r: any) => [r.option_id, r])
  )
  return poll.value.options.map((opt: any) => {
    return resultsMap.get(opt.id) || {
      option_id: opt.id,
      option_text: opt.text,
      votes: 0,
      voter_count: 0,
      percentage: 0,
    }
  }).sort((a: any, b: any) => b.percentage - a.percentage)
})

// Lifecycle — auth-dependent work (client-side only)
onMounted(() => {
  loadKeys()
  if (authStore.isAuthenticated) {
    fetchMyStatus()
  }
})

// Helpers
function getStatusClass(status: string): string {
  switch (status) {
    case 'active':
      return 'bg-success-100 text-success-700 dark:bg-success-900/30 dark:text-success-300'
    case 'ended':
      return 'bg-neutral-100 text-neutral-700 dark:bg-neutral-700 dark:text-neutral-300'
    case 'draft':
      return 'bg-warning-100 text-warning-700 dark:bg-warning-900/30 dark:text-warning-300'
    default:
      return 'bg-neutral-100 text-neutral-700'
  }
}

function getStatusLabel(status: string): string {
  return $t(`governance.status.${status}`, status)
}

function formatDate(dateString: string): string {
  const date = new Date(dateString)
  return date.toLocaleDateString(locale.value, {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}

function getTimeRemaining(endTime: string): string {
  const now = new Date()
  const end = new Date(endTime)
  const diff = end.getTime() - now.getTime()

  if (diff < 0) {
    return $t('governance.timeEnded')
  }

  const days = Math.floor(diff / (1000 * 60 * 60 * 24))
  const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60))

  if (days > 0) {
    return `${$t('governance.timeRemaining')} ${days} ${$t('governance.days')} ${hours} ${$t('governance.hours')}`
  } else if (hours > 0) {
    return `${$t('governance.timeRemaining')} ${hours} ${$t('governance.hours')}`
  } else {
    const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60))
    return `${$t('governance.timeRemaining')} ${minutes} ${$t('governance.minutes')}`
  }
}

function getProgressPercent(poll: any): number {
  if (poll.total_eligible === 0) return 0
  return Math.round((poll.total_voted / poll.total_eligible) * 100)
}

function formatAuthor(hna: string): string {
  if (!hna) return ''
  return hna.split('@')[0]
}

definePageMeta({})
</script>
