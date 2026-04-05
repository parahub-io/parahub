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
          <h1 class="inline text-neutral-900 font-semibold text-lg sm:text-xl">{{ $t('about.cryptoProofs.title') }}</h1>
        </nav>
      </div>
    </div>

    <div class="max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-12 space-y-8">

      <p class="text-neutral-700 dark:text-neutral-300 leading-relaxed">{{ $t('about.cryptoProofs.intro') }}</p>

      <!-- PGP + OTS cards -->
      <div class="grid sm:grid-cols-2 gap-4">
        <div class="border border-neutral-200 dark:border-neutral-800 rounded-lg p-5 space-y-3">
          <div class="flex items-center gap-2">
            <KeyRound class="w-4 h-4 text-neutral-500" />
            <h3 class="font-semibold text-neutral-900 dark:text-neutral-100">{{ $t('about.cryptoProofs.pgp.title') }}</h3>
          </div>
          <p class="text-sm text-neutral-600 dark:text-neutral-400 leading-relaxed">{{ $t('about.cryptoProofs.pgp.text') }}</p>
          <ul class="space-y-1.5 text-sm text-neutral-600 dark:text-neutral-400">
            <li v-for="p in ['point1','point2','point3']" :key="p" class="flex items-start gap-2">
              <span class="text-neutral-400 mt-0.5 flex-shrink-0">—</span>
              <span>{{ $t(`about.cryptoProofs.pgp.${p}`) }}</span>
            </li>
          </ul>
        </div>

        <div class="border border-neutral-200 dark:border-neutral-800 rounded-lg p-5 space-y-3">
          <div class="flex items-center gap-2">
            <Bitcoin class="w-4 h-4 text-neutral-500" />
            <h3 class="font-semibold text-neutral-900 dark:text-neutral-100">{{ $t('about.cryptoProofs.ots.title') }}</h3>
          </div>
          <p class="text-sm text-neutral-600 dark:text-neutral-400 leading-relaxed">{{ $t('about.cryptoProofs.ots.text') }}</p>
          <ul class="space-y-1.5 text-sm text-neutral-600 dark:text-neutral-400">
            <li v-for="p in ['point1','point2','point3']" :key="p" class="flex items-start gap-2">
              <span class="text-neutral-400 mt-0.5 flex-shrink-0">—</span>
              <span>{{ $t(`about.cryptoProofs.ots.${p}`) }}</span>
            </li>
          </ul>
        </div>
      </div>

      <!-- Export section -->
      <div class="p-5 bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg space-y-3">
        <div class="flex items-center gap-2">
          <FileDown class="w-4 h-4 text-neutral-500" />
          <h3 class="font-semibold text-neutral-900 dark:text-white">{{ $t('about.cryptoProofs.export.title') }}</h3>
        </div>
        <p class="text-sm text-neutral-600 dark:text-neutral-400 leading-relaxed">{{ $t('about.cryptoProofs.export.text') }}</p>
        <div class="text-sm text-neutral-500 dark:text-neutral-500 font-medium">{{ $t('about.cryptoProofs.export.contains') }}</div>
        <ul class="space-y-1 text-sm text-neutral-600 dark:text-neutral-400 font-mono">
          <li v-for="i in ['item1','item2','item3','item4']" :key="i" class="flex items-start gap-2">
            <span class="text-yellow-500 flex-shrink-0">›</span>
            <span>{{ $t(`about.cryptoProofs.export.${i}`) }}</span>
          </li>
        </ul>
      </div>

      <!-- Verify section -->
      <div class="space-y-3">
        <h3 class="font-semibold text-neutral-900 dark:text-neutral-100">{{ $t('about.cryptoProofs.verify.title') }}</h3>
        <div class="space-y-2">
          <div v-for="(step, i) in ['step1','step2','step3']" :key="step" class="flex gap-3 items-start">
            <span class="flex-shrink-0 w-5 h-5 rounded-full bg-neutral-100 dark:bg-neutral-800 text-neutral-500 dark:text-neutral-400 text-xs flex items-center justify-center font-mono mt-0.5">{{ i + 1 }}</span>
            <code class="text-sm text-neutral-700 dark:text-neutral-300 font-mono leading-relaxed">{{ $t(`about.cryptoProofs.verify.${step}`) }}</code>
          </div>
        </div>
      </div>

      <!-- Legal note -->
      <div class="p-4 border-l-4 border-neutral-300 dark:border-neutral-600 bg-neutral-50 dark:bg-neutral-900 rounded-r-lg">
        <div class="text-xs font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider mb-1">{{ $t('about.cryptoProofs.legal.title') }}</div>
        <p class="text-sm text-neutral-600 dark:text-neutral-400 leading-relaxed">{{ $t('about.cryptoProofs.legal.text') }}</p>
      </div>

      <DocsPrevNext />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ChevronRight, KeyRound, Bitcoin, FileDown } from 'lucide-vue-next'

const { t } = useI18n()
const localePath = useLocalePath()
useHead({ title: computed(() => `${t('about.cryptoProofs.title')} — Parahub`) })
useSeoMeta({
  description: computed(() => t('docs.crypto_desc')),
  ogTitle: computed(() => `${t('about.cryptoProofs.title')} — Parahub`),
  ogDescription: computed(() => t('docs.crypto_desc')),
})
useDocsBreadcrumb(t('about.cryptoProofs.title'), '/docs/crypto')

definePageMeta({ order: 2 })
</script>

<style scoped>
.docs-header {
  background-color: var(--color-primary);
}
</style>
