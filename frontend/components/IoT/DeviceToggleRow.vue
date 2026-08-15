<template>
  <div class="p-3 rounded-lg border border-neutral-200 dark:border-neutral-700">
    <div class="flex items-start justify-between gap-3">
      <div class="min-w-0">
        <div class="font-medium text-sm text-neutral-900 dark:text-neutral-100">{{ label }}</div>
        <div class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">{{ description }}</div>
      </div>
      <UiToggle
        :model-value="modelValue"
        :loading="busy"
        :disabled="disabled"
        :label="label"
        @update:model-value="$emit('toggle', $event)"
      />
    </div>

    <div v-if="busy" class="text-xs text-neutral-500 dark:text-neutral-400 mt-2">
      {{ $t('mesh.toggling') }}
    </div>
    <div
      v-else-if="modelValue !== null"
      class="text-xs mt-2"
      :class="modelValue ? 'text-success dark:text-success-400' : 'text-neutral-500 dark:text-neutral-400'"
    >
      {{ modelValue ? onText : offText }}
    </div>
    <div v-if="error" class="text-xs text-error dark:text-error-400 mt-2">{{ error }}</div>
  </div>
</template>

<script setup lang="ts">
interface Props {
  label: string
  description: string
  /** null while the state is still being read from the device */
  modelValue: boolean | null
  onText: string
  offText: string
  busy?: boolean
  disabled?: boolean
  error?: string | null
}

withDefaults(defineProps<Props>(), {
  busy: false,
  disabled: false,
  error: null,
})

defineEmits<{ (e: 'toggle', value: boolean): void }>()
</script>
