<template>
  <div class="w-full max-w-2xl mx-auto">
    <!-- Loading -->
    <div v-if="!ad" class="text-center py-12">
      <Loader2 class="w-8 h-8 text-neutral-400 animate-spin mx-auto" />
    </div>

    <div v-else>
      <!-- Card container -->
      <div class="bg-white dark:bg-neutral-800 rounded-2xl border border-neutral-200 dark:border-neutral-700 overflow-hidden shadow-sm">
        <!-- Banner image -->
        <img
          v-if="ad.image_url"
          :src="ad.image_url"
          :alt="ad.post_title"
          class="w-full max-h-[320px] object-cover"
        />

        <div class="p-6 space-y-5">
          <!-- Viewed badge (history mode) -->
          <div v-if="isHistory" class="flex items-center gap-2 text-sm text-green-600 dark:text-green-400 font-medium">
            <CheckCircle class="w-4 h-4" />
            {{ $t('ads.feed.viewed_on', { date: formatDate(ad.viewed_at) }) }}
            <span v-if="ad.earned_sats" class="text-primary ml-1">
              +{{ ad.earned_sats }} sat
            </span>
          </div>

          <!-- Title -->
          <h2 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100 leading-tight">{{ ad.post_title }}</h2>

          <!-- Advertiser -->
          <NuxtLink
            v-if="ad.advertiser_id"
            :to="localePath(`/u/${ad.advertiser_hna?.split('@')[0] || ad.advertiser_id}`)"
            class="inline-flex items-center gap-2 text-sm text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300 transition-colors"
          >
            <img
              v-if="ad.establishment_logo_url"
              :src="ad.establishment_logo_url"
              :alt="ad.establishment_name"
              class="w-6 h-6 rounded-full object-cover"
            />
            <User v-else class="w-4 h-4 flex-shrink-0" />
            <span>{{ ad.establishment_name || ad.advertiser_name || ad.advertiser_hna }}</span>
          </NuxtLink>

          <!-- Content (rich text) -->
          <div
            class="text-neutral-700 dark:text-neutral-300 text-sm leading-relaxed ads-detail-content"
            v-html="ad.post_content"
          />

          <!-- Linked content card -->
          <NuxtLink
            v-if="ad.linked_item || ad.linked_establishment"
            :to="linkedUrl"
            class="flex items-center gap-4 p-4 rounded-xl bg-neutral-50 dark:bg-neutral-900 border border-neutral-100 dark:border-neutral-700 hover:border-primary transition-colors"
          >
            <img
              v-if="linkedImage"
              :src="linkedImage"
              :alt="linkedTitle"
              class="w-14 h-14 rounded-xl object-cover flex-shrink-0"
            />
            <div v-else class="w-14 h-14 rounded-xl bg-neutral-200 dark:bg-neutral-700 flex items-center justify-center flex-shrink-0">
              <Package v-if="ad.linked_item" class="w-6 h-6 text-neutral-400" />
              <Building2 v-else class="w-6 h-6 text-neutral-400" />
            </div>
            <div class="flex-1 min-w-0">
              <p class="text-base font-semibold text-neutral-900 dark:text-neutral-100 truncate">{{ linkedTitle }}</p>
              <p v-if="linkedSub" class="text-sm text-neutral-500 dark:text-neutral-400 mt-0.5">{{ linkedSub }}</p>
            </div>
            <ChevronRight class="w-5 h-5 text-neutral-400 flex-shrink-0" />
          </NuxtLink>

          <!-- Link -->
          <a
            v-if="ad.link"
            :href="ad.link"
            target="_blank"
            rel="noopener noreferrer"
            @click="recordClick"
            class="inline-flex items-center gap-1.5 text-sm text-link break-all"
          >
            <ExternalLink class="w-3.5 h-3.5 flex-shrink-0" />
            {{ ad.link }}
          </a>
        </div>
      </div>

      <!-- Timer / Claim (new ads only) -->
      <div v-if="!isHistory" class="flex flex-col items-center mt-8">
        <!-- Countdown timer -->
        <div v-if="!timerDone" class="flex flex-col items-center gap-3">
          <div class="relative w-20 h-20">
            <svg class="w-20 h-20 -rotate-90" viewBox="0 0 80 80">
              <circle cx="40" cy="40" r="34" fill="none" stroke="currentColor" class="text-neutral-200 dark:text-neutral-700" stroke-width="3" />
              <circle
                cx="40" cy="40" r="34" fill="none" stroke="currentColor"
                class="text-primary transition-all duration-1000 ease-linear"
                stroke-width="3.5"
                stroke-linecap="round"
                :stroke-dasharray="circumference"
                :stroke-dashoffset="timerOffset"
              />
            </svg>
            <span class="absolute inset-0 flex items-center justify-center text-lg font-bold text-neutral-700 dark:text-neutral-300">
              {{ timerSeconds }}s
            </span>
          </div>
          <span class="text-xs text-neutral-400 dark:text-neutral-500">{{ $t('ads.feed.reading_ad') }}</span>
        </div>

        <!-- Claim button (wallet configured) -->
        <button
          v-else-if="walletConfigured"
          @click="claimReward"
          :disabled="claiming"
          class="btn-primary px-8 py-3.5 text-sm font-semibold rounded-xl disabled:opacity-50 flex items-center gap-2.5"
        >
          <Loader2 v-if="claiming" class="w-5 h-5 animate-spin" />
          <Zap v-else class="w-5 h-5 group-hover:scale-110 transition-transform" />
          {{ $t('ads.feed.claim_reward', { sats: ad.reward_sats }) }}
        </button>

        <!-- No wallet — prompt to set up -->
        <div v-else class="flex flex-col items-center gap-3">
          <NuxtLink
            :to="localePath('/profile') + '#lightning'"
            class="btn-primary px-8 py-3.5 text-sm font-semibold rounded-xl flex items-center gap-2.5"
          >
            <Wallet class="w-5 h-5" />
            {{ $t('ads.feed.setup_wallet_to_claim', { sats: ad.reward_sats }) }}
          </NuxtLink>
          <p class="text-xs text-neutral-400 dark:text-neutral-500">{{ $t('ads.feed.wallet_required_hint') }}</p>
        </div>
      </div>
    </div>

    <!-- Toast -->
    <Transition
      enter-active-class="transition ease-out duration-300"
      enter-from-class="translate-y-4 opacity-0"
      enter-to-class="translate-y-0 opacity-100"
      leave-active-class="transition ease-in duration-200"
      leave-from-class="translate-y-0 opacity-100"
      leave-to-class="translate-y-4 opacity-0"
    >
      <div
        v-if="toast"
        class="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 px-5 py-3 rounded-xl shadow-lg text-sm font-medium"
        :class="{
          'bg-green-600 text-white': toast.type === 'success',
          'bg-red-600 text-white': toast.type === 'error',
          'bg-amber-500 text-white': toast.type === 'warning',
        }"
      >
        {{ toast.message }}
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { ExternalLink, Zap, Loader2, CheckCircle, Wallet, User, Package, Building2, ChevronRight } from 'lucide-vue-next'

const { t } = useI18n()
const route = useRoute()
const localePath = useLocalePath()
const authStore = useAuthStore()
const { feedItems, feedViewedIds, feedEarnedMap, feedCount, walletConfigured, profileLoaded, loadAdsProfile, loadHistory } = useAdsState()

const TIMER_DURATION = 3
const campaignId = route.params.id as string
const isHistory = route.query.history === '1'

const ad = ref<any>(null)
const claiming = ref(false)
const toast = ref<{ message: string; type: 'success' | 'error' | 'warning' } | null>(null)

// Timer
const timerSeconds = ref(TIMER_DURATION)
const timerDone = ref(false)
let timerInterval: ReturnType<typeof setInterval> | null = null

const circumference = 2 * Math.PI * 34
const timerOffset = computed(() => {
  const progress = timerSeconds.value / TIMER_DURATION
  return circumference * progress
})

// Linked content computed
const linkedTitle = computed(() =>
  ad.value?.linked_item?.title || ad.value?.linked_establishment?.name || ''
)
const linkedImage = computed(() =>
  ad.value?.linked_item?.image_url || ad.value?.linked_establishment?.logo_url || null
)
const linkedSub = computed(() => {
  if (ad.value?.linked_item?.pricing_options?.length) {
    const p = ad.value.linked_item.pricing_options[0]
    if (p.type === 'free') return 'Free'
    return p.amount ? `${p.amount} ${p.currency || ''}`.trim() : ''
  }
  return ad.value?.linked_establishment?.category_name || ''
})
const linkedUrl = computed(() => {
  if (ad.value?.linked_item) return localePath(`/market/${ad.value.linked_item.slug || ad.value.linked_item.id}`)
  if (ad.value?.linked_establishment) return localePath(`/org/${ad.value.linked_establishment.slug || ad.value.linked_establishment.id}`)
  return '#'
})

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleDateString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

function startTimer() {
  timerSeconds.value = TIMER_DURATION
  timerDone.value = false
  timerInterval = setInterval(() => {
    timerSeconds.value--
    if (timerSeconds.value <= 0) {
      timerDone.value = true
      if (timerInterval) {
        clearInterval(timerInterval)
        timerInterval = null
      }
    }
  }, 1000)
}

function showToast(message: string, type: 'success' | 'error' | 'warning' = 'success') {
  toast.value = { message, type }
  setTimeout(() => { toast.value = null }, 3000)
}

async function recordClick() {
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/ads/feed/${campaignId}/click/`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
    })
  } catch {}
}

async function claimReward() {
  if (!ad.value) return
  claiming.value = true
  try {
    await authStore.ensureToken()
    const result = await $fetch<any>(`/api/v1/ads/feed/${campaignId}/view/`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })

    feedViewedIds.add(campaignId)
    if (feedCount.value > 0) feedCount.value--
    if (result.earned_sats) {
      feedEarnedMap.set(campaignId, result.earned_sats)
    }

    if (result.payment_error) {
      showToast(result.payment_error, 'error')
    } else if (result.payment_sent) {
      showToast(t('ads.feed.payment_sent', { sats: result.earned_sats }), 'success')
    } else {
      showToast(t('ads.feed.payment_pending') + ` — +${result.earned_sats} sats`, 'warning')
    }

    setTimeout(() => {
      navigateTo(localePath('/ads'))
    }, 1500)
  } catch (error: any) {
    const msg = error?.data?.detail || error?.message || 'Error'
    showToast(msg, 'error')
  } finally {
    claiming.value = false
  }
}

onMounted(async () => {
  if (!profileLoaded.value) {
    await loadAdsProfile()
  }

  if (isHistory) {
    const result = await loadHistory(1)
    const found = result.items.find((item: any) => item.campaign_id === campaignId)
    if (found) {
      ad.value = found
    } else {
      navigateTo(localePath('/ads'))
    }
  } else {
    const found = feedItems.value.find((item: any) => item.campaign_id === campaignId)
    if (found) {
      ad.value = found
      startTimer()
    } else {
      navigateTo(localePath('/ads'))
    }
  }
})

onBeforeUnmount(() => {
  if (timerInterval) {
    clearInterval(timerInterval)
    timerInterval = null
  }
})

definePageMeta({
  middleware: 'auth',
})
</script>

<style scoped>
.ads-detail-content :deep(a) {
  color: #4E4EC8;
  text-decoration: underline;
}
.ads-detail-content :deep(ul) { list-style: disc; padding-left: 1.5rem; }
.ads-detail-content :deep(ol) { list-style: decimal; padding-left: 1.5rem; }
.ads-detail-content :deep(blockquote) {
  border-left: 3px solid #4E4EC8;
  padding-left: 1rem;
  margin: 0.75rem 0;
  color: #9ca3af;
}
</style>
