<template>
  <div>
    <div class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <PageHeader
          :title="$t('events.page_title')"
          :create-to="authStore.isAuthenticated ? localePath('/events/create') : undefined"
          :create-label="authStore.isAuthenticated ? $t('events.create_event') : undefined"
        />

        <!-- Time tabs -->
        <UiTabs v-model="timeFilter" :tabs="timeTabs" class="mb-4" />

        <!-- Search -->
        <div class="relative mb-4">
          <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-neutral-400" />
          <input
            v-model="searchQuery"
            @input="debouncedSearch"
            type="text"
            :placeholder="$t('events.search_placeholder')"
            class="w-full pl-10 pr-4 py-2.5 border border-neutral-200 dark:border-neutral-700 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent text-sm"
          />
        </div>

        <!-- Filters -->
        <div class="flex flex-wrap items-center gap-3 mb-6">
          <!-- Type segmented control -->
          <div class="inline-flex rounded-lg border border-neutral-200 dark:border-neutral-700 overflow-hidden">
            <button
              v-for="opt in typeOptions"
              :key="opt.value"
              @click="eventType = opt.value; fetchEvents()"
              :class="eventType === opt.value
                ? 'bg-secondary text-white'
                : 'bg-white dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400 hover:bg-neutral-50 dark:hover:bg-neutral-700'"
              class="px-3 py-2.5 text-sm font-medium transition-colors border-r border-neutral-200 dark:border-neutral-700 last:border-r-0"
            >
              {{ opt.label }}
            </button>
          </div>

          <!-- Category dropdown -->
          <div class="relative">
            <button
              @click.stop="showCategoryPicker = !showCategoryPicker"
              class="inline-flex items-center gap-1.5 px-3 py-2.5 rounded-lg border text-sm font-medium transition-colors"
              :class="selectedCategory
                ? 'border-secondary bg-secondary text-white'
                : 'border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400 hover:border-neutral-300 dark:hover:border-neutral-600'"
            >
              <span v-if="selectedCategoryObj" class="text-base leading-none">{{ selectedCategoryObj.icon }}</span>
              <Tag v-else :size="14" />
              <span>{{ selectedCategoryObj?.name || $t('events.filters.category') }}</span>
              <ChevronDown :size="14" class="transition-transform" :class="{ 'rotate-180': showCategoryPicker }" />
            </button>

            <!-- Dropdown backdrop -->
            <div
              v-if="showCategoryPicker"
              class="fixed inset-0 z-40"
              @click="showCategoryPicker = false"
            />
            <!-- Dropdown panel -->
            <div
              v-if="showCategoryPicker"
              class="absolute left-0 top-full mt-1 w-72 bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg shadow-xl z-50"
            >
              <div class="p-2 max-h-80 overflow-y-auto">
                <CategorySelect
                  v-model="selectedCategory"
                  mode="filter"
                  domain="events"
                  hide-search
                  :initial-visible="20"
                  @change="onCategorySelected"
                />
              </div>
            </div>
          </div>

          <!-- Date filter -->
          <input
            v-model="dateFrom"
            @change="fetchEvents"
            type="date"
            class="px-3 py-2.5 border border-neutral-200 dark:border-neutral-700 rounded-lg bg-white dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400 text-sm"
          />
        </div>

        <!-- Loading skeletons -->
        <div v-if="loading" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <EventCardSkeleton v-for="n in 6" :key="n" />
        </div>

        <!-- Events grid -->
        <div v-else-if="events.length > 0" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <EventCard
            v-for="event in events"
            :key="event.id"
            :event="event"
            @click="viewEvent(event)"
          />
        </div>

        <!-- Empty state -->
        <div v-else class="text-center py-12">
          <img src="/images/para/searching.png" alt="Para" class="mx-auto h-32 w-auto mb-4" />
          <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-1">
            {{ $t('events.empty_title') }}
          </h3>
          <NuxtLink
            v-if="authStore.isAuthenticated"
            :to="localePath('/events/create')"
            class="text-sm text-link hover:underline"
          >
            {{ $t('events.empty_subtitle') }}
          </NuxtLink>
          <p v-else class="text-sm text-neutral-500">
            {{ $t('events.empty_subtitle') }}
          </p>
        </div>

        <!-- Pagination -->
        <div v-if="totalPages > 1" class="mt-8 flex justify-center gap-1">
          <button
            v-for="page in totalPages"
            :key="page"
            @click="currentPage = page; fetchEvents()"
            :class="currentPage === page
              ? 'bg-secondary text-white'
              : 'bg-white dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400 hover:bg-neutral-50 dark:hover:bg-neutral-700'"
            class="w-9 h-9 rounded-lg border border-neutral-200 dark:border-neutral-700 text-sm font-medium transition-colors"
          >
            {{ page }}
          </button>
        </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { debounce } from '~/utils/debounce'
import { Search, Calendar, Plus, Tag, ChevronDown } from 'lucide-vue-next'
import { useToastStore } from '~/stores/toast'
import { useAuthStore } from '~/stores/auth'
import CategorySelect from '~/components/CategorySelect.vue'
import EventCard from '~/components/Directory/EventCard.vue'
import EventCardSkeleton from '~/components/EventCardSkeleton.vue'

definePageMeta({})

const { t } = useI18n()
const router = useRouter()
const localePath = useLocalePath()
const toastStore = useToastStore()
const authStore = useAuthStore()

// SEO meta
useSeoMeta({
  title: t('events.page_title') + ' - Parahub',
  ogTitle: t('events.page_title') + ' - Parahub',
  description: t('events.meta_description'),
  ogDescription: t('events.meta_description'),
  ogImage: '/og-image.jpg',
  ogType: 'website',
  twitterCard: 'summary_large_image',
})

const events = ref([])

// Real-time updates for listed events
useObjectListSubscription(events)

const loading = ref(false)
const searchQuery = ref('')
const selectedCategory = ref('')
const selectedCategoryObj = ref(null)
const eventType = ref('')
const dateFrom = ref('')
const timeFilter = ref('upcoming')
const currentPage = ref(1)
const totalPages = ref(1)
const showCategoryPicker = ref(false)

const timeTabs = computed(() => [
  { id: 'upcoming', label: t('events.tab_upcoming') },
  { id: 'past', label: t('events.tab_past') }
])

watch(timeFilter, () => {
  currentPage.value = 1
  fetchEvents()
})

const typeOptions = computed(() => [
  { value: '', label: t('events.filters.all_types') },
  { value: 'OFFLINE', label: t('events.types.offline') },
  { value: 'ONLINE', label: t('events.types.online') },
  { value: 'HYBRID', label: t('events.types.hybrid') }
])

const fetchEvents = async () => {
  loading.value = true
  try {
    const params = new URLSearchParams({
      page: currentPage.value,
      status: 'PUBLISHED',
      time_filter: timeFilter.value
    })

    if (searchQuery.value) params.append('search', searchQuery.value)
    if (selectedCategory.value) params.append('category_id', selectedCategory.value)
    if (eventType.value) params.append('event_type', eventType.value)
    if (dateFrom.value) params.append('date_from', dateFrom.value)

    const response = await $fetch(`/api/v1/geo/events/?${params}`)
    events.value = response.items || []
    totalPages.value = response.pages || 1
  } catch (error) {
    console.error('Error fetching events:', error)
    toastStore.error('Failed to load events')
  } finally {
    loading.value = false
  }
}

const debouncedSearch = debounce(() => {
  currentPage.value = 1
  fetchEvents()
}, 500)

const onCategorySelected = (cat) => {
  selectedCategoryObj.value = cat || null
  showCategoryPicker.value = false
  fetchEvents()
}

const viewEvent = (event) => {
  router.push(localePath(`/events/${event.id}`))
}

onMounted(() => {
  fetchEvents()
})
</script>
