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
          <h1 class="inline text-neutral-900 font-semibold text-lg sm:text-xl">{{ $t('parasos.title') }}</h1>
        </nav>
      </div>
    </div>

    <div class="max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-12 space-y-8">

      <p class="prose-section">{{ $t('parasos.landing_hero_subtitle') }}</p>

      <!-- Problem cards -->
      <div>
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-3">{{ $t('parasos.landing_problems_title') }}</h3>
        <div class="space-y-3">
          <div v-for="i in 3" :key="i" class="flex gap-3 items-start">
            <span class="flex-shrink-0 w-5 h-5 rounded-full bg-error text-white text-xs font-bold flex items-center justify-center mt-0.5">!</span>
            <span class="text-neutral-700 dark:text-neutral-300">{{ $t(`parasos.landing_problem_${i}`) }}</span>
          </div>
        </div>
      </div>

      <!-- How it works steps -->
      <div>
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-3">{{ $t('parasos.landing_how_title') }}</h3>
        <ol class="space-y-2 text-neutral-700 dark:text-neutral-300">
          <li v-for="i in 3" :key="i" class="flex gap-3">
            <span class="flex-shrink-0 w-5 h-5 rounded-full bg-primary text-neutral-900 text-xs font-bold flex items-center justify-center mt-0.5">{{ i }}</span>
            <span>{{ $t(`parasos.landing_how_${i}`) }}</span>
          </li>
        </ol>
      </div>

      <!-- Feature cards -->
      <div>
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-3">{{ $t('parasos.landing_features_title') }}</h3>
        <div class="grid sm:grid-cols-2 gap-4">
          <div v-for="i in 8" :key="i" class="p-4 border border-neutral-200 dark:border-neutral-800 rounded-lg">
            <div class="flex items-center gap-2 mb-1">
              <component :is="featureIcons[i - 1]" :size="18" class="text-secondary-600 dark:text-secondary-400" />
              <span class="font-semibold text-neutral-900 dark:text-white">{{ $t(`parasos.landing_feature_${i}_title`) }}</span>
            </div>
            <div class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t(`parasos.landing_feature_${i}_desc`) }}</div>
          </div>
        </div>
      </div>

      <!-- Alert levels -->
      <div>
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-3">{{ $t('parasos.sos.select_level') }}</h3>
        <div class="space-y-3">
          <div v-for="lvl in alertLevels" :key="lvl.key" class="p-3 rounded-lg border" :class="lvl.classes">
            <span class="font-medium">{{ $t(`parasos.sos.level.${lvl.key}`) }}</span>
            <span class="text-sm ml-2 opacity-80">— {{ $t(`parasos.sos.level.${lvl.key}_desc`) }}</span>
          </div>
        </div>
      </div>

      <!-- Passive safety + IoT -->
      <div>
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-3">{{ passiveSafetyTitle }}</h3>
        <div class="grid sm:grid-cols-2 gap-4">
          <div v-for="item in passiveFeatures" :key="item.title" class="p-4 border border-neutral-200 dark:border-neutral-800 rounded-lg">
            <div class="flex items-center gap-2 mb-1">
              <component :is="item.icon" :size="18" class="text-secondary-600 dark:text-secondary-400" />
              <span class="font-semibold text-neutral-900 dark:text-white">{{ item.title }}</span>
            </div>
            <div class="text-sm text-neutral-600 dark:text-neutral-400">{{ item.desc }}</div>
          </div>
        </div>
      </div>

      <!-- Privacy guarantee -->
      <div class="p-4 bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg">
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-2">{{ $t('parasos.privacy.title') }}</h3>
        <ul class="text-sm text-neutral-600 dark:text-neutral-400 space-y-1">
          <li>{{ $t('parasos.privacy.no_tracking') }}</li>
          <li>{{ $t('parasos.privacy.sos_only') }}</li>
          <li>{{ $t('parasos.privacy.responder_voluntary') }}</li>
          <li>{{ $t('parasos.privacy.no_history') }}</li>
        </ul>
      </div>

      <!-- Disclaimer -->
      <div class="p-4 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-lg">
        <h3 class="font-semibold text-neutral-900 dark:text-white mb-2">{{ $t('parasos.disclaimer.title') }}</h3>
        <ul class="text-sm text-neutral-600 dark:text-neutral-400 space-y-1">
          <li>{{ $t('parasos.disclaimer.not_police') }}</li>
          <li>{{ $t('parasos.disclaimer.no_obligation') }}</li>
          <li>{{ $t('parasos.disclaimer.no_intervention') }}</li>
          <li>{{ $t('parasos.disclaimer.call_112') }}</li>
        </ul>
      </div>

      <!-- CTA -->
      <div class="text-center pt-4">
        <NuxtLink :to="localePath('/sos')" class="btn-primary inline-flex items-center gap-2">
          <Shield :size="18" />
          {{ $t('parasos.landing_hero_cta') }}
        </NuxtLink>
      </div>

      <DocsPrevNext />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ChevronRight, Shield, Bell, Clock, Users, Eye, Lock, Heart, Activity, Wifi, CircleCheck, Timer, EyeOff, Volume2 } from 'lucide-vue-next'

const { t } = useI18n()
const localePath = useLocalePath()
useHead({ title: computed(() => `${t('parasos.title')} — Parahub`) })
useSeoMeta({
  description: computed(() => t('docs.parasos_desc')),
  ogTitle: computed(() => `${t('parasos.title')} — Parahub`),
  ogDescription: computed(() => t('docs.parasos_desc')),
})
useDocsBreadcrumb(t('parasos.title'), '/docs/sos')

const featureIcons = [Bell, Clock, Users, Eye, Lock, Heart, EyeOff, Volume2]

const passiveSafetyTitle = computed(() => t('parasos.docs_passive_title'))
const passiveFeatures = computed(() => [
  { icon: Activity, title: t('parasos.docs_passive_inactivity_title'), desc: t('parasos.docs_passive_inactivity_desc') },
  { icon: Wifi, title: t('parasos.docs_passive_iot_title'), desc: t('parasos.docs_passive_iot_desc') },
  { icon: CircleCheck, title: t('parasos.docs_passive_checkin_title'), desc: t('parasos.docs_passive_checkin_desc') },
  { icon: Timer, title: t('parasos.docs_passive_autoresolve_title'), desc: t('parasos.docs_passive_autoresolve_desc') },
])

const alertLevels = [
  { key: 'info', classes: 'border-blue-300 dark:border-blue-700 bg-blue-50 dark:bg-blue-950/30 text-blue-800 dark:text-blue-200' },
  { key: 'warning', classes: 'border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/30 text-amber-800 dark:text-amber-200' },
  { key: 'emergency', classes: 'border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-950/30 text-red-800 dark:text-red-200' },
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
