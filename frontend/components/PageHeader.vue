<script setup lang="ts">
import { Plus } from 'lucide-vue-next'

interface Props {
  title: string
  subtitle?: string
  createTo?: string
  createLabel?: string
}

defineProps<Props>()
const emit = defineEmits<{
  create: []
}>()
</script>

<template>
  <div class="flex items-center justify-between mb-6">
    <div :class="{ 'mr-4': createTo || createLabel }">
      <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100">
        {{ title }}
      </h1>
      <p v-if="subtitle" class="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
        {{ subtitle }}
      </p>
    </div>
    <UiButton
      v-if="createTo && createLabel"
      variant="primary"
      size="sm"
      :icon="Plus"
      :to="createTo"
      class="min-h-[44px] shrink-0"
    >
      {{ createLabel }}
    </UiButton>
    <UiButton
      v-else-if="createLabel"
      variant="primary"
      size="sm"
      :icon="Plus"
      class="min-h-[44px] shrink-0"
      @click="emit('create')"
    >
      {{ createLabel }}
    </UiButton>
  </div>
</template>
