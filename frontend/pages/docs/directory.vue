<template>
  <div class="min-h-full bg-white dark:bg-neutral-950">
    <DocsHeader :title="$t('about.directorySystem.title')" />

    <div class="max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-12 space-y-8">

      <p class="prose-section">{{ $t('about.directorySystem.intro') }}</p>

      <!-- Feature cards -->
      <div class="grid sm:grid-cols-2 gap-4">
        <div v-for="feature in features" :key="feature" class="p-4 border border-neutral-200 dark:border-neutral-800 rounded-lg">
          <div class="font-semibold text-neutral-900 dark:text-white mb-1">{{ $t(`about.directorySystem.${feature}.title`) }}</div>
          <div class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t(`about.directorySystem.${feature}.text`) }}</div>
        </div>
      </div>

      <!-- Who can do what -->
      <div class="p-4 bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg">
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-2">{{ $t('about.directorySystem.access.title') }}</h3>
        <p class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t('about.directorySystem.access.text') }}</p>
      </div>

      <DocsPrevNext />
    </div>
  </div>
</template>

<script setup lang="ts">
const { t } = useI18n()
useHead({ title: computed(() => `${t('about.directorySystem.title')} — Parahub`) })
useSeoMeta({
  description: computed(() => t('docs.directory_desc')),
  ogTitle: computed(() => `${t('about.directorySystem.title')} — Parahub`),
  ogDescription: computed(() => t('docs.directory_desc')),
})
useDocsBreadcrumb(t('about.directorySystem.title'), '/docs/directory')

const features = ['buildings', 'orgTypes', 'openNow', 'reviews', 'membership', 'actAs']

definePageMeta({ order: 2 })
</script>

<style scoped>
.prose-section {
  @apply text-neutral-700 dark:text-neutral-300 leading-relaxed;
}
</style>
