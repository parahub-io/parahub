<template>
  <div class="min-h-full bg-white dark:bg-neutral-950">
    <DocsHeader :title="$t('about.communicationSystem.title')" />

    <div class="max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-12 space-y-8">

      <p class="prose-section">{{ $t('about.communicationSystem.intro') }}</p>

      <!-- Feature cards -->
      <div class="grid sm:grid-cols-2 gap-4">
        <div v-for="feature in features" :key="feature" class="p-4 border border-neutral-200 dark:border-neutral-800 rounded-lg">
          <div class="font-semibold text-neutral-900 dark:text-white mb-1">{{ $t(`about.communicationSystem.${feature}.title`) }}</div>
          <div class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t(`about.communicationSystem.${feature}.text`) }}</div>
        </div>
      </div>

      <!-- Open-protocol note -->
      <div class="p-4 bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg">
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-2">{{ $t('about.communicationSystem.callout.title') }}</h3>
        <p class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t('about.communicationSystem.callout.text') }}</p>
      </div>

      <DocsPrevNext />
    </div>
  </div>
</template>

<script setup lang="ts">
const { t } = useI18n()
useHead({ title: computed(() => `${t('about.communicationSystem.title')} — Parahub`) })
useSeoMeta({
  description: computed(() => t('docs.communication_desc')),
  ogTitle: computed(() => `${t('about.communicationSystem.title')} — Parahub`),
  ogDescription: computed(() => t('docs.communication_desc')),
})
useDocsBreadcrumb(t('about.communicationSystem.title'), '/docs/communication')

const features = ['e2e', 'clients', 'calls', 'push']

definePageMeta({ order: 2 })
</script>

<style scoped>
.prose-section {
  @apply text-neutral-700 dark:text-neutral-300 leading-relaxed;
}
</style>
