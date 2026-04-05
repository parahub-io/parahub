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
          <h1 class="inline text-neutral-900 font-semibold text-lg sm:text-xl">{{ $t('about.condoSystem.title') }}</h1>
        </nav>
      </div>
    </div>

    <div class="max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-12 space-y-8">

      <!-- Intro -->
      <p class="prose-section">{{ $t('about.condoSystem.intro') }}</p>

      <!-- 4 concept cards -->
      <div class="grid sm:grid-cols-2 gap-4">
        <div v-for="concept in concepts" :key="concept" class="p-4 border border-neutral-200 dark:border-neutral-800 rounded-lg">
          <div class="font-semibold text-neutral-900 dark:text-white mb-1">{{ $t(`about.condoSystem.${concept}.title`) }}</div>
          <div class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t(`about.condoSystem.${concept}.text`) }}</div>
        </div>
      </div>

      <!-- Permilagem example -->
      <div class="p-4 bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg">
        <div class="flex items-center justify-center gap-3 text-sm font-mono text-neutral-700 dark:text-neutral-300 flex-wrap">
          <span class="px-2 py-1 bg-white dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-600 rounded">T3 — 200‰</span>
          <span class="px-2 py-1 bg-white dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-600 rounded">T2 — 150‰</span>
          <span class="px-2 py-1 bg-white dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-600 rounded">T1 — 100‰</span>
          <span class="px-2 py-1 bg-white dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-600 rounded">Garage — 50‰</span>
          <span class="text-neutral-400 ml-2">= 1000‰</span>
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
useHead({ title: computed(() => `${t('about.condoSystem.title')} — Parahub`) })
useSeoMeta({
  description: computed(() => t('docs.condo_desc')),
  ogTitle: computed(() => `${t('about.condoSystem.title')} — Parahub`),
  ogDescription: computed(() => t('docs.condo_desc')),
})
useDocsBreadcrumb(t('about.condoSystem.title'), '/docs/condo')

const concepts = ['permilagem', 'quotas', 'assembly', 'reuse']

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
