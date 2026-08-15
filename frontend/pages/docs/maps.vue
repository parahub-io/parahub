<template>
  <div class="min-h-full bg-white dark:bg-neutral-950">
    <DocsHeader :title="$t('about.mapsSystem.title')" />

    <div class="max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-12 space-y-8">

      <p class="prose-section">{{ $t('about.mapsSystem.intro') }}</p>

      <div>
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-3">{{ $t('about.mapsSystem.tools.title') }}</h3>
        <div class="grid sm:grid-cols-2 gap-4">
          <div v-for="tool in tools" :key="tool" class="p-4 border border-neutral-200 dark:border-neutral-800 rounded-lg">
            <div class="font-semibold text-neutral-900 dark:text-white mb-1">{{ $t(`about.mapsSystem.tools.${tool}.title`) }}</div>
            <div class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t(`about.mapsSystem.tools.${tool}.text`) }}</div>
          </div>
        </div>
      </div>

      <div>
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-2">{{ $t('about.mapsSystem.layers.title') }}</h3>
        <p class="text-sm text-neutral-600 dark:text-neutral-400 mb-3">{{ $t('about.mapsSystem.layers.intro') }}</p>
        <div class="border border-neutral-200 dark:border-neutral-800 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-800">
          <div v-for="layer in layers" :key="layer.id" class="flex items-start gap-3 p-4">
            <component :is="layer.icon" class="w-5 h-5 text-neutral-400 flex-shrink-0 mt-0.5" />
            <div class="min-w-0">
              <div class="font-semibold text-neutral-900 dark:text-white">{{ $t(`about.mapsSystem.layers.${layer.id}.title`) }}</div>
              <div class="text-sm text-neutral-500 dark:text-neutral-400 mt-0.5">{{ $t(`about.mapsSystem.layers.${layer.id}.text`) }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- People on the map -->
      <div class="p-4 bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg">
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-2">{{ $t('about.mapsSystem.presence.title') }}</h3>
        <p class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t('about.mapsSystem.presence.text') }}</p>
      </div>

      <!-- CTA -->
      <div class="text-center pt-4">
        <NuxtLink :to="localePath('/map')" class="btn-primary inline-flex items-center gap-2">
          <Map :size="18" />
          {{ $t('about.mapsSystem.cta') }}
        </NuxtLink>
      </div>

      <DocsPrevNext />
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  Map, Bus, Building2, MapPin, Package, Zap, Landmark, Wifi, Wind, Plane, Navigation,
} from 'lucide-vue-next'

const { t } = useI18n()
const localePath = useLocalePath()
useHead({ title: computed(() => `${t('about.mapsSystem.title')} — Parahub`) })
useSeoMeta({
  description: computed(() => t('docs.maps_desc')),
  ogTitle: computed(() => `${t('about.mapsSystem.title')} — Parahub`),
  ogDescription: computed(() => t('docs.maps_desc')),
})
useDocsBreadcrumb(t('about.mapsSystem.title'), '/docs/maps')

const tools = ['search', 'directions', 'measure', 'sun', 'weather', 'basemap']

const layers = [
  { id: 'transit', icon: Bus },
  { id: 'places', icon: Building2 },
  { id: 'poi', icon: MapPin },
  { id: 'hubs', icon: Package },
  { id: 'energy', icon: Zap },
  { id: 'condos', icon: Landmark },
  { id: 'mesh', icon: Wifi },
  { id: 'stations', icon: Wind },
  { id: 'aerial', icon: Plane },
  { id: 'devices', icon: Navigation },
]

definePageMeta({ order: 2 })
</script>

<style scoped>
.prose-section {
  @apply text-neutral-700 dark:text-neutral-300 leading-relaxed;
}
</style>
