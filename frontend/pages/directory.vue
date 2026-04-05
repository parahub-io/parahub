<template>
  <div>
    <h1 class="sr-only">{{ $t('directory.title') }}</h1>
    <div class="w-full px-4 sm:px-6 lg:px-8 py-6">
      <div class="max-w-7xl lg:min-w-[1024px] xl:min-w-[1280px] mx-auto w-full">
        <div class="w-full bg-neutral-100 dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700">
          <div class="p-3 sm:p-6 min-h-[400px] sm:min-h-[600px] w-full">

            <!-- Search bar -->
            <div class="mb-4">
              <div class="relative">
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
            </div>

            <!-- Filter chips -->
            <div class="mb-4 flex flex-wrap gap-2">
              <button
                v-if="authStore.isAuthenticated"
                @click="toggleChip('people')"
                class="px-3 py-2.5 rounded-full text-sm font-medium border transition-colors"
                :class="chips.people
                  ? 'bg-primary/15 border-primary/40 text-neutral-900 dark:text-neutral-100'
                  : 'bg-white dark:bg-neutral-900 border-neutral-300 dark:border-neutral-600 text-neutral-600 dark:text-neutral-400 hover:border-neutral-400 dark:hover:border-neutral-500'"
              >
                <Users class="w-3.5 h-3.5 inline -mt-0.5 mr-1" />
                {{ $t('directory.filters.people') }}
              </button>

              <button
                @click="toggleChip('organizations')"
                class="px-3 py-2.5 rounded-full text-sm font-medium border transition-colors"
                :class="chips.organizations
                  ? 'bg-primary/15 border-primary/40 text-neutral-900 dark:text-neutral-100'
                  : 'bg-white dark:bg-neutral-900 border-neutral-300 dark:border-neutral-600 text-neutral-600 dark:text-neutral-400 hover:border-neutral-400 dark:hover:border-neutral-500'"
              >
                <Building2 class="w-3.5 h-3.5 inline -mt-0.5 mr-1" />
                {{ $t('directory.filters.organizations') }}
              </button>

              <template v-if="authStore.isAuthenticated">
                <button
                  @click="toggleChip('partners')"
                  class="px-3 py-2.5 rounded-full text-sm font-medium border transition-colors"
                  :class="chips.partners
                    ? 'bg-secondary/15 border-secondary/40 text-secondary dark:text-secondary-300'
                    : 'bg-white dark:bg-neutral-900 border-neutral-300 dark:border-neutral-600 text-neutral-600 dark:text-neutral-400 hover:border-neutral-400 dark:hover:border-neutral-500'"
                >
                  <UserPlus class="w-3.5 h-3.5 inline -mt-0.5 mr-1" />
                  {{ $t('directory.filters.my_partners') }}
                </button>

                <button
                  @click="toggleChip('memberships')"
                  class="px-3 py-2.5 rounded-full text-sm font-medium border transition-colors"
                  :class="chips.memberships
                    ? 'bg-secondary/15 border-secondary/40 text-secondary dark:text-secondary-300'
                    : 'bg-white dark:bg-neutral-900 border-neutral-300 dark:border-neutral-600 text-neutral-600 dark:text-neutral-400 hover:border-neutral-400 dark:hover:border-neutral-500'"
                >
                  <BadgeCheck class="w-3.5 h-3.5 inline -mt-0.5 mr-1" />
                  {{ $t('directory.filters.my_memberships') }}
                </button>

                <button
                  @click="toggleChip('verified')"
                  class="px-3 py-2.5 rounded-full text-sm font-medium border transition-colors"
                  :class="chips.verified
                    ? 'bg-success/15 border-success/40 text-success dark:text-success-300'
                    : 'bg-white dark:bg-neutral-900 border-neutral-300 dark:border-neutral-600 text-neutral-600 dark:text-neutral-400 hover:border-neutral-400 dark:hover:border-neutral-500'"
                >
                  <Shield class="w-3.5 h-3.5 inline -mt-0.5 mr-1" />
                  {{ $t('directory.filters.verified') }}
                </button>
              </template>

              <button
                v-if="!chips.people || chips.organizations"
                @click="toggleChip('openNow')"
                class="px-3 py-2.5 rounded-full text-sm font-medium border transition-colors"
                :class="chips.openNow
                  ? 'bg-green-100 dark:bg-green-900/30 border-green-400/40 text-green-700 dark:text-green-400'
                  : 'bg-white dark:bg-neutral-900 border-neutral-300 dark:border-neutral-600 text-neutral-600 dark:text-neutral-400 hover:border-neutral-400 dark:hover:border-neutral-500'"
              >
                <Clock class="w-3.5 h-3.5 inline -mt-0.5 mr-1" />
                {{ $t('directory.filters.open_now') }}
              </button>
            </div>

            <!-- Loading skeletons -->
            <div v-if="loading" class="space-y-2">
              <DirectoryCardSkeleton v-for="n in 6" :key="n" />
            </div>

            <!-- Results list -->
            <div v-else-if="results.length > 0" class="space-y-2">
              <template v-for="item in results" :key="item.id">
                <!-- User Card -->
                <NuxtLink
                  v-if="item._type === 'user'"
                  :to="localePath(`/u/${item.hna.split('@')[0]}`)"
                  class="block bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700 hover:bg-primary/10 dark:hover:bg-primary/10 hover:border-primary/40 cursor-pointer"
                  style="transition: none"
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

                <!-- Organization Card -->
                <NuxtLink
                  v-else-if="item._type === 'organization'"
                  :to="localePath(`/org/${item.slug || item.id}`)"
                  class="block bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700 hover:bg-primary/10 dark:hover:bg-primary/10 hover:border-primary/40 cursor-pointer"
                  style="transition: none"
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
                        <span v-if="item.category_name" class="hidden sm:inline">{{ item.category_name }}<span v-if="item.full_address || item.is_online" class="mx-1.5 text-neutral-300 dark:text-neutral-600">&middot;</span></span>
                        <template v-if="item.full_address">
                          <MapPin class="w-3 h-3 inline -mt-0.5" />
                          {{ shortenAddress(item.full_address) }}
                        </template>
                        <span v-else-if="item.is_online" class="text-success dark:text-success-300">Online</span>
                        <span v-else-if="item.category_name" class="sm:hidden">{{ item.category_name }}</span>
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
              </template>
            </div>

            <!-- Empty state -->
            <div v-else-if="!loading" class="text-center py-12">
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
  MapPin, ChevronRight, BadgeCheck, UserPlus, Clock,
  Store, Landmark, Briefcase, Heart, UtensilsCrossed, Building
} from 'lucide-vue-next'
import DirectoryCardSkeleton from '~/components/DirectoryCardSkeleton.vue'
import { checkIsOpen } from '~/composables/useOpeningHours'

definePageMeta({ keepalive: true })

const { t } = useI18n()
const authStore = useAuthStore()
const route = useRoute()
const localePath = useLocalePath()
const router = useRouter()

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

interface ChipState {
  people: boolean
  organizations: boolean
  partners: boolean
  memberships: boolean
  verified: boolean
  openNow: boolean
}

const searchQuery = ref('')
const results = ref<any[]>([])
const loading = ref(false)

// Parse initial chip state from query params
const parseChipsFromQuery = (): ChipState => {
  const type = route.query.type as string | undefined
  const filter = route.query.filter as string | undefined
  const filters = filter ? filter.split(',') : []

  const state: ChipState = {
    people: false,
    organizations: false,
    partners: false,
    memberships: false,
    verified: false,
    openNow: false,
  }

  if (type === 'people' && authStore.isAuthenticated) state.people = true
  else if (type === 'organizations') state.organizations = true

  if (filters.includes('partners') && authStore.isAuthenticated) state.partners = true
  if (filters.includes('memberships') && authStore.isAuthenticated) state.memberships = true
  if (filters.includes('verified') && authStore.isAuthenticated) state.verified = true
  if (filters.includes('open_now')) state.openNow = true

  // Default for authenticated: show all people; for anon: show organizations
  if (!type && !filter) {
    if (authStore.isAuthenticated) state.people = true
    else state.organizations = true
  }

  return state
}

const chips = reactive<ChipState>(parseChipsFromQuery())

const syncQueryParams = () => {
  const query: Record<string, string> = {}

  // Type param
  if (chips.people && !chips.organizations) query.type = 'people'
  else if (chips.organizations && !chips.people) query.type = 'organizations'

  // Filter param
  const filters: string[] = []
  if (chips.partners) filters.push('partners')
  if (chips.memberships) filters.push('memberships')
  if (chips.verified) filters.push('verified')
  if (chips.openNow) filters.push('open_now')
  if (filters.length > 0) query.filter = filters.join(',')

  if (searchQuery.value) query.q = searchQuery.value

  router.replace({ path: localePath('/directory'), query })
}

const toggleChip = (chip: keyof ChipState) => {
  chips[chip] = !chips[chip]

  // People and Organizations are mutually exclusive (radio behavior)
  if (chip === 'people' && chips.people) {
    chips.organizations = false
    chips.memberships = false
  }
  if (chip === 'organizations' && chips.organizations) {
    chips.people = false
    chips.partners = false
    chips.verified = false
  }

  // Implicit type enabling
  if (chip === 'partners' && chips.partners) {
    if (!chips.people && !chips.organizations) chips.people = true
  }
  if (chip === 'memberships' && chips.memberships) {
    if (!chips.people && !chips.organizations) chips.organizations = true
  }
  if (chip === 'openNow' && chips.openNow) {
    if (!chips.organizations) chips.organizations = true
    chips.people = false
    chips.partners = false
    chips.verified = false
  }

  // Turning off people → turn off people-only sub-filters
  if (chip === 'people' && !chips.people) {
    chips.partners = false
    chips.verified = false
  }
  // Turning off organizations → turn off org-only sub-filters
  if (chip === 'organizations' && !chips.organizations) {
    chips.memberships = false
    chips.openNow = false
  }

  syncQueryParams()
  loadResults()
}

// Determine what to load
const shouldLoadPeople = computed(() => {
  // Anonymous users never load people (privacy)
  if (!authStore.isAuthenticated) return false
  // When searching, always include people results
  if (searchQuery.value) return true
  // If only organizations chip is on and people is off → skip people
  if (chips.organizations && !chips.people && !chips.partners && !chips.verified) return false
  // If memberships chip only → skip people
  if (chips.memberships && !chips.people && !chips.partners && !chips.verified) return false
  return true
})

const shouldLoadOrgs = computed(() => {
  // When searching, always include org results
  if (searchQuery.value) return true
  // If only people chip is on and organizations is off → skip orgs
  if (chips.people && !chips.organizations && !chips.memberships) return false
  // If partners chip only → skip orgs
  if (chips.partners && !chips.organizations && !chips.memberships) return false
  // If verified chip only → skip orgs
  if (chips.verified && !chips.organizations && !chips.memberships) return false
  return true
})

const loadResults = async () => {
  loading.value = true
  results.value = []

  try {
    const promises: Promise<any[]>[] = []

    if (shouldLoadPeople.value) promises.push(loadUsers())
    else promises.push(Promise.resolve([]))

    if (shouldLoadOrgs.value) promises.push(loadOrganizations())
    else promises.push(Promise.resolve([]))

    const [people, orgs] = await Promise.all(promises)
    results.value = [...people, ...orgs]
  } finally {
    loading.value = false
  }
}

const loadUsers = async (): Promise<any[]> => {
  try {
    const params = new URLSearchParams({ page_size: '50' })
    if (chips.partners) params.append('only_partners', 'true')
    if (chips.verified) params.append('verified_only', 'true')
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
    if (searchQuery.value) apiParams.append('search', searchQuery.value)
    if (chips.memberships) apiParams.append('my_memberships', 'true')

    const response = await $fetch(`/api/v1/geo/establishments/?${apiParams.toString()}`, {
      credentials: 'include',
      headers
    })
    let orgs = (response?.items || []).map((o: any) => ({ ...o, _type: 'organization' }))
    if (chips.openNow) {
      orgs = orgs.filter((o: any) => checkIsOpen(o.opening_hours) === true)
    }
    return orgs
  } catch (error) {
    console.error('Failed to load organizations:', error)
    return []
  }
}

let searchTimeout: NodeJS.Timeout
const debouncedSearch = () => {
  clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => {
    syncQueryParams()
    loadResults()
  }, 500)
}

// Sync on browser back/forward
watch(() => route.query, (newQuery) => {
  const newChips = parseChipsFromQuery()
  const changed = (Object.keys(newChips) as (keyof ChipState)[]).some(k => chips[k] !== newChips[k])
  const newQ = (newQuery.q as string) || ''
  if (changed || newQ !== searchQuery.value) {
    Object.assign(chips, newChips)
    searchQuery.value = newQ
    loadResults()
  }
}, { deep: true })

// Migrate old hash-based URLs
onMounted(() => {
  const hash = route.hash.replace('#', '')
  const oldTab = route.query.tab as string
  if (oldTab === 'events') {
    router.replace(localePath('/events'))
    return
  }
  if (hash || oldTab) {
    const target = hash || oldTab
    const query: Record<string, string> = {}
    if (target === 'partners') query.filter = 'partners'
    else if (target === 'organizations') query.type = 'organizations'
    // 'people' = default (no params needed)
    router.replace({ path: localePath('/directory'), query })
    return
  }

  // Read search query from URL
  if (route.query.q) searchQuery.value = route.query.q as string

  loadResults()
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
</script>
