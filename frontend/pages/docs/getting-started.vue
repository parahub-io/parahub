<template>
  <div class="min-h-full bg-white dark:bg-neutral-950">
    <DocsHeader :title="$t('about.gettingStarted.title')" />

    <div class="max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-12 space-y-6">

      <p class="prose-section">{{ $t('about.gettingStarted.intro') }}</p>

      <ol class="space-y-4">
        <li v-for="i in 5" :key="i" class="flex gap-4">
          <span class="flex-shrink-0 w-7 h-7 rounded-full bg-yellow-400 text-neutral-900 text-sm font-bold flex items-center justify-center mt-0.5">{{ i }}</span>
          <div>
            <div class="font-semibold text-neutral-900 dark:text-white">{{ $t(`about.gettingStarted.step${i}.title`) }}</div>
            <div class="text-neutral-600 dark:text-neutral-400 text-sm mt-0.5">{{ $t(`about.gettingStarted.step${i}.text`) }}</div>
          </div>
        </li>
      </ol>

<DocsPrevNext />
    </div>
  </div>
</template>

<script setup lang="ts">
const { t } = useI18n()
useHead({ title: computed(() => `${t('about.gettingStarted.title')} — Parahub`) })
useSeoMeta({
  description: computed(() => t('docs.getting_started_desc')),
  ogTitle: computed(() => `${t('about.gettingStarted.title')} — Parahub`),
  ogDescription: computed(() => t('docs.getting_started_desc')),
})
useDocsBreadcrumb(t('about.gettingStarted.title'), '/docs/getting-started')

definePageMeta({ order: 2 })
</script>

<style scoped>
.prose-section {
  @apply text-neutral-700 dark:text-neutral-300 leading-relaxed;
}
</style>
