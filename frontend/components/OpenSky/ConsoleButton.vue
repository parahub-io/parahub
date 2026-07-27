<template>
  <!-- Utility action button in the recon-card dialect (mono, uppercase, h-8) —
       matches the card footer channels; danger switches to the error accent. -->
  <button
    class="h-8 min-w-0 inline-flex items-center justify-center gap-1.5 rounded-md border font-mono text-[10px] font-semibold uppercase tracking-wider transition-colors"
    :class="danger
      ? 'border-error/40 text-error hover:bg-error/10'
      : 'border-neutral-300 dark:border-neutral-700 text-neutral-800 dark:text-neutral-100 hover:bg-primary-100 dark:hover:bg-primary-900/40'"
  >
    <component :is="icon" v-if="icon" class="w-3.5 h-3.5 shrink-0" />
    <span class="truncate"><slot /></span>
  </button>
</template>

<script setup lang="ts">
import type { Component } from 'vue'

defineProps<{ icon?: Component; danger?: boolean }>()
</script>
