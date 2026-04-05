<template>
  <div class="category-select">
    <!-- Mobile: Button to open bottom sheet -->
    <div v-if="isMobile" class="w-full">
      <button
        type="button"
        @click="isModalOpen = true"
        class="w-full px-4 py-3 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-left flex items-center justify-between hover:border-primary transition-colors"
      >
        <div v-if="selectedCategory" class="flex items-center gap-2">
          <span class="text-xl">{{ selectedCategory.icon }}</span>
          <span class="text-neutral-900 dark:text-neutral-100">{{ selectedCategory.name }}</span>
        </div>
        <span v-else class="text-neutral-500 dark:text-neutral-400">
          {{ placeholder || $t('market.category_select.select_placeholder') }}
        </span>
        <ChevronRight class="w-5 h-5 text-neutral-400" />
      </button>

      <!-- Mobile bottom sheet modal -->
      <CategorySelectMobile
        :model-value="modelValue"
        :is-open="isModalOpen"
        :mode="mode"
        :domain="domain"
        @update:model-value="$emit('update:modelValue', $event)"
        @change="$emit('change', $event)"
        @close="isModalOpen = false"
      />
    </div>

    <!-- Desktop: Inline category picker -->
    <div v-else>
      <!-- Search input -->
      <div v-if="!hideSearch" class="relative mb-3">
      <input
        v-model="searchQuery"
        type="text"
        :placeholder="placeholder || $t('market.category_select.search_placeholder')"
        class="w-full px-4 py-2 pr-10 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent text-sm"
        @input="onSearchInput"
      >
      <Search class="absolute right-3 top-2.5 w-4 h-4 text-neutral-400" />
    </div>

    <!-- Loading state -->
    <div v-if="loading" class="flex justify-center py-4">
      <div class="animate-spin rounded-full h-6 w-6 border-b-2 border-primary"></div>
    </div>

    <!-- Search results -->
    <div v-else-if="searchQuery.trim() && filteredCategories.length > 0" class="max-h-64 overflow-y-auto">
      <button
        v-for="cat in filteredCategories"
        :key="cat.id"
        type="button"
        @click="selectCategory(cat)"
        class="w-full text-left px-3 py-2 hover:bg-primary hover:bg-opacity-10 rounded flex items-start gap-2 text-sm"
        :class="{ 'bg-primary bg-opacity-20': modelValue === cat.id }"
      >
        <span class="text-base mt-0.5">{{ cat.icon }}</span>
        <div class="flex-1 min-w-0">
          <div class="font-medium text-neutral-900 dark:text-neutral-100">{{ cat.name }}</div>
          <div v-if="cat.breadcrumbs && cat.breadcrumbs.length > 1" class="text-xs text-neutral-500 dark:text-neutral-400 truncate">
            {{ cat.breadcrumbs.slice(0, -1).map(b => b.name).join(' › ') }}
          </div>
        </div>
        <ChevronRight v-if="modelValue === cat.id" class="w-4 h-4 text-primary mt-0.5 flex-shrink-0" />
      </button>
    </div>

    <!-- No search results -->
    <div v-else-if="searchQuery.trim() && filteredCategories.length === 0" class="text-center py-4 text-sm text-neutral-500">
      {{ $t('market.category_select.no_results') }}
    </div>

    <!-- Category groups (when not searching) -->
    <div v-else class="space-y-2 max-h-96 overflow-y-auto">
      <!-- Popular/Root categories (first N shown by default) -->
      <div v-for="cat in visibleRootCategories" :key="cat.id">
        <button
          type="button"
          @click="toggleCategory(cat)"
          class="w-full flex items-center justify-between px-3 py-2 hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded-lg text-sm font-medium"
          :class="{ 'bg-primary bg-opacity-10': selectedRootCategory?.id === cat.id }"
        >
          <span class="flex items-center gap-2">
            <span class="text-lg">{{ cat.icon }}</span>
            <span class="text-neutral-900 dark:text-neutral-100">{{ cat.name }}</span>
          </span>
          <ChevronRight class="w-4 h-4 text-neutral-600 dark:text-neutral-300 transition-transform" :class="{ 'rotate-90': expandedCategories[cat.id] }" />
        </button>

        <!-- Subcategories (expanded) - recursive -->
        <CategoryTreeLevel
          v-if="expandedCategories[cat.id] && cat.children && cat.children.length"
          :categories="cat.children"
          :selected-id="modelValue"
          :level="1"
          :mode="mode"
          :expanded-subcategories="expandedSubcategories"
          @select="selectCategory"
          @toggle-expand="toggleSubcategory"
        />
      </div>

      <!-- "Show all" toggle button -->
      <button
        v-if="rootCategories.length > initialVisible"
        type="button"
        @click="showAll = !showAll"
        class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-700 text-sm text-neutral-600 dark:text-neutral-400 flex items-center justify-center gap-2"
      >
        <template v-if="!showAll">
          + {{ $t('market.category_select.show_all', { count: rootCategories.length - initialVisible }) }}
        </template>
        <template v-else>
          <ChevronUp class="w-4 h-4" />
          {{ $t('market.category_select.show_less') }}
        </template>
      </button>
    </div>

    <!-- Selected category display (optional, for confirmation) -->
    <div v-if="selectedCategory && !searchQuery" class="mt-3 p-2 bg-primary bg-opacity-10 rounded-lg flex items-center justify-between text-sm">
      <span class="font-medium text-neutral-900 dark:text-yellow-400">
        {{ selectedCategory.icon }} {{ selectedCategory.name }}
      </span>
      <button
        type="button"
        @click="clearSelection"
        class="text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300"
      >
        <X class="w-4 h-4" />
      </button>
    </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useCategories } from '~/composables/useCategories'
import { Search, ChevronRight, ChevronUp, Check, X } from 'lucide-vue-next'
import CategorySelectMobile from './CategorySelectMobile.vue'

const props = defineProps({
  modelValue: {
    type: [String, null],
    default: null
  },
  placeholder: {
    type: String,
    default: ''
  },
  initialVisible: {
    type: Number,
    default: 8  // Show first 8 categories by default
  },
  required: {
    type: Boolean,
    default: false
  },
  mode: {
    type: String,
    default: 'filter',  // 'filter' allows parent categories, 'create' only allows leaf categories
    validator: (value) => ['filter', 'create', 'all'].includes(value)
  },
  hideSearch: {
    type: Boolean,
    default: false
  },
  domain: {
    type: String,
    default: null,  // 'market', 'directory', 'events', or null for all
    validator: (value) => !value || ['market', 'directory', 'events'].includes(value)
  }
})

const emit = defineEmits(['update:modelValue', 'change'])

const { fetchCategoryTree, searchCategories, loading } = useCategories()

// State
const searchQuery = ref('')
const rootCategories = ref([])
const filteredCategories = ref([])
const expandedCategories = ref({})
const expandedSubcategories = ref({})  // Track expanded state for all subcategories
const selectedRootCategory = ref(null)
const showAll = ref(false)
const isMobile = ref(false)
const isModalOpen = ref(false)
let searchTimeout = null

// Computed
const visibleRootCategories = computed(() => {
  if (showAll.value) {
    return rootCategories.value
  }
  return rootCategories.value.slice(0, props.initialVisible)
})

const selectedCategory = computed(() => {
  if (!props.modelValue) return null

  // Find selected category in tree
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
    // Sort root categories alphabetically by name
    rootCategories.value = tree.sort((a, b) => a.name.localeCompare(b.name))
  } catch (error) {
    console.error('Failed to load categories:', error)
  }
}

const onSearchInput = () => {
  clearTimeout(searchTimeout)
  searchTimeout = setTimeout(async () => {
    const query = searchQuery.value.trim()
    // Only search if query has at least 2 characters
    if (query.length >= 2) {
      try {
        const results = await searchCategories(query, null, props.domain)
        // Results already have breadcrumbs from composable
        filteredCategories.value = results.map(cat => ({
          id: cat.id,
          name: cat.name,
          icon: cat.icon,
          label: cat.name,
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

const toggleCategory = (category) => {
  selectedRootCategory.value = category

  // Toggle expansion
  if (expandedCategories.value[category.id]) {
    delete expandedCategories.value[category.id]
  } else {
    expandedCategories.value = { [category.id]: true }
  }
}

const toggleSubcategory = (categoryId) => {
  if (expandedSubcategories.value[categoryId]) {
    delete expandedSubcategories.value[categoryId]
  } else {
    expandedSubcategories.value[categoryId] = true
  }
}

const selectCategory = (category) => {
  // In 'create' mode, only allow leaf categories (no children)
  if (props.mode === 'create' && category.children && category.children.length > 0) {
    // Don't select parent categories, just expand them
    // If user clicked from search, clear search and expand path to category
    if (searchQuery.value.trim()) {
      searchQuery.value = ''
      // Expand path to this category
      expandPathToCategory(category.id)
      // Also expand the category itself to show its children
      expandedSubcategories.value[category.id] = true
    } else {
      // User clicked from tree view, just toggle expand/collapse
      const isRootCategory = rootCategories.value.some(c => c.id === category.id)

      if (isRootCategory) {
        // For root categories, toggle in expandedCategories without resetting others
        if (expandedCategories.value[category.id]) {
          delete expandedCategories.value[category.id]
        } else {
          expandedCategories.value[category.id] = true
        }
        selectedRootCategory.value = category
      } else {
        // For subcategories, toggle in expandedSubcategories
        toggleSubcategory(category.id)
      }
    }
    return
  }

  emit('update:modelValue', category.id)
  // Emit full category object with id, name, slug, icon for caller to choose what to use
  emit('change', category)

  // If selected from search, expand path to show selection in tree
  if (searchQuery.value.trim()) {
    searchQuery.value = ''  // Clear search after selection
    expandPathToCategory(category.id)
  }
}

const clearSelection = () => {
  emit('update:modelValue', null)
  emit('change', null)
}

// Check if mobile (< 768px)
const checkMobile = () => {
  if (typeof window !== 'undefined') {
    isMobile.value = window.innerWidth < 768
  }
}

// Load categories on mount
onMounted(() => {
  loadCategories()
  checkMobile()
  if (typeof window !== 'undefined') {
    window.addEventListener('resize', checkMobile)
  }
})

onBeforeUnmount(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener('resize', checkMobile)
  }
})

// Helper function to expand path to selected category
const expandPathToCategory = (targetId) => {
  if (!targetId || rootCategories.value.length === 0) return

  // Auto-expand the entire path to selected category
  const findCategoryPath = (categories, targetId, path = []) => {
    for (const cat of categories) {
      if (cat.id === targetId) {
        return [...path, cat.id]
      }
      if (cat.children && cat.children.length > 0) {
        const found = findCategoryPath(cat.children, targetId, [...path, cat.id])
        if (found) return found
      }
    }
    return null
  }

  const path = findCategoryPath(rootCategories.value, targetId)
  if (path && path.length > 0) {
    // Expand all categories in the path
    const newExpandedRoot = {}
    const newExpandedSub = {}

    // First category is the root
    if (path[0]) {
      newExpandedRoot[path[0]] = true
      selectedRootCategory.value = rootCategories.value.find(c => c.id === path[0])
    }

    // Expand all intermediate categories
    for (let i = 0; i < path.length - 1; i++) {
      newExpandedSub[path[i]] = true
    }

    expandedCategories.value = newExpandedRoot
    expandedSubcategories.value = newExpandedSub
  }
}

// Watch for external changes to modelValue
watch(() => props.modelValue, (newValue) => {
  if (newValue) {
    expandPathToCategory(newValue)
  }
})

// Watch for rootCategories loading (to expand path after categories are loaded)
watch(() => rootCategories.value, (newCategories) => {
  if (newCategories.length > 0 && props.modelValue) {
    expandPathToCategory(props.modelValue)
  }
})
</script>

<style scoped>
.category-select {
  @apply w-full;
}
</style>
