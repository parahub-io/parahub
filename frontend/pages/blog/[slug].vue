<script setup lang="ts">
import {
  ArrowLeft, Calendar, User, Pin,
  FileText, Download, Pencil
} from 'lucide-vue-next'

definePageMeta({})

const route = useRoute()
const { t, locale } = useI18n()
const localePath = useLocalePath()
const authStore = useAuthStore()

const slug = computed(() => String(route.params.slug))

// Determine context: org blog, user blog, or association blog
const estSlug = computed(() => String(route.query.est || ''))
const authorName = computed(() => String(route.query.author || ''))

const { data: post, error } = await useAsyncData(
  () => `blog-post-${slug.value}`,
  () => $fetch<any>(`/api/v1/cms/posts/by-slug/${slug.value}/`, {
    params: {
      ...(estSlug.value ? { establishment_slug: estSlug.value } : {}),
      ...(authorName.value ? { author_name: authorName.value } : {}),
    },
  }),
  { watch: [slug] },
)

const canEdit = computed(() => {
  if (!authStore.isAuthenticated || !post.value) return false
  const profile = authStore.activeProfile
  if (!profile) return false
  return post.value.author_id === profile.id
})

useHead({
  title: post.value?.title || t('cms.blog'),
  link: [{ rel: 'alternate', type: 'application/rss+xml', title: 'RSS', href: '/api/v1/cms/posts/rss/' }],
  ...(post.value?.is_demo ? { meta: [{ name: 'robots', content: 'noindex, nofollow' }] } : {}),
})

const postDesc = computed(() => post.value?.meta_description || post.value?.excerpt || '')
useSeoMeta({
  title: post.value?.title,
  ogTitle: post.value?.title,
  description: postDesc.value,
  ogDescription: postDesc.value,
  ogType: 'article',
  ...(post.value?.published_at ? { articlePublishedTime: post.value.published_at } : {}),
  ...(post.value?.updated_at ? { articleModifiedTime: post.value.updated_at } : {}),
  ...(post.value?.author_display_name || post.value?.author_hna ? { articleAuthor: post.value.author_display_name || post.value.author_hna } : {}),
  ...(post.value?.featured_image_url ? { ogImage: post.value.featured_image_url, twitterImage: post.value.featured_image_url } : {}),
  twitterCard: post.value?.featured_image_url ? 'summary_large_image' : 'summary',
  twitterTitle: post.value?.title,
  twitterDescription: postDesc.value,
})

// JSON-LD Article
if (post.value) {
  useHead({
    script: [{
      type: 'application/ld+json',
      innerHTML: JSON.stringify({
        '@context': 'https://schema.org',
        '@type': 'Article',
        headline: post.value.title,
        description: post.value.meta_description || post.value.excerpt,
        datePublished: post.value.published_at,
        dateModified: post.value.updated_at,
        author: {
          '@type': 'Person',
          name: post.value.author_display_name || post.value.author_hna,
        },
        ...(post.value.featured_image_url ? { image: post.value.featured_image_url } : {}),
      }),
    }],
  })
}
</script>

<template>
  <div class="py-6">
    <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
      <!-- Back link -->
      <NuxtLink :to="localePath('/blog')" class="inline-flex items-center gap-1 text-sm text-neutral-500 hover:text-secondary mb-4">
        <ArrowLeft class="w-4 h-4" />
        {{ t('cms.blog') }}
      </NuxtLink>

      <UiAlert v-if="error" variant="error" class="mb-6">{{ t('cms.postNotFound') }}</UiAlert>

      <template v-if="post">
        <!-- Header -->
        <div class="mb-6">
          <div class="flex items-center gap-2 mb-2 flex-wrap">
            <UiBadge v-if="post.is_pinned" variant="warning" type="soft" size="sm">
              <Pin class="w-3 h-3 mr-1" />
              {{ t('cms.pinned') }}
            </UiBadge>
            <UiBadge v-if="post.status === 'draft'" variant="default" type="soft" size="sm">
              {{ t('cms.draft') }}
            </UiBadge>
            <UiBadge
              v-for="tag in post.tags"
              :key="tag.id"
              variant="info"
              type="soft"
              size="sm"
            >
              {{ tag.name }}
            </UiBadge>
          </div>

          <div class="flex items-start justify-between gap-4">
            <h1 class="text-3xl font-bold text-neutral-900 dark:text-neutral-100">
              {{ post.title }}
            </h1>
            <NuxtLink
              v-if="canEdit"
              :to="localePath(`/blog/create?edit=${post.id}`)"
              class="btn-outline btn-sm shrink-0"
            >
              <Pencil class="w-4 h-4" />
              {{ t('cms.editPost') }}
            </NuxtLink>
          </div>

          <!-- Translation switcher -->
          <BlogTranslationSwitcher
            v-if="post.translations?.length || canEdit"
            :current-language="post.language"
            :translations="post.translations || []"
            :can-edit="canEdit"
            :post-id="post.id"
            link-base="/blog"
            class="mt-3"
          />

          <!-- Author & date -->
          <div class="flex items-center gap-4 mt-3 text-sm text-neutral-500 dark:text-neutral-400">
            <div class="flex items-center gap-1.5">
              <img
                v-if="post.author_avatar"
                :src="post.author_avatar"
                class="w-6 h-6 rounded-full"
              />
              <User v-else class="w-4 h-4" />
              <NuxtLink
                :to="localePath(`/u/${post.author_hna.split('@')[0]}`)"
                class="text-link"
              >
                {{ post.author_display_name || post.author_hna }}
              </NuxtLink>
            </div>
            <div v-if="post.establishment_name" class="flex items-center gap-1">
              <span>{{ post.establishment_name }}</span>
            </div>
            <div v-if="post.published_at" class="flex items-center gap-1">
              <Calendar class="w-4 h-4" />
              <span>{{ new Date(post.published_at).toLocaleDateString(locale, { day: 'numeric', month: 'long', year: 'numeric' }) }}</span>
            </div>
          </div>
        </div>

        <!-- Featured image -->
        <img
          v-if="post.featured_image_url"
          :src="post.featured_image_url"
          :alt="post.title"
          class="w-full rounded-lg mb-6 max-h-96 object-cover"
        />

        <!-- Content -->
        <div
          class="prose dark:prose-invert prose-neutral max-w-none mb-8"
          v-html="post.content_html"
        />

        <!-- Files -->
        <div v-if="post.files && post.files.length > 0" class="card p-4 mb-6">
          <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-3 flex items-center gap-2">
            <FileText class="w-5 h-5" />
            {{ t('cms.files.title') }}
          </h2>
          <div class="space-y-2">
            <a
              v-for="file in post.files"
              :key="file.id"
              :href="file.url"
              target="_blank"
              class="flex items-center justify-between p-3 rounded-lg border border-neutral-200 dark:border-neutral-700 hover:border-primary transition-colors"
            >
              <div class="flex items-center gap-2 min-w-0">
                <FileText class="w-4 h-4 text-neutral-500 shrink-0" />
                <span class="text-sm text-neutral-900 dark:text-neutral-100 truncate">{{ file.filename }}</span>
                <span class="text-xs text-neutral-400">{{ Math.round(file.size_bytes / 1024) }} KB</span>
              </div>
              <Download class="w-4 h-4 text-neutral-400 shrink-0" />
            </a>
          </div>
        </div>

        <!-- Photos gallery -->
        <BlogPostPhotos :post-id="post.id" />

        <!-- Videos -->
        <ObjectVideos :object-id="post.id" class="mt-4" />

        <!-- Comments -->
        <BlogPostComments :post-id="post.id" :allow-comments="post.allow_comments" :comments-count="post.comments_count" />
      </template>
    </div>
  </div>
</template>
