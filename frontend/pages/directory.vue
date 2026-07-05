<template>
  <div>
    <div class="w-full px-4 sm:px-6 lg:px-8 py-6">
      <div class="max-w-7xl mx-auto w-full">

        <!-- Orientation header -->
        <header class="mb-5">
          <h1 class="text-2xl sm:text-3xl font-bold text-neutral-900 dark:text-neutral-100">{{ $t('directory.title') }}</h1>
          <p class="mt-1 text-sm text-neutral-500 dark:text-neutral-400 max-w-2xl">{{ $t('directory.intro') }}</p>
        </header>

        <div class="w-full bg-neutral-100 dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700">
          <div class="p-3 sm:p-6 min-h-[400px] sm:min-h-[600px] w-full">

            <!-- Search bar + create action -->
            <div class="mb-4 flex flex-col sm:flex-row gap-2">
              <div class="relative flex-1">
                <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-neutral-400" />
                <input
                  v-model="searchQuery"
                  @input="debouncedSearch"
                  @keydown.enter="loadResults"
                  type="text"
                  :placeholder="$t('directory.filters.search_placeholder')"
                  class="w-full pl-10 pr-4 py-2.5 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
                />
              </div>
              <UiButton
                v-if="authStore.isAuthenticated"
                variant="outline"
                :icon="Building2"
                :to="localePath('/org')"
                class="shrink-0 justify-center"
              >
                {{ $t('directory.my_orgs.title') }}
              </UiButton>
              <UiButton
                v-if="canCreateOrg"
                variant="primary"
                :icon="Plus"
                :to="localePath('/org/create')"
                class="shrink-0 justify-center"
              >
                {{ $t('directory.organizations.create_button') }}
              </UiButton>
            </div>

            <!-- Step 1: what are you looking for? (type selector) -->
            <div v-if="showTypeSelector" class="mb-3">
              <UiTabs :model-value="viewType" :tabs="typeTabs" @update:model-value="setViewType" />
            </div>
            <p v-else class="mb-3 text-xs text-neutral-500 dark:text-neutral-400">
              {{ $t('directory.anon_hint') }}
              <NuxtLink :to="localePath('/login')" class="text-link">{{ $t('directory.users.login_button') }}</NuxtLink>
            </p>

            <!-- Step 2: refine (contextual filters) -->
            <div v-if="visibleFilters.length" class="mb-4 flex flex-wrap items-center gap-2">
              <span class="text-xs font-medium text-neutral-400 dark:text-neutral-500 mr-0.5">{{ $t('directory.filters.refine_label') }}:</span>
              <button
                v-for="f in visibleFilters"
                :key="f.key"
                @click="toggleFilter(f.key)"
                class="px-3 py-2 rounded-full text-sm font-medium border transition-colors"
                :class="chipClass(f)"
              >
                <component :is="f.icon" class="w-3.5 h-3.5 inline -mt-0.5 mr-1" />
                {{ $t(f.labelKey) }}
              </button>
            </div>

            <!-- Loading skeletons -->
            <div v-if="loading" class="space-y-2">
              <DirectoryCardSkeleton v-for="n in 6" :key="n" />
            </div>

            <!-- Results -->
            <template v-else-if="peopleResults.length || orgResults.length">

              <!-- People -->
              <section v-if="peopleResults.length" :class="orgResults.length ? 'mb-6' : ''">
                <h2 v-if="grouped" class="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-neutral-400 dark:text-neutral-500 mb-2">
                  <Users class="w-3.5 h-3.5" />
                  {{ $t('directory.filters.people') }}
                  <span class="text-neutral-300 dark:text-neutral-600">&middot;</span>
                  {{ peopleResults.length }}
                </h2>
                <div class="space-y-2">
                  <NuxtLink
                    v-for="item in peopleResults"
                    :key="item.id"
                    :to="localePath(`/u/${item.hna.split('@')[0]}`)"
                    class="block bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700 hover:bg-primary-100 dark:hover:bg-primary-900/40 hover:border-primary transition-colors cursor-pointer"
                  >
                    <div class="flex items-center gap-3 sm:gap-4 px-3 sm:px-4 py-3">
                      <img
                        v-if="item.avatar_url"
                        :src="item.avatar_url"
                        :alt="item.display_name"
                        class="flex-shrink-0 w-10 h-10 sm:w-12 sm:h-12 rounded-full object-cover"
                      />
                      <div v-else class="flex-shrink-0 w-10 h-10 sm:w-12 sm:h-12 bg-gradient-to-br from-primary to-secondary rounded-full flex items-center justify-center">
                        <span class="text-sm sm:text-base font-bold text-black">
                          {{ getInitials(item.display_name || item.hna) }}
                        </span>
                      </div>

                      <div class="flex-1 min-w-0">
                        <div class="flex items-center gap-2">
                          <h3 class="text-sm sm:text-base font-semibold text-neutral-900 dark:text-neutral-100 truncate">
                            {{ item.display_name || item.hna }}
                          </h3>
                          <UiBadge v-if="item.is_partner" variant="secondary" type="soft" size="sm" class="flex-shrink-0">
                            {{ $t('directory.users.partner_badge') }}
                          </UiBadge>
                          <Shield v-if="item.is_verified_wot" class="w-4 h-4 text-success flex-shrink-0" />
                        </div>
                        <p v-if="item.bio" class="text-xs text-neutral-500 dark:text-neutral-400 truncate mt-0.5">{{ item.bio }}</p>
                        <div class="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5 truncate">
                          <span v-if="item.country_code" class="inline-flex items-center gap-0.5">
                            {{ getCountryFlag(item.country_code) }} {{ getCountryName(item.country_code) }}
                            <span class="mx-1 text-neutral-300 dark:text-neutral-600">&middot;</span>
                          </span>
                          <span v-if="item.reputation_score" :title="$t('directory.users.reputation_tooltip')">
                            <Star class="w-3 h-3 inline -mt-0.5 text-warning" />
                            {{ $t('directory.users.reputation_label') }} {{ formatReputation(item.reputation_score) }}
                          </span>
                          <span class="mx-1.5 text-neutral-300 dark:text-neutral-600">&middot;</span>
                          <span :title="$t('directory.users.wot_tooltip', { count: item.verifications_received_count || 0 })">
                            <Shield :class="item.verifications_received_count >= 3 ? 'text-success' : 'text-warning'" class="w-3 h-3 inline -mt-0.5" />
                            {{ $t('directory.users.wot_label') }} {{ item.verifications_received_count || 0 }}/3
                          </span>
                          <span class="mx-1.5 text-neutral-300 dark:text-neutral-600">&middot;</span>
                          <span class="font-mono text-neutral-400 dark:text-neutral-500">{{ item.hna }}</span>
                        </div>
                      </div>

                      <div class="flex-shrink-0 flex items-center gap-3 text-xs text-neutral-400 dark:text-neutral-500">
                        <span v-if="item.items_credit_count" class="hidden sm:flex items-center gap-1" :title="$t('directory.users.items_offered_tooltip')">
                          <Package class="w-3.5 h-3.5" />
                          {{ item.items_credit_count }}
                        </span>
                        <span v-if="item.items_debit_count" class="hidden sm:flex items-center gap-1" :title="$t('directory.users.items_sought_tooltip')">
                          <ShoppingBag class="w-3.5 h-3.5" />
                          {{ item.items_debit_count }}
                        </span>
                        <ChevronRight class="w-4 h-4 hidden sm:block" />
                      </div>
                    </div>
                  </NuxtLink>
                </div>
              </section>

              <!-- Organizations -->
              <section v-if="orgResults.length">
                <h2 v-if="grouped" class="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-neutral-400 dark:text-neutral-500 mb-2">
                  <Building2 class="w-3.5 h-3.5" />
                  {{ $t('directory.filters.organizations') }}
                  <span class="text-neutral-300 dark:text-neutral-600">&middot;</span>
                  {{ orgResults.length }}
                </h2>
                <div class="space-y-2">
                  <NuxtLink
                    v-for="item in orgResults"
                    :key="item.id"
                    :to="localePath(`/org/${item.slug || item.id}`)"
                    class="block bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700 hover:bg-primary-100 dark:hover:bg-primary-900/40 hover:border-primary transition-colors cursor-pointer"
                  >
                    <div class="flex items-center gap-3 sm:gap-4 px-3 sm:px-4 py-3">
                      <!-- Icon -->
                      <div class="flex-shrink-0 w-10 h-10 sm:w-12 sm:h-12 rounded-lg bg-neutral-100 dark:bg-neutral-800 flex items-center justify-center">
                        <img v-if="item.logo_url" :src="item.logo_url" :alt="item.name" class="w-10 h-10 sm:w-12 sm:h-12 rounded-lg object-cover" />
                        <component
                          v-else
                          :is="getEstablishmentIcon(item)"
                          class="w-5 h-5 sm:w-6 sm:h-6 text-neutral-400 dark:text-neutral-500"
                        />
                      </div>

                      <!-- Content -->
                      <div class="flex-1 min-w-0">
                        <div class="flex items-center gap-2">
                          <h3 class="text-sm sm:text-base font-semibold text-neutral-900 dark:text-neutral-100 truncate">
                            {{ item.name }}
                          </h3>
                          <BadgeCheck v-if="item.is_verified" class="w-4 h-4 text-primary flex-shrink-0" />
                          <span
                            v-if="getOpenStatus(item) === true"
                            class="flex-shrink-0 px-1.5 py-0.5 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 rounded-full text-xs font-medium"
                          >{{ $t('directory.establishments.open_now') }}</span>
                          <span
                            v-else-if="getOpenStatus(item) === false"
                            class="flex-shrink-0 px-1.5 py-0.5 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400 rounded-full text-xs font-medium"
                          >{{ $t('directory.establishments.closed_now') }}</span>
                          <DemoBadge :is-demo="item.is_demo" />
                          <UiBadge v-if="item.organization_type" variant="neutral" type="soft" size="sm" class="hidden sm:inline-flex flex-shrink-0">
                            {{ getTypeLabel(item.organization_type) }}
                          </UiBadge>
                        </div>
                        <div class="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5 truncate">
                          <span v-if="item.category_name" class="hidden sm:inline">{{ categoryLabel(item) }}<span v-if="item.full_address || item.is_online" class="mx-1.5 text-neutral-300 dark:text-neutral-600">&middot;</span></span>
                          <template v-if="item.full_address">
                            <MapPin class="w-3 h-3 inline -mt-0.5" />
                            {{ shortenAddress(item.full_address) }}
                          </template>
                          <span v-else-if="item.is_online" class="text-success dark:text-success-300">Online</span>
                          <span v-else-if="item.category_name" class="sm:hidden">{{ categoryLabel(item) }}</span>
                        </div>
                      </div>

                      <!-- Right side stats -->
                      <div class="flex-shrink-0 flex items-center gap-3 text-xs text-neutral-400 dark:text-neutral-500">
                        <span v-if="item.rating_count > 0" class="flex items-center gap-1" :title="$t('directory.organizations.rating_tooltip', { rating: item.rating_avg.toFixed(1), count: item.rating_count })">
                          <Star class="w-3.5 h-3.5 text-warning fill-warning" />
                          {{ item.rating_avg.toFixed(1) }}
                        </span>
                        <span v-if="item.member_count > 0" class="flex items-center gap-1" :title="$t('directory.organizations.members_tooltip', { count: item.member_count })">
                          <Users class="w-3.5 h-3.5" />
                          {{ item.member_count }}
                        </span>
                        <ChevronRight class="w-4 h-4 hidden sm:block" />
                      </div>
                    </div>
                  </NuxtLink>
                </div>
              </section>

            </template>

            <!-- Empty state -->
            <div v-else class="text-center py-12">
              <Search class="w-12 h-12 text-neutral-300 dark:text-neutral-600 mx-auto mb-4" />
              <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-2">{{ $t('directory.filters.no_results') }}</h3>
              <p class="text-neutral-600 dark:text-neutral-400">{{ $t('directory.filters.no_results_desc') }}</p>
            </div>


          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  Users, Shield, Star, Search, Package, ShoppingBag, Building2,
  MapPin, ChevronRight, BadgeCheck, UserPlus, Clock, LayoutGrid,
  Store, Landmark, Briefcase, Heart, UtensilsCrossed, Building, Plus
} from 'lucide-vue-next'
import DirectoryCardSkeleton from '~/components/DirectoryCardSkeleton.vue'
import { checkIsOpen } from '~/composables/useOpeningHours'

definePageMeta({ keepalive: true })

const { t } = useI18n()
const authStore = useAuthStore()
const route = useRoute()
const localePath = useLocalePath()
const router = useRouter()

// Can create an organization? Mirrors backend WoT gate (3+ verifications or foundation member)
const canCreateOrg = computed(() =>
  authStore.isAuthenticated &&
  !!(authStore.user?.profile?.is_verified_wot || authStore.user?.profile?.is_foundation_member)
)

// Localized category labels for list items. The API returns reference data in
// English (category_name — kept as-is for icon matching in getEstablishmentIcon);
// for display we translate by slug via the localized category tree, falling back
// to the English name when the slug is missing or untranslated.
const { fetchCategories } = useCategories()
const { locale: catLocale } = useI18n()
const categoryLabelMap = ref<Record<string, string>>({})
const loadCategoryLabels = async () => {
  try {
    const cats = await fetchCategories({})
    const map: Record<string, string> = {}
    for (const c of cats) map[c.slug] = c.name
    categoryLabelMap.value = map
  } catch { /* keep English category_name fallback */ }
}
const categoryLabel = (item: any) => categoryLabelMap.value[item?.category_slug] || item?.category_name || ''
watch(catLocale, loadCategoryLabels)

// SEO meta
useSeoMeta({
  title: t('directory.title') + ' - Parahub',
  ogTitle: t('directory.title') + ' - Parahub',
  description: t('directory.meta_description'),
  ogDescription: t('directory.meta_description'),
  ogImage: '/og-image.jpg',
  ogType: 'website',
  twitterCard: 'summary_large_image',
})

type ViewType = 'all' | 'people' | 'organizations'
type FilterKey = 'partners' | 'memberships' | 'verified' | 'openNow'

const searchQuery = ref<string>((route.query.q as string) || '')

// Parse view type + active filters from query params (`?type=`, `?filter=`)
const parseFromQuery = (): { viewType: ViewType; filters: Record<FilterKey, boolean> } => {
  const auth = authStore.isAuthenticated
  const type = route.query.type as string | undefined
  const filterCsv = route.query.filter as string | undefined
  const fl = filterCsv ? filterCsv.split(',') : []

  const filters: Record<FilterKey, boolean> = {
    partners: auth && fl.includes('partners'),
    memberships: auth && fl.includes('memberships'),
    verified: auth && fl.includes('verified'),
    openNow: fl.includes('open_now'),
  }

  // Anonymous users can only browse organizations (people are private).
  let viewType: ViewType = 'all'
  if (!auth) viewType = 'organizations'
  else if (type === 'people') viewType = 'people'
  else if (type === 'organizations') viewType = 'organizations'
  else viewType = 'all' // default for authenticated: show everything, grouped

  return { viewType, filters }
}

const _init = parseFromQuery()
const viewType = ref<ViewType>(_init.viewType)
const filters = reactive<Record<FilterKey, boolean>>({ ..._init.filters })

const showTypeSelector = computed(() => authStore.isAuthenticated)

// Result partitions (also drive section grouping + tab count badges)
const peopleResults = computed(() => results.value.filter(r => r._type === 'user'))
const orgResults = computed(() => results.value.filter(r => r._type === 'organization'))
const grouped = computed(() => peopleResults.value.length > 0 && orgResults.value.length > 0)

const typeTabs = computed(() => [
  { id: 'all', label: t('directory.filters.type_all'), icon: LayoutGrid },
  { id: 'people', label: t('directory.filters.people'), icon: Users, badge: peopleResults.value.length || undefined },
  { id: 'organizations', label: t('directory.filters.organizations'), icon: Building2, badge: orgResults.value.length || undefined },
])

// Contextual refinement filters — only the ones relevant to the chosen view type
const FILTER_DEFS = [
  { key: 'partners' as FilterKey, labelKey: 'directory.filters.my_partners', icon: UserPlus, types: ['all', 'people'], authOnly: true },
  { key: 'verified' as FilterKey, labelKey: 'directory.filters.verified', icon: Shield, types: ['all', 'people'], authOnly: true },
  { key: 'memberships' as FilterKey, labelKey: 'directory.filters.my_memberships', icon: BadgeCheck, types: ['all', 'organizations'], authOnly: true },
  { key: 'openNow' as FilterKey, labelKey: 'directory.filters.open_now', icon: Clock, types: ['all', 'organizations'], authOnly: false },
]

const visibleFilters = computed(() => FILTER_DEFS.filter(f =>
  f.types.includes(viewType.value) && (!f.authOnly || authStore.isAuthenticated)
))

// One active treatment for every filter toggle: indigo = "this refinement is on".
// Colour here = state, not category (icon + label already say what the filter is).
// The type selector owns yellow; green stays reserved for trust / "open now" signals.
const ACTIVE_CHIP = 'bg-secondary text-white border-secondary'
const INACTIVE_CHIP = 'bg-white dark:bg-neutral-900 border-neutral-300 dark:border-neutral-600 text-neutral-600 dark:text-neutral-400 hover:border-secondary-400 hover:text-secondary-700 dark:hover:text-secondary-300'
const chipClass = (f: typeof FILTER_DEFS[number]) => filters[f.key] ? ACTIVE_CHIP : INACTIVE_CHIP

const syncQueryParams = () => {
  const query: Record<string, string> = {}

  // Type param (omit for the default 'all', and for anonymous which is always orgs)
  if (viewType.value === 'people') query.type = 'people'
  else if (viewType.value === 'organizations' && authStore.isAuthenticated) query.type = 'organizations'

  const fl: string[] = []
  if (filters.partners) fl.push('partners')
  if (filters.memberships) fl.push('memberships')
  if (filters.verified) fl.push('verified')
  if (filters.openNow) fl.push('open_now')
  if (fl.length > 0) query.filter = fl.join(',')

  if (searchQuery.value) query.q = searchQuery.value

  router.replace({ path: localePath('/directory'), query })
}

const setViewType = (v: ViewType) => {
  viewType.value = v
  // Drop filters that don't apply to the new view type
  if (v === 'people') { filters.memberships = false; filters.openNow = false }
  else if (v === 'organizations') { filters.partners = false; filters.verified = false }
  syncQueryParams()
  loadResults()
}

const toggleFilter = (key: FilterKey) => {
  filters[key] = !filters[key]
  syncQueryParams()
  loadResults()
}

// What to fetch — searching always queries both types
const shouldLoadPeople = computed(() => {
  if (!authStore.isAuthenticated) return false
  if (searchQuery.value) return true
  return viewType.value === 'all' || viewType.value === 'people'
})

const shouldLoadOrgs = computed(() => {
  if (searchQuery.value) return true
  return viewType.value === 'all' || viewType.value === 'organizations'
})

// loadResults / results / loading are declared after the two source loaders
// below (useAsyncData runs its handler immediately — consts must exist).

const loadUsers = async (): Promise<any[]> => {
  try {
    const params = new URLSearchParams({ page_size: '50' })
    if (filters.partners) params.append('only_partners', 'true')
    if (filters.verified) params.append('verified_only', 'true')
    if (searchQuery.value) params.append('q', searchQuery.value)

    const headers: Record<string, string> = {}
    if (authStore.isAuthenticated) {
      await authStore.ensureToken()
      if (authStore.token) headers['Authorization'] = `Bearer ${authStore.token}`
    }

    const response = await $fetch(`/api/v1/profiles/search/?${params.toString()}`, {
      credentials: 'include',
      headers
    })
    return (response.items || []).map((u: any) => ({ ...u, _type: 'user' }))
  } catch (error) {
    console.error('Failed to load users:', error)
    return []
  }
}

const loadOrganizations = async (): Promise<any[]> => {
  try {
    const headers: Record<string, string> = {}
    if (authStore.isAuthenticated) {
      try {
        await authStore.ensureToken()
        if (authStore.token) headers['Authorization'] = `Bearer ${authStore.token}`
      } catch (e) { /* ignore */ }
    }

    const apiParams = new URLSearchParams()
    apiParams.append('owned_only', 'true')  // real member-orgs only; OSM church/gov imports live on the map
    if (searchQuery.value) apiParams.append('search', searchQuery.value)
    if (filters.memberships) apiParams.append('my_memberships', 'true')

    const response = await $fetch(`/api/v1/geo/establishments/?${apiParams.toString()}`, {
      credentials: 'include',
      headers
    })
    let orgs = (response?.items || []).map((o: any) => ({ ...o, _type: 'organization' }))
    if (filters.openNow) {
      orgs = orgs.filter((o: any) => checkIsOpen(o.opening_hours) === true)
    }
    return orgs
  } catch (error) {
    console.error('Failed to load organizations:', error)
    return []
  }
}

// SSR + Suspense-blocking + payload-cached (market/index.vue pattern; multi-
// source page, so useAsyncData over a merged loader instead of useListData).
// During SSR auth is always anonymous → orgs only (the public catalog —
// exactly what crawlers should index); people join on authed client loads.
const resultsData = useAsyncData<any[]>(
  'directory-results',
  async () => {
    const [people, orgs] = await Promise.all([
      shouldLoadPeople.value ? loadUsers() : Promise.resolve([]),
      shouldLoadOrgs.value ? loadOrganizations() : Promise.resolve([]),
    ])
    return [...people, ...orgs]
  },
  { default: () => [] },
)
const { data: results, pending: loading } = resultsData

const loadResults = () => resultsData.refresh()

let searchTimeout: NodeJS.Timeout
const debouncedSearch = () => {
  clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => {
    syncQueryParams()
    loadResults()
  }, 500)
}

// Sync on browser back/forward (programmatic viewType set has no side effects)
watch(() => route.query, (newQuery) => {
  const parsed = parseFromQuery()
  const newQ = (newQuery.q as string) || ''
  const filtersChanged = (Object.keys(parsed.filters) as FilterKey[]).some(k => filters[k] !== parsed.filters[k])
  if (parsed.viewType !== viewType.value || filtersChanged || newQ !== searchQuery.value) {
    viewType.value = parsed.viewType
    Object.assign(filters, parsed.filters)
    searchQuery.value = newQ
    loadResults()
  }
}, { deep: true })

onMounted(() => {
  loadCategoryLabels()

  // Migrate old hash-based / ?tab= URLs
  const hash = route.hash.replace('#', '')
  const oldTab = route.query.tab as string
  if (oldTab === 'events') {
    router.replace(localePath('/events'))
    return
  }
  if (hash || oldTab) {
    const target = hash || oldTab
    const query: Record<string, string> = {}
    if (target === 'partners') { query.filter = 'partners'; if (authStore.isAuthenticated) filters.partners = true }
    else if (target === 'organizations') { query.type = 'organizations'; if (authStore.isAuthenticated) viewType.value = 'organizations' }
    // 'people'/'users' = default (no params needed)
    router.replace({ path: localePath('/directory'), query })
    // The query watcher only reloads when parsed state differs from the current
    // refs. We've just synced those refs to the normalised query, so it stays a
    // no-op — notably for anonymous users, whose viewType is always
    // 'organizations'. Load explicitly so the list isn't left empty.
    loadResults()
    return
  }
  // No unconditional load here — the setup-level useAsyncData already ran
  // (SSR or client) and its payload hydrates the first render.
})

const getInitials = (name: string) => {
  if (!name) return 'U'
  const parts = name.split(' ')
  return parts.length >= 2
    ? (parts[0].charAt(0) + parts[1].charAt(0)).toUpperCase()
    : name.substring(0, 2).toUpperCase()
}

const getTypeLabel = (type: string) => {
  const labels: Record<string, string> = {
    'ASSOCIATION': t('directory.organizations.type_association'),
    'COOPERATIVE': t('directory.organizations.type_cooperative'),
    'COMPANY': t('directory.organizations.type_company'),
    'NGO': t('directory.organizations.type_ngo'),
    'COMMUNITY': t('directory.organizations.type_community'),
    'CONDOMINIUM': t('directory.organizations.type_condominium'),
  }
  return labels[type] || type
}

const getEstablishmentIcon = (item: any) => {
  if (item.organization_type === 'ASSOCIATION' || item.organization_type === 'NGO') return Landmark
  if (item.organization_type === 'COOPERATIVE') return Users
  if (item.organization_type === 'COMPANY') return Briefcase
  if (item.organization_type === 'COMMUNITY') return Heart
  if (item.organization_type === 'CONDOMINIUM') return Building
  const cat = (item.category_name || '').toLowerCase()
  if (cat.includes('cafe') || cat.includes('restaurant') || cat.includes('food')) return UtensilsCrossed
  if (cat.includes('shop') || cat.includes('store') || cat.includes('market')) return Store
  return Building2
}

const getOpenStatus = (item: any): boolean | null => {
  if (item._type !== 'organization') return null
  return checkIsOpen(item.opening_hours)
}

const shortenAddress = (addr: string) => {
  if (!addr) return ''
  const parts = addr.split(',').map(s => s.trim())
  return parts.slice(0, 2).join(', ')
}

function formatReputation(score: number | string): string {
  const n = Number(score)
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return Number.isInteger(n) ? n.toString() : Math.round(n).toString()
}

const getCountryFlag = (code: string) => {
  return String.fromCodePoint(...[...code.toUpperCase()].map(c => 0x1F1E6 + c.charCodeAt(0) - 65))
}

const { locale } = useI18n()

const getCountryName = (code: string) => {
  try {
    const names = new Intl.DisplayNames([locale.value], { type: 'region' })
    return names.of(code.toUpperCase()) || code
  } catch {
    return code
  }
}

// Block client-side navigation until the first results are ready, so Suspense
// holds the previous page instead of flashing an empty shell. Must stay last —
// all lifecycle hooks above must register before this await suspends setup.
await resultsData
</script>
