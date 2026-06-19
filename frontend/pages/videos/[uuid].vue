<template>
  <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
    <!-- Back link -->
    <NuxtLink :to="localePath('/videos')" class="inline-flex items-center gap-1 text-sm text-neutral-500 hover:text-primary mb-4">
      <ArrowLeft class="w-4 h-4" />
      {{ $t('videos.back_to_videos') }}
    </NuxtLink>

    <!-- Loading -->
    <div v-if="pending" class="py-12 text-center" role="status">
      <div class="inline-block h-12 w-12 animate-spin rounded-full border-4 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100" />
      <span class="sr-only">{{ $t('common.loading') }}</span>
    </div>

    <!-- Not found -->
    <div v-else-if="!video" class="py-12 text-center">
      <VideoOff class="w-12 h-12 mx-auto text-neutral-400 mb-3" />
      <h3 class="text-lg font-medium text-neutral-900 dark:text-neutral-100">{{ $t('videos.not_found') }}</h3>
    </div>

    <template v-else>
      <!-- Player -->
      <VideoPlayer
        :embed-url="embedUrl"
        :title="video.name"
        class="mb-4"
      />

      <!-- Title & Stats -->
      <h1 class="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
        {{ video.name }}
      </h1>

      <div class="mt-2 flex flex-wrap items-center gap-3 text-sm text-neutral-500 dark:text-neutral-400">
        <span>{{ formatViews(video.views) }} {{ $t('videos.views') }}</span>
        <span>&middot;</span>
        <span>{{ formatDate(video.publishedAt || video.createdAt) }}</span>
        <span v-if="video.likes" class="flex items-center gap-1">
          &middot;
          <ThumbsUp class="w-3.5 h-3.5" />
          {{ video.likes }}
        </span>
      </div>

      <!-- Author -->
      <div class="mt-4 flex items-center gap-3 py-3 border-t border-b border-neutral-200 dark:border-neutral-700">
        <div class="w-10 h-10 rounded-full bg-neutral-200 dark:bg-neutral-700 flex items-center justify-center overflow-hidden">
          <img
            v-if="video.account?.avatar?.path"
            :src="`${PEERTUBE_URL}${video.account.avatar.path}`"
            :alt="video.account.displayName"
            class="w-full h-full object-cover"
          />
          <User v-else class="w-5 h-5 text-neutral-400" />
        </div>
        <div class="flex-1 min-w-0">
          <NuxtLink
            v-if="video.account?.name"
            :to="localePath(`/u/${video.account.name}`)"
            class="text-sm font-medium text-neutral-900 dark:text-neutral-100 hover:text-secondary"
          >
            {{ video.account?.displayName || video.account?.name }}
          </NuxtLink>
          <p v-else class="text-sm font-medium text-neutral-900 dark:text-neutral-100">
            {{ video.account?.displayName || video.account?.name }}
          </p>
          <p v-if="video.channel?.displayName" class="text-xs text-neutral-500">
            {{ video.channel.displayName }}
          </p>
        </div>
        <!-- Tip button -->
        <UiButton
          v-if="authStore.isAuthenticated && authorProfile"
          variant="ghost"
          size="sm"
          :icon="Zap"
          @click="showTipModal = true"
        >
          {{ $t('videos.tip_author') }}
        </UiButton>
      </div>

      <!-- LN Tip Modal -->
      <UserLightningPayModal v-if="authorProfile" v-model="showTipModal" :profile="authorProfile" />

      <!-- Description -->
      <div v-if="video.description" class="mt-4 card p-4">
        <p class="text-sm text-neutral-700 dark:text-neutral-300 whitespace-pre-line">{{ video.description }}</p>
      </div>

      <!-- Tags -->
      <div v-if="video.tags?.length" class="mt-3 flex flex-wrap gap-2">
        <UiBadge v-for="tag in video.tags" :key="tag" type="soft" variant="default" size="sm">
          {{ tag }}
        </UiBadge>
      </div>

      <!-- Watch on PeerTube link -->
      <div class="mt-4">
        <a
          :href="watchUrl"
          target="_blank"
          rel="noopener noreferrer"
          class="text-sm text-link flex items-center gap-1"
        >
          <ExternalLink class="w-3.5 h-3.5" />
          {{ $t('videos.watch_on_peertube') }}
        </a>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ArrowLeft, ThumbsUp, User, VideoOff, ExternalLink, Zap } from 'lucide-vue-next'

const { t } = useI18n()
const localePath = useLocalePath()
const route = useRoute()
const authStore = useAuthStore()

const PEERTUBE_URL = 'https://video.parahub.io'

const showTipModal = ref(false)
const authorProfile = ref<any>(null)

const uuid = computed(() => route.params.uuid as string)
const embedUrl = computed(() => `${PEERTUBE_URL}/videos/embed/${uuid.value}`)

const { data: video, pending } = await useAsyncData(
  `video-${uuid.value}`,
  () => $fetch<any>(`${PEERTUBE_URL}/api/v1/videos/${uuid.value}`).catch(() => null),
)

const watchUrl = computed(() => `${PEERTUBE_URL}/w/${video.value?.shortUUID || uuid.value}`)

// Fetch author profile for LN tips (client-side only — not needed for SSR/SEO)
// PeerTube account.name = OIDC preferred_username = profile.local_name (see PK/peertube-system.md).
// The public profile endpoint accepts both ULID and local_name, returning ln_address/spark_address.
onMounted(async () => {
  if (video.value?.account?.name && video.value.account.name !== 'root') {
    try {
      const profile = await $fetch<any>(`/api/v1/profiles/${video.value.account.name}/`)
      authorProfile.value = profile
    } catch { /* profile not found or not publicly linked — no tip button */ }
  }
})

function formatViews(views: number): string {
  if (views >= 1_000_000) return `${(views / 1_000_000).toFixed(1)}M`
  if (views >= 1_000) return `${(views / 1_000).toFixed(1)}K`
  return String(views || 0)
}

function formatDate(dateStr: string): string {
  if (!dateStr) return ''
  return new Date(dateStr).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

useHead({
  title: computed(() => video.value?.name || t('videos.title')),
})

const thumbnailUrl = computed(() => {
  if (video.value?.thumbnails?.length) return video.value.thumbnails[0].url
  if (video.value?.thumbnailUrl) return video.value.thumbnailUrl
  if (video.value?.thumbnailPath) return `${PEERTUBE_URL}${video.value.thumbnailPath}`
  return ''
})

const videoDesc = computed(() => video.value?.description?.slice(0, 160) || '')

useSeoMeta({
  title: computed(() => video.value?.name || t('videos.title')),
  ogTitle: computed(() => video.value?.name || t('videos.title')),
  description: videoDesc,
  ogDescription: videoDesc,
  ogType: 'video.other',
  ogImage: thumbnailUrl,
  ogVideo: embedUrl,
  twitterCard: 'player',
  twitterTitle: computed(() => video.value?.name || t('videos.title')),
  twitterDescription: videoDesc,
  twitterImage: thumbnailUrl,
})
</script>
