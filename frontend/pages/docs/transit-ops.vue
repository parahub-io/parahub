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
          <h1 class="inline text-neutral-900 font-semibold text-lg sm:text-xl">{{ $t('about.transitOps.title') }}</h1>
        </nav>
      </div>
    </div>

    <div class="max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-12 space-y-8">

      <p class="prose-section">{{ $t('about.transitOps.intro') }}</p>

      <!-- Capabilities -->
      <div class="grid sm:grid-cols-2 gap-4">
        <div v-for="cap in capabilities" :key="cap" class="p-4 border border-neutral-200 dark:border-neutral-800 rounded-lg">
          <div class="font-semibold text-neutral-900 dark:text-white mb-1">{{ $t(`about.transitOps.${cap}.title`) }}</div>
          <div class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t(`about.transitOps.${cap}.text`) }}</div>
        </div>
      </div>

      <!-- Getting started steps -->
      <div>
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-3">{{ $t('about.transitOps.gettingStarted.title') }}</h3>
        <ol class="space-y-2 text-neutral-700 dark:text-neutral-300">
          <li v-for="i in 5" :key="i" class="flex gap-3">
            <span class="flex-shrink-0 w-5 h-5 rounded-full bg-primary text-neutral-900 text-xs font-bold flex items-center justify-center mt-0.5">{{ i }}</span>
            <span>{{ $t(`about.transitOps.gettingStarted.step${i}`) }}</span>
          </li>
        </ol>
      </div>

      <!-- GTFS export note -->
      <div class="p-4 bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg">
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-2">{{ $t('about.transitOps.gtfsExport.title') }}</h3>
        <p class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t('about.transitOps.gtfsExport.text') }}</p>
      </div>

      <DocsPrevNext />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ChevronRight } from 'lucide-vue-next'

const { t } = useI18n()
const localePath = useLocalePath()
useHead({ title: computed(() => `${t('about.transitOps.title')} — Parahub`) })
useSeoMeta({
  description: computed(() => t('docs.transit_ops_desc')),
  ogTitle: computed(() => `${t('about.transitOps.title')} — Parahub`),
  ogDescription: computed(() => t('docs.transit_ops_desc')),
})
useDocsBreadcrumb(t('about.transitOps.title'), '/docs/transit-ops')

const capabilities = ['routeEditor', 'vehicleTracking', 'schedules', 'realtimeFeed']

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
