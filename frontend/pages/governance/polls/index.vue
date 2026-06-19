<template>
  <div class="py-6">
    <div class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
      <PageHeader
        :title="$t('governance.polls')"
        :create-to="authStore.isAuthenticated ? localePath('/governance/polls/create') : undefined"
        :create-label="authStore.isAuthenticated ? $t('governance.createPoll') : undefined"
      />

      <!-- Tabs -->
      <UiTabs v-model="selectedStatus" :tabs="statusTabs" class="mb-6">

      <!-- Loading State -->
      <div v-if="loading" class="flex justify-center py-12" role="status" aria-live="polite">
        <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-primary" aria-hidden="true"></div>
        <span class="sr-only">{{ $t('common.loading') }}</span>
      </div>

      <!-- Error State -->
      <UiAlert v-else-if="error" variant="error" class="mb-6">{{ error }}</UiAlert>

      <!-- Empty State -->
      <div v-else-if="!polls || polls.length === 0" class="text-center py-12">
        <img src="/images/para/shrug.png" alt="Para" class="mx-auto h-32 w-auto mb-4" />
        <h3 class="text-xl font-semibold text-neutral-700 dark:text-neutral-300 mb-2">
          {{ emptyStateTitle }}
        </h3>
        <p class="text-neutral-600 dark:text-neutral-400">
          {{ emptyStateDescription }}
        </p>
      </div>

      <!-- Polls List -->
      <div v-else class="space-y-4">
        <div
          v-for="poll in polls"
          :key="poll.id"
          @click="router.push(localePath(`/governance/polls/${poll.id}`))"
          class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-6 transition-shadow cursor-pointer"
        >
          <!-- Status Badge -->
          <div class="flex justify-between items-start mb-3">
            <div class="flex items-center gap-2">
              <DemoBadge :is-demo="poll.is_demo" />
              <span
                class="px-3 py-1 rounded-full text-xs font-semibold"
                :class="getStatusClass(poll.status)"
              >
                {{ getStatusLabel(poll.status) }}
              </span>
              <span v-if="poll.end_time" class="text-sm text-neutral-500 dark:text-neutral-400">
                {{ getTimeRemaining(poll.end_time) }}
              </span>
            </div>
            <div class="text-right">
              <div class="text-sm font-medium text-neutral-700 dark:text-neutral-300">
                {{ poll.total_voted }} / {{ poll.total_eligible }}
              </div>
              <div class="text-xs text-neutral-500 dark:text-neutral-400">
                {{ $t('governance.voted') }}
              </div>
            </div>
          </div>

          <!-- Title & Description -->
          <h3 class="text-xl font-semibold text-neutral-900 dark:text-neutral-100 mb-2">
            {{ poll.title }}
          </h3>
          <p class="text-neutral-600 dark:text-neutral-400 mb-4 line-clamp-2">
            {{ poll.description }}
          </p>

          <!-- Meta Info -->
          <div class="flex items-center gap-4 text-sm text-neutral-500 dark:text-neutral-400">
            <div class="flex items-center gap-1">
              <User class="w-4 h-4" />
              <span>{{ poll.created_by_display_name || formatAuthor(poll.created_by_hna) }}</span>
            </div>
            <div class="flex items-center gap-1">
              <Calendar class="w-4 h-4" />
              <span>{{ formatDate(poll.created_at) }}</span>
            </div>
            <div v-if="poll.quorum_met" class="flex items-center gap-1 text-success dark:text-success-400">
              <CheckCircle class="w-4 h-4" />
              <span>{{ $t('governance.quorumReached') }}</span>
            </div>
          </div>

          <!-- Progress Bar -->
          <div class="mt-4">
            <div class="w-full bg-neutral-200 dark:bg-neutral-700 rounded-full h-2">
              <div
                class="bg-secondary h-2 rounded-full transition-all"
                :style="`width: ${getProgressPercent(poll)}%`"
              ></div>
            </div>
            <div class="flex justify-between text-xs text-neutral-500 dark:text-neutral-400 mt-1">
              <span>{{ getProgressPercent(poll) }}%</span>
              <span>{{ $t('governance.quorum') }}: {{ poll.quorum_percent }}%</span>
            </div>
          </div>
        </div>
      </div>

      </UiTabs>

      <!-- Pagination -->
      <div v-if="totalPages > 1" class="mt-8 flex justify-center gap-2">
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
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { Plus, Vote, User, Calendar, CheckCircle } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'

definePageMeta({
  keepalive: true
})

const router = useRouter()
const localePath = useLocalePath()
const authStore = useAuthStore()
const { t: $t, locale } = useI18n()

useSeoMeta({
  title: $t('governance.polls') + ' - Parahub',
  ogTitle: $t('governance.polls') + ' - Parahub',
})

// State
const polls = ref<any[]>([])
const loading = ref(false)
const error = ref('')
const currentPage = ref(1)
const totalPages = ref(1)
const selectedStatus = useTabSync(['active', 'ended', 'all'])

// Tab definitions for UiTabs
const statusTabs = computed(() => [
  { id: 'active', label: $t('governance.filters.active') },
  { id: 'ended', label: $t('governance.filters.ended') },
  { id: 'all', label: $t('governance.filters.all') },
])

// Tab-aware empty state
const emptyStateTitle = computed(() => {
  switch (selectedStatus.value) {
    case 'active': return $t('governance.noPollsActive')
    case 'ended': return $t('governance.noPollsEnded')
    default: return $t('governance.noPolls')
  }
})

const emptyStateDescription = computed(() => {
  switch (selectedStatus.value) {
    case 'active': return $t('governance.noPollsActiveDescription')
    case 'ended': return $t('governance.noPollsEndedDescription')
    default: return $t('governance.noPollsDescription')
  }
})

// Fetch polls
async function fetchPolls() {
  loading.value = true
  error.value = ''

  try {
    const params: any = {
      page: currentPage.value,
    }

    if (selectedStatus.value && selectedStatus.value !== 'all') {
      params.status = selectedStatus.value
    }

    const response = await $fetch('/api/v1/governance/polls/', {
      params,
      credentials: 'include',
    })

    polls.value = response.items || response || []
    totalPages.value = response.pages || 1
  } catch (e: any) {
    console.error('Failed to fetch polls:', e)
    error.value = e.data?.message || e.message || $t('governance.errors.loadingPolls')
  } finally {
    loading.value = false
  }
}

// Watchers
watch([currentPage, selectedStatus], () => {
  fetchPolls()
})

// Lifecycle
onMounted(() => {
  fetchPolls()
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
    case 'cancelled':
      return 'bg-error-100 text-error-700 dark:bg-error-900/30 dark:text-error-300'
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
    month: 'short',
    year: 'numeric',
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
</script>
