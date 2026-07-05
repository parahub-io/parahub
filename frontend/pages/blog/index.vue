<script setup lang="ts">
import { Search } from 'lucide-vue-next'

definePageMeta({ keepalive: true })

const { t } = useI18n()
const localePath = useLocalePath()
const authStore = useAuthStore()

const searchQuery = ref('')
let debounceTimer: ReturnType<typeof setTimeout> | null = null

const fetchParams = computed(() => {
  const p: Record<string, string> = { page_size: '50' }
  if (searchQuery.value.trim()) p.search = searchQuery.value.trim()
  return p
})

const { data: postsData, error, status, refresh } = await useAsyncData(
  'blog-index',
  () => $fetch<{ items: any[]; count: number }>('/api/v1/cms/posts/', {
    params: fetchParams.value,
  }),
)
const posts = computed(() => postsData.value?.items || [])
const loading = computed(() => status.value === 'pending')

function debouncedSearch() {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => refresh(), 400)
}

useHead({
  title: t('cms.blog'),
  link: [{ rel: 'alternate', type: 'application/rss+xml', title: 'RSS', href: '/api/v1/cms/posts/rss/' }],
})
useSeoMeta({
  title: t('cms.blog'),
  ogTitle: t('cms.blog'),
  description: 'Parahub community blog',
  ogDescription: 'Parahub community blog',
  ogType: 'website',
  twitterTitle: t('cms.blog'),
  twitterDescription: 'Parahub community blog',
})
</script>

<template>
  <div class="py-6">
    <div class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
      <PageHeader
        :title="t('cms.blog')"
        :create-to="authStore.isAuthenticated ? localePath('/blog/create') : undefined"
        :create-label="authStore.isAuthenticated ? t('cms.newPost') : undefined"
      />

      <!-- Search -->
      <div class="mb-6">
        <div class="relative max-w-md">
          <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400" />
          <input
            v-model="searchQuery"
            @input="debouncedSearch"
            type="text"
            :placeholder="t('cms.searchPosts')"
            class="w-full pl-9 pr-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 text-sm focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
          />
        </div>
      </div>

      <!-- Loading -->
      <div v-if="loading" class="flex justify-center py-12" role="status">
        <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100" />
        <span class="sr-only">{{ $t('common.loading') }}</span>
      </div>

      <UiAlert v-else-if="error" variant="error" class="mb-6">{{ error }}</UiAlert>

      <!-- Empty -->
      <div v-else-if="posts.length === 0" class="text-center py-12">
        <img src="/images/para/reading.webp" alt="Para" class="mx-auto h-32 w-auto mb-4" />
        <h3 class="text-lg font-semibold text-neutral-700 dark:text-neutral-300 mb-1">
          {{ t('cms.noPosts') }}
        </h3>
        <p class="text-neutral-500 dark:text-neutral-400">
          {{ t('cms.noPostsDesc') }}
        </p>
      </div>

      <!-- Posts list -->
      <div v-else class="space-y-4">
        <BlogPostCard v-for="post in posts" :key="post.id" :post="post" link-base="/blog" />
      </div>
    </div>
  </div>
</template>
