<template>
  <div class="py-6">
    <div class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
      <PageHeader
        :title="$t('governance.polls')"
        :create-to="authStore.isAuthenticated ? localePath('/governance/polls/create') : undefined"
        :create-label="authStore.isAuthenticated ? $t('governance.createPoll') : undefined"
      />

      <div class="-mt-3 mb-4 flex items-center gap-4">
        <NuxtLink :to="localePath('/governance/ideas')" class="text-link text-sm inline-flex items-center gap-1">
          <Lightbulb class="w-4 h-4" aria-hidden="true" />
          {{ $t('civic.ideas.title') }}
        </NuxtLink>
        <NuxtLink v-if="authStore.isAuthenticated" :to="localePath('/governance/delegations')" class="text-link text-sm inline-flex items-center gap-1">
          <GitBranch class="w-4 h-4" aria-hidden="true" />
          {{ $t('civic.delegations.title') }}
        </NuxtLink>
      </div>

      <!-- Scope ladder as filter (U1: one feed, scope chips) -->
      <UiTabs v-model="selectedScope" :tabs="scopeTabs" class="mb-6">

      <!-- Residency CTA (slim inline card, only when a civic scope needs it) -->
      <div
        v-if="needsResidencyCta"
        class="card p-4 mb-4 flex flex-col sm:flex-row sm:items-center gap-3 border-secondary/40"
      >
        <MapPin class="w-6 h-6 text-secondary dark:text-secondary-400 shrink-0" aria-hidden="true" />
        <p class="text-sm text-neutral-700 dark:text-neutral-300 flex-1">
          {{ authStore.isAuthenticated ? $t('civic.feed.needResidency') : $t('civic.feed.loginToSee') }}
        </p>
        <UiButton
          v-if="authStore.isAuthenticated"
          variant="secondary" size="sm"
          :to="localePath('/profile?section=civic')"
        >
          {{ $t('civic.feed.needResidencyAction') }}
        </UiButton>
        <UiButton v-else variant="secondary" size="sm" :to="localePath('/auth/login')">
          {{ $t('civic.vote.loginCta') }}
        </UiButton>
      </div>

      <!-- Loading -->
      <div v-if="loading" class="flex justify-center py-12" role="status" aria-live="polite">
        <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100" aria-hidden="true"></div>
        <span class="sr-only">{{ $t('common.loading') }}</span>
      </div>

      <!-- Empty -->
      <div v-else-if="feedItems.length === 0" class="text-center py-12">
        <img src="/images/para/shrug.webp" alt="Para" class="mx-auto h-32 w-auto mb-4" />
        <h3 class="text-xl font-semibold text-neutral-700 dark:text-neutral-300 mb-2">
          {{ $t('civic.feed.emptyScope') }}
        </h3>
        <p class="text-neutral-600 dark:text-neutral-400">
          {{ $t('civic.feed.emptyScopeHint') }}
        </p>
      </div>

      <!-- Merged feed -->
      <div v-else class="space-y-4">
        <div
          v-for="item in feedItems"
          :key="item.id"
          @click="router.push(localePath(`/governance/polls/${item.id}`))"
          class="card p-6 cursor-pointer hover:border-primary transition-colors"
        >
          <div class="flex flex-wrap justify-between items-start gap-2 mb-3">
            <div class="flex flex-wrap items-center gap-2">
              <CivicScopeBadge v-if="item.kind === 'civic'" :level="item.scope_level" :name="item.scope_name" />
              <CivicScopeBadge v-else />
              <UiBadge v-if="item.kind === 'civic'" variant="secondary" type="soft" :title="$t('civic.badgeHint')">
                {{ $t('civic.badge') }}
              </UiBadge>
              <span class="px-3 py-1 rounded-full text-xs font-semibold" :class="statusClass(item.status)">
                {{ $t(`governance.status.${item.status}`, item.status) }}
              </span>
            </div>
            <div class="flex items-center gap-3 text-sm text-neutral-500 dark:text-neutral-400">
              <span v-if="item.kind === 'civic'" class="flex items-center gap-1">
                <Users class="w-4 h-4" aria-hidden="true" />
                {{ item.n_display }}
              </span>
              <span v-else>{{ item.total_voted }} / {{ item.total_eligible }}</span>
              <CheckCircle
                v-if="item.has_voted"
                class="w-5 h-5 text-success"
                :title="$t('civic.feed.voted')"
                aria-hidden="true"
              />
            </div>
          </div>

          <h3 class="text-xl font-semibold text-neutral-900 dark:text-neutral-100 mb-2">
            {{ item.title }}
          </h3>
          <p class="text-neutral-600 dark:text-neutral-400 line-clamp-2">
            {{ item.description }}
          </p>

          <div v-if="item.civic_destination" class="mt-3 flex items-start gap-2 text-sm text-secondary dark:text-secondary-400">
            <Send class="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" />
            <span>{{ item.civic_destination }}</span>
          </div>

          <div class="mt-3 flex items-center gap-4 text-xs text-neutral-500 dark:text-neutral-400">
            <span class="flex items-center gap-1">
              <Calendar class="w-3.5 h-3.5" aria-hidden="true" />
              {{ formatDate(item.created_at) }}
            </span>
            <span v-if="item.comments_enabled" class="flex items-center gap-1">
              <MessageSquare class="w-3.5 h-3.5" aria-hidden="true" />
              {{ $t('civic.feed.commentsEnabled') }}
            </span>
          </div>
        </div>
      </div>

      </UiTabs>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { Users, Calendar, CheckCircle, Send, MapPin, MessageSquare, GitBranch, Lightbulb } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'

definePageMeta({ keepalive: true })

const router = useRouter()
const localePath = useLocalePath()
const authStore = useAuthStore()
const { t: $t, locale } = useI18n()

useSeoMeta({
  title: $t('governance.polls') + ' - Parahub',
  ogTitle: $t('governance.polls') + ' - Parahub',
})

const SCOPES = ['all', 'household', 'condominium', 'parish', 'municipality', 'region', 'country', 'groups'] as const
const selectedScope = useTabSync([...SCOPES])

const scopeTabs = computed(() => SCOPES.map(id => ({ id, label: $t(`civic.level.${id}`) })))

const civicItems = ref<any[]>([])
const groupItems = ref<any[]>([])
const loading = ref(true)
const residencySet = ref(true) // optimistic until checked

const needsResidencyCta = computed(() => {
  if (selectedScope.value === 'groups') return false
  if (authStore.isAuthenticated) return !residencySet.value
  return civicItems.value.length === 0
})

async function authedHeaders(): Promise<Record<string, string>> {
  if (!authStore.isAuthenticated) return {}
  await authStore.ensureToken()
  return { Authorization: `Bearer ${authStore.token}` }
}

async function fetchCivic(scope: string) {
  try {
    const headers = await authedHeaders()
    const query: Record<string, string> = {}
    if (scope !== 'all') query.scope = scope
    // Anonymous fallback: browser locale country gives the country-level feed
    if (!authStore.isAuthenticated) {
      const guess = (navigator.language?.split('-')[1] || '').toUpperCase()
      if (guess) query.country = guess
    }
    const items: any[] = await $fetch('/api/v1/governance/civic/feed/', {
      credentials: 'include', headers, query,
    })
    return items.map(i => ({ ...i, kind: 'civic' }))
  } catch {
    return []
  }
}

async function checkResidency() {
  if (!authStore.isAuthenticated) return
  try {
    const headers = await authedHeaders()
    const res: any = await $fetch('/api/v1/governance/civic/residency/', {
      credentials: 'include', headers,
    })
    residencySet.value = (res.chain || []).length > 0
  } catch {
    residencySet.value = true // fail quiet, no nagging on errors
  }
}

async function fetchGroups() {
  try {
    const res: any = await $fetch('/api/v1/governance/polls/', { query: { page: 1 } })
    const items = res?.items || res || []
    return items.map((i: any) => ({ ...i, kind: 'group', has_voted: false, comments_enabled: false }))
  } catch {
    return []
  }
}

async function loadFeed() {
  loading.value = true
  const scope = selectedScope.value
  if (scope === 'groups') {
    groupItems.value = await fetchGroups()
    civicItems.value = []
  } else if (scope === 'all') {
    const [civic, groups] = await Promise.all([fetchCivic('all'), fetchGroups()])
    civicItems.value = civic
    groupItems.value = groups
  } else {
    civicItems.value = await fetchCivic(scope)
    groupItems.value = []
  }
  loading.value = false
}

const feedItems = computed(() => {
  const merged = [...civicItems.value, ...groupItems.value]
  // Active first, then newest — same ordering the civic feed endpoint uses
  return merged.sort((a, b) => {
    const activeDiff = Number(a.status !== 'active') - Number(b.status !== 'active')
    if (activeDiff !== 0) return activeDiff
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  })
})

watch(selectedScope, loadFeed)
onMounted(() => {
  loadFeed()
  checkResidency()
})

function statusClass(status: string): string {
  switch (status) {
    case 'active': return 'bg-success-100 text-success-700 dark:bg-success-900/30 dark:text-success-300'
    case 'ended': return 'bg-neutral-100 text-neutral-700 dark:bg-neutral-700 dark:text-neutral-300'
    case 'draft': return 'bg-warning-100 text-warning-700 dark:bg-warning-900/30 dark:text-warning-300'
    case 'cancelled': return 'bg-error-100 text-error-700 dark:bg-error-900/30 dark:text-error-300'
    default: return 'bg-neutral-100 text-neutral-700'
  }
}

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString(locale.value, {
    day: 'numeric', month: 'short', year: 'numeric',
  })
}
</script>
