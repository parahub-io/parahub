<template>
  <div>
    <div class="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
      <PageHeader :title="$t('voice_notes.title')" :subtitle="$t('voice_notes.subtitle')" />

      <!-- What is left of this month's allowance -->
      <div
        v-if="quota && !quota.unlimited"
        class="flex items-center gap-2 mb-4 text-xs text-neutral-500 dark:text-neutral-400"
      >
        <Gauge :size="14" />
        <span>{{ $t('voice_notes.quota_line', { used: usedMinutes, limit: limitMinutes }) }}</span>
      </div>

      <!--
        The other half of the feature, and the one that needs no second account:
        one phone on the table between two people. It leads the page because it
        is what a member can use with the person in front of them right now.
      -->
      <NuxtLink
        :to="localePath('/talk/live')"
        class="card p-4 mb-6 flex items-center gap-3 hover:border-primary transition-colors"
      >
        <div class="w-10 h-10 rounded-full bg-secondary-100 dark:bg-secondary-900/40 flex items-center justify-center flex-shrink-0">
          <Languages :size="20" class="text-secondary dark:text-secondary-400" />
        </div>
        <div class="min-w-0">
          <p class="font-medium text-neutral-900 dark:text-neutral-100">
            {{ $t('voice_notes.live.title') }}
          </p>
          <p class="text-sm text-neutral-500 dark:text-neutral-400">
            {{ $t('voice_notes.live.subtitle') }}
          </p>
        </div>
        <ChevronRight :size="18" class="ml-auto flex-shrink-0 text-neutral-400 dark:text-neutral-500" />
      </NuxtLink>

      <div v-if="isInitial" class="py-12 text-center" role="status">
        <div class="mx-auto h-12 w-12 animate-spin rounded-full border-4 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100" />
        <span class="sr-only">{{ $t('common.loading') }}</span>
      </div>

      <div v-else-if="threads.length === 0" class="py-12 text-center">
        <img src="/images/para/welcome.webp" alt="Para" class="mx-auto h-32 w-auto mb-3">
        <h3 class="text-lg font-medium text-neutral-900 dark:text-neutral-100 mb-2">
          {{ $t('voice_notes.empty_title') }}
        </h3>
        <p class="text-neutral-500 dark:text-neutral-400 mb-6 max-w-md mx-auto">
          {{ $t('voice_notes.empty_subtitle') }}
        </p>
        <UiButton variant="outline" :icon="Users" :to="localePath('/directory')">
          {{ $t('voice_notes.empty_cta') }}
        </UiButton>
      </div>

      <div
        v-else
        class="border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700"
        :class="{ 'opacity-60 transition-opacity': refreshing }"
      >
        <NuxtLink
          v-for="thread in threads"
          :key="thread.profile.id"
          :to="localePath(`/talk/${thread.profile.local_name || thread.profile.id}`)"
          class="flex items-center gap-3 p-3 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors"
        >
          <img
            v-if="thread.profile.avatar_url"
            :src="thread.profile.avatar_url"
            :alt="thread.profile.display_name"
            class="w-10 h-10 rounded-full object-cover flex-shrink-0"
          >
          <div
            v-else
            class="w-10 h-10 rounded-full bg-neutral-200 dark:bg-neutral-700 flex items-center justify-center flex-shrink-0"
          >
            <Mic :size="18" class="text-neutral-500 dark:text-neutral-400" />
          </div>

          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2">
              <span class="font-medium text-neutral-900 dark:text-neutral-100 truncate">
                {{ thread.profile.display_name }}
              </span>
              <UiBadge v-if="thread.unplayed" variant="error" type="solid" size="sm">
                {{ thread.unplayed }}
              </UiBadge>
            </div>
            <p class="text-sm text-neutral-500 dark:text-neutral-400 truncate">
              <span v-if="thread.last_note.direction === 'out'" class="text-neutral-400 dark:text-neutral-500">
                {{ $t('voice_notes.you_prefix') }}
              </span>
              {{ preview(thread.last_note) }}
            </p>
          </div>

          <span class="text-xs text-neutral-400 dark:text-neutral-500 flex-shrink-0 tabular-nums">
            {{ shortTime(thread.last_note.created_at) }}
          </span>
        </NuxtLink>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ChevronRight, Gauge, Languages, Mic, Users } from 'lucide-vue-next'
import type { VoiceNote, VoiceQuota } from '~/composables/useVoiceNotes'

definePageMeta({ middleware: 'auth' })

const { t, locale } = useI18n()
const localePath = useLocalePath()

useSeoMeta({
  title: `${t('voice_notes.title')} — Parahub`,
  description: t('voice_notes.subtitle'),
  robots: 'noindex',
})

interface Thread {
  profile: {
    id: string
    local_name: string
    display_name: string
    avatar_url: string | null
    language: string
  }
  last_note: VoiceNote
  unplayed: number
}

const threadsData = useListData<{ items: Thread[]; count: number; quota: VoiceQuota }>(
  '/api/v1/voice/threads',
  {
    auth: true,
    default: () => ({ items: [], count: 0, quota: null as any }),
    // Notes arrive over the WS while this page is not mounted, so a cache hit
    // renders instantly and is then refreshed behind it.
    revalidate: true,
  },
)

const threads = computed(() => threadsData.data.value?.items || [])
const quota = computed(() => threadsData.data.value?.quota || null)
const isInitial = threadsData.isInitial
const refreshing = threadsData.refreshing

// One decimal: a conversation is minutes long, and a whole-number readout
// sits at "0 of 30" through the first half hour of use.
const usedMinutes = computed(() => Math.round((quota.value?.used_seconds || 0) / 6) / 10)
const limitMinutes = computed(() => Math.round((quota.value?.limit_seconds || 0) / 60))

function preview(note: VoiceNote): string {
  // Outgoing shows what you said; incoming shows what you were meant to hear.
  return note.direction === 'out' ? note.source_text : note.target_text
}

function shortTime(iso: string | null): string {
  if (!iso) return ''
  const date = new Date(iso)
  const sameDay = new Date().toDateString() === date.toDateString()
  return sameDay
    ? date.toLocaleTimeString(locale.value, { hour: '2-digit', minute: '2-digit' })
    : date.toLocaleDateString(locale.value, { day: 'numeric', month: 'short' })
}

// A note that lands while the list is open belongs at the top of it.
const realtime = useRealtimeStore()
function onIncoming() { threadsData.refresh() }
onMounted(() => realtime.on('voice_note.new', onIncoming))
onUnmounted(() => realtime.off('voice_note.new', onIncoming))

// Notes get played (and threads created) on the thread page, so a kept-alive
// list is stale on re-entry. No first-activation guard: this setup is async, so
// `onActivated` never fires on the initial mount — the guard would swallow the
// first real re-entry instead.
onActivated(() => { threadsData.refresh() })

// Last statement on purpose: awaiting here makes setup async, so Suspense holds
// the previous page until the list is ready instead of flashing a skeleton.
await threadsData
</script>
