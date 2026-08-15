<template>
  <section class="card p-4">
    <!-- Wraps, and the text block asks for 16rem: on a phone the action drops to
         its own line instead of squeezing the help into a five-line column
         beside it. `basis` rather than `min-w` so a viewport narrower than that
         shrinks the block instead of overflowing the card. -->
    <div class="flex items-start gap-3 flex-wrap" :class="$slots.default ? 'mb-4' : ''">
      <component :is="icon" class="w-5 h-5 shrink-0 mt-0.5 text-secondary dark:text-secondary-400" aria-hidden="true" />
      <div class="grow shrink basis-64 min-w-0">
        <h2 class="text-base font-semibold text-neutral-900 dark:text-neutral-100">{{ title }}</h2>
        <!-- Every section states what it is for in plain words: this page is
             where a non-technical host learns what a control does. -->
        <p v-if="help" class="text-sm text-neutral-500 dark:text-neutral-400 mt-1">{{ help }}</p>
      </div>
      <div v-if="$slots.actions" class="shrink-0 ml-auto">
        <slot name="actions" />
      </div>
    </div>
    <slot />
  </section>
</template>

<script setup lang="ts">
import type { Component } from 'vue'

interface Props {
  title: string
  help?: string
  icon: Component
}

defineProps<Props>()
</script>
