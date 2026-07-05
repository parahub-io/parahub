<template>
  <div>
    <div class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <PageHeader
          :title="$t('parasos.groups.title')"
          :subtitle="$t('parasos.subtitle')"
          :create-to="authStore.isAuthenticated ? localePath('/sos/create') : undefined"
          :create-label="authStore.isAuthenticated ? $t('parasos.groups.create') : undefined"
        />

        <!-- Tabs: My Groups / Nearby -->
        <UiTabs v-model="activeTab" :tabs="tabs" class="mb-4" />

        <!-- Search -->
        <div class="relative mb-6">
          <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-neutral-400" />
          <input
            v-model="searchInput"
            @input="debouncedSearch"
            type="text"
            :placeholder="$t('parasos.groups.search_placeholder')"
            class="w-full pl-10 pr-4 py-2.5 border border-neutral-200 dark:border-neutral-700 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent text-sm"
          />
        </div>

        <!-- Loading -->
        <div v-if="isInitial" class="text-center py-12 text-neutral-500">
          {{ $t('parasos.loading') }}
        </div>

        <!-- Empty state -->
        <div v-else-if="groups.length === 0" class="text-center py-12">
          <img src="/images/para/welcome.webp" alt="Para" class="mx-auto h-32 w-auto mb-4" />
          <h3 class="text-lg font-medium text-neutral-900 dark:text-neutral-100 mb-2">
            {{ $t('parasos.groups.empty_title') }}
          </h3>
          <p class="text-neutral-500 dark:text-neutral-400 mb-6">
            {{ $t('parasos.groups.empty_subtitle') }}
          </p>
          <NuxtLink
            v-if="authStore.isAuthenticated"
            :to="localePath('/sos/create')"
            class="btn-primary inline-flex items-center gap-2"
          >
            <Plus :size="18" />
            {{ $t('parasos.groups.create') }}
          </NuxtLink>
        </div>

        <!-- Groups grid (dimmed while a tab/search change refetches) -->
        <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4" :class="{ 'opacity-60 transition-opacity': refreshing }">
          <NuxtLink
            v-for="group in groups"
            :key="group.id"
            :to="localePath(`/sos/${group.id}`)"
            class="block border border-neutral-200 dark:border-neutral-700 rounded-lg p-4 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors"
          >
            <div class="flex items-start justify-between mb-2">
              <h3 class="font-medium text-neutral-900 dark:text-neutral-100 line-clamp-1">
                {{ group.name }}
              </h3>
              <Shield :size="18" class="text-neutral-400 flex-shrink-0 ml-2" />
            </div>
            <p v-if="group.description" class="text-sm text-neutral-500 dark:text-neutral-400 line-clamp-2 mb-3">
              {{ group.description }}
            </p>
            <div class="flex items-center gap-3 text-xs text-neutral-500 dark:text-neutral-400">
              <span class="inline-flex items-center gap-1">
                <Users :size="14" />
                {{ $t('parasos.groups.members_count', group.members_count) }}
              </span>
              <span v-if="group.radius_m" class="inline-flex items-center gap-1">
                <MapPin :size="14" />
                {{ $t('parasos.groups.radius', { meters: group.radius_m }) }}
              </span>
              <span v-if="group.visibility === 'PRIVATE'" class="inline-flex items-center gap-1 text-neutral-400">
                {{ $t('parasos.visibility.private') }}
              </span>
            </div>
          </NuxtLink>
        </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Shield, Search, Users, MapPin } from 'lucide-vue-next'

definePageMeta({ middleware: 'auth' })

const { t } = useI18n()
const localePath = useLocalePath()
const authStore = useAuthStore()
const toastStore = useToastStore()

useSeoMeta({
  title: `${t('parasos.groups.title')} — Parahub`,
  description: t('parasos.meta_description'),
})

const activeTab = useTabSync(['my', 'nearby'])
const searchInput = ref('')   // bound to the search field
const searchQuery = ref('')   // debounced value that feeds the query

const tabs = computed(() => [
  { id: 'my', label: t('parasos.groups.my_groups') },
  { id: 'nearby', label: t('parasos.groups.nearby') },
])

// Own groups vs nearby (+ search) → reactive URL/query → background refetch.
const groupsUrl = () => activeTab.value === 'my'
  ? '/api/v1/parasos/groups/my/'
  : '/api/v1/parasos/groups/'
const groupsQuery = computed(() =>
  activeTab.value === 'nearby' && searchQuery.value ? { search: searchQuery.value } : {})

const groupsData = useListData<any>(groupsUrl, {
  auth: true,
  query: groupsQuery,
  default: () => [],
})
const { data, error, isInitial, refreshing } = groupsData
const groups = computed<any[]>(() =>
  Array.isArray(data.value) ? data.value : (data.value?.items || []))

let searchTimeout: ReturnType<typeof setTimeout> | null = null
function debouncedSearch() {
  if (searchTimeout) clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => { searchQuery.value = searchInput.value }, 300)
}

watch(error, (e) => {
  if (e) toastStore.error(t('parasos.errors.fetch_groups'))
})

// Block client-side navigation until groups are ready (Suspense holds the
// previous page — no spinner flash). Cache-first on revisit.
await groupsData
</script>
