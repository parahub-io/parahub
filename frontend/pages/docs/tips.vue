<template>
  <div class="min-h-full bg-white dark:bg-neutral-950">
    <DocsHeader :title="$t('about.tipsSystem.title')" />

    <div class="max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-12 space-y-8">

      <p class="prose-section">{{ $t('about.tipsSystem.intro') }}</p>

      <!-- Mint → print → claim -->
      <div>
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-3">{{ $t('about.tipsSystem.flow.title') }}</h3>
        <ol class="space-y-2 text-neutral-700 dark:text-neutral-300">
          <li v-for="i in 4" :key="i" class="flex gap-3">
            <span class="flex-shrink-0 w-5 h-5 rounded-full bg-primary text-neutral-900 text-xs font-bold flex items-center justify-center mt-0.5">{{ i }}</span>
            <span>{{ $t(`about.tipsSystem.flow.step${i}`) }}</span>
          </li>
        </ol>
      </div>

      <div class="grid sm:grid-cols-2 gap-4">
        <div v-for="feature in features" :key="feature" class="p-4 border border-neutral-200 dark:border-neutral-800 rounded-lg">
          <div class="font-semibold text-neutral-900 dark:text-white mb-1">{{ $t(`about.tipsSystem.${feature}.title`) }}</div>
          <div class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t(`about.tipsSystem.${feature}.text`) }}</div>
        </div>
      </div>

      <!-- Bearer warning: the whole point, and the whole risk -->
      <div class="p-4 bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg">
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-2">{{ $t('about.tipsSystem.callout.title') }}</h3>
        <p class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t('about.tipsSystem.callout.text') }}</p>
      </div>

      <!-- Thirteen years of the same idea; the predecessor's domain now points at this page. -->
      <div class="p-4 border border-neutral-200 dark:border-neutral-800 rounded-lg">
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-2">{{ $t('about.tipsSystem.lineage.title') }}</h3>
        <p class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t('about.tipsSystem.lineage.text') }}</p>
        <a
          href="https://bctip.org" target="_blank" rel="noopener"
          class="inline-flex items-center gap-1 mt-2 text-sm font-medium text-secondary hover:underline"
        >
          bctip.org<ExternalLink class="w-3.5 h-3.5" />
        </a>
      </div>

      <!-- The docs page is where a reader is already convinced — give them the door. -->
      <div class="flex flex-col sm:flex-row sm:items-center gap-3 p-4 sm:p-5 border border-primary/60 bg-primary/10 dark:bg-primary/5 rounded-lg">
        <p class="flex-1 text-sm font-medium text-neutral-800 dark:text-neutral-200">{{ $t('about.tipsSystem.cta.text') }}</p>
        <UiButton :to="ctaTo" :icon="Printer" class="shrink-0">{{ $t('about.tipsSystem.cta.button') }}</UiButton>
      </div>

      <DocsPrevNext />
    </div>
  </div>
</template>

<script setup lang="ts">
import {Printer, ExternalLink} from 'lucide-vue-next'

const { t } = useI18n()
const localePath = useLocalePath()
const authStore = useAuthStore()

// Creating a batch needs an account; anonymous readers log in and land back on it.
const ctaTo = computed(() => authStore.isAuthenticated
  ? localePath('/tips/new')
  : localePath(`/login?redirect=${encodeURIComponent(localePath('/tips/new'))}`))
useHead({ title: computed(() => `${t('about.tipsSystem.title')} — Parahub`) })
useSeoMeta({
  description: computed(() => t('docs.tips_desc')),
  ogTitle: computed(() => `${t('about.tipsSystem.title')} — Parahub`),
  ogDescription: computed(() => t('docs.tips_desc')),
})
useDocsBreadcrumb(t('about.tipsSystem.title'), '/docs/tips')

const features = ['returns', 'noCustody', 'anyWallet', 'noAccount']

definePageMeta({ order: 2 })
</script>

<style scoped>
.prose-section {
  @apply text-neutral-700 dark:text-neutral-300 leading-relaxed;
}
</style>
