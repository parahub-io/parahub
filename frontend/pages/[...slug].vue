<script setup lang="ts">
/**
 * Catch-all page for mini-site subdomain custom pages.
 * On subdomain: loads SitePage by slug (e.g., /about-us → page slug "about-us").
 * On main domain: throws 404.
 */
import { ArrowLeft } from 'lucide-vue-next'

const siteCtx = useSiteContext()

// Not on a subdomain — this is a regular 404
if (!siteCtx.value) {
  throw createError({ statusCode: 404, statusMessage: 'Page not found' })
}

const route = useRoute()
const { t } = useI18n()

const site = useState<any>('siteData')

const pageSlug = computed(() => {
  const parts = route.params.slug as string[]
  return parts.join('/')
})

const { data: page, error } = await useAsyncData(
  `site-page-${pageSlug.value}`,
  async () => {
    if (!site.value?.establishment_id && !site.value?.profile_id) return null

    try {
      if (site.value.establishment_id) {
        return await $fetch<any>(
          `/api/v1/cms/sites/by-establishment/${site.value.establishment_id}/pages/by-slug/${pageSlug.value}/`
        )
      }
      if (site.value.profile_id) {
        return await $fetch<any>(
          `/api/v1/cms/sites/by-profile/${site.value.profile_name}/pages/by-slug/${pageSlug.value}/`
        )
      }
    } catch {
      return null
    }
    return null
  }
)

// Page not found on this site
if (!page.value && !error.value) {
  throw createError({ statusCode: 404, statusMessage: 'Page not found' })
}

useHead(computed(() => ({
  title: page.value?.title || pageSlug.value,
})))
</script>

<template>
  <div class="py-6">
    <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
      <NuxtLink to="/" class="inline-flex items-center gap-1 text-sm text-neutral-500 hover:text-secondary mb-4">
        <ArrowLeft class="w-4 h-4" />
        {{ site?.establishment_name || site?.profile_name || t('common.home') }}
      </NuxtLink>

      <template v-if="page">
        <h1 class="text-3xl font-bold text-neutral-900 dark:text-neutral-100 mb-6">
          {{ page.title }}
        </h1>
        <div
          class="prose dark:prose-invert prose-neutral max-w-none"
          v-html="page.content_html"
        />
      </template>

      <div v-else class="flex justify-center py-12" role="status">
        <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100" />
      </div>
    </div>
  </div>
</template>
