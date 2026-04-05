/**
 * Composable for persisting market filter state across navigation
 * Keeps selected filters when switching between tabs
 */
import { ref } from 'vue'

// Global state that persists across component unmount/mount
const filters = ref({
  type: '',
  pricing_type: '',
  category: '',
  owner_id: '',  // CRITICAL: Must be defined for reactivity
  typeAndPricing: '',
  onlyMine: false
})

// Language filter: false = show only user's language + international (default)
//                  true  = show all languages
const showAllLanguages = ref(false)

const searchQuery = ref('')
const currentPage = ref(1)
const selectedFilterCategory = ref<any>(null)

export const useMarketFilters = () => {
  const setFilters = (newFilters: Partial<typeof filters.value>) => {
    filters.value = { ...filters.value, ...newFilters }
  }

  const setSearchQuery = (query: string) => {
    searchQuery.value = query
  }

  const setCurrentPage = (page: number) => {
    currentPage.value = page
  }

  const setSelectedFilterCategory = (category: any) => {
    selectedFilterCategory.value = category
  }

  const resetFilters = () => {
    filters.value = {
      type: '',
      pricing_type: '',
      category: '',
      owner_id: '',
      typeAndPricing: '',
      onlyMine: false
    }
    showAllLanguages.value = false
    searchQuery.value = ''
    currentPage.value = 1
    selectedFilterCategory.value = null
  }

  return {
    // State
    filters,
    searchQuery,
    currentPage,
    selectedFilterCategory,
    showAllLanguages,

    // Setters
    setFilters,
    setSearchQuery,
    setCurrentPage,
    setSelectedFilterCategory,
    resetFilters
  }
}
