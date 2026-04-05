<template>
  <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
    <NuxtLink :to="localePath('/about')" class="inline-flex items-center gap-1 text-sm text-neutral-500 hover:text-neutral-900 dark:hover:text-neutral-100 mb-4">
      <ArrowLeft class="w-4 h-4" /> {{ $t('about.hero.subtitle', 'About') }}
    </NuxtLink>
    <div class="prose prose-lg max-w-none dark:prose-invert">
      <h1 class="text-2xl sm:text-3xl font-bold mb-6 text-neutral-900 dark:text-neutral-100">{{ $t('codeOfConduct.title') }}</h1>

      <div class="bg-neutral-50 dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-6 mb-8">
        <p class="text-neutral-700 dark:text-neutral-300 mb-0">
          <strong class="text-neutral-900 dark:text-neutral-100">{{ $t('codeOfConduct.version') }}</strong> 1.0<br>
          <strong class="text-neutral-900 dark:text-neutral-100">{{ $t('codeOfConduct.effectiveDate') }}</strong> {{ effectiveDate }}
        </p>
      </div>

      <h2 class="text-2xl font-semibold mt-12 mb-4 text-neutral-900 dark:text-neutral-100 border-b border-neutral-200 dark:border-neutral-700 pb-2">
        1. {{ $t('codeOfConduct.sections.1.title') }}
      </h2>
      <p class="mb-8 text-neutral-800 dark:text-neutral-200">
        {{ $t('codeOfConduct.sections.1.content') }}
      </p>

      <h2 class="text-2xl font-semibold mt-12 mb-4 text-neutral-900 dark:text-neutral-100 border-b border-neutral-200 dark:border-neutral-700 pb-2">
        2. {{ $t('codeOfConduct.sections.2.title') }}
      </h2>
      <p class="mb-4 text-neutral-800 dark:text-neutral-200">{{ $t('codeOfConduct.sections.2.intro') }}</p>
      <ul class="space-y-2 mb-8 list-disc pl-6">
        <li v-for="(item, idx) in $tm('codeOfConduct.sections.2.positive')" :key="idx" class="leading-relaxed text-neutral-800 dark:text-neutral-200" v-html="item"></li>
      </ul>

      <h2 class="text-2xl font-semibold mt-12 mb-4 text-neutral-900 dark:text-neutral-100 border-b border-neutral-200 dark:border-neutral-700 pb-2">
        3. {{ $t('codeOfConduct.sections.3.title') }}
      </h2>
      <p class="mb-4 text-neutral-800 dark:text-neutral-200">{{ $t('codeOfConduct.sections.3.intro') }}</p>
      <ul class="space-y-2 mb-8 list-disc pl-6">
        <li v-for="(item, idx) in $tm('codeOfConduct.sections.3.list')" :key="idx" class="leading-relaxed text-neutral-800 dark:text-neutral-200" v-html="item"></li>
      </ul>

      <h2 class="text-2xl font-semibold mt-12 mb-4 text-neutral-900 dark:text-neutral-100 border-b border-neutral-200 dark:border-neutral-700 pb-2">
        4. {{ $t('codeOfConduct.sections.4.title') }}
      </h2>
      <p class="mb-4 text-neutral-800 dark:text-neutral-200">{{ $t('codeOfConduct.sections.4.intro') }}</p>
      <ul class="space-y-2 mb-4 list-disc pl-6">
        <li v-for="(item, idx) in $tm('codeOfConduct.sections.4.list')" :key="idx" class="text-neutral-800 dark:text-neutral-200">{{ item }}</li>
      </ul>
      <p class="mb-8 text-neutral-800 dark:text-neutral-200">
        {{ $t('codeOfConduct.sections.4.outro') }}
      </p>

      <h2 class="text-2xl font-semibold mt-12 mb-4 text-neutral-900 dark:text-neutral-100 border-b border-neutral-200 dark:border-neutral-700 pb-2">
        5. {{ $t('codeOfConduct.sections.5.title') }}
      </h2>
      <p class="mb-4 text-neutral-800 dark:text-neutral-200" v-html="$t('codeOfConduct.sections.5.intro')"></p>
      <p class="mb-8 text-neutral-800 dark:text-neutral-200">
        {{ $t('codeOfConduct.sections.5.details') }}
      </p>

      <h2 class="text-2xl font-semibold mt-12 mb-4 text-neutral-900 dark:text-neutral-100 border-b border-neutral-200 dark:border-neutral-700 pb-2">
        6. {{ $t('codeOfConduct.sections.6.title') }}
      </h2>
      <p class="mb-4 text-neutral-800 dark:text-neutral-200">{{ $t('codeOfConduct.sections.6.intro') }}</p>
      <ul class="space-y-2 mb-4 list-disc pl-6">
        <li v-for="(item, idx) in $tm('codeOfConduct.sections.6.list')" :key="idx" class="text-neutral-800 dark:text-neutral-200">{{ item }}</li>
      </ul>
      <p class="mb-8 text-neutral-800 dark:text-neutral-200">
        {{ $t('codeOfConduct.sections.6.outro') }}
      </p>

      <h2 class="text-2xl font-semibold mt-12 mb-4 text-neutral-900 dark:text-neutral-100 border-b border-neutral-200 dark:border-neutral-700 pb-2">
        7. {{ $t('codeOfConduct.sections.7.title') }}
      </h2>
      <p class="mb-4 text-neutral-800 dark:text-neutral-200">
        {{ $t('codeOfConduct.sections.7.intro') }}
      </p>
      <p class="mb-8 text-neutral-800 dark:text-neutral-200">
        {{ $t('codeOfConduct.sections.7.outro') }}
      </p>

      <h2 class="text-2xl font-semibold mt-12 mb-4 text-neutral-900 dark:text-neutral-100 border-b border-neutral-200 dark:border-neutral-700 pb-2">
        {{ $t('codeOfConduct.contact.title') }}
      </h2>
      <address class="not-italic bg-neutral-50 dark:bg-neutral-800 border-l-4 border-secondary p-4 rounded-r mb-8">
        <strong class="text-neutral-900 dark:text-neutral-100">{{ $t('codeOfConduct.contact.organization') }}</strong><br>
        <span class="text-neutral-700 dark:text-neutral-300">NIPC: 519046161</span><br>
        <span class="text-neutral-700 dark:text-neutral-300">{{ $t('codeOfConduct.contact.location') }}</span><br>
        <strong class="text-neutral-900 dark:text-neutral-100">{{ $t('codeOfConduct.contact.reportTo') }}</strong> <a :href="`mailto:${emailAddress}`" class="text-secondary dark:text-secondary-400 hover:text-secondary-700 dark:hover:text-secondary-300">{{ emailAddress }}</a><br>
        <strong class="text-neutral-900 dark:text-neutral-100">{{ $t('codeOfConduct.contact.generalInquiries') }}</strong> <a :href="`mailto:${emailAddress}`" class="text-secondary dark:text-secondary-400 hover:text-secondary-700 dark:hover:text-secondary-300">{{ emailAddress }}</a>
      </address>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const { locale } = useI18n()
const localePath = useLocalePath()

const effectiveDate = computed(() => {
  const date = new Date('2026-04-12')
  const options: Intl.DateTimeFormatOptions = {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  }
  return date.toLocaleDateString(locale.value === 'pt' ? 'pt-PT' : locale.value, options)
})

const emailAddress = computed(() => {
  return 'support@parahub.io'
})

definePageMeta({
})
</script>

<style scoped>
.prose {
  @apply text-neutral-800 dark:text-neutral-200;
}

.prose h1 {
  @apply text-neutral-900 dark:text-neutral-100;
}

.prose h2 {
  @apply text-neutral-900 dark:text-neutral-100 border-b border-neutral-200 dark:border-neutral-700 pb-2;
}

.prose h3 {
  @apply text-neutral-800 dark:text-neutral-100;
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

.prose code {
  @apply bg-neutral-100 dark:bg-neutral-800 px-1 py-0.5 rounded text-sm;
}

.prose a {
  @apply underline decoration-1 underline-offset-2 transition-colors;
}
</style>
