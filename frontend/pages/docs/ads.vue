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
          <h1 class="inline text-neutral-900 font-semibold text-lg sm:text-xl">{{ $t('about.adsSystem.title') }}</h1>
        </nav>
      </div>
    </div>

    <div class="max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-12">
      <div class="prose-section space-y-8">

        <div>
          <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-2">{{ $t('about.adsSystem.difference.title') }}</h3>
          <p>{{ $t('about.adsSystem.difference.text') }}</p>
        </div>

        <!-- Visual comparison -->
        <div class="grid sm:grid-cols-2 gap-3 text-sm">
          <div class="border border-red-200 dark:border-red-900 rounded-lg p-4 bg-red-50 dark:bg-red-950/30">
            <div class="font-semibold text-red-700 dark:text-red-400 mb-2">{{ $t('about.adsSystem.compare.traditional') }}</div>
            <div class="text-neutral-600 dark:text-neutral-400 font-mono">
              {{ $t('about.adsSystem.compare.trad_flow') }}
            </div>
          </div>
          <div class="border border-green-200 dark:border-green-900 rounded-lg p-4 bg-green-50 dark:bg-green-950/30">
            <div class="font-semibold text-green-700 dark:text-green-400 mb-2">Parahub</div>
            <div class="text-neutral-600 dark:text-neutral-400 font-mono">
              {{ $t('about.adsSystem.compare.para_flow') }}
            </div>
          </div>
        </div>

        <div>
          <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-3">{{ $t('about.adsSystem.viewer.title') }}</h3>
          <ol class="list-decimal list-inside space-y-2.5 text-neutral-700 dark:text-neutral-300">
            <li>{{ $t('about.adsSystem.viewer.step1') }}</li>
            <li>{{ $t('about.adsSystem.viewer.step2') }}</li>
            <li>{{ $t('about.adsSystem.viewer.step3') }}</li>
            <li>{{ $t('about.adsSystem.viewer.step4') }}</li>
          </ol>
        </div>

        <div>
          <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-3">{{ $t('about.adsSystem.advertiser.title') }}</h3>
          <ol class="list-decimal list-inside space-y-2.5 text-neutral-700 dark:text-neutral-300">
            <li>{{ $t('about.adsSystem.advertiser.step1') }}</li>
            <li>{{ $t('about.adsSystem.advertiser.step2') }}</li>
            <li>{{ $t('about.adsSystem.advertiser.step3') }}</li>
            <li>{{ $t('about.adsSystem.advertiser.step4') }}</li>
          </ol>
        </div>

        <div class="bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 rounded-lg p-4">
          <h4 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-1.5">{{ $t('about.adsSystem.flow.title') }}</h4>
          <p class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t('about.adsSystem.flow.text') }}</p>
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
useHead({ title: computed(() => `${t('about.adsSystem.title')} — Parahub`) })
useSeoMeta({
  description: computed(() => t('docs.ads_desc')),
  ogTitle: computed(() => `${t('about.adsSystem.title')} — Parahub`),
  ogDescription: computed(() => t('docs.ads_desc')),
})
useDocsBreadcrumb(t('about.adsSystem.title'), '/docs/ads')

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
