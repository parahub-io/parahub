<template>
  <!-- Spec-sheet readout line: label, dotted leader, value — keeps the recon
       cards dense while staying scannable. Slot overrides the value (links). -->
  <div class="flex items-baseline font-mono min-w-0">
    <span class="shrink-0 text-[9px] uppercase tracking-[0.18em] text-neutral-400 dark:text-neutral-600">{{ label }}</span>
    <span class="flex-1 min-w-2 mx-1 border-b border-dotted border-neutral-300 dark:border-neutral-700" aria-hidden="true" />
    <span class="min-w-0 truncate text-[11px] tabular-nums text-neutral-800 dark:text-neutral-100">
      <slot>{{ display }}</slot>
    </span>
  </div>
</template>

<script setup lang="ts">
const props = defineProps<{ label: string; value?: string | number | null }>()

const display = computed(() =>
  props.value === null || props.value === undefined || props.value === '' ? '—' : props.value
)
</script>
