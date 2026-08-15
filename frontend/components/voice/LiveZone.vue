<template>
  <!--
    One half of the live-translation screen. The guest's copy is rotated 180°:
    the phone lies flat between two people and each reads their own half the
    right way up. Both halves are this same component, so nothing can drift
    between the sides.
  -->
  <section class="live-zone" :class="{ 'live-zone-flipped': side === 'GUEST' }">
    <!-- Whose half this is, and which language it speaks -->
    <div class="flex items-center gap-2">
      <label :for="`live-lang-${side}`" class="text-xs text-neutral-500 dark:text-neutral-400">
        {{ label }}
      </label>
      <select
        :id="`live-lang-${side}`"
        :value="lang"
        class="form-input py-1 pl-2 pr-7 text-sm w-auto"
        @change="$emit('update:lang', ($event.target as HTMLSelectElement).value)"
      >
        <option v-for="code in LIVE_LANGUAGES" :key="code" :value="code">
          {{ $t(`voice_notes.live.languages.${code}`) }}
        </option>
      </select>
    </div>

    <!-- What this person reads, always in their own language -->
    <div class="live-text-box">
      <p v-if="text" class="live-text">{{ text }}</p>
      <p v-else class="live-placeholder">{{ $t('voice_notes.live.placeholder') }}</p>
    </div>

    <div class="flex items-center gap-2 w-full">
      <UiButton
        size="lg"
        class="flex-1 !whitespace-normal min-w-0 text-center"
        :data-testid="`live-talk-${side.toLowerCase()}`"
        :variant="recording ? 'error' : 'secondary'"
        :icon="recording ? Square : Mic"
        :disabled="disabled"
        :loading="busy"
        @click="$emit('toggle')"
      >
        {{ recording ? $t('voice_notes.live.stop') : $t('voice_notes.live.talk') }}
      </UiButton>

      <UiButton
        variant="ghost"
        size="lg"
        icon-only
        :icon="RotateCcw"
        :disabled="!canReplay"
        :aria-label="$t('voice_notes.live.replay')"
        @click="$emit('replay')"
      />
    </div>
  </section>
</template>

<script setup lang="ts">
import { Mic, RotateCcw, Square } from 'lucide-vue-next'
import { LIVE_LANGUAGES, type LiveSide } from '~/composables/useLiveTranslate'

defineProps<{
  side: LiveSide
  /** "You" / "Them" — which person is on this side of the table. */
  label: string
  lang: string
  text: string
  recording: boolean
  busy: boolean
  disabled: boolean
  canReplay: boolean
}>()

defineEmits<{
  (e: 'update:lang', value: string): void
  (e: 'toggle'): void
  (e: 'replay'): void
}>()
</script>

<style scoped>
.live-zone {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  padding: 0.75rem 0;
}

/* The guest reads from the other side of the table. */
.live-zone-flipped {
  transform: rotate(180deg);
}

.live-text-box {
  flex: 1;
  min-height: 0;
  width: 100%;
  overflow-y: auto;
  scrollbar-gutter: stable;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
}

.live-text {
  font-size: 1.375rem;
  line-height: 1.4;
  color: rgb(24 24 27);
}
:root.dark .live-text {
  color: rgb(244 244 245);
}

.live-placeholder {
  font-size: 0.875rem;
  color: rgb(161 161 170);
}
</style>
