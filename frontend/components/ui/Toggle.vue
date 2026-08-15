<template>
  <button
    type="button"
    role="switch"
    :aria-checked="modelValue === true"
    :aria-label="label"
    :disabled="disabled || loading || modelValue === null"
    class="relative w-10 h-6 rounded-full transition-colors shrink-0 disabled:opacity-50 disabled:cursor-not-allowed"
    :class="[
      modelValue ? 'bg-primary' : 'bg-neutral-300 dark:bg-neutral-600',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-primary',
    ]"
    @click="$emit('update:modelValue', !modelValue)"
  >
    <span
      class="absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform flex items-center justify-center"
      :class="modelValue ? 'translate-x-4' : 'translate-x-0'"
    >
      <Loader2 v-if="loading" class="w-3 h-3 animate-spin text-neutral-500" aria-hidden="true" />
    </span>
  </button>
</template>

<script setup lang="ts">
import { Loader2 } from 'lucide-vue-next'

interface Props {
  /** null = state not known yet (still loading from the device) — renders off and disabled */
  modelValue: boolean | null
  loading?: boolean
  disabled?: boolean
  label?: string
}

withDefaults(defineProps<Props>(), {
  loading: false,
  disabled: false,
})

defineEmits<{ (e: 'update:modelValue', value: boolean): void }>()
</script>
