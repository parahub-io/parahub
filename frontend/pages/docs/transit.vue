<template>
  <div class="min-h-full bg-white dark:bg-neutral-950">
    <DocsHeader :title="$t('about.transitSystem.title')" />

    <div class="max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-12 space-y-8">

      <p class="prose-section">{{ $t('about.transitSystem.intro') }}</p>

      <div class="grid sm:grid-cols-2 gap-4">
        <div v-for="feature in features" :key="feature" class="p-4 border border-neutral-200 dark:border-neutral-800 rounded-lg">
          <div class="font-semibold text-neutral-900 dark:text-white mb-1">{{ $t(`about.transitSystem.${feature}.title`) }}</div>
          <div class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t(`about.transitSystem.${feature}.text`) }}</div>
        </div>
      </div>

      <!-- Waiting at the stop -->
      <div class="p-4 bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg">
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-2">{{ $t('about.transitSystem.waiting.title') }}</h3>
        <p class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t('about.transitSystem.waiting.text') }}</p>
      </div>

      <div>
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-2">{{ $t('about.transitSystem.opendata.title') }}</h3>
        <p class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t('about.transitSystem.opendata.text') }}</p>
      </div>

      <!-- Related docs -->
      <div class="pt-4 border-t border-neutral-200 dark:border-neutral-800">
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-3">{{ $t('about.transitSystem.related.title') }}</h3>
        <div class="border border-neutral-200 dark:border-neutral-800 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-800">
          <NuxtLink
            v-for="link in related"
            :key="link.to"
            :to="localePath(link.to)"
            class="flex items-center gap-3 p-4 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors group"
          >
            <component :is="link.icon" class="w-5 h-5 text-neutral-400 group-hover:text-neutral-700 dark:group-hover:text-neutral-200 flex-shrink-0" />
            <div class="flex-1 min-w-0">
              <div class="font-semibold text-neutral-900 dark:text-white">{{ $t(link.titleKey) }}</div>
              <div class="text-sm text-neutral-500 dark:text-neutral-400 mt-0.5">{{ $t(link.descKey) }}</div>
            </div>
            <ChevronRight class="w-4 h-4 text-neutral-300 dark:text-neutral-600 group-hover:text-neutral-500 dark:group-hover:text-neutral-400 flex-shrink-0" />
          </NuxtLink>
        </div>
      </div>

      <!-- CTA -->
      <div class="text-center pt-4">
        <NuxtLink :to="localePath('/transit')" class="btn-primary inline-flex items-center gap-2">
          <BusFront :size="18" />
          {{ $t('about.transitSystem.cta') }}
        </NuxtLink>
      </div>

      <DocsPrevNext />
    </div>
  </div>
</template>

<script setup lang="ts">
import { BusFront, Bus, Navigation, Ticket, Car, ChevronRight } from 'lucide-vue-next'

const { t } = useI18n()
const localePath = useLocalePath()
useHead({ title: computed(() => `${t('about.transitSystem.title')} — Parahub`) })
useSeoMeta({
  description: computed(() => t('docs.transit_desc')),
  ogTitle: computed(() => `${t('about.transitSystem.title')} — Parahub`),
  ogDescription: computed(() => t('docs.transit_desc')),
})
useDocsBreadcrumb(t('about.transitSystem.title'), '/docs/transit')

const features = ['live', 'pages', 'eta', 'planner']

const related = [
  { to: '/docs/driver', icon: Navigation, titleKey: 'about.driverMode.title', descKey: 'docs.driver_desc' },
  { to: '/docs/transit-ops', icon: Bus, titleKey: 'about.transitOps.title', descKey: 'docs.transit_ops_desc' },
  { to: '/docs/tickets', icon: Ticket, titleKey: 'about.ticketsSystem.title', descKey: 'docs.tickets_desc' },
  { to: '/docs/carpool', icon: Car, titleKey: 'about.carpoolSystem.title', descKey: 'docs.carpool_desc' },
]

definePageMeta({ order: 2 })
</script>

<style scoped>
.prose-section {
  @apply text-neutral-700 dark:text-neutral-300 leading-relaxed;
}
</style>
