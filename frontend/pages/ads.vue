<template>
  <div class="py-6 w-full">
    <h1 class="sr-only">{{ $t('ads.title') }}</h1>
    <div class="w-full px-4 sm:px-6 lg:px-8">
      <div class="max-w-7xl lg:min-w-[1024px] xl:min-w-[1280px] mx-auto w-full">
      <div class="mb-6">
        <UiTabs v-model="activeTab" :tabs="adsTabs" variant="nav" />
      </div>

      <div class="mt-6 w-full">
        <NuxtPage />
      </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Megaphone, Settings, Sparkles } from 'lucide-vue-next'

definePageMeta({
  middleware: 'auth',
  ssr: false,
  keepalive: true
})

const { t } = useI18n()
const route = useRoute()
const localePath = useLocalePath()

const adsTabs = computed(() => [
  { id: 'feed', label: t('ads.tabs.feed'), icon: Sparkles, to: localePath('/ads') },
  { id: 'campaigns', label: t('ads.tabs.campaigns'), icon: Megaphone, to: localePath('/ads/campaigns') },
  { id: 'settings', label: t('ads.tabs.profile'), icon: Settings, to: localePath('/ads/settings') },
])

useSeoMeta({
  title: t('ads.title') + ' - Parahub',
  ogTitle: t('ads.title') + ' - Parahub',
})

const activeTab = computed(() => {
  const path = route.path
  if (path.includes('/ads/campaigns')) return 'campaigns'
  if (path.includes('/ads/settings')) return 'settings'
  return 'feed'
})

// Load shared ads profile on mount
const { loadAdsProfile, profileLoaded } = useAdsState()
onMounted(async () => {
  if (!profileLoaded.value) {
    await loadAdsProfile()
  }
})
</script>
