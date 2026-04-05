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
          <h1 class="inline text-neutral-900 font-semibold text-lg sm:text-xl">{{ $t('about.transparency.title') }}</h1>
        </nav>
      </div>
    </div>

    <div class="max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-12 space-y-8">

      <!-- Intro -->
      <p class="prose-section">{{ $t('about.transparency.intro') }}</p>

      <!-- Principles -->
      <div>
        <h2 class="text-lg font-semibold text-neutral-900 dark:text-white mb-4">{{ $t('about.transparency.principles_title') }}</h2>
        <div class="space-y-3">
          <div v-for="i in 4" :key="i" class="flex gap-3 items-start">
            <component :is="principleIcons[i-1]" class="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5" />
            <div>
              <div class="font-medium text-neutral-900 dark:text-white">{{ $t(`about.transparency.principle${i}_title`) }}</div>
              <div class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t(`about.transparency.principle${i}_text`) }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Revenue sources -->
      <div>
        <h2 class="text-lg font-semibold text-neutral-900 dark:text-white mb-4">{{ $t('about.transparency.sources_title') }}</h2>
        <div class="space-y-4">
          <!-- Voluntary donations -->
          <div class="p-4 border border-amber-200 dark:border-amber-800/50 bg-amber-50/50 dark:bg-amber-950/20 rounded-lg">
            <div class="flex items-center gap-2 mb-2">
              <Heart class="w-4 h-4 text-amber-500" />
              <h3 class="font-medium text-neutral-900 dark:text-white">{{ $t('about.transparency.donations_title') }}</h3>
            </div>
            <p class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t('about.transparency.donations_text') }}</p>
            <div class="mt-3 flex gap-2">
              <span class="px-3 py-1 text-xs rounded-full bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700">0%</span>
              <span class="px-3 py-1 text-xs rounded-full bg-amber-500 text-white">0.1%</span>
              <span class="px-3 py-1 text-xs rounded-full bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700">1%</span>
            </div>
          </div>

          <!-- Ads listing fee -->
          <div class="p-4 border border-neutral-200 dark:border-neutral-700 rounded-lg">
            <div class="flex items-center gap-2 mb-2">
              <Megaphone class="w-4 h-4 text-neutral-500" />
              <h3 class="font-medium text-neutral-900 dark:text-white">{{ $t('about.transparency.ads_title') }}</h3>
            </div>
            <p class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t('about.transparency.ads_text') }}</p>
          </div>

          <!-- EGAC energy fee -->
          <div class="p-4 border border-neutral-200 dark:border-neutral-700 rounded-lg">
            <div class="flex items-center gap-2 mb-2">
              <Zap class="w-4 h-4 text-neutral-500" />
              <h3 class="font-medium text-neutral-900 dark:text-white">{{ $t('about.transparency.energy_title') }}</h3>
            </div>
            <p class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t('about.transparency.energy_text') }}</p>
          </div>
        </div>
      </div>

      <!-- What we never do -->
      <div class="p-4 bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg">
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-2">{{ $t('about.transparency.never_title') }}</h3>
        <ul class="space-y-1.5 text-sm text-neutral-600 dark:text-neutral-400">
          <li v-for="i in 4" :key="i" class="flex gap-2">
            <X class="w-4 h-4 text-error flex-shrink-0 mt-0.5" />
            <span>{{ $t(`about.transparency.never${i}`) }}</span>
          </li>
        </ul>
      </div>

      <!-- Live stats -->
      <div v-if="stats" class="space-y-4">
        <h2 class="text-lg font-semibold text-neutral-900 dark:text-white">{{ $t('about.transparency.stats_title') }}</h2>
        <div class="grid grid-cols-3 gap-3">
          <div class="p-4 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800/50 rounded-lg text-center">
            <div class="text-2xl font-bold text-amber-600 dark:text-amber-400">{{ formatSats(stats.total_donated_sats) }}</div>
            <div class="text-xs text-amber-700 dark:text-amber-300 mt-1">{{ $t('about.transparency.total_sats') }}</div>
          </div>
          <div class="p-4 bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg text-center">
            <div class="text-2xl font-bold text-neutral-900 dark:text-white">{{ stats.total_donations_count }}</div>
            <div class="text-xs text-neutral-500 mt-1">{{ $t('about.transparency.total_donations') }}</div>
          </div>
          <div class="p-4 bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg text-center">
            <div class="text-2xl font-bold text-neutral-900 dark:text-white">{{ stats.supporters_count }}</div>
            <div class="text-xs text-neutral-500 mt-1">{{ $t('about.transparency.supporters') }}</div>
          </div>
        </div>
      </div>

      <DocsPrevNext />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ChevronRight, Heart, Megaphone, Zap, X, HandCoins, Eye, Settings, Ban } from 'lucide-vue-next'

const { t } = useI18n()
const localePath = useLocalePath()
useHead({ title: computed(() => `${t('about.transparency.title')} — Parahub`) })
useSeoMeta({
  description: computed(() => t('docs.transparency_desc')),
  ogTitle: computed(() => `${t('about.transparency.title')} — Parahub`),
  ogDescription: computed(() => t('docs.transparency_desc')),
})
useDocsBreadcrumb(t('about.transparency.title'), '/docs/transparency')

const principleIcons = [HandCoins, Eye, Settings, Ban]

// Fetch live stats
const stats = ref<any>(null)
onMounted(async () => {
  try {
    stats.value = await $fetch('/api/v1/income/transparency/')
  } catch {
    // Stats are non-critical
  }
})

const formatSats = (sats: number) => {
  if (!sats) return '0'
  return sats.toLocaleString()
}

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
