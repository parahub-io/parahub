<template>
  <div class="py-6">
    <h1 class="sr-only">{{ $t('market.title') }}</h1>
    <div class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
      <!-- Sticky Header: search toolbar (all sizes) + desktop quick-filter bar (Row 2) -->
      <div class="sticky top-0 z-20 bg-[var(--color-background)] border-b border-neutral-200 dark:border-neutral-800 -mx-4 sm:-mx-6 lg:-mx-8 px-4 sm:px-6 lg:px-8 py-2 sm:py-3 mb-2 sm:mb-4">
        <div class="max-w-5xl mx-auto">
          <!-- Row 1: search + filters trigger + my + create -->
          <div class="flex items-center gap-2">
            <!-- Search bar -->
            <div class="relative flex-grow">
              <input
                v-model="searchQuery"
                @input="debouncedSearch"
                type="text"
                :placeholder="$t('market.search_placeholder')"
                class="w-full min-h-[44px] px-3 py-2 pr-9 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
              >
              <Search class="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400 dark:text-neutral-500" />
            </div>

            <!-- Filters trigger. Mobile: opens the full bottom-sheet (all filters).
                 Desktop: anchored popover with the SECONDARY filters only — the primary
                 ones (type / category / price / sort) live in the visible bar below. -->
            <div class="relative shrink-0">
              <button
                @click="showFiltersSheet = !showFiltersSheet"
                :aria-label="$t('market.filters.title')"
                :title="$t('market.filters.title')"
                class="relative min-h-[44px] h-11 px-3 border rounded-lg bg-white dark:bg-neutral-800 hover:bg-primary-100 dark:hover:bg-primary-900/40 hover:border-primary dark:hover:border-primary flex items-center gap-2 text-neutral-700 dark:text-neutral-300 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
                :class="hasActiveFilters ? 'border-primary' : 'border-neutral-300 dark:border-neutral-600'"
              >
                <SlidersHorizontal class="w-5 h-5" />
                <span class="hidden sm:inline text-sm font-medium">{{ $t('market.filters.title') }}</span>
                <span v-if="activeFiltersCount > 0" class="absolute -top-1.5 -right-1.5 inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 text-[10px] font-bold text-black bg-primary rounded-full ring-2 ring-[var(--color-background)]">
                  {{ activeFiltersCount }}
                </span>
              </button>

              <!-- Desktop secondary-filters popover (language / barter / self-made) -->
              <div v-if="showFiltersSheet" @click="showFiltersSheet = false" class="hidden md:block fixed inset-0 z-40"></div>
              <Transition
                :enter-active-class="animationEnabled ? 'transition ease-out duration-100' : ''"
                :enter-from-class="animationEnabled ? 'opacity-0 scale-95' : ''"
                :enter-to-class="animationEnabled ? 'opacity-100 scale-100' : ''"
                :leave-active-class="animationEnabled ? 'transition ease-in duration-75' : ''"
                :leave-from-class="animationEnabled ? 'opacity-100 scale-100' : ''"
                :leave-to-class="animationEnabled ? 'opacity-0 scale-95' : ''"
              >
                <div
                  v-if="showFiltersSheet"
                  @click.stop
                  class="hidden md:block absolute right-0 top-full mt-2 w-72 origin-top-right bg-white dark:bg-neutral-800 rounded-xl shadow-lg border border-neutral-200 dark:border-neutral-700 z-50 p-4 space-y-4"
                >
                  <!-- Language -->
                  <label class="flex items-center gap-3 cursor-pointer p-2 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors">
                    <input type="checkbox" v-model="showAllLanguages" @change="languageAutoExpanded = false; resetScroll(); fetchItems()" class="w-4 h-4 rounded border-neutral-300 dark:border-neutral-600 text-primary focus:ring-primary">
                    <span class="text-sm text-neutral-700 dark:text-neutral-300">{{ $t('market.filters.show_all_languages') }}</span>
                  </label>
                  <!-- Barter -->
                  <label class="flex items-center gap-3 cursor-pointer p-2 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors">
                    <input type="checkbox" v-model="includeBarter" @change="onPriceFilterChange" class="w-4 h-4 rounded border-neutral-300 dark:border-neutral-600 text-primary focus:ring-primary">
                    <span class="text-sm text-neutral-700 dark:text-neutral-300">{{ $t('market.filters.include_barter') }}</span>
                  </label>
                  <!-- Made-by-hand filter: producers, not resellers ("своими руками") -->
                  <div class="border-t border-neutral-200 dark:border-neutral-700 pt-3">
                    <label class="flex items-start gap-3 cursor-pointer p-2 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors">
                      <input type="checkbox" v-model="selfMadeOnly" @change="onSelfMadeFilterChange" class="mt-0.5 w-4 h-4 rounded border-neutral-300 dark:border-neutral-600 text-primary focus:ring-primary shrink-0">
                      <span class="text-sm text-neutral-700 dark:text-neutral-300">{{ $t('market.filters.self_made_only') }}</span>
                    </label>
                  </div>
                </div>
              </Transition>
            </div>

            <!-- My listings + bookings (auth only) -->
            <UiButton
              v-if="authStore.isAuthenticated"
              :to="localePath('/market/my')"
              :aria-label="$t('market.my_items.title')"
              variant="outline"
              :icon="Package"
              class="min-h-[44px]"
            >
              <span class="hidden sm:inline">{{ $t('market.my_items.title') }}</span>
            </UiButton>

            <!-- Create button (auth only) -->
            <UiButton
              v-if="authStore.isAuthenticated"
              :to="localePath('/market/create')"
              :aria-label="$t('market.create_listing')"
              :icon="Plus"
              class="min-h-[44px]"
            >
              <span class="hidden sm:inline">{{ $t('market.create_listing') }}</span>
            </UiButton>
          </div>

          <!-- Row 2: Desktop quick-filter bar — primary filters surfaced inline -->
          <div class="hidden md:flex flex-wrap items-center gap-2 mt-2">
            <!-- Type -->
            <select
              v-model="filters.typeAndPricing"
              @change="onTypeFilterChange"
              :aria-label="$t('market.filters.type_label')"
              class="h-10 px-3 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
            >
              <option v-for="opt in typeOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
            </select>

            <!-- "For rent" quick filter — discoverable one-tap entry to the rental demand side -->
            <button
              @click="toggleRentFilter"
              :aria-pressed="isRentFilterActive"
              :title="$t('market.filters.offers_rent')"
              class="h-10 px-3 border rounded-lg flex items-center gap-1.5 text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-primary shrink-0"
              :class="isRentFilterActive
                ? 'border-primary bg-primary-100 dark:bg-primary-900/40 text-neutral-900 dark:text-neutral-100'
                : 'border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300 hover:border-primary hover:bg-primary-100 dark:hover:bg-primary-900/40'"
            >
              <KeyRound class="w-4 h-4" />
              {{ $t('market.pricing_type.rent') }}
            </button>

            <!-- Category -->
            <div class="relative flex items-center gap-1">
              <button
                @click="showCategoryFilter = !showCategoryFilter"
                class="h-10 px-3 min-w-[150px] border rounded-lg bg-white dark:bg-neutral-800 text-sm text-neutral-900 dark:text-neutral-100 flex items-center justify-between gap-2 transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
                :class="filters.category ? 'border-primary' : 'border-neutral-300 dark:border-neutral-600'"
              >
                <span v-if="selectedFilterCategory" class="truncate">{{ selectedFilterCategory.icon }} {{ selectedFilterCategory.name }}</span>
                <span v-else class="text-neutral-500 dark:text-neutral-400">{{ $t('market.filters.all_categories') }}</span>
                <ChevronDown class="w-4 h-4 shrink-0" :class="{ 'rotate-180': showCategoryFilter }" />
              </button>
              <button
                v-if="filters.category"
                @click="resetCategoryFilter"
                :title="$t('market.filters.reset_category_title')"
                class="h-10 w-10 flex items-center justify-center border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 hover:bg-neutral-100 dark:hover:bg-neutral-700"
              >
                <X class="w-4 h-4" />
              </button>
              <div v-if="showCategoryFilter" class="absolute left-0 top-full mt-2 w-80 p-3 border border-neutral-200 dark:border-neutral-700 rounded-xl bg-white dark:bg-neutral-800 shadow-lg z-50">
                <CategorySelect
                  v-model="selectedCategoryId"
                  :placeholder="$t('market.filters.all_categories')"
                  domain="market"
                  @change="onFilterCategoryChange"
                />
              </div>
            </div>

            <!-- Price range -->
            <div class="flex items-center gap-1">
              <input
                v-model.number="minPrice"
                type="number"
                min="0"
                step="1"
                :placeholder="$t('market.filters.min_price')"
                @input="debouncedPriceFilter"
                :aria-label="$t('market.filters.min_price')"
                class="h-10 w-24 px-3 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
              />
              <span class="text-neutral-400">–</span>
              <input
                v-model.number="maxPrice"
                type="number"
                min="0"
                step="1"
                :placeholder="$t('market.filters.max_price')"
                @input="debouncedPriceFilter"
                :aria-label="$t('market.filters.max_price')"
                class="h-10 w-24 px-3 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
              />
            </div>

            <!-- Sort (not a filter — pushed to the far right) -->
            <select
              v-model="sortBy"
              @change="onSortChange"
              :aria-label="$t('market.sort.label')"
              class="h-10 px-3 ml-auto border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
            >
              <option value="-created_at">{{ $t('market.sort.newest') }}</option>
              <option value="created_at">{{ $t('market.sort.oldest') }}</option>
              <option value="min_price">{{ $t('market.sort.price_low') }}</option>
              <option value="-min_price">{{ $t('market.sort.price_high') }}</option>
              <option value="distance">{{ $t('market.sort.nearest') }}</option>
            </select>
          </div>
        </div>
      </div>

      <!-- Barter Banner -->
      <MarketBarterBanner />

      <!-- Filters Bottom Sheet (mobile only; desktop uses the bar + secondary popover above) -->
      <Transition
        :enter-active-class="animationEnabled ? 'transition-all duration-75 ease-out' : ''"
        :enter-from-class="animationEnabled ? 'opacity-0 translate-y-full' : ''"
        :enter-to-class="animationEnabled ? 'opacity-100 translate-y-0' : ''"
        :leave-active-class="animationEnabled ? 'transition-all duration-[50ms] ease-in' : ''"
        :leave-from-class="animationEnabled ? 'opacity-100 translate-y-0' : ''"
        :leave-to-class="animationEnabled ? 'opacity-0 translate-y-full' : ''"
      >
        <div v-if="showFiltersSheet" class="md:hidden fixed inset-0 z-50 flex items-end">
          <!-- Backdrop (invisible, closes on click) -->
          <div
            @click="showFiltersSheet = false"
            class="absolute inset-0 bg-transparent"
          ></div>

          <!-- Filters Panel -->
          <div class="relative w-full bg-white dark:bg-neutral-800 rounded-t-2xl shadow-2xl max-h-[80vh] overflow-y-auto">
            <!-- Header -->
            <div class="sticky top-0 bg-white dark:bg-neutral-800 border-b border-neutral-200 dark:border-neutral-700 px-4 py-3 flex items-center justify-between">
              <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100">{{ $t('market.filters.title') }}</h3>
              <button @click="showFiltersSheet = false" class="p-1 hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded">
                <X class="w-5 h-5" />
              </button>
            </div>

            <!-- Filters Content -->
            <div class="p-4 space-y-4">
              <!-- "For rent" quick filter — surfaced at the top for discoverability -->
              <button
                @click="toggleRentFilter"
                :aria-pressed="isRentFilterActive"
                class="w-full px-3 py-2.5 border rounded-lg flex items-center justify-center gap-2 text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
                :class="isRentFilterActive
                  ? 'border-primary bg-primary-100 dark:bg-primary-900/40 text-neutral-900 dark:text-neutral-100'
                  : 'border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300 hover:border-primary hover:bg-primary-100 dark:hover:bg-primary-900/40'"
              >
                <KeyRound class="w-4 h-4" />
                {{ $t('market.filters.offers_rent') }}
              </button>

              <!-- Active owner_id filter badge -->
              <div v-if="filters.owner_id && ownerDisplayName" class="flex items-center justify-between p-3 bg-primary/10 border border-primary/30 rounded-lg">
                <div class="flex items-center gap-2">
                  <span class="text-sm font-medium text-neutral-900 dark:text-neutral-100">
                    {{ $t('market.filters.filtered_by_user') }}: {{ ownerDisplayName }}
                  </span>
                </div>
                <button
                  @click="clearOwnerFilter"
                  class="p-1 hover:bg-primary/20 rounded-full transition-colors"
                  :title="$t('market.filters.clear_user_filter')"
                >
                  <X class="w-4 h-4 text-neutral-700 dark:text-neutral-300" />
                </button>
              </div>

              <!-- Sort -->
              <div>
                <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
                  {{ $t('market.sort.label') }}
                </label>
                <select
                  v-model="sortBy"
                  @change="onSortChange"
                  class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
                >
                  <option value="-created_at">{{ $t('market.sort.newest') }}</option>
                  <option value="created_at">{{ $t('market.sort.oldest') }}</option>
                  <option value="min_price">{{ $t('market.sort.price_low') }}</option>
                  <option value="-min_price">{{ $t('market.sort.price_high') }}</option>
                  <option value="distance">{{ $t('market.sort.nearest') }}</option>
                </select>
              </div>

              <!-- Language Filter -->
              <div>
                <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
                  {{ $t('market.filters.language_label') }}
                </label>
                <label class="flex items-center gap-3 cursor-pointer p-2 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors">
                  <input
                    type="checkbox"
                    v-model="showAllLanguages"
                    @change="languageAutoExpanded = false; resetScroll(); fetchItems()"
                    class="w-4 h-4 rounded border-neutral-300 dark:border-neutral-600 text-primary focus:ring-primary"
                  >
                  <span class="text-sm text-neutral-700 dark:text-neutral-300">{{ $t('market.filters.show_all_languages') }}</span>
                </label>
              </div>

              <!-- Type Filter -->
              <div>
                <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
                  {{ $t('market.filters.type_label') }}
                </label>
                <select
                  v-model="filters.typeAndPricing"
                  @change="onTypeFilterChange"
                  class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
                >
                  <option v-for="opt in typeOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                </select>
              </div>

              <!-- Category Filter -->
              <div>
                <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
                  {{ $t('market.filters.category_label') }}
                </label>
                <div class="flex gap-2">
                  <button
                    @click="showCategoryFilter = !showCategoryFilter"
                    class="flex-1 px-3 py-2 border rounded-lg bg-white dark:bg-neutral-800 text-sm text-left flex items-center justify-between transition-colors focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
                    :class="filters.category ? 'border-primary' : 'border-neutral-300 dark:border-neutral-600'"
                  >
                    <span v-if="selectedFilterCategory">
                      {{ selectedFilterCategory.icon }} {{ selectedFilterCategory.name }}
                    </span>
                    <span v-else class="text-neutral-500 dark:text-neutral-400">
                      {{ $t('market.filters.all_categories') }}
                    </span>
                    <ChevronDown class="w-4 h-4" :class="{ 'rotate-180': showCategoryFilter }" />
                  </button>
                  <button
                    v-if="filters.category"
                    @click="resetCategoryFilter"
                    class="px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-sm hover:bg-neutral-100 dark:hover:bg-neutral-700"
                    :title="$t('market.filters.reset_category_title')"
                  >
                    <X class="w-4 h-4" />
                  </button>
                </div>

                <!-- Category Dropdown -->
                <div v-if="showCategoryFilter" class="mt-2 p-3 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-neutral-50 dark:bg-neutral-900">
                  <CategorySelect
                    v-model="selectedCategoryId"
                    :placeholder="$t('market.filters.all_categories')"
                    domain="market"
                    @change="onFilterCategoryChange"
                  />
                </div>
              </div>

              <!-- Price Range Filter -->
              <div>
                <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
                  {{ $t('market.filters.price_range') }}
                </label>
                <div class="flex items-center gap-2">
                  <input
                    v-model.number="minPrice"
                    type="number"
                    min="0"
                    step="1"
                    :placeholder="$t('market.filters.min_price')"
                    @input="debouncedPriceFilter"
                    class="flex-1 px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
                  />
                  <span class="text-neutral-400">–</span>
                  <input
                    v-model.number="maxPrice"
                    type="number"
                    min="0"
                    step="1"
                    :placeholder="$t('market.filters.max_price')"
                    @input="debouncedPriceFilter"
                    class="flex-1 px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
                  />
                </div>
                <label class="flex items-center gap-3 cursor-pointer p-2 mt-2 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors">
                  <input
                    type="checkbox"
                    v-model="includeBarter"
                    @change="onPriceFilterChange"
                    class="w-4 h-4 rounded border-neutral-300 dark:border-neutral-600 text-primary focus:ring-primary"
                  />
                  <span class="text-sm text-neutral-700 dark:text-neutral-300">{{ $t('market.filters.include_barter') }}</span>
                </label>
              </div>

              <!-- Made-by-hand filter: producers, not resellers ("своими руками") -->
              <div class="border-t border-neutral-200 dark:border-neutral-700 pt-4">
                <label class="flex items-start gap-3 cursor-pointer p-2 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors">
                  <input
                    type="checkbox"
                    v-model="selfMadeOnly"
                    @change="onSelfMadeFilterChange"
                    class="mt-0.5 w-4 h-4 rounded border-neutral-300 dark:border-neutral-600 text-primary focus:ring-primary shrink-0"
                  />
                  <span class="text-sm text-neutral-700 dark:text-neutral-300">{{ $t('market.filters.self_made_only') }}</span>
                </label>
              </div>

              <!-- Action Buttons -->
              <div class="flex gap-2 pt-2 border-t border-neutral-200 dark:border-neutral-700">
                <UiButton variant="outline" class="flex-1" @click="resetAllFilters">
                  {{ $t('market.filters.reset') }}
                </UiButton>
                <UiButton class="flex-1" @click="showFiltersSheet = false">
                  {{ $t('market.filters.apply') }}
                </UiButton>
              </div>
            </div>
          </div>
        </div>
      </Transition>

      <!-- Active Filters Pills -->
      <MarketFiltersPills
        :filters="filters"
        :owner-display-name="ownerDisplayName"
        :selected-filter-category="selectedFilterCategory"
        :show-all-languages="showAllLanguages"
        :search-query="searchQuery"
        @clear-owner="clearOwnerFilter"
        @clear-type="clearTypeFilter"
        @clear-pricing-type="clearPricingTypeFilter"
        @clear-category="clearCategoryPill"
        @clear-language="showAllLanguages = false; languageAutoExpanded = false; resetScroll(); fetchItems()"
        @clear-search="searchQuery = ''; resetScroll(); fetchItems()"
        @clear-all="resetAllFilters"
      />

      <!-- Auto-expanded language banner: shown when locale had 0 items, showing all languages instead -->
      <UiAlert v-if="languageAutoExpanded && items.length > 0" variant="info" :icon="Globe" class="max-w-4xl mx-auto mb-4">
        <div class="flex items-center gap-3">
          <p class="flex-1">{{ $t('market.language_auto_expanded') }}</p>
          <UiButton
            v-if="authStore.isAuthenticated"
            :to="localePath('/market/create')"
            size="sm"
            class="shrink-0"
          >
            {{ $t('market.create_in_your_language') }}
          </UiButton>
        </div>
      </UiAlert>

      <!-- Loading state with skeletons -->
      <div v-if="pending || loading || isInitialRefetch" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        <MarketItemSkeleton v-for="n in 8" :key="n" />
      </div>

      <!-- Items grid -->
      <div v-else-if="items.length > 0" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        <MarketItemCard
          v-for="item in items"
          :key="item.id"
          :item="item"
          :auth-profile-id="authStore.profile?.id"
          :my-item-categories="myItemCategories"
          :category-map="categoryMap"
          @filter-category="onCardCategoryFilter"
        />
      </div>

      <!-- Empty state -->
      <div v-else class="text-center py-12">
        <!-- Language hint: shown when language filter may be hiding items -->
        <UiAlert v-if="!showAllLanguages" variant="warning" class="max-w-md mx-auto mb-8 text-left">
          <p class="text-sm mb-3">{{ $t('market.empty.language_hint') }}</p>
          <UiButton size="sm" @click="showAllLanguages = true; resetScroll(); fetchItems()">
            {{ $t('market.empty.show_all_languages') }}
          </UiButton>
        </UiAlert>

        <img src="/images/para/searching.webp" alt="Para" class="mx-auto h-32 w-auto mb-6" />
        <h3 class="text-xl font-semibold text-neutral-700 dark:text-neutral-300 mb-2">
          {{ $t('market.empty.title') }}
        </h3>
        <p class="text-neutral-600 dark:text-neutral-400 mb-6">
          {{ $t('market.empty.description') }}
        </p>
        <UiButton v-if="authStore.isAuthenticated" :to="localePath('/market/create')">
          {{ $t('market.empty.create_first') }}
        </UiButton>
      </div>

      <!-- Infinite scroll sentinel -->
      <div ref="scrollSentinel" data-testid="infinite-scroll-sentinel" class="mt-8 flex justify-center" role="status" aria-live="polite">
        <div v-if="loading && items.length > 0" class="text-neutral-600 dark:text-neutral-400 text-sm">
          {{ $t('market.loading_more') || 'Loading more...' }}
        </div>
        <div v-else-if="hasMoreItems" class="h-4"></div>
        <div v-else-if="items.length > 0" class="text-neutral-500 dark:text-neutral-400 text-sm">
          {{ $t('market.no_more_items') || 'No more items' }}
        </div>
      </div>
    </div>

    <!-- Edit Modal -->
    <MarketEditModal
      :model-value="editingItem"
      @update:model-value="editingItem = $event"
      @updated="fetchItems()"
    />

    <!-- Delete Confirmation Modal -->
    <MarketDeleteModal
      :model-value="deletingItem"
      @update:model-value="deletingItem = $event"
      @deleted="fetchItems()"
    />

  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, onActivated, watch, nextTick } from 'vue'
import { useAuthStore } from '~/stores/auth'
import { useMapStore } from '~/stores/map'
import { useNotification } from '~/composables/useNotification'
import { useCategories } from '~/composables/useCategories'
import { Search, Plus, X, Package, ChevronDown, Globe, SlidersHorizontal, KeyRound } from 'lucide-vue-next'
import CategorySelect from '~/components/CategorySelect.vue'
import MarketItemSkeleton from '~/components/MarketItemSkeleton.vue'

// Market is public - no auth required for browsing
definePageMeta({
  keepalive: true  // Enable KeepAlive caching for instant switching
})

const authStore = useAuthStore()
const mapStore = useMapStore()
const { showSuccess, showError } = useNotification()
const { fetchCategoryTree, buildNestedOptions, fetchCategory, loading: categoriesLoading, currentLang } = useCategories()
const { locale, t: $t } = useI18n()
const { formatPricingOption } = usePricingFormat()

// Get URL query params
const route = useRoute()
const router = useRouter()
const localePath = useLocalePath()

// SEO meta
useSeoMeta({
  title: $t('market.title') + ' - Parahub',
  ogTitle: $t('market.title') + ' - Parahub',
  description: $t('market.meta_description'),
  ogDescription: $t('market.meta_description'),
  ogImage: '/og-image.jpg',
  ogType: 'website',
  twitterCard: 'summary_large_image',
})

// Currency preference (localStorage, shared with useBtcPrice)
const userCurrency = useLocalPref('preferred_currency', 'EUR')

// Animation enabled preference (localStorage, shared with PreferencesSection)
const animationEnabled = useLocalPref('animation_enabled', true)

// Initial filters from URL
const initialFilters = {
  type: route.query.type || '',
  pricing_type: route.query.pricing_type || '',
  category: route.query.category || '',
  owner_id: route.query.owner_id || '',  // Filter by specific user
  // onlyMine filter is CLIENT-SIDE ONLY (requires authentication)
  // SSR always loads all items, filtering happens client-side after mount
  onlyMine: false  // Always false in SSR, will be set client-side
}

// SSR data loading - load categories and items in parallel
// Cache key includes query params to prevent showing wrong data when filters change
const cacheKey = `market-page:${route.query.type || ''}:${route.query.pricing_type || ''}:${route.query.category || ''}:${route.query.owner_id || ''}:${route.query.onlyMine || ''}`
const { data: initialData, pending, refresh: refreshAsyncData } = await useAsyncData(cacheKey, async () => {
  try {
    // Load categories and items in parallel
    const [categoryTree, itemsResponse] = await Promise.all([
      // Load categories
      fetchCategoryTree().catch(err => {
        console.error('Failed to load categories:', err)
        return []
      }),

      // SKIP SSR item loading - always load on client side
      // SSR requests fail with 401 (no user session available in SSR context)
      // Items will be loaded in onMounted via fetchItems()
      Promise.resolve({ items: [], pages: 1 })
    ])

    // Note: Profile loading moved to client-side only (in onMounted)
    // to properly handle authentication with session cookies

    // Load selected category if in URL
    let selectedCategory = null
    if (initialFilters.category) {
      try {
        selectedCategory = await fetchCategory(initialFilters.category)
      } catch (err) {
        console.error('Failed to load category from URL:', err)
      }
    }

    return {
      categories: buildNestedOptions(categoryTree),
      items: Array.isArray(itemsResponse) ? itemsResponse : (itemsResponse.items || itemsResponse.results || []),
      totalPages: Array.isArray(itemsResponse) ? 1 : (itemsResponse.pages || Math.ceil((itemsResponse.count || 0) / 20) || 1),
      selectedCategory
    }
  } catch (error) {
    console.error('Failed to load initial data:', error)
    return {
      categories: [],
      items: [],
      totalPages: 1,
      selectedCategory: null
    }
  }
}, {
  // SSR configuration
  server: true,
  lazy: false,
  // Note: getCachedData removed - rely on cacheKey + onActivated to handle KeepAlive properly
  default: () => ({
    categories: [],
    items: [],
    totalPages: 1,
    selectedCategory: null
  })
})

// State - initialized from SSR data
const items = ref(initialData.value?.items || [])
const totalPages = ref(initialData.value?.totalPages || 1)
const hasMoreItems = ref(true)
const totalCount = ref(0)
const rootCategories = ref(initialData.value?.categories || [])

// Real-time updates for listed items
useObjectListSubscription(items)

const loading = ref(false)
// Track initial refetch in onMounted to prevent flicker
// Set to true immediately if query params present (will refetch in onMounted)
const isInitialRefetch = ref(!!(route.query.owner_id || route.query.type || route.query.pricing_type))
const aiAnalysisLogId = ref(null)  // Track AI analysis log for accuracy monitoring

const showCategoryFilter = ref(false)
const editingItem = ref(null)
const deletingItem = ref(null)
const ownerDisplayName = ref('') // Display name for owner_id filter

// New UI state variables
const showFiltersSheet = ref(false) // Bottom sheet for filters (mobile) / dropdown (desktop)
const sortBy = ref('-created_at') // Sort order: -created_at (newest), created_at (oldest), min_price, -min_price
const matchCounts = ref({ offer_matches: 0, want_matches: 0 }) // Match counters for filters

// Price range filter
const minPrice = ref(null)
const maxPrice = ref(null)
const includeBarter = ref(true)  // Default: include barter-only items
const selfMadeOnly = ref(route.query.self_made === 'true')  // Show only producer-made items ("своими руками")
const myItemCategories = ref({ credit: [], debit: [] }) // My items' categories for match detection

// Infinite scroll sentinel ref
const scrollSentinel = ref(null)

// Track when language filter was auto-expanded (0 items in user's language)
const languageAutoExpanded = ref(false)

// Use persistent market filters (survives tab switching)
const { filters, searchQuery, currentPage, selectedFilterCategory, showAllLanguages, setFilters, setSelectedFilterCategory } = useMarketFilters()

// Always initialize from URL params (URL is source of truth)
const urlFilters = {
  type: route.query.type || '',
  pricing_type: route.query.pricing_type || '',
  category: route.query.category || '',
  owner_id: route.query.owner_id || '',
  typeAndPricing: '',
  onlyMine: route.query.onlyMine === 'true'
}

// Initialize combined filter from URL params
if (urlFilters.type && urlFilters.pricing_type) {
  urlFilters.typeAndPricing = `${urlFilters.type}:${urlFilters.pricing_type}`
} else if (urlFilters.type) {
  urlFilters.typeAndPricing = urlFilters.type
}

setFilters(urlFilters)

// Initialize selected category from SSR data
if (initialData.value?.selectedCategory) {
  setSelectedFilterCategory(initialData.value.selectedCategory)
}

// Computed property for category ID (for CategorySelect v-model)
const selectedCategoryId = computed({
  get() {
    return selectedFilterCategory.value?.id || null
  },
  set(id) {
    // This will be handled by @change event
  }
})

// Build a Map of slug -> category data for fast lookups (for i18n category names)
const categoryMap = ref(new Map())

// Helper to build category map from tree
const buildCategoryMap = (categories) => {
  const map = new Map()

  const flattenCategories = (cats) => {
    for (const cat of cats) {
      map.set(cat.slug, { name: cat.name, icon: cat.icon, id: cat.id })
      if (cat.children && cat.children.length > 0) {
        flattenCategories(cat.children)
      }
    }
  }

  flattenCategories(categories)
  return map
}

// Computed for active filters indicator
const hasActiveFilters = computed(() => {
  return !!(
    filters.value.typeAndPricing ||
    filters.value.category ||
    filters.value.onlyMine ||
    filters.value.owner_id ||
    showAllLanguages.value ||
    selfMadeOnly.value ||
    minPrice.value != null && minPrice.value !== '' ||
    maxPrice.value != null && maxPrice.value !== ''
  )
})

const activeFiltersCount = computed(() => {
  let count = 0
  if (filters.value.typeAndPricing) count++
  if (filters.value.category) count++
  if (filters.value.owner_id || filters.value.onlyMine) count++ // Count active owner deep-link filter
  if (showAllLanguages.value) count++ // Show all languages = non-default state
  if ((minPrice.value != null && minPrice.value !== '') || (maxPrice.value != null && maxPrice.value !== '')) count++
  if (selfMadeOnly.value) count++ // Producer-made only ("своими руками")
  return count
})

// Type/pricing options — shared by the desktop quick-filter bar and the mobile sheet.
// Match options require auth; their live counts are folded into the label string because
// a native <option> renders only its text content (nested <span> counts never displayed).
const typeOptions = computed(() => {
  const opts = [
    { value: '', label: $t('market.filters.all_types') },
    { value: 'CREDIT', label: $t('market.filters.offers') },
    { value: 'CREDIT:sale', label: $t('market.filters.offers_sale') },
    { value: 'CREDIT:rent', label: $t('market.filters.offers_rent') },
    { value: 'CREDIT:free', label: $t('market.filters.offers_free') },
    { value: 'DEBIT', label: $t('market.filters.requests') },
    { value: 'DEBIT:sale', label: $t('market.filters.requests_sale') },
    { value: 'DEBIT:rent', label: $t('market.filters.requests_rent') },
    { value: 'DEBIT:free', label: $t('market.filters.requests_free') }
  ]
  if (authStore.isAuthenticated) {
    const om = matchCounts.value.offer_matches
    const wm = matchCounts.value.want_matches
    opts.push({ value: 'MATCH:offer_matches', label: $t('market.filters.matches_i_can_offer') + (om > 0 ? ` (${om})` : '') })
    opts.push({ value: 'MATCH:want_matches', label: $t('market.filters.matches_i_want') + (wm > 0 ? ` (${wm})` : '') })
  }
  return opts
})

// AbortController for search/filter fetches (not infinite scroll)
let fetchSearchController = null

// Fetch items from API
const fetchItems = async (append = false, savedScrollPosition = null) => {
  // Don't fetch if no more items (infinite scroll guard)
  if (append && !hasMoreItems.value) return

  if (append) {
    // Prevent concurrent infinite scroll requests
    if (loading.value) return
  } else {
    // For search/filter: cancel previous in-flight request and start fresh
    fetchSearchController?.abort()
    fetchSearchController = new AbortController()
  }

  loading.value = true
  try {
    await authStore.ensureToken()

    const params = new URLSearchParams({
      page: currentPage.value,
      is_active: true
    })

    // Check if typeAndPricing is a match filter
    const isMatchFilter = filters.value.typeAndPricing?.startsWith('MATCH:')

    if (isMatchFilter) {
      // Extract match_type from MATCH:offer_matches or MATCH:want_matches
      const matchType = filters.value.typeAndPricing.split(':')[1]
      params.append('match_type', matchType)
    } else {
      // Regular type/pricing filters
      if (filters.value.type) params.append('item_type', filters.value.type)
      if (filters.value.pricing_type) params.append('pricing_type', filters.value.pricing_type)
    }

    if (filters.value.category) params.append('category', filters.value.category)
    if (searchQuery.value) params.append('q', searchQuery.value)
    if (userCurrency.value) params.append('target_currency', userCurrency.value)

    // Price range filter
    if (minPrice.value != null && minPrice.value !== '') params.append('min_price', minPrice.value)
    if (maxPrice.value != null && maxPrice.value !== '') params.append('max_price', maxPrice.value)
    if (includeBarter.value) params.append('include_barter', 'true')
    if (selfMadeOnly.value) params.append('self_made', 'true')

    // Language filter: send locale when not showing all languages
    if (!showAllLanguages.value && locale.value) {
      params.append('language', locale.value)
    }

    // Sorting
    if (sortBy.value) {
      params.append('ordering', sortBy.value)

      // Distance sorting requires lat/lng parameters
      if (sortBy.value === 'distance') {
        const [lng, lat] = mapStore.center
        params.append('lat', lat)
        params.append('lng', lng)
      }
    }

    // Owner filter - can be set from URL (owner_id) or from "Only Mine" checkbox
    if (filters.value.owner_id) {
      params.append('owner_id', filters.value.owner_id)
    } else if (filters.value.onlyMine) {
      // Ensure profile is loaded
      if (!authStore.profile) {
        try {
          const profile = await $fetch('/api/v1/profiles/me/', {
            headers: authStore.accessToken ? { Authorization: `Bearer ${authStore.accessToken}` } : {},
            credentials: 'include'
          })
          if (profile?.id) {
            params.append('owner_id', profile.id)
          }
        } catch (err) {
          console.error('Failed to load profile for filter:', err)
        }
      } else if (authStore.profile.id) {
        params.append('owner_id', authStore.profile.id)
      }
    }

    // Update URL query params (only on initial load, not on infinite scroll append)
    // Use router.replace() to avoid adding history entries and triggering unnecessary navigation
    if (!append) {
      const query = {}
      if (filters.value.type) query.type = filters.value.type
      if (filters.value.pricing_type) query.pricing_type = filters.value.pricing_type
      if (filters.value.category) query.category = filters.value.category
      if (filters.value.owner_id) query.owner_id = filters.value.owner_id  // CRITICAL: Keep owner_id in URL
      if (searchQuery.value) query.q = searchQuery.value
      if (filters.value.onlyMine) query.onlyMine = 'true'
      if (selfMadeOnly.value) query.self_made = 'true'

      router.replace({ query })
    }

    const response = await $fetch(`/api/v1/items/?${params}`, {
      headers: authStore.accessToken ? { Authorization: `Bearer ${authStore.accessToken}` } : {},
      credentials: 'include',
      signal: !append ? fetchSearchController?.signal : undefined
    })

    // Handle paginated or direct array response
    const newItems = Array.isArray(response) ? response : (response.items || response.results || [])
    const count = Array.isArray(response) ? response.length : (response.count || 0)

    // Append or replace items
    if (append) {
      // CRITICAL: Preserve scroll position during infinite scroll
      // When new items are added to DOM, browser recalculates layout and scroll position jumps
      const mainContent = document.getElementById('main-content')
      const scrollToRestore = savedScrollPosition || (mainContent ? mainContent.scrollTop : 0)

      // Use push() instead of array spread to avoid recreating the entire array
      // This helps Vue's diff algorithm keep existing DOM elements
      newItems.forEach(item => items.value.push(item))

      // Wait for DOM to fully render before restoring scroll
      // nextTick() is not enough - need to wait for browser layout/paint
      await nextTick()
      await new Promise(resolve => requestAnimationFrame(() => {
        requestAnimationFrame(resolve)
      }))

      if (mainContent && scrollToRestore > 0) {
        mainContent.scrollTop = scrollToRestore
        const actualScrollTop = mainContent.scrollTop

        // If couldn't restore fully (DOM still rendering), retry after short delay
        if (actualScrollTop < scrollToRestore - 50) {
          setTimeout(() => {
            mainContent.scrollTop = scrollToRestore
          }, 100)
        }
      }
    } else {
      items.value = newItems
    }

    // Update pagination state
    totalCount.value = count
    totalPages.value = Array.isArray(response) ? 1 : (response.pages || Math.ceil(count / 20) || 1)
    hasMoreItems.value = currentPage.value < totalPages.value
  } catch (error) {
    if (error?.name === 'AbortError' || error?.cause?.name === 'AbortError') return
    console.error('Failed to fetch items:', error)
    showError($t('market.notifications.load_error'))
  } finally {
    loading.value = false
  }
}

// Load more items for infinite scroll
const loadMore = async () => {
  if (!hasMoreItems.value || loading.value) return

  // CRITICAL: Save scroll position BEFORE any DOM changes
  const mainContent = document.getElementById('main-content')
  const savedScrollPosition = mainContent ? mainContent.scrollTop : window.scrollY

  currentPage.value++
  await fetchItems(true, savedScrollPosition)
}

// Fetch match counts for filter labels and my items categories
const fetchMatchCounts = async () => {
  if (!authStore.isAuthenticated) return

  try {
    await authStore.ensureToken()

    // Fetch my active items to get category lists
    const myItemsResponse = await $fetch('/api/v1/items/?owner_id=' + authStore.profile.id + '&is_active=true&page_size=1000', {
      credentials: 'include',
      headers: authStore.accessToken ? { Authorization: `Bearer ${authStore.accessToken}` } : {}
    })

    const myItems = myItemsResponse.items || []

    // Extract category IDs from my CREDIT and DEBIT items
    myItemCategories.value.credit = [...new Set(
      myItems
        .filter(item => item.item_type === 'CREDIT' && item.category_id)
        .map(item => item.category_id)
    )]

    myItemCategories.value.debit = [...new Set(
      myItems
        .filter(item => item.item_type === 'DEBIT' && item.category_id)
        .map(item => item.category_id)
    )]

    // Fetch offer matches count (items I can offer)
    const offerMatchesResponse = await $fetch('/api/v1/items/?match_type=offer_matches&page_size=1', {
      credentials: 'include',
      headers: authStore.accessToken ? { Authorization: `Bearer ${authStore.accessToken}` } : {}
    })
    matchCounts.value.offer_matches = offerMatchesResponse.count || 0

    // Fetch want matches count (items I want)
    const wantMatchesResponse = await $fetch('/api/v1/items/?match_type=want_matches&page_size=1', {
      credentials: 'include',
      headers: authStore.accessToken ? { Authorization: `Bearer ${authStore.accessToken}` } : {}
    })
    matchCounts.value.want_matches = wantMatchesResponse.count || 0
  } catch (error) {
    console.error('Failed to fetch match counts:', error)
  }
}

// Debounced search
let searchTimeout = null
const debouncedSearch = () => {
  clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => {
    currentPage.value = 1
    hasMoreItems.value = true
    fetchItems()
  }, 500)
}

// Reset scroll - called when filters change
const resetScroll = () => {
  currentPage.value = 1
  hasMoreItems.value = true
  items.value = []
}

// Handle type filter change
const onTypeFilterChange = () => {
  const value = filters.value.typeAndPricing
  if (value.includes(':')) {
    const [type, pricingType] = value.split(':')
    filters.value.type = type
    filters.value.pricing_type = pricingType
  } else if (value) {
    filters.value.type = value
    filters.value.pricing_type = ''
  } else {
    filters.value.type = ''
    filters.value.pricing_type = ''
  }
  resetScroll()
  fetchItems()
}

// "For rent" quick filter — a discoverable one-tap shortcut to offers-for-rent
// (CREDIT:rent). Reuses typeAndPricing so the dropdown + active-filter pills stay
// in sync; toggling off clears the type/pricing filter.
const isRentFilterActive = computed(() => filters.value.typeAndPricing === 'CREDIT:rent')
const toggleRentFilter = () => {
  filters.value.typeAndPricing = isRentFilterActive.value ? '' : 'CREDIT:rent'
  onTypeFilterChange()
}

// Handle sort change
const onSortChange = () => {
  resetScroll()
  fetchItems()
}

const onPriceFilterChange = () => {
  resetScroll()
  fetchItems()
}

const onSelfMadeFilterChange = () => {
  resetScroll()
  fetchItems()
}

let priceFilterTimeout = null
const debouncedPriceFilter = () => {
  clearTimeout(priceFilterTimeout)
  priceFilterTimeout = setTimeout(() => {
    resetScroll()
    fetchItems()
  }, 500)
}

// Reset category filter
const resetCategoryFilter = () => {
  setSelectedFilterCategory(null)
  filters.value.category = ''
  showCategoryFilter.value = false
  resetScroll()
  fetchItems()
}

// Handle filter category change
const onFilterCategoryChange = (category) => {
  if (category) {
    setSelectedFilterCategory(category)
    filters.value.category = category.slug
  } else {
    setSelectedFilterCategory(null)
    filters.value.category = ''
  }
  showCategoryFilter.value = false
  resetScroll()
  fetchItems()
}

// Handle category filter from item card click
const onCardCategoryFilter = (slug) => {
  filters.value.category = slug
  resetScroll()
  fetchItems()
}

// Clear owner filter
const clearOwnerFilter = () => {
  filters.value.owner_id = ''
  filters.value.onlyMine = false
  ownerDisplayName.value = ''
  router.push({ query: { ...route.query, owner_id: undefined, onlyMine: undefined } })
  resetScroll()
  fetchItems()
}

// Clear type filter (from pills)
const clearTypeFilter = () => {
  filters.value.type = ''
  filters.value.typeAndPricing = ''
  resetScroll()
  fetchItems()
}

// Clear pricing type filter (from pills)
const clearPricingTypeFilter = () => {
  filters.value.pricing_type = ''
  filters.value.typeAndPricing = filters.value.type || ''
  resetScroll()
  fetchItems()
}

// Clear category pill
const clearCategoryPill = () => {
  setSelectedFilterCategory(null)
  filters.value.category = ''
  resetScroll()
  fetchItems()
}

// Reset all filters
const resetAllFilters = () => {
  filters.value.typeAndPricing = ''
  filters.value.type = ''
  filters.value.pricing_type = ''
  filters.value.category = ''
  filters.value.onlyMine = false
  filters.value.owner_id = ''
  showAllLanguages.value = false
  languageAutoExpanded.value = false
  setSelectedFilterCategory(null)
  showCategoryFilter.value = false
  ownerDisplayName.value = ''
  searchQuery.value = ''
  minPrice.value = null
  maxPrice.value = null
  includeBarter.value = true
  selfMadeOnly.value = false
  resetScroll()
  fetchItems()
}

// Load owner display name for filter badge
const loadOwnerDisplayName = async (ownerId) => {
  if (!ownerId) {
    ownerDisplayName.value = ''
    return
  }

  try {
    const profile = await $fetch(`/api/v1/profiles/${ownerId}/`, {
      credentials: 'include'
    })
    ownerDisplayName.value = profile.display_name || profile.hna || ownerId
  } catch (err) {
    console.error('Failed to load owner display name:', err)
    ownerDisplayName.value = ownerId // Fallback to ID
  }
}

// Load categories (client-side refresh if needed)
const loadCategories = async () => {
  try {
    const tree = await fetchCategoryTree()
    rootCategories.value = buildNestedOptions(tree)
  } catch (error) {
    console.error('Failed to load categories:', error)
  }
}

// Close category filter when clicking outside
const handleClickOutside = (event) => {
  if (showCategoryFilter.value && !event.target.closest('.relative')) {
    showCategoryFilter.value = false
  }
}

// Contact seller - create DM room with auto-accept and navigate to chat
const contactSeller = async (item) => {
  if (!item.owner_account_id || !item.owner_id) {
    console.error('[market] Missing owner_account_id or owner_id')
    showError($t('market.notifications.seller_not_found'))
    return
  }

  if (!authStore.isAuthenticated) {
    router.push(localePath('/login'))
    return
  }

  try {
    await authStore.ensureToken()

    const response = await $fetch('/api/v1/matrix/create-dm', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`,
        'Content-Type': 'application/json'
      },
      body: {
        target_account_id: item.owner_account_id,
        item_id: item.id,
        item_title: item.title
      }
    })

    if (response.success && response.room_id) {
      router.push({
        path: localePath('/chat'),
        query: { room_id: response.room_id }
      })
    } else {
      console.error('[market] create-dm failed:', response.error)
      showError(response.error || 'Failed to create chat room')
    }
  } catch (error) {
    console.error('[market] Exception in create-dm:', error)
    showError('Failed to create chat room')
  }
}

// ESC key handler to close modals
function handleEscape(event) {
  if (event.key === 'Escape') {
    if (editingItem.value) {
      editingItem.value = null
    } else if (deletingItem.value) {
      deletingItem.value = null
    }
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)

  // Set up infinite scroll observer
  if (scrollSentinel.value) {
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMoreItems.value && !loading.value) {
          loadMore()
        }
      },
      {
        rootMargin: '100px' // Start loading 100px before sentinel is visible
      }
    )
    observer.observe(scrollSentinel.value)

    // Clean up observer on unmount
    onUnmounted(() => {
      observer.disconnect()
    })
  }
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})

// Watch language changes to reload category names
watch(currentLang, async (newLang, oldLang) => {
  if (newLang !== oldLang) {
    try {
      const tree = await fetchCategoryTree()
      categoryMap.value = buildCategoryMap(tree)
    } catch (err) {
      console.error('[Market] Failed to rebuild category map on language change:', err)
    }
  }
})

// Watch ALL query params for filter changes (critical for KeepAlive + navigation with query params)
watch(() => route.query, async (newQuery, oldQuery) => {
  // CRITICAL: Check if query actually changed (ignore key order changes)
  const isInitialNavigation = !oldQuery || Object.keys(oldQuery).length === 0
  if (!isInitialNavigation) {
    // Compare query values (ignore key order)
    const oldKeys = Object.keys(oldQuery || {}).sort()
    const newKeys = Object.keys(newQuery || {}).sort()

    if (oldKeys.length === newKeys.length && oldKeys.every((key, i) => key === newKeys[i])) {
      // Same keys, check values
      const valuesChanged = oldKeys.some(key => oldQuery[key] !== newQuery[key])
      if (!valuesChanged) {
        return
      }
    }
  }

  let needsRefetch = false

  // Check owner_id filter
  const newOwnerId = newQuery.owner_id || ''
  const oldOwnerId = (oldQuery && oldQuery.owner_id) || ''

  if (newOwnerId !== oldOwnerId || (isInitialNavigation && newOwnerId)) {
    filters.value.owner_id = newOwnerId
    if (newOwnerId) {
      filters.value.onlyMine = false
      await loadOwnerDisplayName(newOwnerId)
    } else {
      ownerDisplayName.value = ''
    }
    needsRefetch = true
  }

  // Check type filter
  const newType = newQuery.type || ''
  const oldType = (oldQuery && oldQuery.type) || ''
  if (newType !== oldType || (isInitialNavigation && newType)) {
    filters.value.type = newType
    needsRefetch = true
  }

  // Check pricing_type filter
  const newPricingType = newQuery.pricing_type || ''
  const oldPricingType = (oldQuery && oldQuery.pricing_type) || ''
  if (newPricingType !== oldPricingType || (isInitialNavigation && newPricingType)) {
    filters.value.pricing_type = newPricingType
    needsRefetch = true
  }

  // Update combined typeAndPricing filter
  if (filters.value.type && filters.value.pricing_type) {
    filters.value.typeAndPricing = `${filters.value.type}:${filters.value.pricing_type}`
  } else if (filters.value.type) {
    filters.value.typeAndPricing = filters.value.type
  } else {
    filters.value.typeAndPricing = ''
  }

  // Check category filter
  const newCategory = newQuery.category || ''
  const oldCategory = (oldQuery && oldQuery.category) || ''
  if (newCategory !== oldCategory || (isInitialNavigation && newCategory)) {
    filters.value.category = newCategory

    if (newCategory) {
      try {
        const categoryObj = await fetchCategory(newCategory)
        if (categoryObj) {
          setSelectedFilterCategory(categoryObj)
        }
      } catch (err) {
        console.error('[Market] Failed to load category from URL:', err)
      }
    } else {
      setSelectedFilterCategory(null)
    }
    needsRefetch = true
  }

  // Refetch items if any filters changed
  if (needsRefetch) {
    resetScroll()
    await fetchItems()
  }
})

// Watch language changes and reload categories (debounced to prevent hydration mismatch)
let localeTimeout = null
watch(() => locale.value, async (newLocale, oldLocale) => {
  if (!oldLocale || newLocale === oldLocale) return

  clearTimeout(localeTimeout)
  localeTimeout = setTimeout(async () => {
    await loadCategories()
    resetScroll()
    await fetchItems()
  }, 100)
})

// Client-side initialization after mount
onMounted(async () => {
  // Load category map for i18n category names
  try {
    const tree = await fetchCategoryTree()
    categoryMap.value = buildCategoryMap(tree)
  } catch (err) {
    console.error('[Market] Failed to build category map:', err)
  }

  let needsRefetch = false

  // Load category object if not already loaded from SSR
  if (route.query.category && !selectedFilterCategory.value) {
    try {
      const categoryObj = await fetchCategory(route.query.category)
      if (categoryObj) {
        setSelectedFilterCategory(categoryObj)
        needsRefetch = true
      }
    } catch (err) {
      console.error('[Market] Failed to load category from URL:', err)
    }
  }

  // Check URL query parameter for onlyMine filter
  if (route.query.onlyMine === 'true') {
    await authStore.ensureSession()

    if (authStore.isAuthenticated) {
      filters.value.onlyMine = true
      needsRefetch = true
    }
  }

  // Load owner display name if owner_id filter is set
  if (route.query.owner_id) {
    await loadOwnerDisplayName(route.query.owner_id)
    if (!needsRefetch) {
      needsRefetch = true
    }
  }

  // Check if type filter is in URL but not yet applied
  if (route.query.type && !needsRefetch) {
    needsRefetch = true
  }

  // Check if pricing_type filter is in URL but not yet applied
  if (route.query.pricing_type && !needsRefetch) {
    needsRefetch = true
  }

  // CRITICAL: Always fetch items if SSR returned empty (SSR disabled for items)
  if (items.value.length === 0 && !needsRefetch) {
    needsRefetch = true
  }

  // Refetch items if any filters were updated
  if (needsRefetch) {
    isInitialRefetch.value = true  // Show loading, hide SSR data to prevent flicker
    await fetchItems()

    // Auto-expand language filter if 0 items in user's locale
    // Show all items rather than an empty "dead platform" page
    if (items.value.length === 0 && !showAllLanguages.value && !searchQuery.value && !filters.value.category && !filters.value.type && !filters.value.owner_id) {
      showAllLanguages.value = true
      languageAutoExpanded.value = true
      await fetchItems()
    }

    isInitialRefetch.value = false
  }

  // Fetch match counts for filter labels
  fetchMatchCounts()

  // Add ESC key listener
  window.addEventListener('keydown', handleEscape)
})

onUnmounted(() => {
  // Remove ESC key listener
  window.removeEventListener('keydown', handleEscape)
})

// KeepAlive: Component is now visible again
// CRITICAL: Always reset pagination and refetch to prevent stale page numbers
onActivated(async () => {
  // Clear marketDirty flag if set (e.g., item deleted from detail page)
  const marketDirty = useState('marketDirty', () => false)
  if (marketDirty.value) {
    marketDirty.value = false
  }

  // Sync filters from URL if they changed while component was deactivated
  const newOwnerId = route.query.owner_id || ''
  if (newOwnerId !== filters.value.owner_id) {
    filters.value.owner_id = newOwnerId
    if (newOwnerId) {
      filters.value.onlyMine = false
    }
  }

  const newType = route.query.type || ''
  if (newType !== filters.value.type) {
    filters.value.type = newType
  }

  const newPricingType = route.query.pricing_type || ''
  if (newPricingType !== filters.value.pricing_type) {
    filters.value.pricing_type = newPricingType
  }

  // Update combined typeAndPricing filter
  if (filters.value.type && filters.value.pricing_type) {
    filters.value.typeAndPricing = `${filters.value.type}:${filters.value.pricing_type}`
  } else if (filters.value.type) {
    filters.value.typeAndPricing = filters.value.type
  } else {
    filters.value.typeAndPricing = ''
  }

  const newCategory = route.query.category || ''
  if (newCategory !== filters.value.category) {
    filters.value.category = newCategory

    if (newCategory) {
      try {
        const categoryObj = await fetchCategory(newCategory)
        if (categoryObj) {
          setSelectedFilterCategory(categoryObj)
        }
      } catch (err) {
        console.error('[Market] Failed to load category from URL:', err)
      }
    } else {
      setSelectedFilterCategory(null)
    }
  }

  // Always reset pagination and refetch from page 1 to prevent stale page cache
  currentPage.value = 1
  hasMoreItems.value = true
  await fetchItems()
})
</script>

