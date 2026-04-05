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
          <h1 class="inline text-neutral-900 font-semibold text-lg sm:text-xl">{{ $t('about.toc.mission') }}</h1>
        </nav>
      </div>
    </div>

    <div class="max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-12">
      <div class="prose-section">
        <p>{{ $t('about.mission.intro') }}</p>

        <div class="grid sm:grid-cols-2 gap-4 mt-6">
          <div class="border-l-4 border-red-400 dark:border-red-600 pl-4 py-1">
            <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 text-sm mb-1">{{ $t('about.problem.title') }}</h3>
            <p class="text-sm">{{ $t('about.problem.text') }}</p>
          </div>
          <div class="border-l-4 border-green-400 dark:border-green-600 pl-4 py-1">
            <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 text-sm mb-1">{{ $t('about.solution.title') }}</h3>
            <p class="text-sm">{{ $t('about.solution.text') }}</p>
          </div>
        </div>

        <blockquote class="mt-6 border-l-4 border-neutral-400 dark:border-neutral-500 pl-4 py-2 bg-neutral-50 dark:bg-neutral-900 rounded-r space-y-2 text-neutral-700 dark:text-neutral-300">
          <p class="font-medium">{{ $t('about.mission.manifesto.line1') }}</p>
          <p>{{ $t('about.mission.manifesto.line2') }}</p>
          <p class="italic">{{ $t('about.mission.manifesto.line3') }}</p>
        </blockquote>

        <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mt-10 mb-4">{{ $t('about.values.title') }}</h2>
        <div class="space-y-4">
          <div v-for="i in 7" :key="i" class="flex gap-3">
            <span class="font-mono text-neutral-400 flex-shrink-0 w-6 text-right">{{ i }}.</span>
            <div>
              <span class="font-medium text-neutral-900 dark:text-neutral-100">{{ $t(`manifest.principles.${i}.name`) }}</span>
              <span class="text-neutral-500 dark:text-neutral-400"> &mdash; </span>
              <span class="text-neutral-700 dark:text-neutral-300">{{ $t(`manifest.principles.${i}.text`) }}</span>
            </div>
          </div>
        </div>
      </div>
      <DocsPrevNext />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ChevronRight } from 'lucide-vue-next'

const { t } = useI18n()
const localePath = useLocalePath()
useHead({ title: computed(() => `${t('about.toc.mission')} — Parahub`) })
useSeoMeta({
  description: computed(() => t('docs.mission_desc')),
  ogTitle: computed(() => `${t('about.toc.mission')} — Parahub`),
  ogDescription: computed(() => t('docs.mission_desc')),
})
useDocsBreadcrumb(t('about.toc.mission'), '/docs/mission')

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
