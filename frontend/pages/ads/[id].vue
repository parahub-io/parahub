<template>
  <div class="w-full max-w-2xl mx-auto">
    <!-- Loading -->
    <div v-if="!ad" class="text-center py-12">
      <Loader2 class="w-8 h-8 text-neutral-400 animate-spin mx-auto" />
    </div>

    <div v-else>
      <!-- Card container -->
      <div class="bg-white dark:bg-neutral-800 rounded-2xl border border-neutral-200 dark:border-neutral-700 overflow-hidden">
        <!-- Banner image -->
        <img
          v-if="ad.image_url"
          :src="ad.image_url"
          :alt="ad.post_title"
          class="w-full max-h-[320px] object-cover"
        />

        <div class="p-6 space-y-5">
          <!-- Viewed badge (history mode) -->
          <div v-if="isHistory" class="flex items-center gap-2 text-sm text-success dark:text-success-400 font-medium">
            <CheckCircle class="w-4 h-4" />
            {{ $t('ads.feed.viewed_on', { date: formatDate(ad.viewed_at) }) }}
            <span v-if="ad.earned_sats" class="font-semibold ml-1">
              +{{ ad.earned_sats }} sat
            </span>
          </div>

          <!-- Translation bar: MT badge + original/translation toggle -->
          <div v-if="hasTranslation" class="flex items-center justify-between gap-2 text-xs text-neutral-500 dark:text-neutral-400">
            <span v-if="ad.is_translated && !showOriginal" class="flex items-center gap-1.5">
              <Languages class="w-3.5 h-3.5" />
              {{ $t('ads.feed.auto_translated') }}
            </span>
            <span v-else />
            <button
              type="button"
              class="font-medium text-link hover:underline"
              @click="showOriginal = !showOriginal"
            >
              {{ showOriginal ? $t('ads.feed.show_translation') : $t('ads.feed.show_original') }}
            </button>
          </div>

          <!-- Title -->
          <h2 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100 leading-tight">{{ displayTitle }}</h2>

          <!-- Advertiser -->
          <NuxtLink
            v-if="ad.advertiser_id"
            :to="localePath(`/@${ad.advertiser_hna?.split('@')[0] || ad.advertiser_id}`)"
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
            v-html="displayContent"
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
        <!-- Own campaign: preview only — self-claims are refused server-side -->
        <div v-if="ad.is_own" class="flex flex-col items-center gap-3 max-w-sm text-center">
          <div class="w-12 h-12 rounded-full bg-neutral-100 dark:bg-neutral-800 flex items-center justify-center">
            <Megaphone class="w-6 h-6 text-neutral-400" />
          </div>
          <p class="text-sm font-semibold text-neutral-900 dark:text-neutral-100">
            {{ $t('ads.feed.own_preview_title') }}
          </p>
          <p class="text-xs text-neutral-500 dark:text-neutral-400">
            {{ $t('ads.feed.own_preview_desc') }}
          </p>
          <NuxtLink :to="localePath('/ads/campaigns')" class="btn-secondary btn-sm">
            {{ $t('ads.feed.own_manage_campaigns') }}
          </NuxtLink>
        </div>

        <!-- Countdown timer -->
        <div v-else-if="!timerDone" class="flex flex-col items-center gap-3">
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

        <!-- Queued: the advertiser's own wallet pays — live-flips to paid via WS -->
        <div v-else-if="queuedState" class="flex flex-col items-center gap-3 max-w-sm text-center">
          <div v-if="paidSats === null" class="flex flex-col items-center gap-3">
            <img src="/images/wallet/ad.webp" alt="" aria-hidden="true" class="h-16 w-auto" />
            <p class="text-sm font-semibold text-neutral-900 dark:text-neutral-100 flex items-center justify-center gap-1.5">
              <Clock class="w-4 h-4 text-secondary dark:text-secondary-400" aria-hidden="true" />
              {{ $t('ads.feed.queued_title', { sats: ad.reward_sats }) }}
            </p>
            <p class="text-xs text-neutral-500 dark:text-neutral-400">
              {{ $t('ads.feed.queued_desc') }}
            </p>
          </div>
          <div v-else class="flex flex-col items-center gap-3">
            <img src="/images/wallet/receive.webp" alt="" aria-hidden="true" class="h-16 w-auto" />
            <p class="text-sm font-semibold text-success dark:text-success-400">
              {{ $t('ads.feed.payment_sent', { sats: paidSats }) }}
            </p>
          </div>
        </div>

        <!-- Claim button (wallet configured) -->
        <button
          v-else-if="walletConfigured"
          @click="claimReward"
          :disabled="claiming"
          class="btn-primary btn-lg px-8"
        >
          <Loader2 v-if="claiming" class="w-5 h-5 animate-spin" />
          <Zap v-else class="w-5 h-5" />
          {{ $t('ads.feed.claim_reward', { sats: ad.reward_sats }) }}
        </button>

        <!-- No wallet — prompt to set up -->
        <div v-else class="flex flex-col items-center gap-3">
          <NuxtLink
            :to="localePath('/profile/advanced')"
            class="btn-primary btn-lg px-8"
          >
            <Wallet class="w-5 h-5" />
            {{ $t('ads.feed.setup_wallet_to_claim', { sats: ad.reward_sats }) }}
          </NuxtLink>
          <p class="text-xs text-neutral-400 dark:text-neutral-500">{{ $t('ads.feed.wallet_required_hint') }}</p>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { ExternalLink, Zap, Loader2, CheckCircle, Clock, Wallet, User, Package, Building2, ChevronRight, Languages, Megaphone } from 'lucide-vue-next'
import { useToastStore } from '~/stores/toast'

const { t } = useI18n()
const toastStore = useToastStore()
const route = useRoute()
const localePath = useLocalePath()
const authStore = useAuthStore()
const { feedItems, feedViewedIds, feedEarnedMap, feedCount, feedRewardSats, walletConfigured, profileLoaded, loadAdsProfile, loadHistory } = useAdsState()

const TIMER_DURATION = 3
const campaignId = route.params.id as string
const isHistory = route.query.history === '1'

const ad = ref<any>(null)
const claiming = ref(false)

// Viewer-language text: server resolves advertiser translation or MT; the
// toggle lets the reader compare with the original at any time.
const showOriginal = ref(false)
const hasTranslation = computed(() =>
  !!(ad.value?.translated_post_title || ad.value?.translated_post_content)
)
const displayTitle = computed(() =>
  showOriginal.value ? ad.value?.post_title : (ad.value?.translated_post_title || ad.value?.post_title)
)
const displayContent = computed(() =>
  showOriginal.value ? ad.value?.post_content : (ad.value?.translated_post_content || ad.value?.post_content)
)

// Browser-paid rail: the reward is queued for the advertiser's own wallet.
// If they're online it lands in seconds — wait here and flip live via WS.
const queuedState = ref(false)
const paidSats = ref<number | null>(null)
const realtimeStore = useRealtimeStore()

function onPayoutSent(data: any) {
  if (data.campaign_id !== campaignId) return
  paidSats.value = data.amount_sats
  if (data.amount_sats) feedEarnedMap.set(campaignId, data.amount_sats)
  setTimeout(() => {
    navigateTo(localePath('/ads'))
  }, 2000)
}

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
  toastStore[type](message, undefined, 3000)
}

async function recordClick() {
  // Own-campaign preview: the advertiser's own clicks must not count in CTR.
  if (ad.value?.is_own) return
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

    if (result.queued) {
      // Browser-paid advertiser: the claim became a payout instruction for
      // their wallet. The ad is spent from the viewer's perspective — leave
      // this screen in its waiting state and let WS flip it to paid.
      feedViewedIds.add(campaignId)
      if (feedCount.value > 0) feedCount.value--
      feedRewardSats.value = Math.max(0, feedRewardSats.value - (ad.value?.reward_sats || 0))
      queuedState.value = true
      realtimeStore.on('ads.payout_sent', onPayoutSent)
      return
    }

    if (!result.payment_sent) {
      // Nothing was paid, so the ad is still claimable: leave it in the feed
      // and keep the reader here long enough to read why.
      showToast(t('ads.feed.payment_failed_retry'), 'error')
      return
    }

    feedViewedIds.add(campaignId)
    if (feedCount.value > 0) feedCount.value--
    feedRewardSats.value = Math.max(0, feedRewardSats.value - (ad.value?.reward_sats || 0))
    if (result.earned_sats) {
      feedEarnedMap.set(campaignId, result.earned_sats)
    }
    showToast(t('ads.feed.payment_sent', { sats: result.earned_sats }), 'success')

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
      // Own campaigns are previews: no countdown, no claim.
      if (!found.is_own) startTimer()
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
  realtimeStore.off('ads.payout_sent', onPayoutSent)
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
