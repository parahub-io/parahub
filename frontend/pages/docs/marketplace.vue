<template>
  <div class="min-h-full bg-white dark:bg-neutral-950">
    <DocsHeader :title="$t('about.marketplaceSystem.title')" />

    <div class="max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-12 space-y-8">

      <p class="prose-section">{{ $t('about.marketplaceSystem.intro') }}</p>

      <!-- Feature cards -->
      <div class="grid sm:grid-cols-2 gap-4">
        <div v-for="feature in features" :key="feature" class="p-4 border border-neutral-200 dark:border-neutral-800 rounded-lg">
          <div class="font-semibold text-neutral-900 dark:text-white mb-1">{{ $t(`about.marketplaceSystem.${feature}.title`) }}</div>
          <div class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t(`about.marketplaceSystem.${feature}.text`) }}</div>
        </div>
      </div>

      <!-- No platform fees note -->
      <div class="p-4 bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg">
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-2">{{ $t('about.marketplaceSystem.noFees.title') }}</h3>
        <p class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t('about.marketplaceSystem.noFees.text') }}</p>
      </div>

      <DocsPrevNext />
    </div>
  </div>
</template>

<script setup lang="ts">
const { t } = useI18n()
useHead({ title: computed(() => `${t('about.marketplaceSystem.title')} — Parahub`) })
useSeoMeta({
  description: computed(() => t('docs.marketplace_desc')),
  ogTitle: computed(() => `${t('about.marketplaceSystem.title')} — Parahub`),
  ogDescription: computed(() => t('docs.marketplace_desc')),
})
useDocsBreadcrumb(t('about.marketplaceSystem.title'), '/docs/marketplace')

const features = ['creditDebit', 'pricing', 'visibility', 'selfMade', 'matching', 'barterLink']

definePageMeta({ order: 2 })
</script>

<style scoped>
.prose-section {
  @apply text-neutral-700 dark:text-neutral-300 leading-relaxed;
}
</style>
