<template>
  <div class="min-h-full bg-white dark:bg-neutral-950">
    <DocsHeader :title="$t('about.subscriptionsSystem.title')" />

    <div class="max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-12 space-y-8">

      <p class="prose-section">{{ $t('about.subscriptionsSystem.intro') }}</p>

      <!-- How it works -->
      <div>
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-3">{{ $t('about.subscriptionsSystem.flow.title') }}</h3>
        <ol class="space-y-2 text-neutral-700 dark:text-neutral-300">
          <li v-for="i in 3" :key="i" class="flex gap-3">
            <span class="flex-shrink-0 w-5 h-5 rounded-full bg-primary text-neutral-900 text-xs font-bold flex items-center justify-center mt-0.5">{{ i }}</span>
            <span>{{ $t(`about.subscriptionsSystem.flow.step${i}`) }}</span>
          </li>
        </ol>
      </div>

      <!-- Feature cards -->
      <div class="grid sm:grid-cols-2 gap-4">
        <div v-for="feature in features" :key="feature" class="p-4 border border-neutral-200 dark:border-neutral-800 rounded-lg">
          <div class="font-semibold text-neutral-900 dark:text-white mb-1">{{ $t(`about.subscriptionsSystem.${feature}.title`) }}</div>
          <div class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t(`about.subscriptionsSystem.${feature}.text`) }}</div>
        </div>
      </div>

      <!-- No-cut / no-escrow note -->
      <div class="p-4 bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg">
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-2">{{ $t('about.subscriptionsSystem.noCut.title') }}</h3>
        <p class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t('about.subscriptionsSystem.noCut.text') }}</p>
      </div>

      <DocsPrevNext />
    </div>
  </div>
</template>

<script setup lang="ts">
const { t } = useI18n()
useHead({ title: computed(() => `${t('about.subscriptionsSystem.title')} — Parahub`) })
useSeoMeta({
  description: computed(() => t('docs.subscriptions_desc')),
  ogTitle: computed(() => `${t('about.subscriptionsSystem.title')} — Parahub`),
  ogDescription: computed(() => t('docs.subscriptions_desc')),
})
useDocsBreadcrumb(t('about.subscriptionsSystem.title'), '/docs/subscriptions')

const features = ['subscribersOnly', 'whyPush', 'flatAmount', 'cancelAnytime']

definePageMeta({ order: 2 })
</script>

<style scoped>
.prose-section {
  @apply text-neutral-700 dark:text-neutral-300 leading-relaxed;
}
</style>
