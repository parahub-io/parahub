<template>
  <div class="docs-header border-b border-primary/40 dark:border-primary/30 py-6 sm:py-8">
    <div class="max-w-3xl mx-auto px-4 sm:px-6">
      <nav class="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-sm text-neutral-900/60" aria-label="Breadcrumb">
        <NuxtLink :to="localePath('/about')" class="whitespace-nowrap hover:text-neutral-900 transition-colors">
          {{ $t('about.title') }}
        </NuxtLink>
        <template v-if="!root">
          <ChevronRight class="w-3.5 h-3.5 flex-shrink-0 text-neutral-900/30" />
          <NuxtLink :to="localePath('/docs')" class="whitespace-nowrap hover:text-neutral-900 transition-colors">
            {{ $t('docs.title') }}
          </NuxtLink>
        </template>
      </nav>
      <h1 class="mt-1.5 text-neutral-900 font-semibold text-xl sm:text-2xl leading-tight text-balance">{{ title }}</h1>
      <p v-if="subtitle" class="mt-2 text-sm text-neutral-900/60">{{ subtitle }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ChevronRight } from 'lucide-vue-next'

defineProps<{
  title: string
  subtitle?: string
  /** Docs index itself — drops the trailing "Docs" crumb. */
  root?: boolean
}>()

const localePath = useLocalePath()
</script>

<style scoped>
.docs-header {
  background-color: var(--color-primary);
}
</style>
