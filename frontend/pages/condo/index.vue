<template>
  <div class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
    <PageHeader
      :title="$t('condo.my_title')"
      :subtitle="$t('condo.my_subtitle')"
      :create-to="localePath('/condo/create')"
      :create-label="$t('condo.create')"
    />

    <!-- Loading -->
    <div v-if="loading" class="text-center py-12" role="status">
      <div class="inline-block h-12 w-12 animate-spin rounded-full border-4 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100" />
      <span class="sr-only">Loading...</span>
    </div>

    <!-- Empty state -->
    <div v-else-if="condos.length === 0" class="text-center py-12">
      <img src="/images/para/building.png" alt="Para" class="mx-auto h-32 w-auto mb-4" />
      <h3 class="text-lg font-medium text-neutral-900 dark:text-neutral-100 mb-2">
        {{ $t('condo.empty_title') }}
      </h3>
      <p class="text-neutral-500 dark:text-neutral-400 mb-6 max-w-md mx-auto">
        {{ $t('condo.empty_subtitle') }}
      </p>
      <NuxtLink :to="localePath('/condo/create')" class="btn-primary inline-flex items-center gap-2">
        <Plus :size="18" />
        {{ $t('condo.create') }}
      </NuxtLink>
    </div>

    <!-- Condominiums list -->
    <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      <NuxtLink
        v-for="condo in condos"
        :key="condo.id"
        :to="localePath(`/condo/${condo.slug}/fractions`)"
        class="block border border-neutral-200 dark:border-neutral-700 rounded-lg p-4 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors"
      >
        <div class="flex items-start justify-between mb-2">
          <h3 class="font-medium text-neutral-900 dark:text-neutral-100 line-clamp-1">
            {{ condo.name }}
          </h3>
          <div class="flex items-center gap-1">
            <DemoBadge :is-demo="condo.is_demo" />
            <UiBadge :variant="roleBadgeVariant(condo.role)" type="soft" size="sm">
              {{ $t(`condo.role_${condo.role}`) }}
            </UiBadge>
          </div>
        </div>

        <p v-if="condo.full_address" class="text-sm text-neutral-500 dark:text-neutral-400 line-clamp-1 mb-3">
          {{ condo.full_address }}
        </p>

        <div class="flex items-center gap-4 text-xs text-neutral-500 dark:text-neutral-400">
          <span class="flex items-center gap-1">
            <LayoutGrid :size="14" />
            {{ $t('condo.fractions_short', { count: condo.fraction_count }) }}
          </span>
          <span class="flex items-center gap-1">
            <Users :size="14" />
            {{ $t('condo.members_short', { count: condo.member_count }) }}
          </span>
        </div>
      </NuxtLink>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Building, Plus, LayoutGrid, Users } from 'lucide-vue-next'

definePageMeta({
  middleware: 'auth',
})

// Track onboarding: user has visited condo section
if (import.meta.client) {
  localStorage.setItem('onboarding:condo', '1')
}

const { t } = useI18n()
const localePath = useLocalePath()
const authStore = useAuthStore()

useSeoMeta({
  title: () => t('condo.meta_my_title'),
  ogTitle: () => t('condo.meta_my_title'),
  description: () => t('condo.meta_my_desc'),
  ogDescription: () => t('condo.meta_my_desc'),
})

interface CondoItem {
  id: string
  name: string
  slug: string | null
  full_address: string | null
  fraction_count: number
  member_count: number
  role: string
}

const condos = ref<CondoItem[]>([])
const loading = ref(true)

const roleBadgeVariant = (role: string) => {
  switch (role) {
    case 'owner': return 'warning'
    case 'admin': return 'info'
    case 'resident': return 'success'
    default: return 'secondary'
  }
}

onMounted(async () => {
  try {
    await authStore.ensureToken()
    condos.value = await $fetch<CondoItem[]>('/api/v1/geo/condominiums/my/', {
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.accessToken}` },
    })
  } catch (err) {
    console.error('Failed to load condominiums:', err)
  } finally {
    loading.value = false
  }
})
</script>
