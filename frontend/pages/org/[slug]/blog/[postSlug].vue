<script setup lang="ts">
definePageMeta({})

const route = useRoute()
const { t, locale } = useI18n()
const localePath = useLocalePath()
const authStore = useAuthStore()

const estSlug = computed(() => String(route.params.slug))
const postSlug = computed(() => String(route.params.postSlug))

// Auth headers: forward cookies during SSR, JWT on client (for draft preview)
const ssrHeaders = useRequestHeaders(['cookie'])

const { data: post, error } = await useAsyncData(
  () => `blog-org-${estSlug.value}-${postSlug.value}`,
  () => {
    const headers: Record<string, string> = {}
    if (import.meta.server && ssrHeaders.cookie) {
      headers.cookie = ssrHeaders.cookie
    } else if (import.meta.client && authStore.token) {
      headers['Authorization'] = `Bearer ${authStore.token}`
    }
    return $fetch<any>(`/api/v1/cms/posts/by-slug/${postSlug.value}/`, {
      params: { establishment_slug: estSlug.value },
      headers,
      credentials: 'include',
    })
  },
  { watch: [postSlug] },
)

useHead({
  title: post.value?.title || t('cms.blog'),
  link: [{ rel: 'alternate', type: 'application/rss+xml', title: 'RSS', href: `/api/v1/cms/posts/rss/?establishment_slug=${estSlug.value}` }],
  ...(post.value?.is_demo ? { meta: [{ name: 'robots', content: 'noindex, nofollow' }] } : {}),
})
useBlogHreflang(post, computed(() => `/org/${estSlug.value}/blog`))
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
        author: { '@type': 'Person', name: post.value.author_display_name || post.value.author_hna },
        publisher: post.value.establishment_name ? { '@type': 'Organization', name: post.value.establishment_name } : undefined,
        ...(post.value.featured_image_url ? { image: post.value.featured_image_url } : {}),
      }),
    }],
  })
}
</script>

<template>
  <UiAlert v-if="error" variant="error" class="max-w-4xl mx-auto mt-6 px-4">{{ t('cms.postNotFound') }}</UiAlert>
  <BlogPostView
    v-else-if="post"
    :post="post"
    :back-link="`/org/${estSlug}/blog`"
    :back-label="post.establishment_name || t('cms.blog')"
    :translation-link-base="`/org/${estSlug}/blog`"
  />
</template>
