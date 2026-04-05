<script setup lang="ts">
/**
 * Custom SitePage renderer for mini-sites.
 * Renders markdown content from SitePage model.
 * Only used on subdomain (site context).
 * URL: {slug}.org.parahub.io/{page-slug}
 */
import { ArrowLeft } from 'lucide-vue-next'

definePageMeta({ layout: 'site' })

const route = useRoute()
const { t } = useI18n()

const siteCtx = useSiteContext()
const site = useState<any>('siteData')
const pageSlug = computed(() => String(route.params.pageSlug))

const page = ref<any>(null)
const error = ref(false)

async function fetchPage() {
  if (!site.value?.establishment_id && !site.value?.profile_id) {
    error.value = true
    return
  }

  try {
    if (site.value.establishment_id) {
      page.value = await $fetch<any>(
        `/api/v1/cms/sites/by-establishment/${site.value.establishment_id}/pages/by-slug/${pageSlug.value}/`
      )
    }
  } catch {
    error.value = true
  }
}

onMounted(fetchPage)

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

      <UiAlert v-if="error" variant="error" class="mb-6">Page not found</UiAlert>

      <template v-if="page">
        <h1 class="text-3xl font-bold text-neutral-900 dark:text-neutral-100 mb-6">
          {{ page.title }}
        </h1>
        <div
          class="prose dark:prose-invert prose-neutral max-w-none"
          v-html="page.content_html"
        />
      </template>

      <div v-else-if="!error" class="flex justify-center py-12" role="status">
        <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100" />
      </div>
    </div>
  </div>
</template>
