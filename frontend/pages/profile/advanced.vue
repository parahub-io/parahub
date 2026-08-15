<template>
  <div class="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
    <Head>
      <Title>{{ $t('profile.preferences.advanced_title') }}</Title>
      <Meta name="robots" content="noindex" />
    </Head>

    <!-- Back link -->
    <NuxtLink
      :to="localePath('/profile')"
      class="inline-flex items-center gap-1 text-sm text-neutral-500 dark:text-neutral-400 hover:text-secondary dark:hover:text-secondary-400 transition-colors mb-4"
    >
      <ArrowLeft class="w-4 h-4" />
      {{ $t('nav.profile') }}
    </NuxtLink>

    <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100">
      {{ $t('profile.preferences.advanced_title') }}
    </h1>
    <p class="text-sm text-neutral-500 dark:text-neutral-400 mt-1 mb-6">
      {{ $t('profile.preferences.advanced_subtitle') }}
    </p>

    <div class="space-y-4">
      <AdvancedPreferencesSection />
      <LightningWalletSection />
      <DataPrivacySection />
      <BlockedUsersSection />
      <MigrationSection />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ArrowLeft } from 'lucide-vue-next'
import AdvancedPreferencesSection from '@/components/profile/AdvancedPreferencesSection.vue'
import LightningWalletSection from '@/components/profile/LightningWalletSection.vue'
import DataPrivacySection from '@/components/profile/DataPrivacySection.vue'
import BlockedUsersSection from '@/components/profile/BlockedUsersSection.vue'
import MigrationSection from '@/components/profile/MigrationSection.vue'

definePageMeta({
  middleware: 'auth',
  keepalive: true
})

const localePath = useLocalePath()
</script>
