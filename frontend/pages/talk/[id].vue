<template>
  <div class="talk-page">
    <!-- Who you are talking to, and in which direction the languages run -->
    <header class="talk-header">
      <NuxtLink
        :to="localePath('/talk')"
        class="text-neutral-500 dark:text-neutral-400 hover:text-secondary dark:hover:text-secondary-400 flex-shrink-0"
        :aria-label="$t('common.back')"
      >
        <ArrowLeft :size="20" />
      </NuxtLink>

      <NuxtLink :to="localePath(`/@${counterpart?.local_name}`)" class="flex items-center gap-2 min-w-0 flex-1">
        <img
          v-if="counterpart?.avatar_url"
          :src="counterpart.avatar_url"
          :alt="counterpart.display_name"
          class="w-8 h-8 rounded-full object-cover flex-shrink-0"
        >
        <div class="min-w-0">
          <p class="font-medium text-neutral-900 dark:text-neutral-100 truncate leading-tight">
            {{ counterpart?.display_name }}
          </p>
          <p
            v-if="myLanguage"
            class="text-xs text-neutral-500 dark:text-neutral-400 font-mono uppercase tracking-wider"
          >
            {{ myLanguage }} → {{ counterpart?.language || 'en' }}
          </p>
        </div>
      </NuxtLink>

      <button
        type="button"
        class="flex items-center gap-1 text-xs px-2 py-1 rounded-lg border flex-shrink-0 transition-colors"
        :class="autoplay
          ? 'bg-primary text-neutral-900 border-primary'
          : 'border-neutral-300 dark:border-neutral-600 text-neutral-500 dark:text-neutral-400 hover:bg-primary-100 dark:hover:bg-primary-900/40'"
        :aria-pressed="autoplay"
        @click="autoplay = !autoplay"
      >
        <Volume2 v-if="autoplay" :size="14" />
        <VolumeX v-else :size="14" />
        <span class="hidden sm:inline">{{ $t('voice_notes.autoplay') }}</span>
      </button>
    </header>

    <!-- The conversation -->
    <div ref="scrollRef" class="talk-stream">
      <div v-if="notes.length === 0" class="py-12 text-center">
        <img src="/images/para/pointing.webp" alt="Para" class="mx-auto h-28 w-auto mb-3">
        <h3 class="text-base font-medium text-neutral-900 dark:text-neutral-100 mb-1">
          {{ $t('voice_notes.thread_empty_title') }}
        </h3>
        <p class="text-sm text-neutral-500 dark:text-neutral-400">
          {{ $t('voice_notes.thread_empty_subtitle', { name: counterpart?.display_name }) }}
        </p>
      </div>

      <article
        v-for="note in notes"
        :key="note.id"
        class="talk-note"
        :class="note.direction"
      >
        <div
          class="talk-bubble border rounded-xl px-3 py-2.5"
          :class="note.direction === 'out'
            ? 'border-primary'
            : 'border-neutral-200 dark:border-neutral-700'"
        >
          <p class="text-[0.9375rem] leading-relaxed text-neutral-900 dark:text-neutral-100">
            {{ primaryText(note) }}
          </p>
          <p
            v-if="secondaryText(note) && secondaryText(note) !== primaryText(note)"
            class="mt-1 text-xs text-neutral-500 dark:text-neutral-400 italic"
          >
            {{ secondaryText(note) }}
          </p>

          <div class="mt-2 flex items-center gap-2 flex-wrap">
            <UiButton
              v-if="note.has_audio"
              variant="ghost"
              size="sm"
              :icon="playingNoteId === note.id ? Square : Play"
              @click="togglePlay(note)"
            >
              {{ formatSeconds(note.audio_seconds) }}
            </UiButton>
            <span v-else class="text-xs text-neutral-400 dark:text-neutral-500">
              {{ $t('voice_notes.audio_expired') }}
            </span>

            <!-- AI Act transparency: synthesised speech says so, every time -->
            <UiBadge variant="neutral" type="soft" size="sm">
              <Sparkles :size="12" class="mr-1" />
              {{ note.cloned_voice
                ? $t('voice_notes.synthetic_cloned', { name: senderName(note) })
                : $t('voice_notes.synthetic') }}
            </UiBadge>

            <span class="text-xs text-neutral-400 dark:text-neutral-500 tabular-nums ml-auto">
              {{ shortTime(note.created_at) }}
            </span>
          </div>
        </div>
      </article>
    </div>

    <!-- Recorder -->
    <div class="talk-controls">
      <UiAlert v-if="error" variant="error" dismissible class="mb-2" @dismiss="error = ''">
        {{ error }}
      </UiAlert>

      <UiAlert v-else-if="needsInteraction" variant="info" class="mb-2">
        {{ $t('voice_notes.autoplay_blocked') }}
      </UiAlert>

      <div
        v-else-if="isProcessing"
        class="mb-2 text-center text-sm text-neutral-500 dark:text-neutral-400"
        role="status"
      >
        {{ $t(`voice_notes.status.${status}`) }}
      </div>

      <div
        v-else-if="isRecording"
        class="mb-2 text-center text-sm tabular-nums"
        :class="countdown ? 'text-error font-semibold' : 'text-neutral-500 dark:text-neutral-400'"
      >
        {{ countdown ? $t('voice_notes.countdown', { n: countdown }) : formatSeconds(elapsedMs / 1000) }}
      </div>

      <UiButton
        data-testid="talk-button"
        size="lg"
        class="w-full"
        :variant="isRecording ? 'error' : 'secondary'"
        :icon="isRecording ? Square : Mic"
        :disabled="!canRecord && !isRecording"
        :loading="isProcessing"
        @click="toggleRecording"
      >
        {{ isRecording ? $t('voice_notes.stop') : $t('voice_notes.talk') }}
      </UiButton>

      <p class="mt-2 text-center text-xs text-neutral-400 dark:text-neutral-500">
        <template v-if="quotaExhausted">{{ $t('voice_notes.quota_spent') }}</template>
        <template v-else-if="quota && !quota.unlimited">
          {{ $t('voice_notes.quota_line', { used: usedMinutes, limit: limitMinutes }) }}
        </template>
        <template v-else>{{ $t('voice_notes.hint') }}</template>
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ArrowLeft, Mic, Play, Sparkles, Square, Volume2, VolumeX } from 'lucide-vue-next'
import type { VoiceNote, VoiceQuota } from '~/composables/useVoiceNotes'

definePageMeta({ middleware: 'auth', layout: 'default' })

const route = useRoute()
const { t, locale } = useI18n()
const localePath = useLocalePath()
const authStore = useAuthStore()

const reference = computed(() => String(route.params.id))
const notes = ref<VoiceNote[]>([])
const counterpart = ref<{
  id: string; local_name: string; display_name: string
  avatar_url: string | null; language: string
} | null>(null)
const scrollRef = ref<HTMLElement | null>(null)
const autoplay = useLocalPref('voice_notes_autoplay', true)

useSeoMeta({ title: `${t('voice_notes.title')} — Parahub`, robots: 'noindex' })

const {
  isRecording, isProcessing, status, error, quota, myLanguage, quotaExhausted,
  canRecord, elapsedMs, countdown, needsInteraction, playingNoteId,
  connect, disconnect, startRecording, stopRecording, play, stopPlayback, markPlayed,
} = useVoiceNotes({ onNote: appendNote })

// One decimal: a conversation is minutes long, and a whole-number readout
// sits at "0 of 30" through the first half hour of use.
const usedMinutes = computed(() => Math.round((quota.value?.used_seconds || 0) / 6) / 10)
const limitMinutes = computed(() => Math.round((quota.value?.limit_seconds || 0) / 60))

function primaryText(note: VoiceNote): string {
  // You read what you said; they read what you meant them to hear.
  return note.direction === 'in' ? note.target_text : note.source_text
}

function secondaryText(note: VoiceNote): string {
  return note.direction === 'in' ? note.source_text : note.target_text
}

function senderName(note: VoiceNote): string {
  return note.direction === 'in'
    ? (counterpart.value?.display_name || '')
    : (authStore.activeProfile?.display_name || authStore.user?.username || '')
}

function formatSeconds(seconds: number): string {
  const total = Math.max(0, Math.round(seconds))
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}

function shortTime(iso: string | null): string {
  if (!iso) return ''
  const date = new Date(iso)
  const sameDay = new Date().toDateString() === date.toDateString()
  return sameDay
    ? date.toLocaleTimeString(locale.value, { hour: '2-digit', minute: '2-digit' })
    : date.toLocaleDateString(locale.value, { day: 'numeric', month: 'short' })
}

async function loadThread() {
  await authStore.ensureToken()
  const data = await $fetch<{ profile: any; items: VoiceNote[]; quota: VoiceQuota }>(
    `/api/v1/voice/threads/${reference.value}`,
    { credentials: 'include', headers: { Authorization: `Bearer ${authStore.token}` } },
  )
  counterpart.value = data.profile
  notes.value = data.items
  quota.value = data.quota
  scrollToEnd()
}

function appendNote(note: VoiceNote) {
  if (notes.value.some(n => n.id === note.id)) return
  notes.value.push(note)
  scrollToEnd()
  if (note.direction === 'in' && autoplay.value && note.has_audio) {
    void play(note.id)
    void markPlayed(note.id)
  }
}

function scrollToEnd() {
  nextTick(() => {
    if (scrollRef.value) scrollRef.value.scrollTop = scrollRef.value.scrollHeight
  })
}

function toggleRecording() {
  if (isRecording.value) stopRecording()
  else void startRecording()
}

function togglePlay(note: VoiceNote) {
  if (playingNoteId.value === note.id) {
    stopPlayback()
    return
  }
  void play(note.id)
  if (note.direction === 'in' && !note.played_at) {
    note.played_at = new Date().toISOString()
    void markPlayed(note.id)
  }
}

// A note from the other side arrives on the account's own channel.
const realtime = useRealtimeStore()
function onIncoming(payload: any) {
  const note = payload?.note as VoiceNote | undefined
  if (!note || note.sender_id !== counterpart.value?.id) return
  appendNote(note)
}

async function openThread() {
  await loadThread()
  await connect(reference.value)
}

onMounted(async () => {
  realtime.on('voice_note.new', onIncoming)
  await openThread()
})

// /talk/alice → /talk/bob reuses this component (same route, different param),
// so nothing remounts and the old conversation would stay on screen.
watch(reference, () => {
  stopPlayback()
  notes.value = []
  void openThread()
})

// Kept-alive: this page is cached, so returning to it neither remounts nor
// refetches, and its socket would otherwise stay open behind whatever the user
// is looking at instead. Setup here is not async, so `onActivated` also fires
// once right after mount — hence the guard.
let firstActivation = true
onActivated(() => {
  if (firstActivation) { firstActivation = false; return }
  void openThread()
})

onDeactivated(() => {
  stopPlayback()
  disconnect()
})

onUnmounted(() => {
  realtime.off('voice_note.new', onIncoming)
})
</script>

<style scoped>
/* Fills the band between the chrome bars, wherever the nav bar is docked. */
.talk-page {
  position: fixed;
  top: var(--nav-inset-top);
  bottom: var(--nav-inset-bottom);
  left: 0;
  right: 0;
  display: flex;
  flex-direction: column;
  max-width: 42rem;
  margin: 0 auto;
  padding: 0 1rem;
  overflow: hidden;
}

.talk-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 0;
  border-bottom: 1px solid rgb(212 212 216 / 0.6);
  flex-shrink: 0;
}
:root.dark .talk-header {
  border-color: rgb(82 82 91 / 0.6);
}

.talk-stream {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  scrollbar-gutter: stable;
  padding: 1rem 0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.talk-note {
  display: flex;
}
.talk-note.out {
  justify-content: flex-end;
}

.talk-bubble {
  max-width: 85%;
}

.talk-controls {
  padding: 0.75rem 0 1rem;
  flex-shrink: 0;
}
</style>
