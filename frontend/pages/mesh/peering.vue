<template>
  <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
    <NuxtLink :to="localePath('/mesh')" class="inline-flex items-center gap-1 text-sm text-neutral-500 hover:text-neutral-900 dark:hover:text-neutral-100 mb-4">
      <ArrowLeft class="w-4 h-4" /> {{ $t('mesh.title') }}
    </NuxtLink>

    <div class="prose prose-lg max-w-none dark:prose-invert">
      <h1 class="text-2xl sm:text-3xl font-bold mb-6 text-neutral-900 dark:text-neutral-100">{{ $t('mesh.peering.title') }}</h1>

      <UiAlert variant="warning" :title="$t('mesh.peering.draft_title')" class="mb-6">
        {{ $t('mesh.peering.draft_text') }}
      </UiAlert>

      <p class="mb-4 text-neutral-800 dark:text-neutral-200">{{ $t('mesh.peering.intro') }}</p>
      <p class="mb-8 text-neutral-800 dark:text-neutral-200" v-html="adoptedText"></p>

      <!-- Base: Pico Peering Agreement v1.0 -->
      <h2 class="text-2xl font-semibold mt-12 mb-4 text-neutral-900 dark:text-neutral-100 border-b border-neutral-200 dark:border-neutral-700 pb-2">
        {{ $t('mesh.peering.ppa_heading') }}
      </h2>

      <h3 class="text-lg font-semibold mt-6 mb-2 text-neutral-800 dark:text-neutral-100">{{ $t('mesh.peering.preamble_title') }}</h3>
      <p v-for="(para, idx) in $tm('mesh.peering.preamble')" :key="'pre-' + idx" class="mb-4 text-neutral-800 dark:text-neutral-200">{{ para }}</p>

      <template v-for="n in 4" :key="'sec-' + n">
        <h3 class="text-lg font-semibold mt-8 mb-2 text-neutral-800 dark:text-neutral-100">{{ n }}. {{ $t(`mesh.peering.s${n}_title`) }}</h3>
        <ul class="space-y-2 mb-4 list-disc pl-6">
          <li v-for="(item, idx) in $tm(`mesh.peering.s${n}`)" :key="'s' + n + '-' + idx" class="leading-relaxed text-neutral-800 dark:text-neutral-200">{{ item }}</li>
        </ul>
      </template>

      <!-- Section 5 — Parahub local amendments -->
      <h3 class="text-lg font-semibold mt-8 mb-2 text-neutral-800 dark:text-neutral-100">5. {{ $t('mesh.peering.s5_title') }}</h3>
      <p class="mb-3 text-neutral-800 dark:text-neutral-200">{{ $t('mesh.peering.amend_intro') }}</p>
      <ul class="space-y-2 mb-4 list-disc pl-6">
        <li v-for="(item, idx) in $tm('mesh.peering.amend')" :key="'amend-' + idx" class="leading-relaxed text-neutral-800 dark:text-neutral-200" v-html="item"></li>
      </ul>

      <!-- Definitions -->
      <h2 class="text-2xl font-semibold mt-12 mb-4 text-neutral-900 dark:text-neutral-100 border-b border-neutral-200 dark:border-neutral-700 pb-2">
        {{ $t('mesh.peering.defs_title') }}
      </h2>
      <ul class="space-y-2 mb-8 list-disc pl-6">
        <li v-for="(item, idx) in $tm('mesh.peering.defs')" :key="'def-' + idx" class="leading-relaxed text-neutral-800 dark:text-neutral-200" v-html="item"></li>
      </ul>

      <!-- The PPA in practice -->
      <h2 class="text-2xl font-semibold mt-12 mb-4 text-neutral-900 dark:text-neutral-100 border-b border-neutral-200 dark:border-neutral-700 pb-2">
        {{ $t('mesh.peering.practice_title') }}
      </h2>
      <p class="mb-8 text-neutral-800 dark:text-neutral-200">{{ $t('mesh.peering.practice') }}</p>

      <!-- Attribution + source -->
      <p class="text-sm text-neutral-500 dark:text-neutral-400 border-t border-neutral-200 dark:border-neutral-700 pt-6" v-html="attributionText"></p>

      <address class="not-italic bg-neutral-50 dark:bg-neutral-800 border-l-4 border-secondary p-4 rounded-r mt-6 mb-8 text-sm">
        <strong class="text-neutral-900 dark:text-neutral-100">Parahub — Associação</strong><br>
        <span class="text-neutral-700 dark:text-neutral-300">NIPC: 519 190 904</span><br>
        <span class="text-neutral-700 dark:text-neutral-300">Rua das Regueiras 78, Podame, Monção, 4950-670, Portugal</span><br>
        <a href="mailto:info@parahub.io" class="text-secondary dark:text-secondary-400 hover:text-secondary-700 dark:hover:text-secondary-300">info@parahub.io</a>
      </address>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ArrowLeft } from 'lucide-vue-next'

const { t } = useI18n()
const localePath = useLocalePath()

definePageMeta({
  auth: false,
})

useHead({
  title: computed(() => `${t('mesh.peering.title')} — Parahub`),
})

useSeoMeta({
  description: computed(() => t('mesh.peering.meta_desc')),
})

const PICOPEER_URL = 'https://picopeer.net'
const CANONICAL_URL = 'https://github.com/freifunk/PicoPeeringAgreement/blob/master/PPAv1.0/PPA1.0-en.md'

const adoptedText = computed(() =>
  t('mesh.peering.adopted', {
    ppa: `<a href="${PICOPEER_URL}" target="_blank" rel="noopener noreferrer" class="text-secondary hover:underline">Pico Peering Agreement v1.0</a>`,
  })
)

const attributionText = computed(() =>
  t('mesh.peering.attribution', {
    source: `<a href="${CANONICAL_URL}" target="_blank" rel="noopener noreferrer" class="text-secondary hover:underline">picopeer.net</a>`,
  })
)
</script>

<style scoped>
.prose {
  @apply text-neutral-800 dark:text-neutral-200;
}
.prose h1 {
  @apply text-neutral-900 dark:text-neutral-100;
}
.prose h2 {
  @apply text-neutral-900 dark:text-neutral-100;
}
.prose p {
  @apply leading-relaxed;
}
.prose ul {
  @apply list-disc pl-6;
}
.prose li {
  @apply leading-relaxed;
}
.prose strong {
  @apply text-neutral-900 dark:text-neutral-100 font-semibold;
}
.prose a {
  @apply underline decoration-1 underline-offset-2 transition-colors;
}
</style>
