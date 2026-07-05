<template>
  <div class="w-full">
    <!-- Subtitle + earnings glance -->
    <div class="mb-4 flex items-center justify-between gap-3">
      <p class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t('ads.subtitle') }}</p>
      <NuxtLink
        v-if="totalEarned > 0"
        :to="localePath('/ads/settings')"
        class="shrink-0 inline-flex items-center gap-1.5 text-xs font-medium text-neutral-700 dark:text-neutral-300 hover:text-primary transition-colors"
        :title="$t('ads.profile.total_earned')"
      >
        <Zap class="w-3.5 h-3.5 text-primary" />
        {{ totalEarned }} sat
      </NuxtLink>
    </div>

    <!-- Wallet not configured warning -->
    <UiAlert v-if="!showHistory && !walletConfigured" variant="warning" :title="$t('ads.feed.wallet_not_configured')" class="mb-6">
      <p>{{ $t('ads.feed.wallet_not_configured_desc') }}</p>
      <NuxtLink
        :to="localePath('/profile') + '#lightning'"
        class="mt-2 inline-block text-sm font-medium underline"
      >
        {{ $t('ads.feed.configure_wallet') }} →
      </NuxtLink>
    </UiAlert>

    <!-- Controls row -->
    <div class="flex items-center justify-between mb-4">
      <!-- Left: sort control (feed mode only) -->
      <button
        v-if="!showHistory && ads.length > 0"
        @click="toggleSort"
        class="flex items-center gap-1.5 text-xs text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300 transition-colors"
      >
        <ArrowUpDown class="w-3.5 h-3.5" />
        {{ sortDesc ? $t('ads.feed.sort_high_low') : $t('ads.feed.sort_low_high') }}
      </button>
      <!-- Left: search (history mode) -->
      <div v-else-if="showHistory" class="relative flex-1 max-w-xs">
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400" />
        <input
          v-model="searchQuery"
          type="text"
          :placeholder="$t('ads.feed.search_placeholder')"
          class="w-full pl-9 pr-3 py-1.5 text-sm bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
        />
      </div>
      <div v-else></div>

      <!-- Right: history toggle -->
      <button
        @click="toggleHistory"
        class="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg transition-colors"
        :class="showHistory
          ? 'bg-primary text-neutral-900'
          : 'text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800'"
      >
        <History v-if="!showHistory" class="w-3.5 h-3.5" />
        <Sparkles v-else class="w-3.5 h-3.5" />
        {{ showHistory ? $t('ads.feed.tab_new') : $t('ads.feed.tab_history') }}
      </button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-center py-12" role="status" aria-live="polite">
      <Loader2 class="w-8 h-8 text-neutral-400 animate-spin mx-auto mb-3" aria-hidden="true" />
      <p class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('ads.feed.loading') }}</p>
    </div>

    <!-- ═══ FEED VIEW (CARDS) ═══ -->
    <template v-else-if="!showHistory">
      <div v-if="ads.length > 0" class="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <AdsFeedCard
          v-for="ad in sortedAds"
          :key="ad.id"
          :ad="ad"
          :is-viewed="feedViewedIds.has(ad.campaign_id)"
          :earned-sats="feedEarnedMap.get(ad.campaign_id)"
        />
      </div>

      <!-- Load more -->
      <div v-if="hasMore" class="text-center pt-4">
        <button
          @click="loadMore"
          :disabled="loadingMore"
          class="px-4 py-2 text-sm text-neutral-600 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-neutral-100 disabled:opacity-50"
        >
          <Loader2 v-if="loadingMore" class="w-4 h-4 animate-spin inline mr-1" />
          {{ $t('ads.feed.load_more') }}
        </button>
      </div>

      <!-- Empty state -->
      <div v-if="ads.length === 0" class="text-center py-12">
        <img src="/images/para/shrug.webp" alt="Para" class="mx-auto h-32 w-auto mb-4" />
        <p class="text-neutral-500 dark:text-neutral-400 font-medium">{{ $t('ads.feed.empty') }}</p>
        <p class="text-sm text-neutral-400 dark:text-neutral-500 mt-2 max-w-sm mx-auto">{{ $t('ads.feed.empty_desc') }}</p>
      </div>
    </template>

    <!-- ═══ HISTORY VIEW ═══ -->
    <template v-else>
      <div v-if="historyLoading" class="text-center py-12">
        <Loader2 class="w-8 h-8 text-neutral-400 animate-spin mx-auto mb-3" />
        <p class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('ads.feed.loading') }}</p>
      </div>

      <template v-else>
        <div v-if="historyItems.length > 0" class="space-y-3">
          <NuxtLink
            v-for="item in historyItems"
            :key="item.id"
            :to="localePath(`/ads/${item.campaign_id}`) + '?history=1'"
            class="block bg-white dark:bg-neutral-800 rounded-xl border border-neutral-200 dark:border-neutral-700 overflow-hidden hover:border-primary/30 hover:shadow-md transition-all"
          >
            <div class="flex">
              <!-- Thumbnail -->
              <img
                v-if="item.image_url"
                :src="item.image_url"
                :alt="item.post_title"
                class="w-20 h-20 object-cover flex-shrink-0"
              />
              <!-- Content -->
              <div class="flex-1 p-3 min-w-0">
                <div class="flex items-center justify-between gap-3">
                  <h3 class="text-sm font-medium text-neutral-900 dark:text-neutral-100 truncate">{{ item.post_title }}</h3>
                  <span class="flex-shrink-0 text-xs font-medium flex items-center gap-1" :class="item.payment_sent ? 'text-green-600 dark:text-green-400' : 'text-amber-600 dark:text-amber-400'">
                    <CheckCircle v-if="item.payment_sent" class="w-3.5 h-3.5" />
                    <Clock v-else class="w-3.5 h-3.5" />
                    +{{ item.earned_sats }} sat
                  </span>
                </div>
                <p class="mt-1 text-xs text-neutral-400 dark:text-neutral-500">
                  {{ $t('ads.feed.viewed_on', { date: formatDate(item.viewed_at) }) }}
                </p>
              </div>
            </div>
          </NuxtLink>

          <!-- Load more history -->
          <div v-if="historyHasMore" class="text-center pt-2">
            <button
              @click="loadMoreHistory"
              :disabled="historyLoadingMore"
              class="px-4 py-2 text-sm text-neutral-600 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-neutral-100 disabled:opacity-50"
            >
              <Loader2 v-if="historyLoadingMore" class="w-4 h-4 animate-spin inline mr-1" />
              {{ $t('ads.feed.load_more') }}
            </button>
          </div>
        </div>

        <!-- History empty -->
        <div v-else class="text-center py-12">
          <div class="w-20 h-20 rounded-full bg-neutral-100 dark:bg-neutral-800 flex items-center justify-center mx-auto mb-4">
            <History class="w-10 h-10 text-neutral-300 dark:text-neutral-600" />
          </div>
          <p class="text-neutral-500 dark:text-neutral-400 font-medium">{{ $t('ads.feed.history_empty') }}</p>
          <p class="text-sm text-neutral-400 dark:text-neutral-500 mt-2">{{ $t('ads.feed.history_empty_desc') }}</p>
        </div>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onActivated, onDeactivated, onUnmounted } from 'vue'
import { Inbox, Zap, CheckCircle, Loader2, ArrowUpDown, History, Search, Clock, Sparkles } from 'lucide-vue-next'

const authStore = useAuthStore()
const localePath = useLocalePath()
const { walletConfigured, totalEarned, feedItems, feedViewedIds, feedEarnedMap, loadHistory } = useAdsState()
const realtimeStore = useRealtimeStore()

const isActive = ref(false)

// ── Feed state ──
const ads = ref<any[]>([])
const loading = ref(true)
const loadingMore = ref(false)
const hasMore = ref(false)
const page = ref(1)
const sortDesc = ref(true)

const sortedAds = computed(() => {
  return [...ads.value].sort((a, b) =>
    sortDesc.value ? b.reward_sats - a.reward_sats : a.reward_sats - b.reward_sats
  )
})

function toggleSort() {
  sortDesc.value = !sortDesc.value
}

// ── History state ──
const showHistory = ref(false)
const historyItems = ref<any[]>([])
const historyLoading = ref(false)
const historyLoadingMore = ref(false)
const historyHasMore = ref(false)
const historyPage = ref(1)
const searchQuery = ref('')
let historyLoaded = false
let searchDebounce: ReturnType<typeof setTimeout> | null = null

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleDateString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

async function fetchHistory(pageNum = 1, append = false) {
  const result = await loadHistory(pageNum, searchQuery.value)
  if (append) {
    historyItems.value.push(...result.items)
  } else {
    historyItems.value = result.items
  }
  historyHasMore.value = result.items.length > 0 && (result.count > historyItems.value.length)
  historyPage.value = pageNum
}

async function toggleHistory() {
  showHistory.value = !showHistory.value
  if (showHistory.value && !historyLoaded) {
    historyLoading.value = true
    await fetchHistory(1)
    historyLoading.value = false
    historyLoaded = true
  }
}

async function loadMoreHistory() {
  historyLoadingMore.value = true
  try {
    await fetchHistory(historyPage.value + 1, true)
  } finally {
    historyLoadingMore.value = false
  }
}

// Debounced search for history
watch(searchQuery, () => {
  if (searchDebounce) clearTimeout(searchDebounce)
  searchDebounce = setTimeout(async () => {
    historyLoading.value = true
    await fetchHistory(1)
    historyLoading.value = false
  }, 300)
})

// ── Feed logic ──
async function prependNewAds() {
  try {
    await authStore.ensureToken()
    const response = await $fetch<any>('/api/v1/ads/feed/', {
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
      params: { page: 1 }
    })
    const incoming = response.items || []
    const existingIds = new Set(ads.value.map((a: any) => a.campaign_id))
    const fresh = incoming.filter((a: any) => !existingIds.has(a.campaign_id))
    if (fresh.length > 0) {
      ads.value = [...fresh, ...ads.value]
      feedItems.value = ads.value
    }
  } catch (e) {
    console.error('Failed to fetch new ads:', e)
  }
}

function handleNewAd() {
  if (isActive.value) prependNewAds()
}

async function loadFeed(pageNum = 1) {
  try {
    await authStore.ensureToken()
    const response = await $fetch<any>('/api/v1/ads/feed/', {
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
      params: { page: pageNum }
    })
    const items = response.items || []
    if (pageNum === 1) {
      ads.value = items
    } else {
      ads.value.push(...items)
    }
    feedItems.value = ads.value
    hasMore.value = items.length > 0 && (response.count > ads.value.length)
    page.value = pageNum
  } catch (error) {
    console.error('Failed to load feed:', error)
  }
}

async function loadMore() {
  loadingMore.value = true
  try {
    await loadFeed(page.value + 1)
  } finally {
    loadingMore.value = false
  }
}

onMounted(() => {
  isActive.value = true
  realtimeStore.on('ads.new_ad', handleNewAd)
})

onActivated(() => {
  isActive.value = true
  prependNewAds()
})

onDeactivated(() => {
  isActive.value = false
})

onUnmounted(() => {
  realtimeStore.off('ads.new_ad', handleNewAd)
})

definePageMeta({
  middleware: 'auth',
})

// Client-side fetch behind Suspense (token-authed → no SSR): client-side
// navigation holds the previous page until the feed is ready instead of
// flashing an empty shell (was inside onMounted). Must stay after all
// lifecycle hooks above so they register before setup suspends.
const bootstrap = useAsyncData('ads-bootstrap', async () => {
  await loadFeed()
  loading.value = false
  return true
}, { server: false })

await bootstrap
</script>
