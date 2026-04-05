<template>
  <nav class="grid gap-3 sm:gap-4 pt-8 mt-8 border-t border-neutral-200 dark:border-neutral-800" :class="prev && next ? 'sm:grid-cols-2' : ''">
    <NuxtLink
      v-if="prev"
      :to="localePath(prev.path)"
      class="card group flex items-center gap-3 px-4 py-3 sm:px-5 sm:py-4 hover:border-primary hover:bg-primary/15 dark:hover:bg-primary/10 transition-colors"
    >
      <ChevronLeft class="w-5 h-5 flex-shrink-0 text-neutral-400 group-hover:text-neutral-900 dark:group-hover:text-white group-hover:-translate-x-0.5 transition-all" />
      <div class="min-w-0">
        <div class="text-xs font-medium text-neutral-400 dark:text-neutral-500 uppercase tracking-wide">{{ $t('docs.prev') }}</div>
        <div class="text-sm font-semibold text-neutral-700 dark:text-neutral-200 group-hover:text-neutral-900 dark:group-hover:text-white transition-colors">{{ $t(prev.titleKey) }}</div>
      </div>
    </NuxtLink>

    <NuxtLink
      v-if="next"
      :to="localePath(next.path)"
      class="card group flex items-center gap-3 px-4 py-3 sm:px-5 sm:py-4 hover:border-primary hover:bg-primary/15 dark:hover:bg-primary/10 transition-colors"
      :class="prev ? 'justify-end text-right' : 'justify-end text-right sm:col-start-1'"
    >
      <div class="min-w-0">
        <div class="text-xs font-medium text-neutral-400 dark:text-neutral-500 uppercase tracking-wide">{{ $t('docs.next') }}</div>
        <div class="text-sm font-semibold text-neutral-700 dark:text-neutral-200 group-hover:text-neutral-900 dark:group-hover:text-white transition-colors">{{ $t(next.titleKey) }}</div>
      </div>
      <ChevronRight class="w-5 h-5 flex-shrink-0 text-neutral-400 group-hover:text-neutral-900 dark:group-hover:text-white group-hover:translate-x-0.5 transition-all" />
    </NuxtLink>
  </nav>
</template>

<script setup lang="ts">
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'

const { prev, next, localePath } = useDocNav()
</script>
