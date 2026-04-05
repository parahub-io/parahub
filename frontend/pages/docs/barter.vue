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
          <h1 class="inline text-neutral-900 font-semibold text-lg sm:text-xl">{{ $t('about.barterSystem.title') }}</h1>
        </nav>
      </div>
    </div>

    <div class="max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-12">
      <div class="prose-section">
        <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-2">{{ $t('about.barterSystem.why.title') }}</h3>
        <p>{{ $t('about.barterSystem.why.text') }}</p>

        <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mt-6 mb-2">{{ $t('about.barterSystem.howItWorks.title') }}</h3>
        <ol class="list-decimal list-inside space-y-3 text-neutral-700 dark:text-neutral-300">
          <li>{{ $t('about.barterSystem.howItWorks.step1') }}</li>
          <li>{{ $t('about.barterSystem.howItWorks.step2') }}</li>
          <li>
            {{ $t('about.barterSystem.howItWorks.step3') }}
            <ul class="list-disc list-inside ml-4 mt-1 space-y-1 text-sm">
              <li>{{ $t('about.barterSystem.howItWorks.step3_bilateral') }}</li>
              <li>{{ $t('about.barterSystem.howItWorks.step3_trilateral') }}</li>
              <li>{{ $t('about.barterSystem.howItWorks.step3_multilateral') }}</li>
            </ul>
          </li>
          <li>{{ $t('about.barterSystem.howItWorks.step4') }}</li>
          <li>{{ $t('about.barterSystem.howItWorks.step5') }}</li>
        </ol>

        <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mt-6 mb-3">{{ $t('about.barterSystem.example.title') }}</h3>
        <div class="bg-neutral-50 dark:bg-neutral-900 rounded border border-neutral-200 dark:border-neutral-800 p-4 font-mono text-sm space-y-2">
          <div>
            <span class="text-neutral-500">A:</span>
            <span class="text-neutral-900 dark:text-neutral-100 font-medium"> {{ $t('about.barterSystem.example.alice') }}</span>
            &mdash; {{ $t('about.barterSystem.example.offers_label') }} <span class="text-secondary dark:text-secondary-400">{{ $t('about.barterSystem.example.alice_offers') }}</span>,
            {{ $t('about.barterSystem.example.wants_label') }} <span class="text-green-600 dark:text-green-400">{{ $t('about.barterSystem.example.alice_wants') }}</span>
          </div>
          <div class="text-neutral-400 pl-2">&darr;</div>
          <div>
            <span class="text-neutral-500">B:</span>
            <span class="text-neutral-900 dark:text-neutral-100 font-medium"> {{ $t('about.barterSystem.example.bob') }}</span>
            &mdash; {{ $t('about.barterSystem.example.offers_label') }} <span class="text-secondary dark:text-secondary-400">{{ $t('about.barterSystem.example.bob_offers') }}</span>,
            {{ $t('about.barterSystem.example.wants_label') }} <span class="text-green-600 dark:text-green-400">{{ $t('about.barterSystem.example.bob_wants') }}</span>
          </div>
          <div class="text-neutral-400 pl-2">&darr;</div>
          <div>
            <span class="text-neutral-500">C:</span>
            <span class="text-neutral-900 dark:text-neutral-100 font-medium"> {{ $t('about.barterSystem.example.vera') }}</span>
            &mdash; {{ $t('about.barterSystem.example.offers_label') }} <span class="text-secondary dark:text-secondary-400">{{ $t('about.barterSystem.example.vera_offers') }}</span>,
            {{ $t('about.barterSystem.example.wants_label') }} <span class="text-green-600 dark:text-green-400">{{ $t('about.barterSystem.example.vera_wants') }}</span>
          </div>
          <div class="border-t border-neutral-200 dark:border-neutral-700 pt-2 mt-2 text-green-700 dark:text-green-400">
            &rArr; {{ $t('about.barterSystem.example.result') }}
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
useHead({ title: computed(() => `${t('about.barterSystem.title')} — Parahub`) })
useSeoMeta({
  description: computed(() => t('docs.barter_desc')),
  ogTitle: computed(() => `${t('about.barterSystem.title')} — Parahub`),
  ogDescription: computed(() => t('docs.barter_desc')),
})
useDocsBreadcrumb(t('about.barterSystem.title'), '/docs/barter')

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
