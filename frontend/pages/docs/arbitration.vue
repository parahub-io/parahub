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
          <h1 class="inline text-neutral-900 font-semibold text-lg sm:text-xl">{{ $t('about.arbitration.title') }}</h1>
        </nav>
      </div>
    </div>

    <div class="max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-12">
      <div class="prose-section">
        <p>{{ $t('about.arbitration.intro') }}</p>

        <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mt-6 mb-3">{{ $t('about.arbitration.modes.title') }}</h3>
        <div class="grid sm:grid-cols-2 gap-4">
          <div class="border border-neutral-200 dark:border-neutral-800 rounded p-4">
            <h4 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-2">{{ $t('about.arbitration.modes.reputation.title') }}</h4>
            <p class="text-sm text-neutral-700 dark:text-neutral-300 mb-2">{{ $t('about.arbitration.modes.reputation.desc') }}</p>
            <ul class="text-sm text-neutral-600 dark:text-neutral-400 space-y-1">
              <li>- {{ $t('about.arbitration.modes.reputation.point1') }}</li>
              <li>- {{ $t('about.arbitration.modes.reputation.point2') }}</li>
              <li>- {{ $t('about.arbitration.modes.reputation.point3') }}</li>
            </ul>
          </div>
          <div class="border border-neutral-200 dark:border-neutral-800 rounded p-4">
            <h4 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-2">{{ $t('about.arbitration.modes.multisig.title') }}</h4>
            <p class="text-sm text-neutral-700 dark:text-neutral-300 mb-2">{{ $t('about.arbitration.modes.multisig.desc') }}</p>
            <ul class="text-sm text-neutral-600 dark:text-neutral-400 space-y-1">
              <li>- {{ $t('about.arbitration.modes.multisig.point1') }}</li>
              <li>- {{ $t('about.arbitration.modes.multisig.point2') }}</li>
              <li>- {{ $t('about.arbitration.modes.multisig.point3') }}</li>
            </ul>
          </div>
        </div>

        <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mt-6 mb-3">{{ $t('about.arbitration.escalation.title') }}</h3>
        <div class="space-y-3">
          <div class="flex gap-3">
            <div class="flex items-center gap-1.5 flex-shrink-0 w-12 justify-end">
              <MessageSquare class="w-3.5 h-3.5 text-neutral-400" />
              <span class="font-mono text-neutral-400 text-sm">L1</span>
            </div>
            <div>
              <span class="font-medium text-neutral-900 dark:text-neutral-100">{{ $t('about.arbitration.escalation.level1.title') }}</span>
              <span class="text-neutral-500 dark:text-neutral-400"> &mdash; </span>
              <span class="text-neutral-700 dark:text-neutral-300">{{ $t('about.arbitration.escalation.level1.desc') }}</span>
            </div>
          </div>
          <div class="flex gap-3">
            <div class="flex items-center gap-1.5 flex-shrink-0 w-12 justify-end">
              <UserCheck class="w-3.5 h-3.5 text-neutral-400" />
              <span class="font-mono text-neutral-400 text-sm">L2</span>
            </div>
            <div>
              <span class="font-medium text-neutral-900 dark:text-neutral-100">{{ $t('about.arbitration.escalation.level2.title') }}</span>
              <span class="text-neutral-500 dark:text-neutral-400"> &mdash; </span>
              <span class="text-neutral-700 dark:text-neutral-300">{{ $t('about.arbitration.escalation.level2.desc') }}</span>
            </div>
          </div>
          <div class="flex gap-3">
            <div class="flex items-center gap-1.5 flex-shrink-0 w-12 justify-end">
              <Landmark class="w-3.5 h-3.5 text-neutral-400" />
              <span class="font-mono text-neutral-400 text-sm">L3</span>
            </div>
            <div>
              <span class="font-medium text-neutral-900 dark:text-neutral-100">{{ $t('about.arbitration.escalation.level3.title') }}</span>
              <span class="text-neutral-500 dark:text-neutral-400"> &mdash; </span>
              <span class="text-neutral-700 dark:text-neutral-300">{{ $t('about.arbitration.escalation.level3.desc') }}</span>
            </div>
          </div>
        </div>
      </div>
      <DocsPrevNext />
    </div>
  </div>
</template>

<script setup lang="ts">
import { MessageSquare, UserCheck, Landmark, ChevronRight } from 'lucide-vue-next'

const { t } = useI18n()
const localePath = useLocalePath()
useHead({ title: computed(() => `${t('about.arbitration.title')} — Parahub`) })
useSeoMeta({
  description: computed(() => t('docs.arbitration_desc')),
  ogTitle: computed(() => `${t('about.arbitration.title')} — Parahub`),
  ogDescription: computed(() => t('docs.arbitration_desc')),
})
useDocsBreadcrumb(t('about.arbitration.title'), '/docs/arbitration')

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
