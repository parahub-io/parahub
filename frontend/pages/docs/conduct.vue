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
          <h1 class="inline text-neutral-900 font-semibold text-lg sm:text-xl">{{ $t('footer.code_of_conduct') }}</h1>
        </nav>
      </div>
    </div>

    <div class="max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-12">
      <div class="bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 rounded-lg p-4 mb-8 text-sm text-neutral-700 dark:text-neutral-300">
        <strong class="text-neutral-900 dark:text-neutral-100">{{ $t('codeOfConduct.version') }}</strong> 1.0<br>
        <strong class="text-neutral-900 dark:text-neutral-100">{{ $t('codeOfConduct.effectiveDate') }}</strong> {{ effectiveDate }}
      </div>

      <div class="prose-section space-y-10">
        <section v-for="i in 7" :key="i">
          <h2 class="text-lg font-bold text-neutral-900 dark:text-white mb-3 pb-2 border-b border-neutral-200 dark:border-neutral-800">
            {{ i }}. {{ $t(`codeOfConduct.sections.${i}.title`) }}
          </h2>

          <template v-if="i === 1">
            <p>{{ $t('codeOfConduct.sections.1.content') }}</p>
          </template>

          <template v-else-if="i === 2">
            <p class="mb-3">{{ $t('codeOfConduct.sections.2.intro') }}</p>
            <ul class="list-disc pl-6 space-y-1.5">
              <li v-for="(item, idx) in $tm('codeOfConduct.sections.2.positive')" :key="idx" v-html="item" />
            </ul>
          </template>

          <template v-else-if="i === 3">
            <p class="mb-3">{{ $t('codeOfConduct.sections.3.intro') }}</p>
            <ul class="list-disc pl-6 space-y-1.5">
              <li v-for="(item, idx) in $tm('codeOfConduct.sections.3.list')" :key="idx" v-html="item" />
            </ul>
          </template>

          <template v-else-if="i === 4">
            <p class="mb-3">{{ $t('codeOfConduct.sections.4.intro') }}</p>
            <ul class="list-disc pl-6 space-y-1.5 mb-3">
              <li v-for="(item, idx) in $tm('codeOfConduct.sections.4.list')" :key="idx">{{ item }}</li>
            </ul>
            <p>{{ $t('codeOfConduct.sections.4.outro') }}</p>
          </template>

          <template v-else-if="i === 5">
            <p class="mb-3" v-html="$t('codeOfConduct.sections.5.intro')" />
            <p>{{ $t('codeOfConduct.sections.5.details') }}</p>
          </template>

          <template v-else-if="i === 6">
            <p class="mb-3">{{ $t('codeOfConduct.sections.6.intro') }}</p>
            <ul class="list-disc pl-6 space-y-1.5 mb-3">
              <li v-for="(item, idx) in $tm('codeOfConduct.sections.6.list')" :key="idx">{{ item }}</li>
            </ul>
            <p>{{ $t('codeOfConduct.sections.6.outro') }}</p>
          </template>

          <template v-else-if="i === 7">
            <p class="mb-3">{{ $t('codeOfConduct.sections.7.intro') }}</p>
            <p>{{ $t('codeOfConduct.sections.7.outro') }}</p>
          </template>
        </section>

        <section>
          <h2 class="text-lg font-bold text-neutral-900 dark:text-white mb-3 pb-2 border-b border-neutral-200 dark:border-neutral-800">
            {{ $t('codeOfConduct.contact.title') }}
          </h2>
          <address class="not-italic bg-neutral-50 dark:bg-neutral-900 border-l-4 border-primary/50 p-4 rounded-r text-sm">
            <strong class="text-neutral-900 dark:text-neutral-100">{{ $t('codeOfConduct.contact.organization') }}</strong><br>
            <span class="text-neutral-600 dark:text-neutral-400">{{ $t('codeOfConduct.contact.location') }}</span><br>
            <strong class="text-neutral-900 dark:text-neutral-100">{{ $t('codeOfConduct.contact.reportTo') }}</strong>
            <a href="mailto:support@parahub.io" class="text-link">support&#64;parahub.io</a><br>
            <strong class="text-neutral-900 dark:text-neutral-100">{{ $t('codeOfConduct.contact.generalInquiries') }}</strong>
            <a href="mailto:support@parahub.io" class="text-link">support&#64;parahub.io</a>
          </address>
        </section>
      </div>
      <DocsPrevNext />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ChevronRight } from 'lucide-vue-next'

const { t, locale } = useI18n()
const localePath = useLocalePath()
useHead({ title: computed(() => `${t('footer.code_of_conduct')} — Parahub`) })
useSeoMeta({
  description: computed(() => t('docs.conduct_desc')),
  ogTitle: computed(() => `${t('footer.code_of_conduct')} — Parahub`),
  ogDescription: computed(() => t('docs.conduct_desc')),
})
useDocsBreadcrumb(t('footer.code_of_conduct'), '/docs/conduct')

const effectiveDate = computed(() => {
  const date = new Date('2025-10-20')
  const options: Intl.DateTimeFormatOptions = {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  }
  return date.toLocaleDateString(locale.value === 'pt' ? 'pt-PT' : locale.value, options)
})

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
