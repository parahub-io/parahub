<script setup lang="ts">
import { Languages } from 'lucide-vue-next'

const props = defineProps<{
  currentLanguage: string
  translations: Array<{ id: string; language: string; slug: string; title: string }>
  canEdit?: boolean
  postId?: string
  /** Base path for building links, e.g. '/blog', '/org/slug/blog', '/u/name/blog' */
  linkBase?: string
}>()

const { t } = useI18n()
const localePath = useLocalePath()

const langNames: Record<string, string> = {
  en: 'English',
  pt: 'Portugues',
  es: 'Espanol',
  fr: 'Francais',
  de: 'Deutsch',
  ru: 'Russkiy',
}

const base = computed(() => props.linkBase || '/blog')

function postLink(tr: { slug: string }) {
  return localePath(`${base.value}/${tr.slug}`)
}
</script>

<template>
  <div v-if="translations.length > 0 || canEdit" class="flex items-center gap-2 flex-wrap">
    <!-- When translations exist: "Also available in: [EN] [PT] ..." -->
    <template v-if="translations.length > 0">
      <span class="text-xs text-neutral-500 dark:text-neutral-400 flex items-center gap-1">
        <Languages class="w-3.5 h-3.5" />
        {{ t('cms.availableIn') }}:
      </span>

      <!-- Current language (non-clickable) -->
      <span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-primary-100 dark:bg-primary-900/40 text-primary-700 dark:text-primary-300">
        {{ langNames[currentLanguage] || currentLanguage }}
      </span>

      <!-- Translation links -->
      <NuxtLink
        v-for="tr in translations"
        :key="tr.id"
        :to="postLink(tr)"
        class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-neutral-100 dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300 hover:bg-primary-100 dark:hover:bg-primary-900/40 hover:text-primary-700 dark:hover:text-primary-300 transition-colors"
        :title="tr.title"
      >
        {{ langNames[tr.language] || tr.language }}
      </NuxtLink>
    </template>

    <!-- Translate button for editors -->
    <NuxtLink
      v-if="canEdit && postId"
      :to="localePath(`/blog/create?translate=${postId}`)"
      class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border border-dashed border-neutral-300 dark:border-neutral-600 text-neutral-500 dark:text-neutral-400 hover:border-primary hover:text-primary transition-colors"
    >
      + {{ t('cms.translateThisPost') }}
    </NuxtLink>
  </div>
</template>
