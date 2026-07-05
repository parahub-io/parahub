<template>
  <div class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
    <PageHeader :title="$t('videos.title')" />

    <!-- Tabs + Upload -->
    <div class="flex items-center justify-between mb-6">
      <UiTabs
        v-model="activeTab"
        :tabs="tabs"
        variant="underline"
        class="flex-1"
      />
      <UiButton
        v-if="authStore.isAuthenticated"
        size="sm"
        class="ml-4 shrink-0"
        @click="showUpload = !showUpload"
      >
        <Upload class="w-4 h-4" />
        {{ showUpload ? $t('common.cancel') : $t('videos.upload.button') }}
      </UiButton>
    </div>

    <!-- Inline upload zone -->
    <div v-if="showUpload" class="mb-6">
      <VideoUpload @uploaded="onVideoUploaded" />
    </div>

    <!-- Loading -->
    <div v-if="pending" class="py-12 text-center" role="status">
      <div class="inline-block h-12 w-12 animate-spin rounded-full border-4 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100" />
      <span class="sr-only">{{ $t('common.loading') }}</span>
    </div>

    <!-- Video Grid -->
    <div v-else-if="videos.length" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-6">
      <NuxtLink
        v-for="video in videos"
        :key="video.uuid"
        :to="localePath(`/videos/${video.shortUUID || video.uuid}`)"
        class="group card overflow-hidden hover:border-primary transition-colors"
      >
        <!-- Thumbnail -->
        <div class="relative aspect-video bg-neutral-200 dark:bg-neutral-700">
          <img
            v-if="getThumbnailUrl(video)"
            :src="getThumbnailUrl(video)"
            :alt="video.name"
            class="w-full h-full object-cover"
            loading="lazy"
          />
          <div v-else class="w-full h-full flex items-center justify-center">
            <Play class="w-10 h-10 text-neutral-400" />
          </div>

          <!-- Duration badge -->
          <span
            v-if="video.duration"
            class="absolute bottom-2 right-2 px-1.5 py-0.5 bg-black/80 text-white text-xs font-medium rounded"
          >
            {{ formatDuration(video.duration) }}
          </span>
        </div>

        <!-- Info -->
        <div class="p-3">
          <h3 class="text-sm font-medium text-neutral-900 dark:text-neutral-100 line-clamp-2 group-hover:text-secondary">
            {{ video.name }}
          </h3>
          <div class="mt-1.5 flex items-center gap-2 text-xs text-neutral-500 dark:text-neutral-400">
            <span>{{ video.account?.displayName || video.account?.name }}</span>
            <span>&middot;</span>
            <span>{{ formatViews(video.views) }}</span>
            <span>&middot;</span>
            <span>{{ formatRelativeDate(video.publishedAt || video.createdAt) }}</span>
          </div>
        </div>
      </NuxtLink>
    </div>

    <!-- Empty state -->
    <div v-else class="py-12 text-center">
      <img src="/images/para/searching.webp" alt="Para" class="mx-auto h-32 w-auto mb-6" />
      <h3 class="text-lg font-medium text-neutral-900 dark:text-neutral-100">{{ $t('videos.empty') }}</h3>
      <p class="mt-1 text-sm text-neutral-500 mb-6">{{ $t('videos.empty_desc') }}</p>
      <UiButton
        v-if="authStore.isAuthenticated"
        @click="showUpload = true"
      >
        <Upload class="w-4 h-4" />
        {{ $t('videos.upload.button') }}
      </UiButton>
      <NuxtLink
        v-else
        :to="localePath('/login')"
        class="inline-block px-6 py-2 bg-primary text-black font-medium rounded-lg hover:bg-opacity-90"
      >
        {{ $t('videos.sign_in_to_upload') }}
      </NuxtLink>
    </div>

    <!-- Load more -->
    <div v-if="hasMore && !pending" class="mt-6 text-center">
      <UiButton variant="outline" :loading="loadingMore" @click="loadMore">
        {{ $t('common.load_more') }}
      </UiButton>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Play, Upload } from 'lucide-vue-next'

const { t } = useI18n()
const localePath = useLocalePath()
const authStore = useAuthStore()

const PEERTUBE_URL = 'https://video.parahub.io'
const PAGE_SIZE = 12

const activeTab = useTabSync(['trending', 'recent'])
const videos = ref<any[]>([])
const pending = ref(true)
const loadingMore = ref(false)
const totalCount = ref(0)
const currentStart = ref(0)
const showUpload = ref(false)

async function onVideoUploaded() {
  showUpload.value = false
  pending.value = true
  await fetchVideos(0)
  pending.value = false
}

const tabs = computed(() => [
  { id: 'trending', label: t('videos.trending') },
  { id: 'recent', label: t('videos.recent') },
])

const hasMore = computed(() => currentStart.value + PAGE_SIZE < totalCount.value)

const sortMap: Record<string, string> = {
  trending: '-trending',
  recent: '-publishedAt',
}

async function fetchVideos(start = 0, append = false) {
  try {
    const sort = sortMap[activeTab.value] || '-trending'
    const data = await $fetch<any>(`${PEERTUBE_URL}/api/v1/videos`, {
      params: { start, count: PAGE_SIZE, sort, nsfw: 'false' },
    })

    if (append) {
      videos.value.push(...(data.data || []))
    } else {
      videos.value = data.data || []
    }
    totalCount.value = data.total || 0
    currentStart.value = start
  } catch (e) {
    console.error('Failed to fetch videos:', e)
    videos.value = append ? videos.value : []
  }
}

async function loadMore() {
  loadingMore.value = true
  await fetchVideos(currentStart.value + PAGE_SIZE, true)
  loadingMore.value = false
}

watch(activeTab, async () => {
  pending.value = true
  await fetchVideos(0)
  pending.value = false
})

onMounted(async () => {
  await fetchVideos(0)
  pending.value = false
})

function getThumbnailUrl(video: any): string {
  // v8.1+: thumbnails array with full URLs
  if (video.thumbnails?.length) return video.thumbnails[0].url
  // Fallback for older API responses
  if (video.thumbnailUrl) return video.thumbnailUrl
  if (video.thumbnailPath) return `${PEERTUBE_URL}${video.thumbnailPath}`
  return ''
}

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

function formatViews(views: number): string {
  if (views >= 1_000_000) return `${(views / 1_000_000).toFixed(1)}M`
  if (views >= 1_000) return `${(views / 1_000).toFixed(1)}K`
  return String(views || 0)
}

function formatRelativeDate(dateStr: string): string {
  if (!dateStr) return ''
  const now = Date.now()
  const diff = now - new Date(dateStr).getTime()
  const minutes = Math.floor(diff / 60000)
  if (minutes < 60) return `${minutes}m`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}d`
  const months = Math.floor(days / 30)
  return `${months}mo`
}

useHead({
  title: t('videos.title'),
})
useSeoMeta({
  title: t('videos.title'),
  ogTitle: t('videos.title'),
  description: t('videos.seo_description'),
  ogDescription: t('videos.seo_description'),
  ogType: 'website',
  twitterCard: 'summary',
  twitterTitle: t('videos.title'),
  twitterDescription: t('videos.seo_description'),
})
</script>
