<template>
  <NuxtLink
    v-if="to"
    :to="to"
    class="flex flex-col items-center text-center gap-2 bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4 hover:border-primary transition-colors group"
  >
    <img :src="image" alt="" class="h-24 sm:h-28 w-auto object-contain" loading="lazy" />
    <span class="font-medium text-neutral-900 dark:text-neutral-100 flex items-center gap-1.5">
      {{ title }}
      <ExternalLink v-if="external" class="w-3.5 h-3.5 text-neutral-400" />
    </span>
    <span class="text-sm text-neutral-500 dark:text-neutral-400">{{ description }}</span>
  </NuxtLink>
  <button
    v-else
    type="button"
    class="flex flex-col items-center text-center gap-2 bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4 hover:border-primary transition-colors group"
    @click="$emit('select')"
  >
    <img :src="image" alt="" class="h-24 sm:h-28 w-auto object-contain" loading="lazy" />
    <span class="font-medium text-neutral-900 dark:text-neutral-100">{{ title }}</span>
    <span class="text-sm text-neutral-500 dark:text-neutral-400">{{ description }}</span>
  </button>
</template>

<script setup lang="ts">
import { ExternalLink } from 'lucide-vue-next'

defineProps<{
  image: string
  title: string
  description: string
  to?: string
  external?: boolean
}>()

defineEmits<{ (e: 'select'): void }>()
</script>
