<template>
  <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
    <NuxtLink :to="localePath('/about')" class="inline-flex items-center gap-1 text-sm text-neutral-500 hover:text-neutral-900 dark:hover:text-neutral-100 mb-4">
      <ArrowLeft class="w-4 h-4" /> {{ $t('about.hero.subtitle', 'About') }}
    </NuxtLink>
    <div class="prose prose-base sm:prose-lg max-w-none break-words">
      <h1 class="text-2xl sm:text-3xl font-bold mb-6">{{ $t('terms.title') }}</h1>

      <div class="bg-neutral-50 dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-6 mb-8">
        <p class="text-neutral-700 dark:text-neutral-300 mb-0">
          <strong class="text-neutral-900 dark:text-neutral-100">{{ $t('terms.version') }}:</strong> 1.0<br>
          <strong class="text-neutral-900 dark:text-neutral-100">{{ $t('terms.effective_date') }}:</strong> {{ effectiveDate }}
        </p>
      </div>

      <UiAlert variant="warning" :title="$t('terms.important_notice.title')" class="mb-8">
        <p v-html="importantNoticeText"></p>
      </UiAlert>

      <h2 class="text-xl sm:text-2xl font-semibold mt-8 sm:mt-12 mb-3 sm:mb-4">{{ $t('terms.sections.about.title') }}</h2>
      <p class="mb-8">{{ $t('terms.sections.about.text') }}</p>

      <h2 class="text-xl sm:text-2xl font-semibold mt-8 sm:mt-12 mb-3 sm:mb-4">{{ $t('terms.sections.acceptance.title') }}</h2>
      <ul class="space-y-2 mb-8">
        <li>{{ $t('terms.sections.acceptance.item1') }}</li>
        <li>{{ $t('terms.sections.acceptance.item2') }}</li>
        <li>{{ $t('terms.sections.acceptance.item3') }}</li>
      </ul>

      <h2 class="text-xl sm:text-2xl font-semibold mt-8 sm:mt-12 mb-3 sm:mb-4">{{ $t('terms.sections.responsibilities.title') }}</h2>

      <h3 class="text-lg sm:text-xl font-semibold mt-6 sm:mt-8 mb-2 sm:mb-3">{{ $t('terms.sections.responsibilities.keys.title') }}</h3>
      <p class="mb-6" v-html="keysResponsibilityText"></p>

      <h3 class="text-lg sm:text-xl font-semibold mt-6 sm:mt-8 mb-2 sm:mb-3">{{ $t('terms.sections.responsibilities.signatures.title') }}</h3>
      <p class="mb-6">{{ $t('terms.sections.responsibilities.signatures.text') }}</p>

      <h3 class="text-lg sm:text-xl font-semibold mt-6 sm:mt-8 mb-2 sm:mb-3">{{ $t('terms.sections.responsibilities.content.title') }}</h3>
      <p class="mb-6">{{ $t('terms.sections.responsibilities.content.text') }}</p>

      <h3 class="text-lg sm:text-xl font-semibold mt-6 sm:mt-8 mb-2 sm:mb-3">{{ $t('terms.sections.responsibilities.imagery.title') }}</h3>
      <p class="mb-6">{{ $t('terms.sections.responsibilities.imagery.text') }}</p>

      <h3 class="text-lg sm:text-xl font-semibold mt-6 sm:mt-8 mb-2 sm:mb-3">{{ $t('terms.sections.responsibilities.compliance.title') }}</h3>
      <p class="mb-6">{{ $t('terms.sections.responsibilities.compliance.text') }}</p>

      <h3 class="text-lg sm:text-xl font-semibold mt-6 sm:mt-8 mb-2 sm:mb-3">{{ $t('terms.sections.responsibilities.security.title') }}</h3>
      <p class="mb-6">{{ $t('terms.sections.responsibilities.security.text') }}</p>

      <h2 class="text-xl sm:text-2xl font-semibold mt-8 sm:mt-12 mb-3 sm:mb-4">{{ $t('terms.sections.disclaimer.title') }}</h2>

      <h3 class="text-lg sm:text-xl font-semibold mt-6 sm:mt-8 mb-2 sm:mb-3">{{ $t('terms.sections.disclaimer.as_is.title') }}</h3>
      <p class="mb-6">{{ $t('terms.sections.disclaimer.as_is.text') }}</p>

      <h3 class="text-lg sm:text-xl font-semibold mt-6 sm:mt-8 mb-2 sm:mb-3">{{ $t('terms.sections.disclaimer.no_liability.title') }}</h3>
      <ul class="space-y-2 mb-6">
        <li v-html="noLiabilityItem1"></li>
        <li v-html="noLiabilityItem2"></li>
        <li v-html="noLiabilityItem3"></li>
        <li v-html="noLiabilityItem4"></li>
        <li v-html="noLiabilityItem5"></li>
      </ul>

      <h3 class="text-lg sm:text-xl font-semibold mt-6 sm:mt-8 mb-2 sm:mb-3">{{ $t('terms.sections.disclaimer.max_liability.title') }}</h3>
      <p class="mb-6">{{ $t('terms.sections.disclaimer.max_liability.text') }}</p>

      <h2 class="text-xl sm:text-2xl font-semibold mt-8 sm:mt-12 mb-3 sm:mb-4">{{ $t('terms.sections.operator_rights.title') }}</h2>
      <p class="mb-4">{{ $t('terms.sections.operator_rights.intro') }}</p>
      <ul class="space-y-2 mb-8">
        <li>{{ $t('terms.sections.operator_rights.item1') }}</li>
        <li>{{ $t('terms.sections.operator_rights.item2') }}</li>
        <li>{{ $t('terms.sections.operator_rights.item3') }}</li>
        <li>{{ $t('terms.sections.operator_rights.item4') }}</li>
      </ul>

      <h2 class="text-xl sm:text-2xl font-semibold mt-8 sm:mt-12 mb-3 sm:mb-4">{{ $t('terms.sections.modifications.title') }}</h2>
      <p class="mb-8">{{ $t('terms.sections.modifications.text') }}</p>

      <h2 class="text-xl sm:text-2xl font-semibold mt-8 sm:mt-12 mb-3 sm:mb-4">{{ $t('terms.sections.law.title') }}</h2>
      <p class="mb-8">{{ $t('terms.sections.law.text') }}</p>

      <h2 class="text-xl sm:text-2xl font-semibold mt-8 sm:mt-12 mb-3 sm:mb-4">{{ $t('terms.sections.contact.title') }}</h2>
      <p class="mb-4" v-html="contactText"></p>
      <address class="not-italic bg-neutral-50 dark:bg-neutral-800 border-l-4 border-secondary dark:border-secondary-400 p-4 rounded-r mb-8">
        <strong>Parahub - Associação</strong><br>
        NIPC: 519046161<br>
        Rua das Regueiras 78, Podame, Monção, 4950-670, Portugal<br>
        Email: <a href="mailto:info@parahub.io" class="text-secondary dark:text-secondary-400 hover:text-secondary-700 dark:hover:text-secondary-300">info@parahub.io</a>
      </address>
    </div>
  </div>
</template>

<script setup lang="ts">

const { t, locale } = useI18n()
const localePath = useLocalePath()

const effectiveDate = computed(() => {
  const date = new Date('2026-04-08')
  const options: Intl.DateTimeFormatOptions = {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  }
  return date.toLocaleDateString(locale.value === 'pt' ? 'pt-PT' : locale.value, options)
})

// Computed properties for interpolated text
// Pass plain text to t() parameters, then add HTML after
const importantNoticeText = computed(() => {
  const text = t('terms.important_notice.text')
  // Manual string replacement (not using t() parameters to avoid SSR issues)
  return text
    .replace('__OPERATOR__', `<strong>${t('terms.important_notice.operator')}</strong>`)
    .replace('__MANIFESTO__', `<a href="${localePath('/manifest')}" class="underline">${t('terms.important_notice.manifesto')}</a>`)
    .replace('__CODE_OF_CONDUCT__', `<a href="${localePath('/about/code-of-conduct')}" class="underline">${t('terms.important_notice.code_of_conduct')}</a>`)
    .replace('__ESTATUTOS__', `<a href="${localePath('/estatutos')}" class="underline">${t('terms.important_notice.estatutos')}</a>`)
})

const keysResponsibilityText = computed(() => {
  return t('terms.sections.responsibilities.keys.text', {
    never: `<strong>${t('terms.sections.responsibilities.keys.never')}</strong>`
  })
})

const noLiabilityItem1 = computed(() => {
  return t('terms.sections.disclaimer.no_liability.item1', {
    is_not_liable: `<strong>${t('terms.sections.disclaimer.no_liability.is_not_liable')}</strong>`
  })
})

const noLiabilityItem2 = computed(() => {
  return t('terms.sections.disclaimer.no_liability.item2', {
    is_not_party: `<strong>${t('terms.sections.disclaimer.no_liability.is_not_party')}</strong>`
  })
})

const noLiabilityItem3 = computed(() => {
  return t('terms.sections.disclaimer.no_liability.item3', {
    does_not_control: `<strong>${t('terms.sections.disclaimer.no_liability.does_not_control')}</strong>`
  })
})

const noLiabilityItem4 = computed(() => {
  return t('terms.sections.disclaimer.no_liability.item4', {
    is_not_responsible: `<strong>${t('terms.sections.disclaimer.no_liability.is_not_responsible')}</strong>`
  })
})

const noLiabilityItem5 = computed(() => {
  return t('terms.sections.disclaimer.no_liability.item5', {
    is_not_responsible: `<strong>${t('terms.sections.disclaimer.no_liability.is_not_responsible')}</strong>`
  })
})

const contactText = computed(() => {
  const email = t('terms.sections.contact.email')
  return t('terms.sections.contact.text', {
    email: `<a href="mailto:${email}" class="text-secondary dark:text-secondary-400 hover:text-secondary-700 dark:hover:text-secondary-300">${email}</a>`
  })
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

.prose h3 {
  @apply text-neutral-800 dark:text-neutral-200;
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

.prose code {
  @apply bg-neutral-100 dark:bg-neutral-800 px-1 py-0.5 rounded text-sm;
  word-break: break-all;
}

.prose a {
  @apply underline decoration-1 underline-offset-2 transition-colors;
  word-break: break-word;
}

.prose address {
  word-break: break-word;
}
</style>