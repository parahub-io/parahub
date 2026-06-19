<script setup lang="ts">
import {
  ArrowLeft, Calendar, User, Pin, Clock,
  FileText, Download, Pencil
} from 'lucide-vue-next'

const { t, locale } = useI18n()
const localePath = useLocalePath()
const authStore = useAuthStore()

const props = defineProps<{
  post: any
  backLink: string
  backLabel: string
  translationLinkBase: string
}>()

const canEdit = computed(() => {
  if (!authStore.isAuthenticated || !props.post) return false
  const profile = authStore.activeProfile
  if (!profile) return false
  return props.post.author_id === profile.id
})

const readingTime = computed(() => {
  if (!props.post?.content) return 0
  const words = props.post.content.trim().split(/\s+/).length
  return Math.max(1, Math.round(words / 200))
})

const formattedDate = computed(() => {
  if (!props.post?.published_at) return null
  return new Date(props.post.published_at).toLocaleDateString(locale.value, {
    day: 'numeric', month: 'long', year: 'numeric',
  })
})

const scrollProgress = ref(0)
let scrollTarget: HTMLElement | Window | null = null
function getScrollMetrics() {
  const mc = document.getElementById('main-content')
  if (mc && mc.scrollHeight > mc.clientHeight) {
    return { scrollTop: mc.scrollTop, scrollable: mc.scrollHeight - mc.clientHeight }
  }
  const el = document.documentElement
  return { scrollTop: el.scrollTop || window.scrollY, scrollable: el.scrollHeight - el.clientHeight }
}
function updateScrollProgress() {
  const { scrollTop, scrollable } = getScrollMetrics()
  scrollProgress.value = scrollable > 0
    ? Math.min(100, Math.max(0, (scrollTop / scrollable) * 100))
    : 0
}
onMounted(() => {
  scrollTarget = document.getElementById('main-content') || window
  scrollTarget.addEventListener('scroll', updateScrollProgress, { passive: true })
  window.addEventListener('resize', updateScrollProgress, { passive: true })
  updateScrollProgress()
  loadRelated()
})
onUnmounted(() => {
  if (scrollTarget) scrollTarget.removeEventListener('scroll', updateScrollProgress)
  window.removeEventListener('resize', updateScrollProgress)
})

const relatedPosts = ref<any[]>([])
async function loadRelated() {
  if (!props.post?.id || !props.post?.language) {
    relatedPosts.value = []
    return
  }
  try {
    const data = await $fetch<{ items: any[] }>('/api/v1/cms/posts/', {
      params: { language: props.post.language, page_size: 6 },
    })
    relatedPosts.value = (data?.items || [])
      .filter((p: any) => p.id !== props.post.id)
      .slice(0, 3)
  } catch {
    relatedPosts.value = []
  }
}
watch(() => props.post?.id, loadRelated, { immediate: false })
</script>

<template>
  <!-- Reading progress bar -->
  <div
    class="fixed top-0 left-0 h-[2px] bg-primary z-[70] pointer-events-none transition-[width] duration-75"
    :style="{ width: scrollProgress + '%' }"
    aria-hidden="true"
  />
  <div class="py-6">
    <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
      <!-- Back -->
      <NuxtLink :to="localePath(backLink)" class="inline-flex items-center gap-1 text-sm text-neutral-500 hover:text-secondary mb-6">
        <ArrowLeft class="w-4 h-4" />
        {{ backLabel }}
      </NuxtLink>

      <!-- Featured image — full-bleed hero -->
      <img
        v-if="post.featured_image_url"
        :src="post.featured_image_url"
        :alt="post.title"
        class="w-full aspect-[2/1] object-cover rounded-xl mb-8"
      />

      <!-- Article card -->
      <article class="card overflow-hidden">
        <!-- Yellow accent bar -->
        <div class="h-1 bg-primary" />

        <div class="p-6 sm:p-8">
          <!-- Badges row -->
          <div v-if="post.status === 'draft' || post.is_pinned || post.is_demo || post.tags?.length" class="flex items-center gap-2 mb-4 flex-wrap">
            <DemoBadge :is-demo="post.is_demo" />
            <UiBadge v-if="post.status === 'draft'" variant="default" type="soft" size="sm">
              {{ t('cms.draft') }}
            </UiBadge>
            <UiBadge v-if="post.is_pinned" variant="warning" type="soft" size="sm">
              <Pin class="w-3 h-3 mr-1" />{{ t('cms.pinned') }}
            </UiBadge>
            <UiBadge v-for="tag in post.tags" :key="tag.id" variant="info" type="soft" size="sm">
              {{ tag.name }}
            </UiBadge>
          </div>

          <!-- Title + edit -->
          <div class="flex items-start justify-between gap-4 mb-5">
            <h1 class="text-2xl sm:text-3xl font-bold text-neutral-900 dark:text-neutral-100 leading-tight">
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

          <!-- Author / date / reading time bar -->
          <div class="flex items-center gap-3 flex-wrap text-sm text-neutral-500 dark:text-neutral-400 pb-5 mb-6 border-b border-neutral-200 dark:border-neutral-700">
            <!-- Author -->
            <NuxtLink
              :to="localePath(`/u/${post.author_hna.split('@')[0]}`)"
              class="flex items-center gap-2 hover:text-secondary transition-colors"
            >
              <img
                v-if="post.author_avatar"
                :src="post.author_avatar"
                class="w-7 h-7 rounded-full ring-2 ring-neutral-100 dark:ring-neutral-700"
              />
              <div v-else class="w-7 h-7 rounded-full bg-neutral-200 dark:bg-neutral-700 flex items-center justify-center">
                <User class="w-4 h-4 text-neutral-500" />
              </div>
              <span class="font-medium text-neutral-700 dark:text-neutral-300">
                {{ post.author_display_name || post.author_hna }}
              </span>
            </NuxtLink>

            <!-- Org name -->
            <span v-if="post.establishment_name" class="text-neutral-400">
              {{ post.establishment_name }}
            </span>

            <!-- Date -->
            <div v-if="formattedDate" class="flex items-center gap-1">
              <Calendar class="w-3.5 h-3.5" />
              {{ formattedDate }}
            </div>

            <!-- Reading time -->
            <div v-if="readingTime" class="flex items-center gap-1">
              <Clock class="w-3.5 h-3.5" />
              {{ readingTime }} {{ t('cms.minRead') }}
            </div>
          </div>

          <!-- Translation switcher -->
          <BlogTranslationSwitcher
            v-if="post.translations?.length || canEdit"
            :current-language="post.language"
            :translations="post.translations || []"
            :can-edit="canEdit"
            :post-id="post.id"
            :link-base="translationLinkBase"
            class="mb-6"
          />

          <!-- Content (hide leading h1 — already shown in card header) -->
          <div
            class="blog-content prose dark:prose-invert prose-neutral prose-headings:text-neutral-900 dark:prose-headings:text-neutral-100 prose-a:text-secondary prose-img:rounded-lg max-w-none"
            v-html="post.content_html"
          />
        </div>
      </article>

      <!-- Files -->
      <div v-if="post.files && post.files.length > 0" class="card p-5 sm:p-6 mt-6">
        <h2 class="text-base font-semibold text-neutral-900 dark:text-neutral-100 mb-3 flex items-center gap-2">
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

      <!-- Photos -->
      <BlogPostPhotos :post-id="post.id" class="mt-6" />

      <!-- Videos -->
      <ObjectVideos :object-id="post.id" class="mt-6" />

      <!-- Comments -->
      <div class="mt-6">
        <BlogPostComments
          :post-id="post.id"
          :allow-comments="post.allow_comments"
          :comments-count="post.comments_count"
        />
      </div>

      <!-- Related posts -->
      <section v-if="relatedPosts.length" class="mt-8">
        <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4">
          {{ t('cms.relatedPosts') }}
        </h2>
        <div class="space-y-3">
          <BlogPostCard v-for="rp in relatedPosts" :key="rp.id" :post="rp" />
        </div>
      </section>
    </div>
  </div>
</template>
