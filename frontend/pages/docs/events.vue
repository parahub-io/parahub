<template>
  <div class="min-h-full bg-white dark:bg-neutral-950">
    <DocsHeader :title="$t('about.eventsSystem.title')" />

    <div class="max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-12 space-y-8">

      <p class="prose-section">{{ $t('about.eventsSystem.intro') }}</p>

      <div class="grid sm:grid-cols-3 gap-4">
        <div v-for="kind in kinds" :key="kind.id" class="p-4 border border-neutral-200 dark:border-neutral-800 rounded-lg">
          <component :is="kind.icon" class="w-5 h-5 text-neutral-400 mb-2" />
          <div class="font-semibold text-neutral-900 dark:text-white mb-1">{{ $t(`about.eventsSystem.types.${kind.id}.title`) }}</div>
          <div class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t(`about.eventsSystem.types.${kind.id}.text`) }}</div>
        </div>
      </div>

      <div>
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-3">{{ $t('about.eventsSystem.flow.title') }}</h3>
        <ol class="space-y-2 text-neutral-700 dark:text-neutral-300">
          <li v-for="i in 4" :key="i" class="flex gap-3">
            <span class="flex-shrink-0 w-5 h-5 rounded-full bg-primary text-neutral-900 text-xs font-bold flex items-center justify-center mt-0.5">{{ i }}</span>
            <span>{{ $t(`about.eventsSystem.flow.step${i}`) }}</span>
          </li>
        </ol>
      </div>

      <div class="grid sm:grid-cols-2 gap-4">
        <div v-for="feature in features" :key="feature" class="p-4 border border-neutral-200 dark:border-neutral-800 rounded-lg">
          <div class="font-semibold text-neutral-900 dark:text-white mb-1">{{ $t(`about.eventsSystem.${feature}.title`) }}</div>
          <div class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t(`about.eventsSystem.${feature}.text`) }}</div>
        </div>
      </div>

      <!-- Who can do what -->
      <div class="p-4 bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg">
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-2">{{ $t('about.eventsSystem.access.title') }}</h3>
        <p class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t('about.eventsSystem.access.text') }}</p>
      </div>

      <!-- CTA -->
      <div class="text-center pt-4">
        <NuxtLink :to="localePath('/events')" class="btn-primary inline-flex items-center gap-2">
          <CalendarDays :size="18" />
          {{ $t('about.eventsSystem.cta') }}
        </NuxtLink>
      </div>

      <DocsPrevNext />
    </div>
  </div>
</template>

<script setup lang="ts">
import { CalendarDays, MapPin, Video, Blend } from 'lucide-vue-next'

const { t } = useI18n()
const localePath = useLocalePath()
useHead({ title: computed(() => `${t('about.eventsSystem.title')} — Parahub`) })
useSeoMeta({
  description: computed(() => t('docs.events_desc')),
  ogTitle: computed(() => `${t('about.eventsSystem.title')} — Parahub`),
  ogDescription: computed(() => t('docs.events_desc')),
})
useDocsBreadcrumb(t('about.eventsSystem.title'), '/docs/events')

const kinds = [
  { id: 'offline', icon: MapPin },
  { id: 'online', icon: Video },
  { id: 'hybrid', icon: Blend },
]
const features = ['participate', 'discover']

definePageMeta({ order: 2 })
</script>

<style scoped>
.prose-section {
  @apply text-neutral-700 dark:text-neutral-300 leading-relaxed;
}
</style>
