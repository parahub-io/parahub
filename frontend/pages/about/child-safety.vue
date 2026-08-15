<template>
  <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
    <NuxtLink :to="localePath('/about')" class="inline-flex items-center gap-1 text-sm text-neutral-500 hover:text-neutral-900 dark:hover:text-neutral-100 mb-4">
      <ArrowLeft class="w-4 h-4" /> {{ $t('about.hero.subtitle', 'About') }}
    </NuxtLink>
    <div class="prose prose-base sm:prose-lg max-w-none break-words">
      <h1 class="text-2xl sm:text-3xl font-bold mb-6">{{ $t('childsafety.title') }}</h1>

      <p class="mb-8">{{ intro }}</p>

      <h2 class="text-xl sm:text-2xl font-semibold mt-8 sm:mt-12 mb-3 sm:mb-4">1. {{ $t('childsafety.commitment.title') }}</h2>
      <p class="mb-8">{{ $t('childsafety.commitment.text') }}</p>

      <h2 class="text-xl sm:text-2xl font-semibold mt-8 sm:mt-12 mb-3 sm:mb-4">2. {{ $t('childsafety.prohibited.title') }}</h2>
      <p class="mb-4">{{ $t('childsafety.prohibited.intro') }}</p>
      <ul class="space-y-2 mb-8">
        <li>{{ $t('childsafety.prohibited.item1') }}</li>
        <li>{{ $t('childsafety.prohibited.item2') }}</li>
        <li>{{ $t('childsafety.prohibited.item3') }}</li>
        <li>{{ $t('childsafety.prohibited.item4') }}</li>
        <li>{{ $t('childsafety.prohibited.item5') }}</li>
      </ul>

      <h2 class="text-xl sm:text-2xl font-semibold mt-8 sm:mt-12 mb-3 sm:mb-4">3. {{ $t('childsafety.reporting.title') }}</h2>
      <p class="mb-4">{{ $t('childsafety.reporting.text1') }}</p>
      <p class="mb-8">{{ $t('childsafety.reporting.text2') }}</p>

      <h2 class="text-xl sm:text-2xl font-semibold mt-8 sm:mt-12 mb-3 sm:mb-4">4. {{ $t('childsafety.enforcement.title') }}</h2>
      <p class="mb-4">{{ $t('childsafety.enforcement.intro') }}</p>
      <ul class="space-y-2 mb-8">
        <li>{{ $t('childsafety.enforcement.item1') }}</li>
        <li>{{ $t('childsafety.enforcement.item2') }}</li>
        <li>{{ $t('childsafety.enforcement.item3') }}</li>
        <li>{{ $t('childsafety.enforcement.item4') }}</li>
      </ul>

      <h2 class="text-xl sm:text-2xl font-semibold mt-8 sm:mt-12 mb-3 sm:mb-4">5. {{ $t('childsafety.authorities.title') }}</h2>
      <p class="mb-8">{{ $t('childsafety.authorities.text') }}</p>

      <h2 class="text-xl sm:text-2xl font-semibold mt-8 sm:mt-12 mb-3 sm:mb-4">6. {{ $t('childsafety.contact.title') }}</h2>
      <p class="mb-4">{{ $t('childsafety.contact.text') }}</p>
      <address class="not-italic bg-neutral-50 dark:bg-neutral-800 border-l-4 border-secondary dark:border-secondary-400 p-4 rounded-r mb-8">
        <strong>Parahub - Associação</strong><br>
        NIPC: 519 190 904<br>
        Rua das Regueiras 78, Podame, Monção, 4950-670, Portugal<br>
        <a href="mailto:info@parahub.io" class="text-secondary dark:text-secondary-400 hover:text-secondary-700 dark:hover:text-secondary-300">info@parahub.io</a>
      </address>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ArrowLeft } from 'lucide-vue-next'

const { t } = useI18n()
const localePath = useLocalePath()

const intro = computed(() =>
  t('childsafety.intro', { operator: 'Parahub - Associação' })
)

useHead({
  title: t('childsafety.title')
})
</script>

<style scoped>
.prose {
  @apply text-neutral-800 dark:text-neutral-200;
  word-wrap: break-word;
  overflow-wrap: break-word;
}

.prose h1 {
  @apply text-neutral-900 dark:text-neutral-100;
}

.prose h2 {
  @apply text-neutral-900 dark:text-neutral-100 border-b border-neutral-200 dark:border-neutral-700 pb-2;
}

.prose p {
  @apply leading-relaxed;
}

.prose ul {
  @apply list-disc pl-4 sm:pl-6;
}

.prose li {
  @apply leading-relaxed;
}

.prose strong {
  @apply text-neutral-900 dark:text-neutral-100 font-semibold;
}

.prose address {
  word-break: break-word;
}
</style>
