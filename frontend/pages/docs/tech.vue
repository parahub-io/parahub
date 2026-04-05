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
          <h1 class="inline text-neutral-900 font-semibold text-lg sm:text-xl">{{ $t('about.techStack.title') }}</h1>
        </nav>
      </div>
    </div>

    <div class="max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-12">
      <div class="prose-section grid sm:grid-cols-2 gap-x-8 gap-y-4">
        <div v-for="cat in techCategories" :key="cat.key">
          <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 text-sm mb-1.5">{{ $t(`about.techStack.${cat.key}.title`) }}</h3>
          <ul class="text-sm space-y-0.5">
            <li v-for="item in cat.items" :key="item" class="text-neutral-600 dark:text-neutral-400">
              {{ $t(`about.techStack.${cat.key}.${item}`) }}
            </li>
          </ul>
        </div>
      </div>
      <DocsPrevNext />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ChevronRight } from 'lucide-vue-next'

const { t } = useI18n()
const localePath = useLocalePath()
useHead({ title: computed(() => `${t('about.techStack.title')} — Parahub`) })
useSeoMeta({
  description: computed(() => t('docs.tech_desc')),
  ogTitle: computed(() => `${t('about.techStack.title')} — Parahub`),
  ogDescription: computed(() => t('docs.tech_desc')),
})
useDocsBreadcrumb(t('about.techStack.title'), '/docs/tech')

const techCategories = [
  { key: 'backend', items: ['django', 'postgres', 'timescale', 'redis', 'neo4j'] },
  { key: 'frontend', items: ['nuxt', 'maplibre', 'lucide', 'tailwind'] },
  { key: 'communications', items: ['matrix', 'jitsi', 'breez', 'traccar', 'mailcow'] },
  { key: 'maps', items: ['martin', 'pelias', 'valhalla', 'motis', 'osm'] },
  { key: 'infrastructure', items: ['docker', 'nginx', 'systemd', 'gitea', 'capacitor'] },
]

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
