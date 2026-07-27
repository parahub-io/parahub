<template>
  <div class="min-h-full bg-white dark:bg-neutral-950">
    <DocsHeader :title="$t('about.smartHomeSystem.title')" />

    <div class="max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-12 space-y-8">

      <p class="prose-section">{{ $t('about.smartHomeSystem.intro') }}</p>

      <!-- Connection flow -->
      <div>
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-3">{{ $t('about.smartHomeSystem.flow.title') }}</h3>
        <ol class="space-y-2 text-neutral-700 dark:text-neutral-300">
          <li v-for="i in 3" :key="i" class="flex gap-3">
            <span class="flex-shrink-0 w-5 h-5 rounded-full bg-primary text-neutral-900 text-xs font-bold flex items-center justify-center mt-0.5">{{ i }}</span>
            <span>{{ $t(`about.smartHomeSystem.flow.step${i}`) }}</span>
          </li>
        </ol>
      </div>

      <!-- Feature cards -->
      <div class="grid sm:grid-cols-2 gap-4">
        <div v-for="feature in features" :key="feature" class="p-4 border border-neutral-200 dark:border-neutral-800 rounded-lg">
          <div class="font-semibold text-neutral-900 dark:text-white mb-1">{{ $t(`about.smartHomeSystem.${feature}.title`) }}</div>
          <div class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t(`about.smartHomeSystem.${feature}.text`) }}</div>
        </div>
      </div>

      <DocsPrevNext />
    </div>
  </div>
</template>

<script setup lang="ts">
const { t } = useI18n()
useHead({ title: computed(() => `${t('about.smartHomeSystem.title')} — Parahub`) })
useSeoMeta({
  description: computed(() => t('docs.smart_home_desc')),
  ogTitle: computed(() => `${t('about.smartHomeSystem.title')} — Parahub`),
  ogDescription: computed(() => t('docs.smart_home_desc')),
})
useDocsBreadcrumb(t('about.smartHomeSystem.title'), '/docs/smart-home')

const features = ['direct', 'security', 'domains', 'property']

definePageMeta({ order: 2 })
</script>

<style scoped>
.prose-section {
  @apply text-neutral-700 dark:text-neutral-300 leading-relaxed;
}
</style>
