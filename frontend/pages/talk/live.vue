<template>
  <div class="live-page">
    <!-- Guest on top, upside down; the strip between them; the phone's owner below -->
    <VoiceLiveZone
      side="GUEST"
      :label="$t('voice_notes.live.them')"
      :lang="guestLang"
      :text="guestText"
      :recording="isRecordingSide('GUEST')"
      :busy="isBusySide('GUEST')"
      :disabled="isDisabled('GUEST')"
      :can-replay="canReplay"
      @update:lang="guestLang = $event"
      @toggle="toggle('GUEST')"
      @replay="replay"
    />

    <!-- The strip between them: state the phone's owner reads -->
    <div class="live-divider">
      <UiAlert v-if="error" variant="error" dismissible class="w-full" @dismiss="error = ''">
        {{ error }}
      </UiAlert>

      <UiAlert v-else-if="sameLanguage" variant="warning" class="w-full">
        {{ $t('voice_notes.errors.same_language') }}
      </UiAlert>

      <UiAlert v-else-if="needsInteraction" variant="info" class="w-full">
        {{ $t('voice_notes.autoplay_blocked') }}
      </UiAlert>

      <template v-else>
        <NuxtLink
          :to="localePath('/talk')"
          class="text-neutral-500 dark:text-neutral-400 hover:text-secondary dark:hover:text-secondary-400 flex-shrink-0"
          :aria-label="$t('common.back')"
        >
          <ArrowLeft :size="18" />
        </NuxtLink>

        <p v-if="isProcessing" class="text-sm text-neutral-500 dark:text-neutral-400" role="status">
          {{ $t(`voice_notes.status.${status}`) }}
        </p>
        <p
          v-else-if="isRecording"
          class="text-sm tabular-nums"
          :class="countdown ? 'text-error font-semibold' : 'text-neutral-500 dark:text-neutral-400'"
        >
          {{ countdown ? $t('voice_notes.countdown', { n: countdown }) : formatSeconds(elapsedMs / 1000) }}
        </p>
        <p v-else class="text-xs text-neutral-400 dark:text-neutral-500 text-center">
          <template v-if="quotaExhausted">{{ $t('voice_notes.quota_spent') }}</template>
          <template v-else-if="quota && !quota.unlimited">
            {{ $t('voice_notes.quota_line', { used: usedMinutes, limit: limitMinutes }) }}
          </template>
          <template v-else>{{ $t('voice_notes.live.hint') }}</template>
        </p>

        <!-- AI Act transparency: every clip this page plays is synthesised -->
        <UiBadge v-if="lastTurn" variant="neutral" type="soft" size="sm">
          <Sparkles :size="12" class="mr-1" />
          {{ lastTurn.cloned_voice
            ? $t('voice_notes.live.synthetic_cloned')
            : $t('voice_notes.synthetic') }}
        </UiBadge>
      </template>
    </div>

    <VoiceLiveZone
      side="HOST"
      :label="$t('voice_notes.live.you')"
      :lang="hostLang"
      :text="hostText"
      :recording="isRecordingSide('HOST')"
      :busy="isBusySide('HOST')"
      :disabled="isDisabled('HOST')"
      :can-replay="canReplay"
      @update:lang="hostLang = $event"
      @toggle="toggle('HOST')"
      @replay="replay"
    />
  </div>
</template>

<script setup lang="ts">
import { ArrowLeft, Sparkles } from 'lucide-vue-next'
import type { LiveSide } from '~/composables/useLiveTranslate'

definePageMeta({ middleware: 'auth', layout: 'default' })

const { t } = useI18n()
const localePath = useLocalePath()

useSeoMeta({ title: `${t('voice_notes.live.title')} — Parahub`, robots: 'noindex' })

const {
  isReady, isProcessing, status, error, quota, quotaExhausted, canRecord,
  isRecording, elapsedMs, countdown, needsInteraction, activeSide,
  hostLang, guestLang, hostText, guestText, lastTurn, sameLanguage, canReplay,
  connect, disconnect, speak, stop, replay, stopPlayback,
} = useLiveTranslate()

const usedMinutes = computed(() => Math.round((quota.value?.used_seconds || 0) / 6) / 10)
const limitMinutes = computed(() => Math.round((quota.value?.limit_seconds || 0) / 60))

const isRecordingSide = (side: LiveSide) => isRecording.value && activeSide.value === side
const isBusySide = (side: LiveSide) => isProcessing.value && activeSide.value === side

// One microphone, one speaker: the other half's turn locks this one.
const isDisabled = (side: LiveSide) =>
  !isRecordingSide(side) && (!canRecord.value || isRecording.value)

function toggle(side: LiveSide) {
  if (isRecordingSide(side)) stop()
  else void speak(side)
}

function formatSeconds(seconds: number): string {
  const total = Math.max(0, Math.round(seconds))
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}

onMounted(() => { void connect() })

// Kept-alive: leaving this page hands back the microphone and the socket, and
// returning to it must find a live one. Setup here is not async, so
// `onActivated` also fires once right after mount — hence the guard.
let firstActivation = true
onActivated(() => {
  if (firstActivation) { firstActivation = false; return }
  void connect()
})
onDeactivated(() => {
  stopPlayback()
  disconnect()
})

// A reconnect that succeeded clears the "connection lost" line it left behind.
watch(isReady, (ready) => { if (ready) error.value = '' })
</script>

<style scoped>
/* Fills the band between the chrome bars, wherever the nav bar is docked. */
.live-page {
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

.live-divider {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  min-height: 3rem;
  padding: 0.5rem 0;
  border-top: 1px solid rgb(212 212 216 / 0.6);
  border-bottom: 1px solid rgb(212 212 216 / 0.6);
}
:root.dark .live-divider {
  border-color: rgb(82 82 91 / 0.6);
}
</style>
