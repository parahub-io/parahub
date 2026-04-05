<template>
  <component
    :is="isViewed ? 'div' : NuxtLink"
    :to="isViewed ? undefined : localePath(`/ads/${ad.campaign_id}`)"
    :class="[
      'block rounded-xl border overflow-hidden transition-all',
      isViewed
        ? 'border-neutral-200 dark:border-neutral-800 opacity-60'
        : 'border-neutral-200 dark:border-neutral-700 hover:border-primary transition-colors cursor-pointer',
    ]"
  >
    <!-- Banner image -->
    <div v-if="ad.image_url" class="relative">
      <img
        :src="ad.image_url"
        :alt="ad.post_title"
        class="w-full h-[180px] object-cover"
        loading="lazy"
      />
      <!-- Reward badge floating on image -->
      <div
        v-if="!isViewed"
        class="absolute top-3 right-3 flex items-center gap-1 px-2.5 py-1 rounded-full bg-primary text-black flex-shrink-0"
      >
        <Zap class="w-3.5 h-3.5" />
        <span class="text-sm font-bold tabular-nums">{{ ad.reward_sats }}</span>
        <span class="text-[10px] opacity-70 font-medium">sat</span>
      </div>
      <!-- Viewed overlay -->
      <div v-if="isViewed" class="absolute inset-0 bg-black/30 flex items-center justify-center">
        <div class="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-green-600/90 text-white text-sm font-medium">
          <CheckCircle class="w-4 h-4" />
          <span v-if="earnedSats">+{{ earnedSats }} sat</span>
          <span v-else>{{ $t('ads.feed.viewed') }}</span>
        </div>
      </div>
    </div>

    <!-- Content body -->
    <div class="p-4">
      <!-- Top row: establishment logo + reward (when no image) -->
      <div class="flex items-start justify-between gap-3 mb-2">
        <div class="flex items-center gap-2 min-w-0 flex-1">
          <!-- Establishment logo -->
          <img
            v-if="ad.establishment_logo_url"
            :src="ad.establishment_logo_url"
            :alt="ad.establishment_name"
            class="w-8 h-8 rounded-full object-cover flex-shrink-0 ring-1 ring-neutral-200 dark:ring-neutral-700"
          />
          <div class="min-w-0">
            <h3 class="text-base font-semibold text-neutral-900 dark:text-neutral-100 leading-snug line-clamp-2">
              {{ ad.post_title }}
            </h3>
            <p v-if="ad.establishment_name || ad.advertiser_name" class="text-xs text-neutral-500 dark:text-neutral-400 truncate mt-0.5">
              {{ ad.establishment_name || ad.advertiser_name || ad.advertiser_hna }}
            </p>
          </div>
        </div>

        <!-- Reward badge (when no image) -->
        <div
          v-if="!ad.image_url && !isViewed"
          class="flex items-center gap-1 px-2.5 py-1 rounded-full bg-primary text-black flex-shrink-0"
        >
          <Zap class="w-3.5 h-3.5" />
          <span class="text-sm font-bold tabular-nums">{{ ad.reward_sats }}</span>
          <span class="text-[10px] opacity-70 font-medium">sat</span>
        </div>

        <!-- Viewed badge (when no image) -->
        <div
          v-if="!ad.image_url && isViewed"
          class="flex items-center gap-1 px-2 py-1 rounded-full bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400 text-xs font-medium flex-shrink-0"
        >
          <CheckCircle class="w-3.5 h-3.5" />
          <span v-if="earnedSats">+{{ earnedSats }}</span>
          <span v-else>{{ $t('ads.feed.viewed') }}</span>
        </div>
      </div>

      <!-- Content preview (rich text) -->
      <div
        class="text-sm text-neutral-600 dark:text-neutral-400 leading-relaxed line-clamp-3 ads-feed-content"
        v-html="ad.post_content"
      />

      <!-- Linked content card -->
      <div
        v-if="ad.linked_item || ad.linked_establishment"
        class="mt-3 flex items-center gap-3 p-2.5 rounded-lg bg-neutral-50 dark:bg-neutral-800/70 border border-neutral-100 dark:border-neutral-700/50"
      >
        <img
          v-if="linkedImage"
          :src="linkedImage"
          :alt="linkedTitle"
          class="w-10 h-10 rounded-lg object-cover flex-shrink-0"
        />
        <div v-else class="w-10 h-10 rounded-lg bg-neutral-200 dark:bg-neutral-700 flex items-center justify-center flex-shrink-0">
          <Package v-if="ad.linked_item" class="w-4 h-4 text-neutral-400" />
          <Building2 v-else class="w-4 h-4 text-neutral-400" />
        </div>
        <div class="flex-1 min-w-0">
          <p class="text-sm font-medium text-neutral-900 dark:text-neutral-100 truncate">{{ linkedTitle }}</p>
          <p v-if="linkedSub" class="text-xs text-neutral-500 dark:text-neutral-400">{{ linkedSub }}</p>
        </div>
        <ChevronRight class="w-4 h-4 text-neutral-400 flex-shrink-0" />
      </div>

      <!-- Bottom row: link + sponsored label -->
      <div v-if="ad.link || !isViewed" class="mt-3 flex items-center justify-between">
        <a
          v-if="ad.link"
          :href="ad.link"
          target="_blank"
          rel="noopener noreferrer"
          class="text-xs text-link truncate max-w-[70%]"
          @click.stop
        >
          {{ cleanUrl(ad.link) }}
        </a>
        <span v-else />
        <span class="text-[10px] text-neutral-400 dark:text-neutral-500 uppercase tracking-wider">
          {{ $t('ads.feed.sponsored') }}
        </span>
      </div>
    </div>
  </component>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Zap, CheckCircle, Package, Building2, ChevronRight } from 'lucide-vue-next'

const NuxtLink = resolveComponent('NuxtLink')
const localePath = useLocalePath()

const props = defineProps<{
  ad: any
  isViewed?: boolean
  earnedSats?: number
}>()

const linkedTitle = computed(() =>
  props.ad.linked_item?.title || props.ad.linked_establishment?.name || ''
)
const linkedImage = computed(() =>
  props.ad.linked_item?.image_url || props.ad.linked_establishment?.logo_url || null
)
const linkedSub = computed(() => {
  if (props.ad.linked_item?.pricing_options?.length) {
    const p = props.ad.linked_item.pricing_options[0]
    if (p.type === 'free') return 'Free'
    return p.amount ? `${p.amount} ${p.currency || ''}`.trim() : ''
  }
  return props.ad.linked_establishment?.category_name || ''
})

function cleanUrl(url: string): string {
  try {
    const u = new URL(url)
    return u.hostname + (u.pathname !== '/' ? u.pathname : '')
  } catch {
    return url
  }
}
</script>

<style scoped>
.ads-feed-content :deep(a) {
  color: #4E4EC8;
  text-decoration: underline;
}
.ads-feed-content :deep(ul) { list-style: disc; padding-left: 1.5rem; }
.ads-feed-content :deep(ol) { list-style: decimal; padding-left: 1.5rem; }
.ads-feed-content :deep(blockquote) {
  border-left: 3px solid #4E4EC8;
  padding-left: 0.75rem;
  color: #9ca3af;
}
</style>
