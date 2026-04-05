<template>
  <div class="max-w-4xl mx-auto py-8 px-4">
    <Head>
      <Title>{{ pageTitle }}</Title>
      <Meta name="description" :content="`Estatutos - ${establishmentName}`" />
    </Head>

    <div v-if="loading" class="flex justify-center items-center py-32">
      <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
    </div>

    <UiAlert v-else-if="fetchError" variant="error" title="Erro">
      <p>Estatutos não encontrados.</p>
      <NuxtLink :to="localePath(`/org/${route.params.slug}`)" class="mt-2 inline-block text-sm underline">
        Voltar
      </NuxtLink>
    </UiAlert>

    <div v-else-if="termsData" class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-8">
      <!-- Header -->
      <div class="text-center mb-8 pb-6 border-b border-neutral-300 dark:border-neutral-600">
        <h1 class="text-3xl font-bold text-neutral-900 dark:text-neutral-100 mb-2">
          {{ termsData.establishment_name }}
        </h1>
        <p class="text-sm text-neutral-600 dark:text-neutral-400">
          Estatutos
        </p>
      </div>

      <!-- Translation notice -->
      <div v-if="isTranslation" class="mb-6 p-4 bg-secondary-50 dark:bg-secondary-900/30 border border-secondary-200 dark:border-secondary-800 rounded-lg text-sm text-secondary-700 dark:text-secondary-300">
        {{ $t('profile.estatutos_translation_notice') }}
        <NuxtLink :to="ptOriginalPath" class="underline font-medium">{{ $t('profile.estatutos_translation_link') }}</NuxtLink>.
      </div>

      <!-- Content -->
      <div class="terms-content" v-html="renderedContent"></div>

      <!-- Back link -->
      <div class="mt-12 pt-6 border-t border-neutral-300 dark:border-neutral-600 text-center">
        <NuxtLink
          :to="localePath(`/org/${route.params.slug}`)"
          class="inline-block px-6 py-3 bg-neutral-200 dark:bg-neutral-700 hover:bg-neutral-300 dark:hover:bg-neutral-600 text-neutral-900 dark:text-neutral-100 rounded-lg transition-colors"
        >
          Voltar
        </NuxtLink>
      </div>
    </div>

    <!-- Print button -->
    <div v-if="termsData && !fetchError" class="mt-6 text-center">
      <button
        @click="window.print()"
        class="inline-flex items-center px-4 py-2 bg-neutral-200 dark:bg-neutral-700 hover:bg-neutral-300 dark:hover:bg-neutral-600 text-neutral-900 dark:text-neutral-100 rounded-lg transition-colors"
      >
        <Printer class="w-5 h-5 mr-2" />
        Imprimir
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Printer } from 'lucide-vue-next'
import { marked } from 'marked'

const route = useRoute()
const localePath = useLocalePath()
const { locale } = useI18n()
const slug = route.params.slug as string

const TRANSLATED_LOCALES = ['en', 'ru', 'es', 'fr', 'de']

const termsData = ref<any>(null)
const translatedContent = ref<string>('')
const loading = ref(true)
const fetchError = ref(false)

const isTranslation = computed(() => locale.value !== 'pt' && TRANSLATED_LOCALES.includes(locale.value))
const ptOriginalPath = computed(() => `/pt/org/${slug}/estatutos`)

onMounted(async () => {
  try {
    termsData.value = await $fetch(`/api/v1/geo/establishments/${slug}/terms/`)
    // Load translation if available
    if (isTranslation.value) {
      try {
        translatedContent.value = await $fetch(`/estatutos/${locale.value}.md`, { responseType: 'text' })
      } catch {
        // Fallback to original Portuguese
      }
    }
  } catch {
    fetchError.value = true
  } finally {
    loading.value = false
  }
})

const establishmentName = computed(() => termsData.value?.establishment_name || '')
const pageTitle = computed(() => establishmentName.value ? `Estatutos - ${establishmentName.value}` : 'Estatutos')

const renderedContent = computed(() => {
  // Use translation if available, otherwise original
  let content = translatedContent.value || termsData.value?.terms_content
  if (!content) return ''
  // Strip preamble — component header already shows name
  // Match first ## heading (CAPÍTULO/CHAPTER/ГЛАВА/CHAPITRE/KAPITEL)
  const match = content.match(/^## /m)
  if (match?.index && match.index > 0) content = content.substring(match.index)
  return marked.parse(content, { async: false }) as string
})
</script>

<style scoped>
@media print {
  button {
    display: none;
  }
}

.terms-content :deep(h1) {
  font-size: 1.75rem;
  font-weight: 700;
  margin-top: 2rem;
  margin-bottom: 1rem;
  color: var(--color-neutral-900);
}
.terms-content :deep(h2) {
  font-size: 1.5rem;
  font-weight: 700;
  margin-top: 2.5rem;
  margin-bottom: 1rem;
  color: var(--color-neutral-900);
}
.terms-content :deep(h3) {
  font-size: 1.25rem;
  font-weight: 600;
  margin-top: 2rem;
  margin-bottom: 0.75rem;
  color: var(--color-neutral-800);
}
.terms-content :deep(h4) {
  font-size: 1.125rem;
  font-weight: 600;
  margin-top: 1.5rem;
  margin-bottom: 0.5rem;
  color: var(--color-neutral-800);
}
.terms-content :deep(p) {
  margin-bottom: 0.75rem;
  line-height: 1.75;
  color: var(--color-neutral-700);
}
.terms-content :deep(ol) {
  list-style-type: decimal;
  padding-left: 1.5rem;
  margin-bottom: 0.75rem;
  color: var(--color-neutral-700);
}
.terms-content :deep(ul) {
  list-style-type: disc;
  padding-left: 1.5rem;
  margin-bottom: 0.75rem;
  color: var(--color-neutral-700);
}
.terms-content :deep(li) {
  margin-bottom: 0.25rem;
  line-height: 1.75;
}
.terms-content :deep(li > ol),
.terms-content :deep(li > ul) {
  margin-top: 0.25rem;
  margin-bottom: 0;
}
.terms-content :deep(blockquote) {
  border-left: 3px solid var(--color-neutral-300);
  padding-left: 1rem;
  margin: 1rem 0;
  color: var(--color-neutral-500);
  font-style: italic;
}
.terms-content :deep(hr) {
  border: none;
  border-top: 1px solid var(--color-neutral-200);
  margin: 2rem 0;
}
.terms-content :deep(strong) {
  font-weight: 700;
}

:root.dark .terms-content :deep(h1),
:root.dark .terms-content :deep(h2) {
  color: var(--color-neutral-100);
}
:root.dark .terms-content :deep(h3),
:root.dark .terms-content :deep(h4) {
  color: var(--color-neutral-200);
}
:root.dark .terms-content :deep(p),
:root.dark .terms-content :deep(ol),
:root.dark .terms-content :deep(ul) {
  color: var(--color-neutral-300);
}
:root.dark .terms-content :deep(blockquote) {
  border-left-color: var(--color-neutral-600);
  color: var(--color-neutral-400);
}
:root.dark .terms-content :deep(hr) {
  border-top-color: var(--color-neutral-700);
}
</style>
