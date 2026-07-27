<template>
  <div class="min-h-full bg-white dark:bg-neutral-950">
    <DocsHeader :title="$t('about.techStack.title')" />

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
const { t } = useI18n()
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
  { key: 'communications', items: ['matrix', 'jitsi', 'peertube', 'breez', 'traccar', 'mailcow'] },
  { key: 'maps', items: ['martin', 'pelias', 'valhalla', 'motis', 'osm'] },
  { key: 'infrastructure', items: ['docker', 'nginx', 'systemd', 'gitea', 'capacitor'] },
]

definePageMeta({ order: 2 })
</script>

<style scoped>
.prose-section {
  @apply text-neutral-700 dark:text-neutral-300 leading-relaxed;
}
</style>
