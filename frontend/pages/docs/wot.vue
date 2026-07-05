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
          <h1 class="inline text-neutral-900 font-semibold text-lg sm:text-xl">{{ $t('about.wotSystem.title') }}</h1>
        </nav>
      </div>
    </div>

    <div class="max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-12">
      <div class="prose-section space-y-8">

        <div>
          <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-2">{{ $t('about.wotSystem.problem.title') }}</h3>
          <p>{{ $t('about.wotSystem.problem.text') }}</p>
        </div>

        <img
          src="/images/docs/wot.webp"
          alt=""
          aria-hidden="true"
          width="1200"
          height="670"
          loading="lazy"
          class="w-full h-auto rounded-xl ring-1 ring-neutral-900/10 dark:ring-white/10"
        />

        <div>
          <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-3">{{ $t('about.wotSystem.how.title') }}</h3>
          <ol class="list-decimal list-inside space-y-2.5 text-neutral-700 dark:text-neutral-300">
            <li>{{ $t('about.wotSystem.how.step1') }}</li>
            <li>{{ $t('about.wotSystem.how.step2') }}</li>
            <li>{{ $t('about.wotSystem.how.step3') }}</li>
            <li>{{ $t('about.wotSystem.how.step4') }}</li>
          </ol>
        </div>

        <UiAlert variant="warning" :title="$t('about.wotSystem.stake.title')">
          {{ $t('about.wotSystem.stake.text') }}
        </UiAlert>

        <div>
          <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-3">{{ $t('about.wotSystem.unlocks.title') }}</h3>
          <ul class="space-y-2 text-sm text-neutral-700 dark:text-neutral-300">
            <li class="flex items-start gap-2">
              <span class="text-neutral-400 mt-0.5">○</span>
              <span>{{ $t('about.wotSystem.unlocks.basic') }}</span>
            </li>
            <li class="flex items-start gap-2">
              <span class="text-secondary mt-0.5">●</span>
              <span>{{ $t('about.wotSystem.unlocks.wot1') }}</span>
            </li>
            <li class="flex items-start gap-2">
              <span class="text-green-500 mt-0.5">●</span>
              <span>{{ $t('about.wotSystem.unlocks.wot2') }}</span>
            </li>
            <li class="flex items-start gap-2">
              <span class="text-yellow-500 mt-0.5">●</span>
              <span>{{ $t('about.wotSystem.unlocks.wot3') }}</span>
            </li>
          </ul>
        </div>

      </div>
      <DocsPrevNext />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ChevronRight, ShieldAlert } from 'lucide-vue-next'

const { t } = useI18n()
const localePath = useLocalePath()
useHead({ title: computed(() => `${t('about.wotSystem.title')} — Parahub`) })
useSeoMeta({
  description: computed(() => t('docs.wot_desc')),
  ogTitle: computed(() => `${t('about.wotSystem.title')} — Parahub`),
  ogDescription: computed(() => t('docs.wot_desc')),
})
useDocsBreadcrumb(t('about.wotSystem.title'), '/docs/wot')

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
