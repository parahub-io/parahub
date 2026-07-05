<template>
  <!-- Mini-site subdomain: show site home -->
  <BlogSiteHome v-if="siteCtx" />

  <!-- Unauthenticated or SSR: show landing page -->
  <!-- Use !isAuthenticated (not authCheckComplete gate) to avoid unmount/remount during auth check -->
  <TheLanding v-else-if="isSSR || !authStore.isAuthenticated" />

  <!-- Auth check in progress (client-only, for authenticated users before dashboard loads) -->
  <div v-else-if="!authCheckComplete" class="min-h-full overflow-hidden dashboard-bg">
  </div>

  <!-- Authenticated: show dashboard -->
  <div v-else class="min-h-full overflow-hidden dashboard-bg">
    <h1 class="sr-only">{{ $t('nav.dashboard', 'Dashboard') }}</h1>
    <!-- Loading State -->
    <div v-if="loading" class="flex-1 flex items-center justify-center" role="status" aria-live="polite">
      <div class="text-center">
        <div class="rounded-full h-12 w-12 border-b-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100 mx-auto animate-spin" aria-hidden="true"></div>
        <p class="mt-4 text-neutral-500 dark:text-neutral-400">{{ $t('dashboard.loading', 'Loading dashboard...') }}</p>
      </div>
    </div>

    <!-- Dashboard Content -->
    <template v-else-if="dashboardData">
      <!-- Main Content Area (full height with padding for stats bar) -->
      <div class="flex flex-col items-center justify-start px-3 pt-4 pb-14 sm:px-4 sm:pt-6 sm:pb-20 relative z-10">

        <!-- Community Pulse Banner -->
        <div class="w-full max-w-4xl mb-4 sm:mb-6">
          <div class="flex items-center justify-center gap-3 sm:gap-6 text-xs sm:text-sm text-neutral-500 dark:text-neutral-400">
            <span class="flex items-center gap-1">
              <Users class="w-3.5 h-3.5 sm:w-4 sm:h-4" />
              <strong class="text-neutral-700 dark:text-neutral-200">{{ dashboardData.pulse.total_members }}</strong>
              {{ $t('dashboard.pulse_members') }}
            </span>
            <span class="text-neutral-300 dark:text-neutral-600">|</span>
            <span class="flex items-center gap-1">
              <ShoppingBag class="w-3.5 h-3.5 sm:w-4 sm:h-4" />
              <strong class="text-neutral-700 dark:text-neutral-200">{{ dashboardData.pulse.active_listings }}</strong>
              {{ $t('dashboard.pulse_listings') }}
            </span>
            <span v-if="dashboardData.pulse.upcoming_events > 0" class="text-neutral-300 dark:text-neutral-600">|</span>
            <span v-if="dashboardData.pulse.upcoming_events > 0" class="flex items-center gap-1">
              <CalendarDays class="w-3.5 h-3.5 sm:w-4 sm:h-4" />
              <strong class="text-neutral-700 dark:text-neutral-200">{{ dashboardData.pulse.upcoming_events }}</strong>
              {{ $t('dashboard.pulse_events') }}
            </span>
            <span v-if="dashboardData.pulse.active_polls > 0" class="text-neutral-300 dark:text-neutral-600">|</span>
            <span v-if="dashboardData.pulse.active_polls > 0" class="flex items-center gap-1">
              <Vote class="w-3.5 h-3.5 sm:w-4 sm:h-4" />
              <strong class="text-neutral-700 dark:text-neutral-200">{{ dashboardData.pulse.active_polls }}</strong>
              {{ $t('dashboard.pulse_polls') }}
            </span>
          </div>
        </div>

        <!-- Getting Started (hide when all steps done) -->
        <div v-if="!allOnboardingDone" class="w-full max-w-4xl mb-4 sm:mb-6">
          <div class="flex items-center justify-between mb-3 sm:mb-4">
            <h2 class="text-sm sm:text-lg font-semibold text-neutral-900 dark:text-neutral-100">
              {{ $t('dashboard.getting_started') }}
            </h2>
            <span class="text-xs text-neutral-400 dark:text-neutral-500">
              {{ Object.values(onboardingStepsDone).filter(Boolean).length }}/{{ Object.values(onboardingStepsDone).length }}
            </span>
          </div>
          <div class="grid grid-cols-2 sm:grid-cols-5 gap-2 sm:gap-3">
            <NuxtLink
              v-for="action in gettingStartedActions"
              :key="action.key"
              :to="action.to"
              class="card p-3 sm:p-4 flex flex-col items-center gap-2 text-center
                transition-colors cursor-pointer group"
              :class="onboardingStepsDone[action.key]
                ? 'border-success/30 dark:border-success/20 opacity-60'
                : 'hover:border-primary'"
            >
              <div class="relative">
                <div class="w-10 h-10 sm:w-12 sm:h-12 rounded-xl flex items-center justify-center transition-colors"
                  :class="onboardingStepsDone[action.key]
                    ? 'bg-success/10 dark:bg-success/20'
                    : 'bg-primary/10 dark:bg-primary-900/30 group-hover:bg-primary/20'"
                >
                  <component
                    :is="action.icon"
                    class="w-5 h-5 sm:w-6 sm:h-6"
                    :class="onboardingStepsDone[action.key]
                      ? 'text-success dark:text-success-300'
                      : 'text-neutral-700 dark:text-neutral-200'"
                  />
                </div>
                <div v-if="onboardingStepsDone[action.key]"
                  class="absolute -top-1 -right-1 w-4 h-4 sm:w-5 sm:h-5 rounded-full bg-success flex items-center justify-center">
                  <Check class="w-2.5 h-2.5 sm:w-3 sm:h-3 text-white" />
                </div>
              </div>
              <div class="min-w-0">
                <div class="text-xs sm:text-sm font-medium leading-tight"
                  :class="onboardingStepsDone[action.key]
                    ? 'text-neutral-500 dark:text-neutral-400 line-through'
                    : 'text-neutral-900 dark:text-neutral-100'"
                >
                  {{ action.label }}
                </div>
                <div class="text-[10px] sm:text-xs text-neutral-500 dark:text-neutral-400 mt-0.5 leading-tight hidden sm:block">
                  {{ action.desc }}
                </div>
              </div>
            </NuxtLink>
          </div>

          <!-- WoT verification hint -->
          <div class="mt-3 sm:mt-4 rounded-lg bg-secondary/5 border border-secondary/20 p-3">
            <div class="flex items-start gap-2">
              <ShieldCheck class="w-4 h-4 text-secondary dark:text-secondary-400 flex-shrink-0 mt-0.5" />
              <div class="min-w-0">
                <p class="text-xs text-neutral-600 dark:text-neutral-300">
                  {{ $t('dashboard.wot_hint') }}
                </p>
                <div class="flex gap-3 mt-2">
                  <NuxtLink :to="localePath('/docs/wot')" class="text-xs font-medium text-link">
                    {{ $t('dashboard.wot_learn_how') }}
                  </NuxtLink>
                  <NuxtLink :to="localePath('/directory')" class="text-xs font-medium text-link">
                    {{ $t('dashboard.wot_find_people') }}
                  </NuxtLink>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Partner Cards (if any) -->
        <div v-if="dashboardData.top_partners.length > 0" class="w-full max-w-4xl mb-4 sm:mb-6">
          <h2 class="text-sm sm:text-base font-semibold text-neutral-900 dark:text-neutral-100 mb-2 sm:mb-3">
            {{ $t('dashboard.top_partners', 'Top Partners') }}
          </h2>
          <div class="flex gap-1.5 sm:gap-3 flex-wrap">
            <DashboardPartnerCard
              v-for="partner in dashboardData.top_partners"
              :key="partner.id"
              :partner="partner"
              :pending="pendingRemovePartnerId === partner.id"
              @remove="handleRemovePartner"
              class="w-24 sm:w-36"
            />
          </div>
        </div>

        <!-- Activity Feed -->
        <div v-if="hasFeedContent" class="w-full max-w-4xl">

          <!-- Recent Listings (compact list) -->
          <div v-if="dashboardData.recent_items.length > 0" class="mb-4 sm:mb-6">
            <div class="flex items-center justify-between mb-2 sm:mb-3">
              <h2 class="text-sm sm:text-base font-semibold text-neutral-900 dark:text-neutral-100">
                {{ $t('dashboard.recent_listings') }}
              </h2>
              <NuxtLink :to="localePath('/market')" class="text-xs text-link">
                {{ $t('dashboard.view_all') }}
              </NuxtLink>
            </div>
            <div class="bg-neutral-100 dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700">
              <NuxtLink
                v-for="item in dashboardData.recent_items"
                :key="item.id"
                :to="localePath(`/market/${item.slug}`)"
                class="flex items-center gap-3 px-3 py-2 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors"
              >
                <div class="w-10 h-10 flex-shrink-0 rounded bg-neutral-100 dark:bg-neutral-800 overflow-hidden flex items-center justify-center">
                  <img
                    v-if="item.thumbnail_url"
                    :src="item.thumbnail_url"
                    :alt="item.title"
                    class="w-full h-full object-cover"
                    loading="lazy"
                  />
                  <ShoppingBag v-else class="w-4 h-4 text-neutral-300 dark:text-neutral-600" />
                </div>
                <div class="min-w-0 flex-1">
                  <p class="text-sm font-medium text-neutral-900 dark:text-neutral-100 truncate">
                    {{ item.title }}
                  </p>
                  <p class="text-xs text-neutral-400 dark:text-neutral-500 truncate">
                    {{ item.owner_name }}
                  </p>
                </div>
                <span class="text-xs font-semibold text-secondary flex-shrink-0">{{ item.pricing_display }}</span>
              </NuxtLink>
            </div>
          </div>

          <!-- Upcoming Events -->
          <div v-if="dashboardData.upcoming_events.length > 0" class="mb-4 sm:mb-6">
            <div class="flex items-center justify-between mb-2 sm:mb-3">
              <h2 class="text-sm sm:text-base font-semibold text-neutral-900 dark:text-neutral-100">
                {{ $t('dashboard.upcoming_events') }}
              </h2>
              <NuxtLink :to="localePath('/events')" class="text-xs text-link">
                {{ $t('dashboard.view_all') }}
              </NuxtLink>
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 sm:gap-3">
              <NuxtLink
                v-for="ev in dashboardData.upcoming_events"
                :key="ev.id"
                :to="localePath(`/events/${ev.id}`)"
                class="card flex overflow-hidden hover:border-primary transition-colors group"
              >
                <div v-if="ev.cover_image_url" class="w-20 sm:w-28 flex-shrink-0 bg-neutral-100 dark:bg-neutral-800 overflow-hidden">
                  <img
                    :src="ev.cover_image_url"
                    :alt="ev.title"
                    class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-200"
                    loading="lazy"
                  />
                </div>
                <div v-else class="w-20 sm:w-28 flex-shrink-0 bg-primary-100 dark:bg-primary-900/30 flex items-center justify-center">
                  <CalendarDays class="w-6 h-6 text-primary dark:text-primary-400" />
                </div>
                <div class="p-2 sm:p-3 min-w-0 flex flex-col justify-center">
                  <p class="text-xs sm:text-sm font-medium text-neutral-900 dark:text-neutral-100 line-clamp-2 leading-tight">
                    {{ ev.title }}
                  </p>
                  <p class="text-[10px] sm:text-xs text-secondary font-medium mt-1">
                    {{ formatEventDate(ev.starts_at) }}
                  </p>
                  <p v-if="ev.location_name" class="text-[10px] sm:text-xs text-neutral-400 dark:text-neutral-500 mt-0.5 truncate">
                    {{ ev.location_name }}
                  </p>
                </div>
              </NuxtLink>
            </div>
          </div>

          <!-- Active Polls -->
          <div v-if="dashboardData.active_polls.length > 0" class="mb-4 sm:mb-6">
            <div class="flex items-center justify-between mb-2 sm:mb-3">
              <h2 class="text-sm sm:text-base font-semibold text-neutral-900 dark:text-neutral-100">
                {{ $t('dashboard.active_polls') }}
              </h2>
              <NuxtLink :to="localePath('/governance')" class="text-xs text-link">
                {{ $t('dashboard.view_all') }}
              </NuxtLink>
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 sm:gap-3">
              <NuxtLink
                v-for="poll in dashboardData.active_polls"
                :key="poll.id"
                :to="localePath(`/governance/polls/${poll.id}`)"
                class="card p-3 sm:p-4 hover:border-primary transition-colors group"
              >
                <div class="flex items-start gap-3">
                  <div class="w-8 h-8 sm:w-10 sm:h-10 rounded-lg bg-success/10 dark:bg-success/20 flex items-center justify-center flex-shrink-0">
                    <Vote class="w-4 h-4 sm:w-5 sm:h-5 text-success dark:text-success-300" />
                  </div>
                  <div class="min-w-0">
                    <p class="text-xs sm:text-sm font-medium text-neutral-900 dark:text-neutral-100 line-clamp-2 leading-tight">
                      {{ poll.title }}
                    </p>
                    <div class="flex items-center gap-2 mt-1">
                      <span class="text-[10px] sm:text-xs text-neutral-400 dark:text-neutral-500">
                        {{ poll.options_count }} {{ $t('dashboard.options') }}
                      </span>
                      <span v-if="poll.end_time" class="text-[10px] sm:text-xs text-neutral-400 dark:text-neutral-500">
                        {{ $t('dashboard.ends') }} {{ formatEventDate(poll.end_time) }}
                      </span>
                    </div>
                  </div>
                </div>
              </NuxtLink>
            </div>
          </div>
        </div>

        <!-- Quick Actions (shown when onboarding IS complete but feed has little content) -->
        <div v-if="allOnboardingDone && !hasFeedContent" class="w-full max-w-4xl mb-4 sm:mb-6">
          <h2 class="text-sm sm:text-base font-semibold text-neutral-900 dark:text-neutral-100 mb-3">
            {{ $t('dashboard.quick_actions') }}
          </h2>
          <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 sm:gap-3">
            <NuxtLink
              v-for="action in quickActions"
              :key="action.to"
              :to="action.to"
              class="card p-3 sm:p-4 flex flex-col items-center gap-2 text-center
                hover:border-primary transition-colors cursor-pointer group"
            >
              <div class="w-10 h-10 rounded-xl bg-primary/10 dark:bg-primary-900/30
                flex items-center justify-center group-hover:bg-primary/20 transition-colors">
                <component
                  :is="action.icon"
                  class="w-5 h-5 text-neutral-700 dark:text-neutral-200"
                />
              </div>
              <span class="text-xs sm:text-sm font-medium text-neutral-900 dark:text-neutral-100 leading-tight">
                {{ action.label }}
              </span>
            </NuxtLink>
          </div>
        </div>

        <!-- Online Now (staff only) — live presence -->
        <DashboardOnlineNow v-if="isStaff" />

        <!-- Admin Quick Access (staff only) — unified bento grid, nav-menu style -->
        <div v-if="isStaff" class="w-full max-w-4xl mt-2 sm:mt-4">
          <h3 class="text-xs sm:text-sm font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider mb-2 sm:mb-3 px-1">
            Admin
          </h3>
          <div class="grid grid-cols-4 sm:grid-cols-8 gap-px rounded-xl overflow-hidden border border-neutral-300/70 dark:border-neutral-600/70 bg-neutral-300/70 dark:bg-neutral-600/70">
            <NavItem
              v-for="item in adminLinks"
              :key="item.path"
              :to="item.path"
              :icon="item.icon"
              :label="item.label"
              size="grid"
              flush
            />
          </div>
        </div>
      </div>

      <!-- Stats Bar (Fixed Overlay at Bottom) -->
      <div class="fixed bottom-0 left-0 right-0 z-50">
        <DashboardStatsBar :stats="dashboardData.stats" />
      </div>
    </template>

    <!-- Error State -->
    <div v-else class="flex flex-col items-center justify-center px-4 pt-16">
      <div class="text-center text-neutral-500 dark:text-neutral-400 max-w-sm">
        <p>{{ error || $t('dashboard.load_error', 'Failed to load dashboard') }}</p>
        <div class="flex gap-3 justify-center mt-4">
          <UiButton variant="primary" @click="fetchDashboard">
            {{ $t('common.retry', 'Retry') }}
          </UiButton>
          <UiButton variant="secondary" :to="localePath('/login')">
            {{ $t('nav.login', 'Log in') }}
          </UiButton>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import {
  Users, CarFront, LayoutDashboard, ScanLine,
  Sparkles, ShieldCheck, User, ShoppingBag, Map,
  Globe, Video, Building2, Building, CalendarDays,
  Vote, Plus, FileText, MapPin, Check, Share2,
} from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'
import { useToastStore } from '~/stores/toast'
import { useWebSocket } from '~/composables/useWebSocket'

// Page metadata
definePageMeta({
  order: 0,
})

const authStore = useAuthStore()
const toastStore = useToastStore()
const { t, d } = useI18n()
const router = useRouter()
const localePath = useLocalePath()

// Mini-site subdomain detection
const siteCtx = useSiteContext()

// SSR always renders landing page (crawlers are anonymous)
const isSSR = import.meta.server

useHead(computed(() => ({
  title: siteCtx.value ? undefined : (authStore.isAuthenticated ? 'Dashboard - Parahub' : undefined),
})))

// Landing SEO for anonymous users / crawlers (skip on subdomain — site layout handles it)
if (!siteCtx.value) {
  useSeoMeta({
    title: () => authStore.isAuthenticated ? undefined : t('landing.seo.title'),
    ogTitle: () => authStore.isAuthenticated ? undefined : t('landing.seo.title'),
    description: () => authStore.isAuthenticated ? undefined : t('landing.seo.description'),
    ogDescription: () => authStore.isAuthenticated ? undefined : t('landing.seo.description'),
    twitterCard: 'summary_large_image',
  })
}

interface Achievement {
  category: string
  level: number
  progress: number
  next_threshold: number | null
}

interface Partner {
  id: string
  object_type: string
  local_name: string
  hna: string
  display_name: string
  reputation_score: number
  is_verified_wot: boolean
  verifications_count: number
  items_count: number
  avatar_url?: string | null
}

interface DashboardStats {
  verifications_count: number
  reputation_score: number
  active_deals_count: number
  partners_count: number
  partnered_by_count: number
}

interface FeedItem {
  id: string
  object_type: string
  title: string
  slug: string
  pricing_display: string
  owner_name: string
  owner_local_name: string
  thumbnail_url: string | null
  created_at: string
}

interface FeedEvent {
  id: string
  object_type: string
  title: string
  starts_at: string
  location_name: string
  cover_image_url: string | null
  organizer_name: string
  participants_count: number
}

interface FeedPoll {
  id: string
  object_type: string
  title: string
  options_count: number
  end_time: string | null
  context_name: string
}

interface CommunityPulse {
  total_members: number
  active_listings: number
  upcoming_events: number
  active_polls: number
}

interface OnboardingSteps {
  has_profile: boolean
  has_listing: boolean
  has_partners: boolean
}

interface DashboardData {
  top_partners: Partner[]
  achievements: Achievement[]
  stats: DashboardStats
  recent_items: FeedItem[]
  upcoming_events: FeedEvent[]
  active_polls: FeedPoll[]
  pulse: CommunityPulse
  onboarding_complete: boolean
  onboarding_steps: OnboardingSteps
}

const isStaff = computed(() => authStore.user?.is_staff ?? false)

const hasFeedContent = computed(() => {
  if (!dashboardData.value) return false
  return dashboardData.value.recent_items.length > 0
    || dashboardData.value.upcoming_events.length > 0
    || dashboardData.value.active_polls.length > 0
})

const adminLinks = [
  { path: '/driver', icon: CarFront, label: 'Driver Mode' },
  { path: '/dispatch', icon: LayoutDashboard, label: 'Dispatch' },
  { path: '/tickets/scan', icon: ScanLine, label: 'Tickets' },
  { path: '/zenith', icon: Sparkles, label: 'Zenith' },
  { path: '/federation', icon: Globe, label: 'Federation' },
  { path: '/wot/graph', icon: Share2, label: 'WoT Graph' },
  { path: '/call', icon: Video, label: 'Calls' },
  { path: '/condo/create', icon: Building2, label: 'Condo' },
]

// Onboarding completion: combine server steps with localStorage for map/condo
const onboardingStepsDone = computed(() => {
  const steps = dashboardData.value?.onboarding_steps
  if (!steps) return {} as Record<string, boolean>
  const lsMap = import.meta.client ? localStorage.getItem('onboarding:map') === '1' : false
  const lsCondo = import.meta.client ? localStorage.getItem('onboarding:condo') === '1' : false
  return {
    profile: steps.has_profile,
    listing: steps.has_listing,
    directory: steps.has_partners,
    map: lsMap,
    condo: lsCondo,
  } as Record<string, boolean>
})

const allOnboardingDone = computed(() =>
  Object.values(onboardingStepsDone.value).every(Boolean)
)

const gettingStartedActions = computed(() => [
  {
    key: 'profile',
    to: localePath('/profile'),
    icon: User,
    label: t('dashboard.action_profile'),
    desc: t('dashboard.action_profile_desc'),
  },
  {
    key: 'listing',
    to: localePath('/market/create'),
    icon: ShoppingBag,
    label: t('dashboard.action_listing'),
    desc: t('dashboard.action_listing_desc'),
  },
  {
    key: 'directory',
    to: localePath('/directory'),
    icon: Building2,
    label: t('dashboard.action_directory'),
    desc: t('dashboard.action_directory_desc'),
  },
  {
    key: 'map',
    to: localePath('/map'),
    icon: Map,
    label: t('dashboard.action_map'),
    desc: t('dashboard.action_map_desc'),
  },
  {
    key: 'condo',
    to: localePath('/condo/create'),
    icon: Building,
    label: t('dashboard.action_condo'),
    desc: t('dashboard.action_condo_desc'),
  },
])

const quickActions = computed(() => [
  {
    to: localePath('/market/create'),
    icon: Plus,
    label: t('dashboard.action_listing'),
  },
  {
    to: localePath('/events/create'),
    icon: CalendarDays,
    label: t('dashboard.create_event'),
  },
  {
    to: localePath('/directory'),
    icon: MapPin,
    label: t('dashboard.action_directory'),
  },
  {
    to: localePath('/contracts/create'),
    icon: FileText,
    label: t('dashboard.create_contract'),
  },
])

const authCheckComplete = ref(false)
const loading = ref(true)
const error = ref<string | null>(null)
const dashboardData = ref<DashboardData | null>(null)

function formatEventDate(isoStr: string): string {
  const date = new Date(isoStr)
  const now = new Date()
  const isToday = date.toDateString() === now.toDateString()
  const tomorrow = new Date(now)
  tomorrow.setDate(tomorrow.getDate() + 1)
  const isTomorrow = date.toDateString() === tomorrow.toDateString()
  const time = date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })

  if (isToday) {
    return t('dashboard.today') + ' ' + time
  }
  if (isTomorrow) {
    return t('dashboard.tomorrow') + ' ' + time
  }
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) + ' ' + time
}

async function fetchDashboard() {
  loading.value = true
  error.value = null

  // Abort if loading takes too long (15s)
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 15000)

  try {
    // Ensure auth
    await authStore.ensureToken()

    // Final check - if still not authenticated, landing is shown via template
    if (!authStore.isAuthenticated) {
      return
    }

    // Guard: if token is null after ensureToken, show error instead of sending bad request
    if (!authStore.token) {
      error.value = t('dashboard.auth_error', 'Session expired. Please log in again.')
      return
    }

    // Fetch dashboard data
    const data = await $fetch<DashboardData>('/api/v1/dashboard/game', {
      credentials: 'include',
      headers: {
        Authorization: `Bearer ${authStore.token}`
      },
      signal: controller.signal,
    })

    dashboardData.value = data
  } catch (err: any) {
    if (err.name === 'AbortError') {
      error.value = t('dashboard.timeout', 'Dashboard loading timed out. Please try again.')
    } else {
      console.error('Failed to fetch dashboard:', err)
      error.value = err.data?.detail || err.message || 'Failed to load dashboard'
    }
  } finally {
    clearTimeout(timeout)
    loading.value = false
  }
}

const pendingRemovePartnerId = ref<string | null>(null)
let pendingRemoveTimer: ReturnType<typeof setTimeout> | null = null

async function handleRemovePartner(partnerId: string) {
  if (pendingRemovePartnerId.value !== partnerId) {
    pendingRemovePartnerId.value = partnerId
    if (pendingRemoveTimer) clearTimeout(pendingRemoveTimer)
    pendingRemoveTimer = setTimeout(() => { pendingRemovePartnerId.value = null }, 3000)
    return
  }
  pendingRemovePartnerId.value = null
  if (pendingRemoveTimer) clearTimeout(pendingRemoveTimer)

  try {
    await $fetch(`/api/v1/partners/${partnerId}/`, {
      method: 'DELETE',
      credentials: 'include',
      headers: {
        Authorization: `Bearer ${authStore.token}`
      }
    })

    // Refresh dashboard
    await fetchDashboard()
  } catch (err: any) {
    console.error('Failed to remove partner:', err)
  }
}

onMounted(async () => {
  // Wait for auth check before showing content
  await authStore.ensureSession()

  if (!authStore.isAuthenticated) {
    // Not authenticated yet — mark check complete (shows landing)
    // Watch for auth state change (e.g. after OAuth login redirect back)
    authCheckComplete.value = true
    const unwatch = watch(() => authStore.isAuthenticated, async (isAuth) => {
      if (isAuth) {
        unwatch()
        authCheckComplete.value = true
        await fetchDashboard()
      }
    })
    return
  }

  // Auth confirmed, show content and fetch data
  authCheckComplete.value = true
  await fetchDashboard()
})
</script>

<style scoped>
/* Gradient overlay: readable cards at top, particles shine through at bottom */
.dashboard-bg {
  background: linear-gradient(to bottom, rgba(255,255,255,0.85) 0%, rgba(255,255,255,0.3) 50%, rgba(255,255,255,0.05) 100%);
}

:root.dark .dashboard-bg {
  background: linear-gradient(to bottom, rgba(0,0,0,0.6) 0%, rgba(0,0,0,0.3) 50%, rgba(0,0,0,0.1) 100%);
}
</style>
