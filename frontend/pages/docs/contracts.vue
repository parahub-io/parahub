<template>
  <div class="min-h-full bg-white dark:bg-neutral-950">
    <DocsHeader :title="$t('about.contractsSystem.title')" />

    <div class="max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-12 space-y-8">

      <p class="prose-section">{{ $t('about.contractsSystem.intro') }}</p>

      <div>
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-3">{{ $t('about.contractsSystem.how.title') }}</h3>
        <ol class="space-y-2 text-neutral-700 dark:text-neutral-300">
          <li v-for="i in 5" :key="i" class="flex gap-3">
            <span class="flex-shrink-0 w-5 h-5 rounded-full bg-primary text-neutral-900 text-xs font-bold flex items-center justify-center mt-0.5">{{ i }}</span>
            <span>{{ $t(`about.contractsSystem.how.step${i}`) }}</span>
          </li>
        </ol>
      </div>

      <!-- Only the fingerprint is stored -->
      <div class="p-4 bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg">
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-2">{{ $t('about.contractsSystem.privacy.title') }}</h3>
        <p class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t('about.contractsSystem.privacy.text') }}</p>
      </div>

      <div class="grid sm:grid-cols-2 gap-4">
        <div v-for="feature in features" :key="feature" class="p-4 border border-neutral-200 dark:border-neutral-800 rounded-lg">
          <div class="font-semibold text-neutral-900 dark:text-white mb-1">{{ $t(`about.contractsSystem.${feature}.title`) }}</div>
          <div class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t(`about.contractsSystem.${feature}.text`) }}</div>
        </div>
      </div>

      <div>
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-2">{{ $t('about.contractsSystem.disputes.title') }}</h3>
        <p class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t('about.contractsSystem.disputes.text') }}</p>
      </div>

      <!-- Related docs -->
      <div class="border border-neutral-200 dark:border-neutral-800 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-800">
        <NuxtLink
          v-for="link in related"
          :key="link.to"
          :to="localePath(link.to)"
          class="flex items-center gap-3 p-4 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors group"
        >
          <component :is="link.icon" class="w-5 h-5 text-neutral-400 group-hover:text-neutral-700 dark:group-hover:text-neutral-200 flex-shrink-0" />
          <div class="flex-1 min-w-0">
            <div class="font-semibold text-neutral-900 dark:text-white">{{ $t(link.titleKey) }}</div>
            <div class="text-sm text-neutral-500 dark:text-neutral-400 mt-0.5">{{ $t(link.descKey) }}</div>
          </div>
          <ChevronRight class="w-4 h-4 text-neutral-300 dark:text-neutral-600 group-hover:text-neutral-500 dark:group-hover:text-neutral-400 flex-shrink-0" />
        </NuxtLink>
      </div>

      <DocsPrevNext />
    </div>
  </div>
</template>

<script setup lang="ts">
import { Scale, KeyRound, ChevronRight } from 'lucide-vue-next'

const { t } = useI18n()
const localePath = useLocalePath()
useHead({ title: computed(() => `${t('about.contractsSystem.title')} — Parahub`) })
useSeoMeta({
  description: computed(() => t('docs.contracts_desc')),
  ogTitle: computed(() => `${t('about.contractsSystem.title')} — Parahub`),
  ogDescription: computed(() => t('docs.contracts_desc')),
})
useDocsBreadcrumb(t('about.contractsSystem.title'), '/docs/contracts')

const features = ['linking', 'proof']

const related = [
  { to: '/docs/arbitration', icon: Scale, titleKey: 'about.arbitration.title', descKey: 'docs.arbitration_desc' },
  { to: '/docs/crypto', icon: KeyRound, titleKey: 'about.cryptoProofs.title', descKey: 'docs.crypto_desc' },
]

definePageMeta({ order: 2 })
</script>

<style scoped>
.prose-section {
  @apply text-neutral-700 dark:text-neutral-300 leading-relaxed;
}
</style>
