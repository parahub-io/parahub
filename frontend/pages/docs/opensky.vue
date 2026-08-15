<template>
  <div class="min-h-full bg-white dark:bg-neutral-950">
    <DocsHeader :title="$t('about.openskySystem.title')" />

    <div class="max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-12 space-y-8">

      <p class="prose-section">{{ $t('about.openskySystem.intro') }}</p>

      <div>
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-3">{{ $t('about.openskySystem.flow.title') }}</h3>
        <ol class="space-y-2 text-neutral-700 dark:text-neutral-300">
          <li v-for="i in 5" :key="i" class="flex gap-3">
            <span class="flex-shrink-0 w-5 h-5 rounded-full bg-primary text-neutral-900 text-xs font-bold flex items-center justify-center mt-0.5">{{ i }}</span>
            <span>{{ $t(`about.openskySystem.flow.step${i}`) }}</span>
          </li>
        </ol>
      </div>

      <!-- Pre-flight checks: the four things the planner classifies a square by -->
      <div>
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-3">{{ $t('about.openskySystem.checks.title') }}</h3>
        <div class="grid sm:grid-cols-2 gap-4">
          <div v-for="check in checks" :key="check" class="p-4 border border-neutral-200 dark:border-neutral-800 rounded-lg">
            <div class="font-semibold text-neutral-900 dark:text-white mb-1">{{ $t(`about.openskySystem.checks.${check}.title`) }}</div>
            <div class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t(`about.openskySystem.checks.${check}.text`) }}</div>
          </div>
        </div>
      </div>

      <!-- The planner is advisory: never let it read as legal clearance -->
      <div class="p-4 bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg">
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-2">{{ $t('about.openskySystem.limits.title') }}</h3>
        <p class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t('about.openskySystem.limits.text') }}</p>
      </div>

      <div>
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-3">{{ $t('about.openskySystem.upload.title') }}</h3>
        <ul class="space-y-2">
          <li v-for="i in 4" :key="i" class="flex items-start gap-2 text-neutral-700 dark:text-neutral-300 text-sm">
            <span class="w-1.5 h-1.5 rounded-full bg-yellow-400 flex-shrink-0 mt-1.5" />
            {{ $t(`about.openskySystem.upload.rule${i}`) }}
          </li>
        </ul>
      </div>

      <div class="p-4 bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg">
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-2">{{ $t('about.openskySystem.license.title') }}</h3>
        <p class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t('about.openskySystem.license.text') }}</p>
      </div>

      <DocsPrevNext />
    </div>
  </div>
</template>

<script setup lang="ts">
const { t } = useI18n()
useHead({ title: computed(() => `${t('about.openskySystem.title')} — Parahub`) })
useSeoMeta({
  description: computed(() => t('docs.opensky_desc')),
  ogTitle: computed(() => `${t('about.openskySystem.title')} — Parahub`),
  ogDescription: computed(() => t('docs.opensky_desc')),
})
useDocsBreadcrumb(t('about.openskySystem.title'), '/docs/opensky')

const checks = ['range', 'ceiling', 'link', 'airspace']

definePageMeta({ order: 2 })
</script>

<style scoped>
.prose-section {
  @apply text-neutral-700 dark:text-neutral-300 leading-relaxed;
}
</style>
