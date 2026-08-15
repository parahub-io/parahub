<template>
  <div class="py-6">
    <div class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
      <PageHeader
        :title="$t('governance.polls')"
        :create-to="authStore.isAuthenticated ? localePath('/governance/polls/create') : undefined"
        :create-label="authStore.isAuthenticated ? $t('governance.createPoll') : undefined"
      />

      <div class="-mt-3 mb-4 flex flex-wrap items-center gap-x-4 gap-y-2">
        <NuxtLink :to="localePath('/governance/ideas')" class="text-link text-sm inline-flex items-center gap-1">
          <Lightbulb class="w-4 h-4" aria-hidden="true" />
          {{ $t('civic.ideas.title') }}
        </NuxtLink>
        <NuxtLink v-if="authStore.isAuthenticated" :to="localePath('/governance/delegations')" class="text-link text-sm inline-flex items-center gap-1">
          <GitBranch class="w-4 h-4" aria-hidden="true" />
          {{ $t('civic.delegations.title') }}
        </NuxtLink>
        <button
          v-if="anyVoted"
          type="button"
          class="ml-auto inline-flex items-center gap-1.5 text-sm text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300 transition-colors"
          :aria-pressed="hideVoted"
          @click="hideVoted = !hideVoted"
        >
          <component :is="hideVoted ? Eye : EyeOff" class="w-4 h-4" aria-hidden="true" />
          {{ hideVoted ? $t('civic.feed.showVoted') : $t('civic.feed.hideVoted') }}
        </button>
      </div>

      <!-- Single-organization view: reached from the org page, one click back to everything -->
      <div v-if="orgFilter" class="-mt-1 mb-4 flex flex-wrap items-center gap-3">
        <span class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-secondary-50 dark:bg-secondary-900/20 border border-secondary-200 dark:border-secondary-800 text-sm text-neutral-900 dark:text-neutral-100">
          <Users class="w-4 h-4 text-secondary dark:text-secondary-400" aria-hidden="true" />
          {{ orgName || $t('civic.level.groups') }}
        </span>
        <NuxtLink :to="localePath('/governance/polls')" class="text-link text-sm">
          {{ $t('civic.feed.allPolls') }}
        </NuxtLink>
      </div>

      <!-- Voting identity: current residency + one-click switch to property-derived parishes -->
      <div
        v-if="!orgFilter && authStore.isAuthenticated && residencyName"
        class="card p-4 mb-4 flex flex-wrap items-center gap-x-3 gap-y-2"
      >
        <MapPin class="w-5 h-5 text-secondary dark:text-secondary-400 shrink-0" aria-hidden="true" />
        <p class="text-sm text-neutral-700 dark:text-neutral-300">
          {{ $t('civic.residency.voteAs', { name: shortName(residencyName) }) }}
        </p>
        <template v-if="switchTargets.length && !cooldownActive">
          <UiButton
            v-for="t in switchTargets"
            :key="t.id"
            variant="outline" size="sm"
            :loading="switchingId === t.id"
            :title="switchTitle(t)"
            @click="confirmResidency(t)"
          >
            {{ shortName(t.name) }}
          </UiButton>
        </template>
        <span v-else-if="switchTargets.length && cooldownActive" class="text-xs text-neutral-500 dark:text-neutral-400">
          {{ $t('civic.residency.cooldown', { date: formatDate(cooldownUntil!) }) }}
        </span>
        <NuxtLink :to="localePath('/profile?section=civic')" class="text-link text-sm ml-auto">
          {{ $t('civic.residency.change') }}
        </NuxtLink>
        <p v-if="residencyError" class="w-full text-sm text-error">{{ residencyError }}</p>
      </div>

      <!-- No residency yet: suggest parishes derived from the user's properties -->
      <div
        v-else-if="!orgFilter && authStore.isAuthenticated && !residencyName && candidateRows.length && !loading"
        class="card p-4 mb-4 border-secondary/40"
      >
        <div class="flex items-center gap-2 mb-1">
          <MapPin class="w-5 h-5 text-secondary dark:text-secondary-400 shrink-0" aria-hidden="true" />
          <h3 class="font-medium text-neutral-900 dark:text-neutral-100">{{ $t('civic.residency.suggestTitle') }}</h3>
        </div>
        <p class="text-sm text-neutral-600 dark:text-neutral-400 mb-3">{{ $t('civic.residency.suggestHint') }}</p>
        <div class="space-y-2">
          <div v-for="row in candidateRows" :key="row.property_id" class="flex flex-wrap items-center gap-2">
            <span class="text-sm text-neutral-500 dark:text-neutral-400 inline-flex items-center gap-1">
              <Home class="w-4 h-4" aria-hidden="true" />
              {{ row.property_name }}
            </span>
            <UiButton
              v-for="t in row.territories"
              :key="t.id"
              variant="outline" size="sm"
              :loading="switchingId === t.id"
              :title="t.name"
              @click="confirmResidency(t)"
            >
              {{ shortName(t.name) }}<span v-if="t.distance_m > 0" class="text-neutral-400">&nbsp;· ~{{ Math.round(t.distance_m) }}m</span>
            </UiButton>
          </div>
        </div>
        <p v-if="residencyError" class="text-sm text-error mt-2">{{ residencyError }}</p>
      </div>

      <!-- Residency CTA (no residency and nothing derivable) -->
      <div
        v-else-if="!orgFilter && needsResidencyCta && !loading"
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
        <UiButton v-else variant="secondary" size="sm" :to="localePath('/login')">
          {{ $t('civic.vote.loginCta') }}
        </UiButton>
      </div>

      <!-- Loading -->
      <div v-if="loading" class="flex justify-center py-12" role="status" aria-live="polite">
        <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100" aria-hidden="true"></div>
        <span class="sr-only">{{ $t('common.loading') }}</span>
      </div>

      <!-- Empty -->
      <div v-else-if="sections.length === 0 && historyItems.length === 0" class="text-center py-12">
        <img src="/images/para/shrug.webp" alt="Para" class="mx-auto h-32 w-auto mb-4" />
        <h3 class="text-xl font-semibold text-neutral-700 dark:text-neutral-300 mb-2">
          {{ $t('civic.feed.emptyScope') }}
        </h3>
        <p v-if="!orgFilter" class="text-neutral-600 dark:text-neutral-400">
          {{ $t('civic.feed.emptyScopeHint') }}
        </p>
      </div>

      <!-- Feed grouped by scope: nearest first, real territory names as headers -->
      <div v-else class="space-y-8">
        <section v-for="sec in sections" :key="sec.key" :id="`sec-${sec.key}`">
          <h2 class="flex items-center gap-2 mb-3 text-lg font-semibold text-neutral-900 dark:text-neutral-100">
            <component :is="levelIcon(sec.level)" class="w-5 h-5 text-neutral-400 dark:text-neutral-500" aria-hidden="true" />
            {{ sec.title }}
            <span v-if="sec.caption" class="text-sm font-normal text-neutral-500 dark:text-neutral-400">{{ sec.caption }}</span>
            <UiBadge v-if="sec.actionable > 0" variant="primary" type="solid" size="sm">{{ sec.actionable }}</UiBadge>
          </h2>

          <div class="space-y-4">
            <CivicFeedCard v-for="item in visibleItems(sec)" :key="item.id" :item="item" />
          </div>

          <UiButton
            v-if="filteredItems(sec).length > SECTION_PREVIEW && !expanded[sec.key]"
            variant="ghost" size="sm" class="mt-2"
            @click="expanded[sec.key] = true"
          >
            {{ $t('civic.feed.showAll', { n: filteredItems(sec).length }) }}
          </UiButton>

          <!-- Proposals from neighbours: not ballots yet, so they sit under them -->
          <div v-if="filteredIdeas(sec).length" class="mt-4">
            <h3 class="flex items-center gap-2 mb-2 text-sm font-medium text-neutral-500 dark:text-neutral-400">
              <Lightbulb class="w-4 h-4" aria-hidden="true" />
              {{ $t('civic.ideas.sectionTitle') }}
            </h3>
            <div class="space-y-3">
              <CivicIdeaCard
                v-for="idea in visibleIdeas(sec)"
                :key="idea.id"
                :idea="idea"
                dense
                @update="replaceIdea($event)"
                @changed="loadFeed"
              />
            </div>
            <UiButton
              v-if="filteredIdeas(sec).length > IDEA_PREVIEW && !ideasExpanded[sec.key]"
              variant="ghost" size="sm" class="mt-2"
              @click="ideasExpanded[sec.key] = true"
            >
              {{ $t('civic.feed.showAll', { n: filteredIdeas(sec).length }) }}
            </UiButton>
          </div>
        </section>

        <!-- The proposal funnel lives where the eyes are, not on a side page -->
        <section v-if="!orgFilter && authStore.isAuthenticated && !needsResidencyCta" class="card p-5 flex flex-col sm:flex-row sm:items-center gap-3 border-secondary/40">
          <Lightbulb class="w-6 h-6 text-secondary dark:text-secondary-400 shrink-0" aria-hidden="true" />
          <div class="flex-1">
            <h3 class="font-medium text-neutral-900 dark:text-neutral-100">{{ $t('civic.ideas.ctaTitle') }}</h3>
            <p class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t('civic.ideas.ctaHint') }}</p>
          </div>
          <UiButton variant="secondary" size="sm" :to="localePath('/governance/ideas?new=1')">
            {{ $t('civic.ideas.create') }}
          </UiButton>
        </section>

        <!-- Ended/cancelled polls: one collapsed history block, out of the way -->
        <section v-if="historyItems.length" id="sec-history">
          <button
            type="button"
            class="flex items-center gap-2 text-lg font-semibold text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200 transition-colors"
            :aria-expanded="historyOpen"
            aria-controls="history-list"
            @click="historyOpen = !historyOpen"
          >
            <component :is="historyOpen ? ChevronDown : ChevronRight" class="w-5 h-5" aria-hidden="true" />
            <History class="w-5 h-5" aria-hidden="true" />
            {{ $t('civic.feed.history') }}
            <UiBadge variant="neutral" type="soft" size="sm">{{ historyItems.length }}</UiBadge>
          </button>

          <div v-if="historyOpen" id="history-list" class="space-y-4 mt-3">
            <CivicFeedCard v-for="item in historyItems" :key="item.id" :item="item" show-scope />
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, nextTick } from 'vue'
import {
  Users, MapPin, GitBranch, Lightbulb, Home, Building2, Church, Landmark,
  Map as MapIcon, Flag, Euro, Eye, EyeOff, History, ChevronDown, ChevronRight,
} from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'

definePageMeta({ keepalive: true })

const router = useRouter()
const route = useRoute()
const localePath = useLocalePath()
const authStore = useAuthStore()
const { t: $t, locale } = useI18n()

useSeoMeta({
  title: $t('governance.polls') + ' - Parahub',
  ogTitle: $t('governance.polls') + ' - Parahub',
})

const SECTION_PREVIEW = 3
const IDEA_PREVIEW = 2
const LEVEL_ORDER = ['household', 'condominium', 'parish', 'municipality', 'region', 'country', 'eu', 'groups']
const LEVEL_ICONS: Record<string, any> = {
  household: Home, condominium: Building2, parish: Church, municipality: Landmark,
  region: MapIcon, country: Flag, eu: Euro, groups: Users,
}

// ?org=<establishment ULID> narrows the feed to one organization's polls —
// the transparency link from an org page lands here
const orgFilter = computed(() => String(route.query.org || ''))
const orgName = ref('')

const civicItems = ref<any[]>([])
const groupItems = ref<any[]>([])
const ideaItems = ref<any[]>([])
const loading = ref(true)
const hideVoted = useLocalPref('civic:hideVoted', false)
const expanded = reactive<Record<string, boolean>>({})
const ideasExpanded = reactive<Record<string, boolean>>({})
const historyOpen = ref(false)

const HISTORY_STATUSES = new Set(['ended', 'cancelled'])

// Residency + property-derived parish candidates
const residencyName = ref('')
const residencyTerritoryId = ref<string | null>(null)
const cooldownUntil = ref<string | null>(null)
const candidateRows = ref<any[]>([])
const switchingId = ref('')
const residencyError = ref('')

const needsResidencyCta = computed(() => {
  if (authStore.isAuthenticated) return !residencyName.value && !candidateRows.value.length
  return civicItems.value.length === 0
})

const cooldownActive = computed(() =>
  !!cooldownUntil.value && new Date(cooldownUntil.value).getTime() > Date.now())

const anyVoted = computed(() =>
  [...civicItems.value, ...groupItems.value].some(
    i => i.has_voted && !HISTORY_STATUSES.has(i.status)))

// Unique candidate territories other than the current residency, best distance first.
// Downward refinements (parish inside the declared municipality) skip the cooldown
// server-side, so they stay clickable even inside the window — the server decides.
const switchTargets = computed(() => {
  const seen = new Map<string, any>()
  for (const row of candidateRows.value) {
    for (const t of row.territories) {
      if (t.id === residencyTerritoryId.value) continue
      const e = seen.get(t.id)
      if (e) {
        e.properties.push(row.property_name)
        e.distance_m = Math.min(e.distance_m, t.distance_m)
      } else {
        seen.set(t.id, { ...t, properties: [row.property_name] })
      }
    }
  }
  return [...seen.values()].sort((a, b) => a.distance_m - b.distance_m)
})

function switchTitle(t: any): string {
  const parts = [t.name, ...t.properties]
  if (t.distance_m > 0) parts.push(`~${Math.round(t.distance_m)}m`)
  return parts.join(' · ')
}

// PT parish unions read better without the administrative prefix
function shortName(name: string): string {
  return name.replace(/^União das freguesias d(e|a|o|as|os)\s+/i, '')
}

function levelIcon(level: string) {
  return LEVEL_ICONS[level] || Users
}

interface Section {
  key: string
  level: string
  title: string
  caption: string
  items: any[]
  ideas: any[]
  actionable: number
}

// Ended/cancelled polls live in one collapsed history block at the bottom —
// scope sections carry only what can still be acted on
const historyItems = computed(() =>
  [...civicItems.value, ...groupItems.value]
    .filter(i => HISTORY_STATUSES.has(i.status))
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()))

const sections = computed<Section[]>(() => {
  const map = new Map<string, Section>()
  const ensure = (key: string, level: string, title: string, caption: string): Section => {
    let sec = map.get(key)
    if (!sec) {
      sec = { key, level, title, caption, items: [], ideas: [], actionable: 0 }
      map.set(key, sec)
    }
    return sec
  }
  const add = (key: string, level: string, title: string, caption: string, item: any) => {
    if (HISTORY_STATUSES.has(item.status)) return
    const sec = ensure(key, level, title, caption)
    sec.items.push(item)
    if (item.status === 'active' && !item.has_voted) sec.actionable++
  }

  for (const i of civicItems.value) {
    const level = i.scope_level
    if (level === 'household' || level === 'condominium') {
      add(level, level, $t(`civic.level.${level}`), '', i)
    } else if (level === 'eu') {
      add('eu', 'eu', $t('civic.level.eu'), '', i)
    } else {
      const key = `${level}-${i.territory_id || i.scope_name}`
      add(key, level, shortName(i.scope_name) || $t(`civic.level.${level}`), $t(`civic.level.${level}`), i)
    }
  }
  for (const g of groupItems.value) {
    add('groups', 'groups', orgName.value || $t('civic.level.groups'), '', g)
  }
  // Ideas land in the same territory sections — a proposal waiting for support
  // is something to act on, exactly like an unvoted ballot
  for (const idea of ideaItems.value) {
    const level = idea.territory_level
    const key = level === 'eu' ? 'eu' : `${level}-${idea.territory_id}`
    const sec = ensure(key, level,
      level === 'eu' ? $t('civic.level.eu') : shortName(idea.territory_name),
      level === 'eu' ? '' : $t(`civic.level.${level}`))
    sec.ideas.push(idea)
    if (!idea.supported_by_me) sec.actionable++
  }

  const rank = (i: any) => (i.status === 'active' ? (i.has_voted ? 1 : 0) : 2)
  for (const sec of map.values()) {
    sec.items.sort((a, b) => {
      const d = rank(a) - rank(b)
      if (d !== 0) return d
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    })
  }

  return [...map.values()]
    .filter(sec => filteredItems(sec).length > 0 || filteredIdeas(sec).length > 0)
    .sort((a, b) => {
      const d = LEVEL_ORDER.indexOf(a.level) - LEVEL_ORDER.indexOf(b.level)
      if (d !== 0) return d
      return a.title.localeCompare(b.title)
    })
})

function filteredItems(sec: Section): any[] {
  return hideVoted.value ? sec.items.filter(i => !i.has_voted) : sec.items
}

function visibleItems(sec: Section): any[] {
  const items = filteredItems(sec)
  return expanded[sec.key] ? items : items.slice(0, SECTION_PREVIEW)
}

// "Hide voted" reads as "hide what I already acted on" — a supported idea qualifies
function filteredIdeas(sec: Section): any[] {
  return hideVoted.value ? sec.ideas.filter(i => !i.supported_by_me) : sec.ideas
}

function visibleIdeas(sec: Section): any[] {
  const ideas = filteredIdeas(sec)
  return ideasExpanded[sec.key] ? ideas : ideas.slice(0, IDEA_PREVIEW)
}

function replaceIdea(updated: any) {
  const index = ideaItems.value.findIndex(i => i.id === updated.id)
  if (index >= 0) ideaItems.value[index] = updated
}

async function authedHeaders(): Promise<Record<string, string>> {
  if (!authStore.isAuthenticated) return {}
  await authStore.ensureToken()
  return { Authorization: `Bearer ${authStore.token}` }
}

async function fetchCivic() {
  try {
    const headers = await authedHeaders()
    // More territories per viewer now (residency chain + property parishes) —
    // raise the page over the default 20 so sections don't silently truncate
    const query: Record<string, string> = { page_size: '50' }
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

async function fetchGroups() {
  try {
    // Send auth so staff/test viewers still see demo polls (hidden from the public)
    const headers = await authedHeaders()
    const query: Record<string, string | number> = { page: 1 }
    if (orgFilter.value) query.context_id = orgFilter.value
    const res: any = await $fetch('/api/v1/governance/polls/', {
      credentials: 'include', headers, query,
    })
    const items = res?.items || res || []
    return items.map((i: any) => ({
      ...i, kind: 'group', has_voted: i.has_voted ?? false, comments_enabled: false,
    }))
  } catch {
    return []
  }
}

async function fetchIdeas() {
  try {
    const headers = await authedHeaders()
    const query: Record<string, string> = { translate_to: locale.value, page_size: '50' }
    if (!authStore.isAuthenticated) {
      const guess = (navigator.language?.split('-')[1] || '').toUpperCase()
      if (guess) query.country = guess
    }
    const items: any[] = await $fetch('/api/v1/governance/civic/ideas/', {
      credentials: 'include', headers, query,
    })
    // Promoted ideas are already in the feed as their own poll — no double row
    return items.filter(i => i.status === 'open' || i.status === 'review')
  } catch {
    return []
  }
}

async function fetchResidency() {
  if (!authStore.isAuthenticated) return
  try {
    const headers = await authedHeaders()
    const res: any = await $fetch('/api/v1/governance/civic/residency/', {
      credentials: 'include', headers,
    })
    const deepest = (res.chain || [])[0]
    residencyName.value = deepest?.name || ''
    residencyTerritoryId.value = res.territory_id || null
    cooldownUntil.value = res.cooldown_until || null
  } catch { /* fail quiet, no nagging on errors */ }
}

async function fetchCandidates() {
  if (!authStore.isAuthenticated) return
  try {
    const headers = await authedHeaders()
    candidateRows.value = await $fetch('/api/v1/governance/civic/residency/candidates/', {
      credentials: 'include', headers,
    })
  } catch {
    candidateRows.value = []
  }
}

async function confirmResidency(t: any) {
  if (switchingId.value) return
  switchingId.value = t.id
  residencyError.value = ''
  try {
    const headers = await authedHeaders()
    await $fetch('/api/v1/governance/civic/residency/', {
      method: 'PUT', credentials: 'include', headers,
      body: { territory_id: t.id },
    })
    await Promise.all([fetchResidency(), loadFeed()])
  } catch (e: any) {
    residencyError.value = e?.response?._data?.detail || e?.data?.detail || String(e?.message || e)
  } finally {
    switchingId.value = ''
  }
}

async function fetchOrgName() {
  if (!orgFilter.value) return
  try {
    const est: any = await $fetch(`/api/v1/geo/establishments/${orgFilter.value}/`)
    orgName.value = est?.name || ''
  } catch {
    orgName.value = ''
  }
}

async function loadFeed() {
  // Org view is about that organization only — territory ballots and ideas stay out
  if (orgFilter.value) {
    civicItems.value = []
    ideaItems.value = []
    groupItems.value = await fetchGroups()
    loading.value = false
    return
  }
  const [civic, groups, ideas] = await Promise.all([fetchCivic(), fetchGroups(), fetchIdeas()])
  civicItems.value = civic
  groupItems.value = groups
  ideaItems.value = ideas
  loading.value = false
}

onMounted(async () => {
  if (orgFilter.value) {
    await Promise.all([loadFeed(), fetchOrgName()])
    return
  }
  await Promise.all([loadFeed(), fetchResidency(), fetchCandidates()])
  // Legacy deep links (?tab=household etc.) land on the matching section
  const tab = String(route.query.tab || '')
  if (tab && tab !== 'all') {
    await nextTick()
    const sec = sections.value.find(s => s.level === tab)
    if (sec) document.getElementById(`sec-${sec.key}`)?.scrollIntoView({ behavior: 'smooth' })
  }
})

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString(locale.value, {
    day: 'numeric', month: 'short', year: 'numeric',
  })
}
</script>
