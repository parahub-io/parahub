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
          <h1 class="inline text-neutral-900 font-semibold text-lg sm:text-xl">{{ $t('about.energySystem.title') }}</h1>
        </nav>
      </div>
    </div>

    <div class="max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-12 space-y-8">

      <!-- WIP badge -->
      <UiBadge variant="warning" type="soft" size="lg" class="gap-2">
        <Wrench class="w-3.5 h-3.5" />
        {{ $t('about.energySystem.wip') }}
      </UiBadge>

      <!-- Problem -->
      <p class="prose-section">{{ $t('about.energySystem.problem.text') }}</p>

      <!-- Price comparison -->
      <div class="grid grid-cols-3 gap-3">
        <div class="p-4 bg-error-50 dark:bg-error-900/10 border border-error-200 dark:border-error-800 rounded-lg text-center">
          <div class="text-2xl font-bold text-error dark:text-error-400">0,05 €</div>
          <div class="text-xs text-error-700 dark:text-error-300 mt-1">{{ $t('about.energySystem.compare.grid_sell') }}</div>
        </div>
        <div class="p-4 bg-success-50 dark:bg-success-900/10 border border-success-200 dark:border-success-800 rounded-lg text-center">
          <div class="text-2xl font-bold text-success-600 dark:text-success-400">0,08 €</div>
          <div class="text-xs text-success-700 dark:text-success-300 mt-1">{{ $t('about.energySystem.compare.parahub_price') }}</div>
        </div>
        <div class="p-4 bg-error-50 dark:bg-error-900/10 border border-error-200 dark:border-error-800 rounded-lg text-center">
          <div class="text-2xl font-bold text-error dark:text-error-400">0,20 €</div>
          <div class="text-xs text-error-700 dark:text-error-300 mt-1">{{ $t('about.energySystem.compare.grid_buy') }}</div>
        </div>
      </div>

      <!-- EU note -->
      <p class="text-xs text-neutral-500 dark:text-neutral-400 text-center -mt-4">
        {{ $t('energy.eu_note') }}
      </p>

      <!-- Win-win explanation -->
      <p class="prose-section">{{ $t('about.energySystem.winwin.text') }}</p>

      <!-- Steps: Producer -->
      <div>
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-3">{{ $t('about.energySystem.producer.title') }}</h3>
        <ol class="space-y-2 text-neutral-700 dark:text-neutral-300">
          <li v-for="i in 4" :key="i" class="flex gap-3">
            <span class="flex-shrink-0 w-5 h-5 rounded-full bg-primary text-neutral-900 text-xs font-bold flex items-center justify-center mt-0.5">{{ i }}</span>
            <span>{{ $t(`about.energySystem.producer.step${i}`) }}</span>
          </li>
        </ol>
      </div>

      <!-- Steps: Neighbor -->
      <div>
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-3">{{ $t('about.energySystem.neighbor.title') }}</h3>
        <ol class="space-y-2 text-neutral-700 dark:text-neutral-300">
          <li v-for="i in 3" :key="i" class="flex gap-3">
            <span class="flex-shrink-0 w-5 h-5 rounded-full bg-primary text-neutral-900 text-xs font-bold flex items-center justify-center mt-0.5">{{ i }}</span>
            <span>{{ $t(`about.energySystem.neighbor.step${i}`) }}</span>
          </li>
        </ol>
      </div>

      <!-- Technical requirements -->
      <div class="p-4 bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg">
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-2">{{ $t('about.energySystem.requirements.title') }}</h3>
        <p class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t('about.energySystem.requirements.text') }}</p>
      </div>

      <!-- Markets -->
      <p class="prose-section">{{ $t('about.energySystem.markets.text') }}</p>

      <DocsPrevNext />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ChevronRight, Wrench } from 'lucide-vue-next'

const { t } = useI18n()
const localePath = useLocalePath()
useHead({ title: computed(() => `${t('about.energySystem.title')} — Parahub`) })
useSeoMeta({
  description: computed(() => t('docs.energy_desc')),
  ogTitle: computed(() => `${t('about.energySystem.title')} — Parahub`),
  ogDescription: computed(() => t('docs.energy_desc')),
})
useDocsBreadcrumb(t('about.energySystem.title'), '/docs/energy')

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
