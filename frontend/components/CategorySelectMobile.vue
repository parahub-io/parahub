<template>
  <!-- Full-screen bottom sheet -->
  <Teleport to="body">
    <div v-if="isOpen" class="fixed inset-0 z-[60] flex items-end md:items-center justify-center">
      <!-- Backdrop -->
      <div
        @click="close"
        class="absolute inset-0 bg-black bg-opacity-50 transition-opacity"
      ></div>

      <!-- Bottom sheet content -->
      <div class="relative w-full h-[90vh] bg-white dark:bg-neutral-800 rounded-t-2xl flex flex-col animate-slide-up">
        <!-- Header -->
        <div class="flex-shrink-0 px-4 py-4 border-b border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 sticky top-0 z-10">
          <div class="flex items-center justify-between mb-3">
            <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
              {{ $t('market.category_select.select_category') }}
            </h3>
            <button
              @click="close"
              class="p-2 hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded-lg transition-colors"
            >
              <X class="w-6 h-6 text-neutral-600 dark:text-neutral-300" />
            </button>
          </div>

          <!-- Back button + breadcrumbs -->
          <div v-if="navigationStack.length > 0" class="flex items-center gap-2 text-sm">
            <button
              @click="goBack"
              class="flex items-center gap-1 text-primary hover:text-opacity-80 transition-colors"
            >
              <ChevronLeft class="w-4 h-4" />
              <span>{{ $t('market.category_select.back') }}</span>
            </button>
            <div class="flex items-center gap-1 text-neutral-500 dark:text-neutral-400">
              <ChevronRight class="w-3 h-3" />
              <span class="truncate">{{ currentCategory?.name || '' }}</span>
            </div>
          </div>

          <!-- Search -->
          <div class="relative mt-3">
            <input
              v-model="searchQuery"
              type="text"
              :placeholder="$t('market.category_select.search_placeholder')"
              class="w-full px-4 py-3 pr-10 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent text-base"
              @input="onSearchInput"
            >
            <Search class="absolute right-3 top-3.5 w-5 h-5 text-neutral-400" />
          </div>
        </div>

        <!-- Loading state -->
        <div v-if="loading" class="flex-1 flex items-center justify-center">
          <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100"></div>
        </div>

        <!-- Search results -->
        <div v-else-if="searchQuery.trim() && filteredCategories.length > 0" class="flex-1 overflow-y-auto px-4 py-2">
          <button
            v-for="cat in filteredCategories"
            :key="cat.id"
            type="button"
            @click="selectCategory(cat)"
            class="w-full text-left px-4 py-4 hover:bg-neutral-100 dark:hover:bg-neutral-700 active:bg-neutral-200 dark:active:bg-neutral-600 rounded-xl transition-colors mb-2 flex items-center justify-between"
            :class="{ 'bg-primary bg-opacity-10': modelValue === cat.id }"
          >
            <div class="flex items-start gap-3 flex-1">
              <span class="text-2xl">{{ cat.icon }}</span>
              <div class="flex-1 min-w-0">
                <div class="font-medium text-base text-neutral-900 dark:text-neutral-100">{{ cat.name }}</div>
                <div v-if="cat.breadcrumbs && cat.breadcrumbs.length > 1" class="text-sm text-neutral-500 dark:text-neutral-400 truncate mt-0.5">
                  {{ cat.breadcrumbs.slice(0, -1).map(b => b.name).join(' › ') }}
                </div>
              </div>
            </div>
            <Check v-if="modelValue === cat.id" class="w-5 h-5 text-primary flex-shrink-0 ml-2" />
          </button>
        </div>

        <!-- No search results -->
        <div v-else-if="searchQuery.trim() && filteredCategories.length === 0" class="flex-1 flex items-center justify-center text-neutral-500 dark:text-neutral-400">
          {{ $t('market.category_select.no_results') }}
        </div>

        <!-- Category list (current level) -->
        <div v-else class="flex-1 overflow-y-auto px-4 py-2">
          <Transition name="slide" mode="out-in">
            <div :key="currentLevelKey">
              <button
                v-for="cat in currentLevelCategories"
                :key="cat.id"
                type="button"
                @click="handleCategoryClick(cat)"
                class="w-full text-left px-4 py-4 hover:bg-neutral-100 dark:hover:bg-neutral-700 active:bg-neutral-200 dark:active:bg-neutral-600 rounded-xl transition-colors mb-2 flex items-center justify-between touch-manipulation"
                :class="{
                  'bg-primary bg-opacity-10': modelValue === cat.id,
                  'text-neutral-400 dark:text-neutral-500': mode === 'create' && cat.children && cat.children.length > 0
                }"
              >
                <div class="flex items-center gap-3 flex-1">
                  <span class="text-2xl">{{ cat.icon }}</span>
                  <span class="font-medium text-base text-neutral-900 dark:text-neutral-100">{{ cat.name }}</span>
                </div>
                <div class="flex items-center gap-2">
                  <Check v-if="modelValue === cat.id" class="w-5 h-5 text-primary" />
                  <ChevronRight v-if="cat.children && cat.children.length > 0 && !cat._allIn" class="w-5 h-5 text-neutral-400" />
                </div>
              </button>
            </div>
          </Transition>
        </div>

        <!-- Selected category footer -->
        <div v-if="selectedCategory && !searchQuery" class="flex-shrink-0 px-4 py-4 border-t border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-900">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2 flex-1">
              <span class="text-xl">{{ selectedCategory.icon }}</span>
              <div class="flex-1 min-w-0">
                <div class="text-xs text-neutral-500 dark:text-neutral-400">{{ $t('market.category_select.selected') }}</div>
                <div class="font-medium text-neutral-900 dark:text-neutral-100 truncate">{{ selectedCategory.name }}</div>
              </div>
            </div>
            <button
              @click="confirmSelection"
              class="px-6 py-2.5 bg-primary text-black font-medium rounded-lg hover:bg-opacity-90 transition-colors"
            >
              {{ $t('market.category_select.confirm') }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useCategories } from '~/composables/useCategories'
import { Search, ChevronRight, ChevronLeft, Check, X } from 'lucide-vue-next'

const { t } = useI18n()

const props = defineProps({
  modelValue: {
    type: [String, null],
    default: null
  },
  isOpen: {
    type: Boolean,
    default: false
  },
  mode: {
    type: String,
    default: 'filter',
    validator: (value) => ['filter', 'create', 'all'].includes(value)
  },
  domain: {
    type: String,
    default: null,
    validator: (value) => !value || ['market', 'directory', 'events'].includes(value)
  }
})

const emit = defineEmits(['update:modelValue', 'change', 'close'])

const { fetchCategoryTree, searchCategories, loading } = useCategories()

// State
const searchQuery = ref('')
const rootCategories = ref([])
const filteredCategories = ref([])
const navigationStack = ref([]) // Stack для навигации: [{id, name, children}]
const currentLevelKey = ref(0) // Для анимации transition
let searchTimeout = null

// Computed
const breadcrumbs = computed(() => navigationStack.value.slice(0, -1))

const currentCategory = computed(() => {
  return navigationStack.value[navigationStack.value.length - 1] || null
})

const currentLevelCategories = computed(() => {
  if (navigationStack.value.length === 0) {
    return rootCategories.value
  }
  const current = navigationStack.value[navigationStack.value.length - 1]
  const children = current?.children || []

  // In 'all' mode, prepend a "All in [parent]" entry to allow selecting the parent
  if (props.mode === 'all' && current && children.length > 0) {
    const allInEntry = {
      ...current,
      name: t('market.category_select.all_in', { name: current.name }),
      _allIn: true
    }
    return [allInEntry, ...children]
  }

  return children
})

const selectedCategory = computed(() => {
  if (!props.modelValue) return null

  const findCategory = (categories, id) => {
    for (const cat of categories) {
      if (cat.id === id) return cat
      if (cat.children) {
        const found = findCategory(cat.children, id)
        if (found) return found
      }
    }
    return null
  }

  return findCategory(rootCategories.value, props.modelValue)
})

// Methods
const loadCategories = async () => {
  try {
    const tree = await fetchCategoryTree({ domain: props.domain })
    rootCategories.value = tree.sort((a, b) => a.name.localeCompare(b.name))
  } catch (error) {
    console.error('Failed to load categories:', error)
  }
}

const onSearchInput = () => {
  clearTimeout(searchTimeout)
  searchTimeout = setTimeout(async () => {
    const query = searchQuery.value.trim()
    if (query.length >= 2) {
      try {
        const results = await searchCategories(query, null, props.domain)
        filteredCategories.value = results.map(cat => ({
          id: cat.id,
          name: cat.name,
          icon: cat.icon,
          slug: cat.slug,
          breadcrumbs: cat.breadcrumbs || []
        }))
      } catch (error) {
        console.error('Search failed:', error)
        filteredCategories.value = []
      }
    } else {
      filteredCategories.value = []
    }
  }, 300)
}

const handleCategoryClick = (category) => {
  // In 'create' and 'all' modes, drill into parent categories
  if ((props.mode === 'create' || props.mode === 'all') && category.children && category.children.length > 0) {
    // Skip drill-down for synthetic "all_in" entries — select them directly
    if (category._allIn) {
      selectCategory(category)
      return
    }
    // Navigate to subcategories
    navigationStack.value.push(category)
    currentLevelKey.value++
    return
  }

  // Selectable category
  selectCategory(category)
}

const selectCategory = (category) => {
  emit('update:modelValue', category.id)
  emit('change', category)
  searchQuery.value = '' // Clear search
}

const confirmSelection = () => {
  close()
}

const goBack = () => {
  if (navigationStack.value.length > 0) {
    navigationStack.value.pop()
    currentLevelKey.value--
  }
}

const close = () => {
  // Reset state
  navigationStack.value = []
  searchQuery.value = ''
  currentLevelKey.value = 0
  emit('close')
}

// Load categories on mount
onMounted(() => {
  loadCategories()
})

// Watch for prop changes
watch(() => props.isOpen, (isOpen) => {
  if (isOpen) {
    // Reset navigation when opening
    navigationStack.value = []
    searchQuery.value = ''
    currentLevelKey.value = 0
    // Prevent body scroll
    document.body.style.overflow = 'hidden'
  } else {
    // Restore body scroll
    document.body.style.overflow = ''
  }
})
</script>

<style scoped>
@keyframes slide-up {
  from {
    transform: translateY(100%);
  }
  to {
    transform: translateY(0);
  }
}

.animate-slide-up {
  animation: slide-up 0.3s ease-out;
}

/* Slide transition for level changes */
.slide-enter-active,
.slide-leave-active {
  transition: all 0.3s ease;
}

.slide-enter-from {
  opacity: 0;
  transform: translateX(20px);
}

.slide-leave-to {
  opacity: 0;
  transform: translateX(-20px);
}
</style>
