<template>
  <Teleport to="body">
    <Transition name="update-card">
      <div
        v-if="show"
        class="fixed inset-x-0 z-[100] flex justify-center px-4 pointer-events-none"
        :style="{ bottom: 'calc(1rem + var(--nav-inset-bottom))' }"
      >
        <div class="relative w-full max-w-sm pointer-events-auto">
          <img
            src="/images/para/building.webp"
            alt=""
            aria-hidden="true"
            class="update-card-para absolute -top-[4.75rem] right-5 h-28 w-auto select-none pointer-events-none"
          />
          <div class="relative overflow-hidden rounded-2xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 shadow-xl">
            <div class="pointer-events-none absolute inset-x-0 top-0 h-16 bg-gradient-to-b from-secondary-50/70 to-transparent dark:from-secondary-900/25" />
            <div role="status" class="relative px-5 py-4">
              <p class="text-sm font-semibold text-neutral-900 dark:text-neutral-100">
                {{ title }}
              </p>
              <p class="mt-1 text-xs leading-relaxed text-neutral-500 dark:text-neutral-400">
                {{ description }}
              </p>
              <slot />
              <div class="mt-3.5 flex items-center gap-2">
                <UiButton v-if="actionLabel" variant="secondary" size="sm" :icon="icon" @click="emit('action')">
                  {{ actionLabel }}
                </UiButton>
                <UiButton :variant="actionLabel ? 'ghost' : 'secondary'" size="sm" @click="emit('dismiss')">
                  {{ dismissLabel || $t('update.later') }}
                </UiButton>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import type { Component } from 'vue'

// Without actionLabel the card is informational only (WhatsNewCard): the
// dismiss button takes over as the single, primary-styled action.
defineProps<{
  show: boolean
  title: string
  description: string
  actionLabel?: string
  dismissLabel?: string
  icon?: Component
}>()

const emit = defineEmits<{ action: []; dismiss: [] }>()
</script>

<style scoped>
.update-card-enter-active {
  transition: opacity 0.35s ease, transform 0.35s cubic-bezier(0.16, 1, 0.3, 1);
}
/* Para pops out from behind the card once it has landed */
.update-card-enter-active .update-card-para {
  transition: transform 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) 0.2s;
}
.update-card-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.update-card-enter-from,
.update-card-leave-to {
  opacity: 0;
  transform: translateY(1.25rem);
}
.update-card-enter-from .update-card-para {
  transform: translateY(6rem);
}

@media (prefers-reduced-motion: reduce) {
  .update-card-enter-active,
  .update-card-leave-active,
  .update-card-enter-active .update-card-para {
    transition: opacity 0.2s ease;
  }
  .update-card-enter-from,
  .update-card-leave-to,
  .update-card-enter-from .update-card-para {
    transform: none;
  }
}
</style>
