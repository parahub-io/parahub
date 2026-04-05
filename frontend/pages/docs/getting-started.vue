<template>
  <div class="min-h-full bg-white dark:bg-neutral-950">
    <div class="docs-header border-b border-primary/40 dark:border-primary/30 py-6 sm:py-8">
      <div class="max-w-3xl mx-auto px-4 sm:px-6">
        <nav class="flex items-center gap-1.5 text-sm">
          <NuxtLink :to="localePath('/about')" class="text-neutral-900/60 hover:text-neutral-900 transition-colors">
            {{ $t('about.title') }}
          </NuxtLink>
          <ChevronRight class="w-3.5 h-3.5 text-neutral-900/30" />
          <NuxtLink :to="localePath('/docs')" class="text-neutral-900/60 hover:text-neutral-900 transition-colors">
            {{ $t('docs.title') }}
          </NuxtLink>
          <ChevronRight class="w-3.5 h-3.5 text-neutral-900/30" />
          <h1 class="inline text-neutral-900 font-semibold text-lg sm:text-xl">{{ $t('about.gettingStarted.title') }}</h1>
        </nav>
      </div>
    </div>

    <div class="max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-12 space-y-6">

      <p class="prose-section">{{ $t('about.gettingStarted.intro') }}</p>

      <ol class="space-y-4">
        <li v-for="i in 5" :key="i" class="flex gap-4">
          <span class="flex-shrink-0 w-7 h-7 rounded-full bg-yellow-400 text-neutral-900 text-sm font-bold flex items-center justify-center mt-0.5">{{ i }}</span>
          <div>
            <div class="font-semibold text-neutral-900 dark:text-white">{{ $t(`about.gettingStarted.step${i}.title`) }}</div>
            <div class="text-neutral-600 dark:text-neutral-400 text-sm mt-0.5">{{ $t(`about.gettingStarted.step${i}.text`) }}</div>
          </div>
        </li>
      </ol>

<DocsPrevNext />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ChevronRight } from 'lucide-vue-next'

const { t } = useI18n()
const localePath = useLocalePath()
useHead({ title: computed(() => `${t('about.gettingStarted.title')} — Parahub`) })
useSeoMeta({
  description: computed(() => t('docs.getting_started_desc')),
  ogTitle: computed(() => `${t('about.gettingStarted.title')} — Parahub`),
  ogDescription: computed(() => t('docs.getting_started_desc')),
})
useDocsBreadcrumb(t('about.gettingStarted.title'), '/docs/getting-started')

definePageMeta({ order: 2 })
</script>

<style scoped>
.docs-header {
  background-color: var(--color-primary);
}
.prose-section {
  @apply text-neutral-700 dark:text-neutral-300 leading-relaxed;
}
</style>
