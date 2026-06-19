<template>
  <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
    <NuxtLink :to="localePath('/about')" class="inline-flex items-center gap-1 text-sm text-neutral-500 hover:text-neutral-900 dark:hover:text-neutral-100 mb-4">
      <ArrowLeft class="w-4 h-4" /> {{ $t('about.hero.subtitle', 'About') }}
    </NuxtLink>
    <div class="prose prose-base sm:prose-lg max-w-none break-words">
      <h1 class="text-2xl sm:text-3xl font-bold mb-6">{{ $t('privacy.title') }}</h1>

      <div class="bg-neutral-50 dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-6 mb-8">
        <p class="text-neutral-700 dark:text-neutral-300 mb-0">
          <strong class="text-neutral-900 dark:text-neutral-100">{{ $t('privacy.version') }}:</strong> 1.0<br>
          <strong class="text-neutral-900 dark:text-neutral-100">{{ $t('privacy.effective_date') }}:</strong> {{ effectiveDate }}
        </p>
      </div>

      <p>{{ privacyIntro }}</p>

      <h2 class="text-xl sm:text-2xl font-semibold mt-8 sm:mt-12 mb-3 sm:mb-4">1. {{ $t('privacy.sections.controller.title') }}</h2>
      <p class="mb-4">{{ $t('privacy.sections.controller.text') }}</p>
      <address class="not-italic bg-neutral-50 dark:bg-neutral-800 border-l-4 border-secondary dark:border-secondary-400 p-4 rounded-r mb-8">
        <strong>Parahub - Associação</strong><br>
        NIPC: 519046161<br>
        Rua das Regueiras 78, Podame, Monção, 4950-670, Portugal<br>
        {{ $t('privacy.sections.controller.email_label') }}: <a href="mailto:support@parahub.io" class="text-secondary dark:text-secondary-400 hover:text-secondary-700 dark:hover:text-secondary-300">support@parahub.io</a>
      </address>

      <h2 class="text-xl sm:text-2xl font-semibold mt-8 sm:mt-12 mb-3 sm:mb-4">2. {{ $t('privacy.sections.data_collected.title') }}</h2>
      <p class="mb-6">{{ $t('privacy.sections.data_collected.intro') }}</p>

      <h3 class="text-lg sm:text-xl font-semibold mt-6 sm:mt-8 mb-2 sm:mb-3">{{ $t('privacy.sections.data_collected.provided.title') }}</h3>
      <ul class="space-y-2 mb-6">
        <li><strong>{{ $t('privacy.sections.data_collected.provided.account_label') }}:</strong> {{ $t('privacy.sections.data_collected.provided.account') }}</li>
        <li><strong>{{ $t('privacy.sections.data_collected.provided.profile_label') }}:</strong> {{ $t('privacy.sections.data_collected.provided.profile') }}</li>
        <li><strong>{{ $t('privacy.sections.data_collected.provided.pgp_label') }}:</strong> <span v-html="pgpText"></span></li>
        <li><strong>{{ $t('privacy.sections.data_collected.provided.content_label') }}:</strong> {{ $t('privacy.sections.data_collected.provided.content') }}</li>
        <li><strong>Web of Trust (WoT):</strong> {{ $t('privacy.sections.data_collected.provided.wot') }}</li>
      </ul>

      <h3 class="text-lg sm:text-xl font-semibold mt-6 sm:mt-8 mb-2 sm:mb-3">{{ $t('privacy.sections.data_collected.automatic.title') }}</h3>
      <ul class="space-y-2 mb-6">
        <li><strong>{{ $t('privacy.sections.data_collected.automatic.logs_label') }}:</strong> {{ automaticLogs }}</li>
        <li><strong>{{ $t('privacy.sections.data_collected.automatic.session_label') }}:</strong> {{ $t('privacy.sections.data_collected.automatic.session') }}</li>
        <li><strong>Matrix:</strong> {{ matrixData }}</li>
      </ul>

      <h3 class="text-lg sm:text-xl font-semibold mt-6 sm:mt-8 mb-2 sm:mb-3">{{ $t('privacy.sections.data_collected.not_collected.title') }}</h3>
      <ul class="space-y-2 mb-6">
        <li>{{ $t('privacy.sections.data_collected.not_collected.sensitive') }}</li>
        <li>{{ $t('privacy.sections.data_collected.not_collected.location') }}</li>
        <li>{{ $t('privacy.sections.data_collected.not_collected.crypto') }}</li>
      </ul>

      <h2 class="text-xl sm:text-2xl font-semibold mt-8 sm:mt-12 mb-3 sm:mb-4">3. {{ $t('privacy.sections.legal_basis.title') }}</h2>
      <ul class="space-y-2 mb-6">
        <li><strong>{{ $t('privacy.sections.legal_basis.consent_label') }} (Art. 6(1)(a) GDPR):</strong> {{ $t('privacy.sections.legal_basis.consent') }}</li>
        <li><strong>{{ $t('privacy.sections.legal_basis.contract_label') }} (Art. 6(1)(b) GDPR):</strong> {{ $t('privacy.sections.legal_basis.contract') }}</li>
        <li><strong>{{ $t('privacy.sections.legal_basis.legitimate_label') }} (Art. 6(1)(f) GDPR):</strong> {{ $t('privacy.sections.legal_basis.legitimate') }}</li>
        <li><strong>{{ $t('privacy.sections.legal_basis.legal_label') }} (Art. 6(1)(c) GDPR):</strong> {{ $t('privacy.sections.legal_basis.legal') }}</li>
      </ul>

      <h2 class="text-xl sm:text-2xl font-semibold mt-8 sm:mt-12 mb-3 sm:mb-4">4. {{ $t('privacy.sections.usage.title') }}</h2>
      <ul class="space-y-2 mb-6">
        <li v-for="(purpose, index) in purposes" :key="index">
          {{ purpose }}
        </li>
      </ul>

      <h2 class="text-xl sm:text-2xl font-semibold mt-8 sm:mt-12 mb-3 sm:mb-4">5. {{ $t('privacy.sections.sharing.title') }}</h2>
      <ul class="space-y-2 mb-6">
        <li><strong>{{ $t('privacy.sections.sharing.federation_label') }}:</strong> {{ $t('privacy.sections.sharing.federation') }}</li>
        <li><strong>Matrix:</strong> {{ $t('privacy.sections.sharing.matrix') }}</li>
        <li><strong>{{ $t('privacy.sections.sharing.legal_label') }}:</strong> {{ $t('privacy.sections.sharing.legal') }}</li>
        <li><strong>{{ $t('privacy.sections.sharing.no_sale') }}</strong></li>
      </ul>

      <h2 class="text-xl sm:text-2xl font-semibold mt-8 sm:mt-12 mb-3 sm:mb-4">6. {{ $t('privacy.sections.storage.title') }}</h2>
      <ul class="space-y-2 mb-6">
        <li>{{ $t('privacy.sections.storage.measures') }}</li>
        <li>{{ $t('privacy.sections.storage.location') }}</li>
        <li>{{ $t('privacy.sections.storage.retention') }}</li>
      </ul>

      <h2 class="text-xl sm:text-2xl font-semibold mt-8 sm:mt-12 mb-3 sm:mb-4">7. {{ $t('privacy.sections.rights.title') }}</h2>
      <p class="mb-4">{{ $t('privacy.sections.rights.intro') }}</p>
      <ul class="space-y-2 mb-4">
        <li><strong>{{ $t('privacy.sections.rights.access_label') }} (Art. 15 GDPR):</strong> {{ $t('privacy.sections.rights.access') }}</li>
        <li><strong>{{ $t('privacy.sections.rights.rectification_label') }} (Art. 16 GDPR):</strong> {{ $t('privacy.sections.rights.rectification') }}</li>
        <li><strong>{{ $t('privacy.sections.rights.erasure_label') }} (Art. 17 GDPR):</strong> {{ $t('privacy.sections.rights.erasure') }}</li>
        <li><strong>{{ $t('privacy.sections.rights.restriction_label') }} (Art. 18 GDPR):</strong> {{ $t('privacy.sections.rights.restriction') }}</li>
        <li><strong>{{ $t('privacy.sections.rights.portability_label') }} (Art. 20 GDPR):</strong> {{ $t('privacy.sections.rights.portability') }}</li>
        <li><strong>{{ $t('privacy.sections.rights.object_label') }} (Art. 21 GDPR):</strong> {{ $t('privacy.sections.rights.object') }}</li>
        <li><strong>{{ $t('privacy.sections.rights.withdraw_label') }}:</strong> {{ $t('privacy.sections.rights.withdraw') }}</li>
        <li><strong>{{ $t('privacy.sections.rights.complaint_label') }} (Art. 77 GDPR):</strong> {{ $t('privacy.sections.rights.complaint') }}</li>
      </ul>
      <p class="mb-8" v-html="rightsContact"></p>

      <h2 class="text-xl sm:text-2xl font-semibold mt-8 sm:mt-12 mb-3 sm:mb-4">8. {{ $t('privacy.sections.cookies.title') }}</h2>
      <p class="mb-8">{{ $t('privacy.sections.cookies.text') }}</p>

      <h2 class="text-xl sm:text-2xl font-semibold mt-8 sm:mt-12 mb-3 sm:mb-4">9. {{ $t('privacy.sections.changes.title') }}</h2>
      <p class="mb-8">{{ $t('privacy.sections.changes.text') }}</p>

      <h2 class="text-xl sm:text-2xl font-semibold mt-8 sm:mt-12 mb-3 sm:mb-4">10. {{ $t('privacy.sections.contact.title') }}</h2>
      <p class="mb-4">{{ $t('privacy.sections.contact.text') }}</p>
      <address class="not-italic bg-neutral-50 dark:bg-neutral-800 border-l-4 border-secondary dark:border-secondary-400 p-4 rounded-r mb-8">
        <strong>Parahub - Associação</strong><br>
        NIPC: 519046161<br>
        Rua das Regueiras 78, Podame, Monção, 4950-670, Portugal<br>
        {{ $t('privacy.sections.contact.email_label') }}: <a href="mailto:support@parahub.io" class="text-secondary dark:text-secondary-400 hover:text-secondary-700 dark:hover:text-secondary-300">support@parahub.io</a>
      </address>
    </div>
  </div>
</template>

<script setup lang="ts">

const { t, tm, locale } = useI18n()
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
const privacyIntro = computed(() => {
  const text = t('privacy.intro')
  return text.replace('{operator}', 'Parahub - Associação')
})

const pgpText = computed(() => {
  const text = t('privacy.sections.data_collected.provided.pgp')
  const important = t('privacy.sections.data_collected.provided.pgp_important')
  return text.replace('{important}', `<strong>${important}</strong>`)
})

const automaticLogs = computed(() => {
  const text = t('privacy.sections.data_collected.automatic.logs')
  return text.replace('{days}', '30')
})

const matrixData = computed(() => {
  const text = t('privacy.sections.data_collected.automatic.matrix')
  return text.replace('{example}', '@local_name:instance.domain')
})

const rightsContact = computed(() => {
  const text = t('privacy.sections.rights.contact')
  return text.replace('{email}', '<a href="mailto:support@parahub.io" class="text-secondary dark:text-secondary-400 hover:text-secondary-700 dark:hover:text-secondary-300">support@parahub.io</a>')
})

// Get purposes array
const purposes = computed(() => {
  try {
    return tm('privacy.sections.usage.purposes') || []
  } catch (e) {
    // Fallback if tm() doesn't work
    return [
      t('privacy.sections.usage.purpose1'),
      t('privacy.sections.usage.purpose2'),
      t('privacy.sections.usage.purpose3'),
      t('privacy.sections.usage.purpose4'),
      t('privacy.sections.usage.purpose5'),
      t('privacy.sections.usage.purpose6'),
      t('privacy.sections.usage.purpose7')
    ].filter(p => p && !p.includes('privacy.sections.usage.purpose'))
  }
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