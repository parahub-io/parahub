<script setup lang="ts">
import { Send, Check, Undo2, Star, AlertCircle, Trash2, Pin } from 'lucide-vue-next'

interface TopicGroup {
  key: string
  order: number | null
  displayTitle: string
  displayPostId: string
  posts: any[]
  missingLangs: string[]
  allApproved: boolean
  anyApproved: boolean
  allPublished: boolean
  anyPublished: boolean
}

const props = defineProps<{
  group: TopicGroup
  estSlug: string
  busy: boolean
  section?: 'drafts' | 'ready' | 'published'
  canApprove?: boolean
  isNextRecommended?: boolean
  locale: string
  t: (key: string, params?: any) => string
  localPath: (path: string) => string
}>()

const emit = defineEmits<{
  (e: 'approve', g: TopicGroup): void
  (e: 'unapprove', g: TopicGroup): void
  (e: 'publish', g: TopicGroup): void
  (e: 'delete', g: TopicGroup): void
}>()

const approver = computed(() => {
  const postWithApprover = props.group.posts.find(p => p.approved_by_name)
  return postWithApprover?.approved_by_name || ''
})

const publishedAt = computed(() => {
  const p = props.group.posts.find(p => p.published_at)
  if (!p) return ''
  return new Date(p.published_at).toLocaleDateString(props.locale, {
    day: 'numeric', month: 'short', year: 'numeric',
  })
})

// Topic is "pinned" if any of its language versions has is_pinned set.
// Pin status is per-post in DB but conceptually a topic-level flag here.
const isPinned = computed(() => props.group.posts.some(p => p.is_pinned))

const lastUpdated = computed(() => {
  let max = 0
  for (const p of props.group.posts) {
    if (p.updated_at) {
      const t = new Date(p.updated_at).getTime()
      if (t > max) max = t
    }
  }
  if (!max) return ''
  const diff = Date.now() - max
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'now'
  if (mins < 60) return `${mins}m`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h`
  const days = Math.floor(hours / 24)
  return `${days}d`
})

function langBadgeVariant(lang: string): 'info' | 'default' {
  return lang === 'pt' ? 'info' : 'default'
}
</script>

<template>
  <div
    class="p-4 bg-white dark:bg-neutral-800 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors"
    :class="{
      'ring-2 ring-primary bg-primary/5 dark:bg-primary/10': isNextRecommended,
    }"
  >
    <!-- Mobile: stack vertically. Desktop (sm+): title left, actions right. -->
    <div class="flex flex-col sm:flex-row sm:items-start gap-3 sm:gap-4">
      <!-- Title + language chips + meta -->
      <div class="flex-1 min-w-0">
        <div class="flex items-start gap-2 mb-2">
          <Star v-if="isNextRecommended" class="w-4 h-4 text-primary shrink-0 mt-0.5" />
          <Pin v-if="isPinned" class="w-4 h-4 text-yellow-500 shrink-0 mt-0.5" :title="t('cms.pinned') || 'Pinned'" />
          <span
            v-if="group.order != null"
            class="text-xs text-neutral-400 shrink-0 mt-0.5 tabular-nums"
            :title="t('cms.manage.publishOrder') || 'Порядок публикации'"
          >
            #{{ group.order }}
          </span>
          <NuxtLink
            :to="{ path: localPath('/blog/create'), query: { edit: group.displayPostId, back: localPath(`/org/${estSlug}/manage`) } }"
            class="text-sm font-medium text-neutral-900 dark:text-neutral-100 hover:text-secondary truncate"
          >
            {{ group.displayTitle }}
          </NuxtLink>
        </div>

        <!-- Language chips (clickable → edit) -->
        <div class="flex flex-wrap items-center gap-1.5">
          <NuxtLink
            v-for="post in group.posts"
            :key="post.id"
            :to="{ path: localPath('/blog/create'), query: { edit: post.id, back: localPath(`/org/${estSlug}/manage`) } }"
            class="inline-block"
            :title="post.title"
          >
            <UiBadge :variant="langBadgeVariant(post.language)" type="soft" size="sm">
              {{ post.language.toUpperCase() }}
            </UiBadge>
          </NuxtLink>
          <!-- Missing language badges -->
          <UiBadge
            v-for="lang in group.missingLangs"
            :key="`missing-${lang}`"
            variant="warning"
            type="soft"
            size="sm"
            class="opacity-70"
          >
            {{ t('cms.manage.missingLanguage', { lang: lang.toUpperCase() }) }}
          </UiBadge>

          <!-- Meta info -->
          <span v-if="section === 'ready' && approver" class="text-xs text-neutral-500 ml-2">
            · {{ t('cms.manage.approvedBy', { name: approver }) }}
          </span>
          <span v-if="section === 'published' && publishedAt" class="text-xs text-neutral-500 ml-2">
            · {{ publishedAt }}
          </span>
          <span v-if="isNextRecommended" class="text-xs text-primary font-medium ml-2">
            · {{ t('cms.manage.nextRecommended') }}
          </span>
          <span v-if="lastUpdated" class="text-xs text-neutral-400 ml-2" :title="t('cms.manage.lastUpdated')">
            · {{ lastUpdated }}
          </span>
        </div>
      </div>

      <!-- Actions: wrap freely on narrow screens, right-aligned on desktop -->
      <div class="flex flex-wrap items-center gap-2 sm:shrink-0 sm:justify-end">
        <!-- Drafts: Approve button -->
        <UiButton
          v-if="!section || section === 'drafts'"
          variant="primary"
          size="sm"
          :icon="Check"
          :disabled="!canApprove"
          :loading="busy"
          :title="!canApprove && group.missingLangs.length ? t('cms.manage.cannotApproveIncomplete') : ''"
          @click="emit('approve', group)"
        >
          {{ t('cms.manage.approve') }}
        </UiButton>

        <!-- Ready: Publish + Unapprove buttons -->
        <template v-if="section === 'ready'">
          <UiButton
            variant="primary"
            size="sm"
            :icon="Send"
            :loading="busy"
            @click="emit('publish', group)"
          >
            {{ t('cms.manage.publish') }}
          </UiButton>
          <UiButton
            variant="ghost"
            size="sm"
            :icon="Undo2"
            :loading="busy"
            @click="emit('unapprove', group)"
          >
            {{ t('cms.manage.unapprove') }}
          </UiButton>
        </template>

        <!-- Delete (always available, confirms in parent) -->
        <UiButton
          variant="ghost"
          size="sm"
          :icon="Trash2"
          :disabled="busy"
          @click="emit('delete', group)"
        >
          {{ t('cms.deleteTopic') }}
        </UiButton>
      </div>
    </div>
  </div>
</template>
