<script setup lang="ts">
/**
 * Mini-site home page content.
 * Shows recent posts and links to custom pages.
 * Used when subdomain is detected.
 */
import { Newspaper, FileText } from 'lucide-vue-next'

const { t } = useI18n()

const site = useState<any>('siteData')
const posts = ref<any[]>([])
const loading = ref(true)

async function fetchPosts() {
  if (!site.value) return
  try {
    const params: Record<string, string> = { page_size: '10' }
    if (site.value.establishment_id) {
      params.establishment_id = site.value.establishment_id
    } else if (site.value.profile_local_name) {
      params.author_name = site.value.profile_local_name
    }
    const res = await $fetch<{ items: any[] }>('/api/v1/cms/posts/', { params })
    posts.value = res.items
  } catch { /* ignore */ }
  loading.value = false
}

onMounted(fetchPosts)

const siteName = computed(() =>
  site.value?.establishment_name || site.value?.profile_name || ''
)
</script>

<template>
  <div class="py-8">
    <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
      <!-- Welcome -->
      <div v-if="!site?.hero_text_html" class="text-center mb-8">
        <h1 class="text-3xl font-bold text-neutral-900 dark:text-neutral-100 mb-2">
          {{ siteName }}
        </h1>
      </div>

      <!-- Recent posts -->
      <div v-if="loading" class="flex justify-center py-12" role="status">
        <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100" />
      </div>

      <div v-else-if="posts.length > 0">
        <h2 class="text-xl font-semibold text-neutral-900 dark:text-neutral-100 mb-4 flex items-center gap-2">
          <Newspaper class="w-5 h-5" />
          {{ t('cms.posts') }}
        </h2>
        <div class="space-y-4">
          <BlogPostCard
            v-for="post in posts"
            :key="post.id"
            :post="post"
            link-base="/blog"
          />
        </div>
      </div>

      <!-- Custom pages grid -->
      <div v-if="site?.nav_pages?.length" class="mt-8">
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <NuxtLink
            v-for="page in site.nav_pages"
            :key="page.id"
            :to="`/${page.slug}`"
            class="card p-4 hover:border-primary transition-colors flex items-center gap-3"
          >
            <FileText class="w-5 h-5 text-neutral-400 shrink-0" />
            <span class="text-neutral-900 dark:text-neutral-100 font-medium">{{ page.title }}</span>
          </NuxtLink>
        </div>
      </div>

      <!-- Empty state -->
      <div v-if="!loading && posts.length === 0 && !site?.nav_pages?.length" class="text-center py-12">
        <Newspaper class="w-12 h-12 text-neutral-400 mx-auto mb-3" />
        <h3 class="text-lg font-semibold text-neutral-700 dark:text-neutral-300 mb-1">
          {{ t('cms.noPosts') }}
        </h3>
        <p class="text-neutral-500 dark:text-neutral-400">
          {{ t('cms.noPostsDesc') }}
        </p>
      </div>
    </div>
  </div>
</template>
