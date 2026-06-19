<script setup lang="ts">
/**
 * Mini-site home page content.
 * Priority: homepage page → pages grid + optional blog → empty "configure" state.
 */
import { Newspaper, FileText, Settings } from 'lucide-vue-next'

const { t } = useI18n()

const site = useState<any>('siteData')

// Check if blog section is enabled in nav_sections
const blogEnabled = computed(() =>
  (site.value?.nav_sections || []).some((s: any) => s.type === 'blog')
)

// Homepage page (is_homepage=true)
const homePage = computed(() =>
  site.value?.nav_pages?.find((p: any) => p.is_homepage) || null
)

// Regular nav pages (exclude homepage)
const navPages = computed(() =>
  (site.value?.nav_pages || []).filter((p: any) => !p.is_homepage)
)

// Blog posts — only fetch if blog section enabled
const posts = ref<any[]>([])
const loading = ref(true)

async function fetchPosts() {
  if (!site.value || !blogEnabled.value) {
    loading.value = false
    return
  }
  try {
    const params: Record<string, string> = { page_size: '6' }
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

const manageUrl = computed(() => {
  if (site.value?.establishment_slug) return `https://parahub.io/org/${site.value.establishment_slug}/manage`
  if (site.value?.profile_local_name) return `https://parahub.io/u/${site.value.profile_local_name}/manage`
  return null
})
</script>

<template>
  <div class="py-8">
    <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">

      <!-- Site name (when no hero) -->
      <div v-if="!site?.hero_text_html" class="text-center mb-8">
        <h1 class="text-3xl font-bold text-neutral-900 dark:text-neutral-100 mb-2">
          {{ siteName }}
        </h1>
      </div>

      <!-- Homepage page content -->
      <div v-if="homePage" class="mb-8">
        <div
          class="prose dark:prose-invert prose-neutral max-w-none"
          v-html="homePage.content_html"
        />
      </div>

      <!-- Custom pages grid (when no homepage page) -->
      <div v-else-if="navPages.length" class="mb-8">
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <NuxtLink
            v-for="page in navPages"
            :key="page.id"
            :to="`/${page.slug}`"
            class="card p-4 hover:border-primary transition-colors flex items-center gap-3"
          >
            <FileText class="w-5 h-5 text-neutral-400 shrink-0" />
            <span class="text-neutral-900 dark:text-neutral-100 font-medium">{{ page.title }}</span>
          </NuxtLink>
        </div>
      </div>

      <!-- Blog posts (only when blog section enabled) -->
      <div v-if="blogEnabled">
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
      </div>

      <!-- Empty state: no pages, no posts, no homepage -->
      <div v-if="!loading && !homePage && navPages.length === 0 && posts.length === 0" class="text-center py-12">
        <img src="/images/para/welcome.png" alt="" aria-hidden="true" class="mx-auto h-32 w-auto mb-4" />
        <h3 class="text-lg font-semibold text-neutral-700 dark:text-neutral-300 mb-1">
          {{ t('cms.site.emptyTitle') }}
        </h3>
        <p class="text-neutral-500 dark:text-neutral-400 mb-4">
          {{ t('cms.site.emptyDesc') }}
        </p>
        <NuxtLink
          v-if="manageUrl"
          :to="manageUrl"
          class="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg bg-primary text-white hover:bg-primary/90 transition-colors"
        >
          <Settings class="w-4 h-4" />
          {{ t('cms.site.configure') }}
        </NuxtLink>
      </div>

    </div>
  </div>
</template>
