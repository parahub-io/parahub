<script setup lang="ts">
import { ArrowLeft, Search, Settings } from 'lucide-vue-next'

definePageMeta({ keepalive: true })

const route = useRoute()
const { t } = useI18n()
const localePath = useLocalePath()
const authStore = useAuthStore()

const estSlug = computed(() => String(route.params.slug))
const searchQuery = ref('')
let debounceTimer: ReturnType<typeof setTimeout> | null = null

// Check if user can manage this establishment (owner/admin)
const canManage = ref(false)
if (authStore.isAuthenticated) {
  authStore.ensureToken().then(async () => {
    try {
      const res = await $fetch<any[]>('/api/v1/geo/establishments/my-postable/', {
        credentials: 'include',
        headers: { Authorization: `Bearer ${authStore.token}` },
      })
      canManage.value = res.some((e: any) => e.slug === estSlug.value)
    } catch { /* ignore */ }
  })
}

const fetchParams = computed(() => {
  const p: Record<string, string> = { establishment_slug: estSlug.value, page_size: '50' }
  if (searchQuery.value.trim()) p.search = searchQuery.value.trim()
  return p
})

const { data: postsData, error, status, refresh } = await useAsyncData(
  () => `blog-org-${estSlug.value}`,
  () => $fetch<{ items: any[]; count: number }>('/api/v1/cms/posts/', {
    params: fetchParams.value,
  }),
  { watch: [estSlug] },
)
const posts = computed(() => postsData.value?.items || [])
const loading = computed(() => status.value === 'pending')

function debouncedSearch() {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => refresh(), 400)
}
const estName = computed(() => posts.value[0]?.establishment_name || estSlug.value)

const blogTitle = computed(() => `${t('cms.blog')} — ${estName.value || estSlug.value}`)
useHead({
  title: blogTitle.value,
  link: [{ rel: 'alternate', type: 'application/rss+xml', title: 'RSS', href: `/api/v1/cms/posts/rss/?establishment_slug=${estSlug.value}` }],
})
useSeoMeta({
  title: blogTitle.value,
  ogTitle: blogTitle.value,
  description: blogTitle.value,
  ogDescription: blogTitle.value,
  ogType: 'website',
  twitterTitle: blogTitle.value,
  twitterDescription: blogTitle.value,
})
</script>

<template>
  <div class="py-6">
    <div class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
      <!-- Back to org -->
      <NuxtLink :to="localePath(`/org/${estSlug}`)" class="inline-flex items-center gap-1 text-sm text-neutral-500 hover:text-secondary mb-4">
        <ArrowLeft class="w-4 h-4" />
        {{ estName || estSlug }}
      </NuxtLink>

      <PageHeader
        :title="t('cms.blog')"
        :subtitle="estName"
        :create-to="canManage ? localePath(`/blog/create?est=${estSlug}`) : undefined"
        :create-label="canManage ? t('cms.newPost') : undefined"
      />

      <!-- Manage link for admins -->
      <div v-if="canManage" class="mb-4">
        <NuxtLink :to="localePath(`/org/${estSlug}/manage`)" class="inline-flex items-center gap-1.5 text-sm text-neutral-500 hover:text-secondary">
          <Settings class="w-4 h-4" />
          {{ t('cms.manage.title') }}
        </NuxtLink>
      </div>

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
        <img src="/images/para/reading.png" alt="Para" class="mx-auto h-32 w-auto mb-4" />
        <h3 class="text-lg font-semibold text-neutral-700 dark:text-neutral-300 mb-1">{{ t('cms.noPosts') }}</h3>
        <p class="text-neutral-500 dark:text-neutral-400">{{ t('cms.noPostsDesc') }}</p>
      </div>

      <!-- Posts list -->
      <div v-else class="space-y-4">
        <BlogPostCard
          v-for="post in posts"
          :key="post.id"
          :post="post"
          :link-base="`/org/${estSlug}/blog`"
        />
      </div>
    </div>
  </div>
</template>
