<script setup lang="ts">
import { Calendar, Languages, MessageCircle, Pin, User } from 'lucide-vue-next'

interface Post {
  id: string
  title: string
  slug: string
  excerpt: string
  status: string
  language: string
  published_at: string | null
  is_pinned: boolean
  comments_count: number
  author_hna: string
  author_display_name: string | null
  author_avatar: string | null
  establishment_slug: string | null
  establishment_name: string | null
  featured_image_url: string | null
  tags: { id: string; name: string; slug: string }[]
  available_languages?: { id: string; language: string; slug: string }[]
}

const langCodes: Record<string, string> = {
  en: 'EN', pt: 'PT', es: 'ES', fr: 'FR', de: 'DE', ru: 'RU',
}

defineProps<{
  post: Post
  linkBase?: string
}>()

const { locale } = useI18n()
const localePath = useLocalePath()

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(locale.value, { day: 'numeric', month: 'short', year: 'numeric' })
}

function postUrl(post: Post, base?: string) {
  if (base) return localePath(`${base}/${post.slug}`)
  if (post.establishment_slug) return localePath(`/org/${post.establishment_slug}/blog/${post.slug}`)
  return localePath(`/blog/${post.slug}`)
}
</script>

<template>
  <NuxtLink
    :to="postUrl(post, linkBase)"
    class="block card p-4 sm:p-5 hover:border-primary transition-colors"
  >
    <div class="flex gap-4">
      <!-- Featured image -->
      <img
        v-if="post.featured_image_url"
        :src="post.featured_image_url"
        :alt="post.title"
        class="w-24 h-24 sm:w-32 sm:h-32 rounded-lg object-cover shrink-0"
      />

      <div class="flex-1 min-w-0">
        <!-- Badges -->
        <div class="flex items-center gap-2 mb-1.5 flex-wrap">
          <UiBadge v-if="post.is_pinned" variant="warning" type="soft" size="sm">
            <Pin class="w-3 h-3 mr-1" />
            {{ $t('cms.pinned') }}
          </UiBadge>
          <UiBadge v-if="post.status === 'draft'" variant="default" type="soft" size="sm">
            {{ $t('cms.draft') }}
          </UiBadge>
          <UiBadge
            v-for="tag in post.tags.slice(0, 3)"
            :key="tag.id"
            variant="info"
            type="soft"
            size="sm"
          >
            {{ tag.name }}
          </UiBadge>
        </div>

        <!-- Title -->
        <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-1 line-clamp-2">
          {{ post.title }}
        </h3>

        <!-- Excerpt -->
        <p class="text-sm text-neutral-600 dark:text-neutral-400 line-clamp-2 mb-2">
          {{ post.excerpt }}
        </p>

        <!-- Meta -->
        <div class="flex items-center gap-3 text-xs text-neutral-500 dark:text-neutral-400">
          <div class="flex items-center gap-1">
            <User class="w-3.5 h-3.5" />
            <span>{{ post.author_display_name || post.author_hna }}</span>
          </div>
          <div v-if="post.published_at" class="flex items-center gap-1">
            <Calendar class="w-3.5 h-3.5" />
            <span>{{ formatDate(post.published_at) }}</span>
          </div>
          <div v-if="post.comments_count > 0" class="flex items-center gap-1">
            <MessageCircle class="w-3.5 h-3.5" />
            <span>{{ post.comments_count }}</span>
          </div>
          <div v-if="post.available_languages?.length" class="flex items-center gap-1">
            <Languages class="w-3.5 h-3.5" />
            <span class="uppercase">{{ langCodes[post.language] || post.language }}</span>
            <span v-for="al in post.available_languages" :key="al.id" class="uppercase">{{ langCodes[al.language] || al.language }}</span>
          </div>
        </div>
      </div>
    </div>
  </NuxtLink>
</template>
