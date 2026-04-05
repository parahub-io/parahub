<template>
  <div v-if="hasActiveFilters" class="mb-4 flex flex-wrap items-center gap-2">
    <span class="text-sm font-medium text-neutral-600 dark:text-neutral-400">
      {{ $t('market.filters.active_filters') }}:
    </span>

    <!-- Owner filter chip -->
    <button
      v-if="filters.owner_id && ownerDisplayName"
      @click="$emit('clear-owner')"
      class="inline-flex items-center gap-1.5 px-3 py-1.5 bg-primary/10 hover:bg-primary/20 border border-primary/30 rounded-full text-sm font-medium text-neutral-900 dark:text-neutral-100 transition-colors"
    >
      <span>{{ ownerDisplayName }}</span>
      <X class="w-3.5 h-3.5" />
    </button>

    <!-- Only Mine filter chip -->
    <button
      v-if="filters.onlyMine"
      @click="$emit('clear-owner')"
      class="inline-flex items-center gap-1.5 px-3 py-1.5 bg-primary/10 hover:bg-primary/20 border border-primary/30 rounded-full text-sm font-medium text-neutral-900 dark:text-neutral-100 transition-colors"
    >
      <span>{{ $t('market.filters.only_mine') }}</span>
      <X class="w-3.5 h-3.5" />
    </button>

    <!-- Type filter chip -->
    <button
      v-if="filters.type"
      @click="$emit('clear-type')"
      class="inline-flex items-center gap-1.5 px-3 py-1.5 bg-secondary-50 hover:bg-secondary-100 dark:bg-secondary-900/20 dark:hover:bg-secondary-900/30 border border-secondary-200 dark:border-secondary-800 rounded-full text-sm font-medium text-secondary-900 dark:text-secondary-100 transition-colors"
    >
      <span>{{ $t(`market.type.${filters.type.toLowerCase()}`) }}</span>
      <X class="w-3.5 h-3.5" />
    </button>

    <!-- Pricing type filter chip -->
    <button
      v-if="filters.pricing_type"
      @click="$emit('clear-pricing-type')"
      class="inline-flex items-center gap-1.5 px-3 py-1.5 bg-green-50 hover:bg-green-100 dark:bg-green-900/20 dark:hover:bg-green-900/30 border border-green-200 dark:border-green-800 rounded-full text-sm font-medium text-green-900 dark:text-green-100 transition-colors"
    >
      <span>{{ $t(`market.pricing_type.${filters.pricing_type.toLowerCase()}`) }}</span>
      <X class="w-3.5 h-3.5" />
    </button>

    <!-- Category filter chip -->
    <button
      v-if="selectedFilterCategory"
      @click="$emit('clear-category')"
      class="inline-flex items-center gap-1.5 px-3 py-1.5 bg-purple-50 hover:bg-purple-100 dark:bg-purple-900/20 dark:hover:bg-purple-900/30 border border-purple-200 dark:border-purple-800 rounded-full text-sm font-medium text-purple-900 dark:text-purple-100 transition-colors"
    >
      <span>{{ selectedFilterCategory.name }}</span>
      <X class="w-3.5 h-3.5" />
    </button>

    <!-- All languages chip -->
    <button
      v-if="showAllLanguages"
      @click="$emit('clear-language')"
      class="inline-flex items-center gap-1.5 px-3 py-1.5 bg-orange-50 hover:bg-orange-100 dark:bg-orange-900/20 dark:hover:bg-orange-900/30 border border-orange-200 dark:border-orange-800 rounded-full text-sm font-medium text-orange-900 dark:text-orange-100 transition-colors"
    >
      <span>{{ $t('market.filters.all_languages') }}</span>
      <X class="w-3.5 h-3.5" />
    </button>

    <!-- Search query chip -->
    <button
      v-if="searchQuery"
      @click="$emit('clear-search')"
      class="inline-flex items-center gap-1.5 px-3 py-1.5 bg-neutral-100 hover:bg-neutral-200 dark:bg-neutral-700 dark:hover:bg-neutral-600 border border-neutral-300 dark:border-neutral-600 rounded-full text-sm font-medium text-neutral-900 dark:text-neutral-100 transition-colors"
    >
      <span>"{{ searchQuery }}"</span>
      <X class="w-3.5 h-3.5" />
    </button>

    <!-- Clear all button -->
    <button
      v-if="activeFiltersCount > 1"
      @click="$emit('clear-all')"
      class="ml-2 px-3 py-1.5 text-sm font-medium text-neutral-600 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-neutral-100 hover:underline transition-colors"
    >
      {{ $t('market.filters.clear_all') }}
    </button>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { X } from 'lucide-vue-next'

const props = defineProps({
  filters: { type: Object, required: true },
  ownerDisplayName: { type: String, default: '' },
  selectedFilterCategory: { type: Object, default: null },
  showAllLanguages: { type: Boolean, default: false },
  searchQuery: { type: String, default: '' }
})

defineEmits(['clear-owner', 'clear-type', 'clear-pricing-type', 'clear-category', 'clear-language', 'clear-search', 'clear-all'])

const hasActiveFilters = computed(() => {
  return !!(
    props.filters.typeAndPricing ||
    props.filters.category ||
    props.filters.onlyMine ||
    props.filters.owner_id ||
    props.showAllLanguages ||
    props.searchQuery
  )
})

const activeFiltersCount = computed(() => {
  let count = 0
  if (props.filters.type) count++
  if (props.filters.pricing_type) count++
  if (props.filters.owner_id || props.filters.onlyMine) count++
  if (props.filters.category) count++
  if (props.showAllLanguages) count++
  if (props.searchQuery) count++
  return count
})
</script>
