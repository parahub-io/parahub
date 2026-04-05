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
          <h1 class="inline text-neutral-900 font-semibold text-lg sm:text-xl">{{ $t('about.governanceSystem.title') }}</h1>
        </nav>
      </div>
    </div>

    <div class="max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-12 space-y-8">

      <!-- Intro -->
      <p class="prose-section">{{ $t('about.governanceSystem.intro') }}</p>

      <!-- 4 concept cards -->
      <div class="grid sm:grid-cols-2 gap-4">
        <div v-for="concept in concepts" :key="concept" class="p-4 border border-neutral-200 dark:border-neutral-800 rounded-lg">
          <div class="font-semibold text-neutral-900 dark:text-white mb-1">{{ $t(`about.governanceSystem.${concept}.title`) }}</div>
          <div class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t(`about.governanceSystem.${concept}.text`) }}</div>
        </div>
      </div>

      <!-- Transitivity example -->
      <div class="p-4 bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg">
        <div class="flex items-center justify-center gap-2 text-sm font-mono text-neutral-700 dark:text-neutral-300 flex-wrap">
          <span class="px-2 py-1 bg-white dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-600 rounded">{{ $t('about.governanceSystem.example.alice') }}</span>
          <span class="text-neutral-400">→</span>
          <span class="px-2 py-1 bg-white dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-600 rounded">{{ $t('about.governanceSystem.example.bob') }}</span>
          <span class="text-neutral-400">→</span>
          <span class="px-2 py-1 bg-yellow-400 text-neutral-900 border border-primary/60 rounded font-bold">{{ $t('about.governanceSystem.example.carol') }} ✓</span>
          <span class="text-neutral-500 ml-2">{{ $t('about.governanceSystem.example.votes') }}</span>
        </div>
      </div>

      <!-- Audit -->
      <div class="p-4 bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg">
        <div class="font-semibold text-neutral-900 dark:text-white mb-1">{{ $t('about.governanceSystem.audit.title') }}</div>
        <p class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t('about.governanceSystem.audit.text') }}</p>
      </div>

      <!-- Contexts -->
      <div>
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-3">{{ $t('about.governanceSystem.contexts.title') }}</h3>
        <ul class="space-y-2">
          <li v-for="ctx in ['community', 'establishment', 'adhoc']" :key="ctx" class="flex items-start gap-2 text-neutral-700 dark:text-neutral-300 text-sm">
            <span class="w-1.5 h-1.5 rounded-full bg-yellow-400 flex-shrink-0 mt-1.5" />
            {{ $t(`about.governanceSystem.contexts.${ctx}`) }}
          </li>
        </ul>
      </div>

      <DocsPrevNext />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ChevronRight } from 'lucide-vue-next'

const { t } = useI18n()
const localePath = useLocalePath()
useHead({ title: computed(() => `${t('about.governanceSystem.title')} — Parahub`) })
useSeoMeta({
  description: computed(() => t('docs.governance_desc')),
  ogTitle: computed(() => `${t('about.governanceSystem.title')} — Parahub`),
  ogDescription: computed(() => t('docs.governance_desc')),
})
useDocsBreadcrumb(t('about.governanceSystem.title'), '/docs/governance')

const concepts = ['direct', 'delegate', 'transitive', 'revoke']

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
