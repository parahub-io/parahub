<template>
  <div class="max-w-2xl mx-auto px-4 py-2">
    <h1 class="sr-only">{{ $t('transit.title') }}</h1>

    <!-- Quick links: Rideshare + Driver Mode -->
    <div class="grid grid-cols-2 gap-2 mb-4">
      <NuxtLink
        :to="localePath('/transit/rides')"
        class="flex items-center gap-2.5 p-3 rounded-lg hover:brightness-95 transition-all border border-success/60 dark:border-success/40 bg-success"
      >
        <Car class="w-5 h-5 text-white flex-shrink-0" />
        <div class="min-w-0">
          <div class="font-medium text-white text-sm">{{ $t('transit.rideshare') }}</div>
          <div class="text-xs text-white/80 truncate">{{ $t('transit.rideshare_desc') }}</div>
        </div>
      </NuxtLink>
      <NuxtLink
        :to="localePath('/driver')"
        class="flex items-center gap-2.5 p-3 rounded-lg hover:brightness-95 transition-all border border-secondary-500/60 dark:border-secondary-500/40 bg-secondary-600"
      >
        <Radio class="w-5 h-5 text-white flex-shrink-0" />
        <div class="min-w-0">
          <div class="font-medium text-white text-sm">{{ $t('transit.driver.title') }}</div>
          <div class="text-xs text-white/80 truncate">{{ $t('transit.driver.nav_desc') }}</div>
        </div>
      </NuxtLink>
    </div>

    <!-- Country + City Selector (collapsible) -->
    <div v-if="countries.length" class="mb-4">
      <button
        @click="citySelectorOpen = !citySelectorOpen"
        :aria-expanded="citySelectorOpen"
        class="flex items-center gap-2 w-full px-3 py-2.5 mb-2 text-left text-sm bg-white dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-600 rounded-lg hover:border-neutral-400 dark:hover:border-neutral-500 focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-colors"
      >
        <MapPin class="w-4 h-4 flex-shrink-0 text-neutral-400" />
        <span class="flex-shrink-0 text-neutral-500 dark:text-neutral-400">{{ $t('transit.cities.label') }}</span>
        <span class="truncate font-medium text-neutral-900 dark:text-neutral-100">{{ selectedCityName || $t('transit.cities.select') }}</span>
        <ChevronDown class="w-4 h-4 ml-auto flex-shrink-0 text-neutral-400 transition-transform" :class="citySelectorOpen ? 'rotate-180' : ''" />
      </button>

      <template v-if="citySelectorOpen">
        <!-- Country pills -->
        <div class="flex gap-1.5 mb-3 overflow-x-auto pb-1">
          <button
            v-for="country in countries"
            :key="country.code"
            @click="selectCountry(country.code)"
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium whitespace-nowrap transition-colors"
            :class="selectedCountry === country.code
              ? 'bg-secondary-600 text-white'
              : 'bg-neutral-200 dark:bg-neutral-700 text-neutral-700 dark:text-neutral-300 hover:bg-neutral-300 dark:hover:bg-neutral-600'"
          >
            <span class="text-base leading-none">{{ countryFlag(country.code) }}</span>
            {{ $t(`transit.countries.${country.code}`, country.code) }}
          </button>
        </div>

        <!-- City search (for countries with many cities) -->
        <div v-if="countryCities.length > 30" class="relative mb-2">
          <Search class="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-neutral-400" />
          <input
            v-model="citySearch"
            :placeholder="$t('transit.cities.search_city')"
            class="w-full pl-8 pr-3 py-1.5 bg-white dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-600 rounded-lg text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none"
          />
        </div>

        <!-- Top cities (cards) -->
        <div v-if="topCities.length" class="grid grid-cols-2 sm:grid-cols-3 gap-2 mb-2">
          <button
            v-for="c in topCities"
            :key="c.slug"
            @click="selectCity(c.slug)"
            class="city-card p-2.5 rounded-lg text-left transition-colors border"
            :class="selectedCity === c.slug
              ? 'bg-secondary-600 text-white border-secondary-600'
              : 'bg-white dark:bg-neutral-800 border-neutral-200 dark:border-neutral-700 hover:border-secondary-400 dark:hover:border-secondary-500'"
          >
            <div class="font-medium text-sm truncate">{{ cityDisplayName(c) }}</div>
            <div class="flex gap-2 mt-0.5 text-xs" :class="selectedCity === c.slug ? 'text-white/70' : 'text-neutral-500 dark:text-neutral-400'">
              <span>{{ $t('transit.cities.stops', { n: c.stops_count }) }}</span>
              <span v-if="c.routes_count">{{ $t('transit.cities.routes', { n: c.routes_count }) }}</span>
            </div>
          </button>
        </div>

        <!-- Remaining cities (compact pills) -->
        <div v-if="smallCities.length" class="flex flex-wrap gap-1.5">
          <button
            v-for="c in visibleSmallCities"
            :key="c.slug"
            @click="selectCity(c.slug)"
            class="px-2.5 py-1 rounded-full text-xs font-medium whitespace-nowrap transition-colors"
            :class="selectedCity === c.slug
              ? 'bg-secondary-600 text-white'
              : 'bg-neutral-100 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-300 hover:bg-neutral-200 dark:hover:bg-neutral-600'"
          >
            {{ cityDisplayName(c) }}
          </button>
          <button
            v-if="smallCities.length > SMALL_VISIBLE && !showAllCities && !citySearch"
            @click="showAllCities = true"
            class="px-2.5 py-1 rounded-full text-xs font-medium text-secondary-600 dark:text-secondary-400 bg-secondary-50 dark:bg-secondary-900/30 hover:bg-secondary-100 dark:hover:bg-secondary-900/50 transition-colors"
          >
            {{ $t('transit.cities.show_all', { n: smallCities.length }) }}
          </button>
          <button
            v-else-if="showAllCities && smallCities.length > SMALL_VISIBLE && !citySearch"
            @click="showAllCities = false"
            class="px-2.5 py-1 rounded-full text-xs font-medium text-secondary-600 dark:text-secondary-400 bg-secondary-50 dark:bg-secondary-900/30 hover:bg-secondary-100 dark:hover:bg-secondary-900/50 transition-colors"
          >
            {{ $t('transit.cities.hide') }}
          </button>
        </div>
      </template>
    </div>

    <!-- Search -->
    <div class="flex gap-2 mb-6">
      <div class="relative flex-1">
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400" />
        <input
          v-model="searchQuery"
          :placeholder="$t('transit.search_placeholder')"
          class="w-full pl-10 pr-3 py-2.5 bg-white dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-600 rounded-lg text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none"
          @input="debouncedSearch"
        />
      </div>
      <button
        @click="findNearest"
        class="btn-secondary btn-sm flex items-center gap-1.5 whitespace-nowrap transition-colors min-h-[44px]"
      >
        <LocateFixed class="w-4 h-4" />
        <span class="hidden sm:inline">{{ $t('transit.find_nearest') }}</span>
      </button>
    </div>

    <!-- GPS Error -->
    <UiAlert v-if="gpsError" variant="error" class="mb-4">{{ gpsError }}</UiAlert>

    <!-- Search Results -->
    <template v-if="searchResults">
      <div v-if="!searchResults.stops.length && !searchResults.routes.length" class="text-center text-neutral-500 dark:text-neutral-400 py-8">
        {{ $t('transit.no_results') }}
      </div>
      <div v-else class="border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700">
        <button
          v-for="s in searchResults.stops"
          :key="'s'+s.id"
          @click="openStop(s)"
          class="w-full text-left p-3 hover:bg-primary/15 dark:hover:bg-primary/10 transition-colors flex items-center gap-3"
        >
          <img src="/img/bus-stop.png" alt="" class="w-8 h-8 flex-shrink-0" />
          <div class="flex-1 min-w-0">
            <div class="font-medium text-neutral-900 dark:text-neutral-100">
              {{ s.name }}
              <span v-if="s.member_count > 1" class="ml-1 inline-block px-1.5 py-0.5 rounded text-xs font-medium bg-neutral-100 dark:bg-neutral-800 text-neutral-500 dark:text-neutral-400">{{ $t('transit.stops_count', { count: s.member_count }) }}</span>
            </div>
            <div v-if="s.directions?.length" class="text-xs text-secondary-600 dark:text-secondary-400 truncate mt-0.5">{{ $t('transit.towards', { dest: s.directions.join(' · ') }) }}</div>
            <div v-if="s.routes?.length" class="flex flex-wrap gap-1 mt-1">
              <span v-for="r in s.routes" :key="r.short_name" class="px-1.5 py-0.5 text-xs rounded font-medium" :style="routeBadgeStyle(r)">{{ r.short_name }}</span>
            </div>
          </div>
        </button>
        <button
          v-for="r in searchResults.routes"
          :key="'r'+r.id"
          @click="openRoute(r)"
          class="w-full text-left p-3 hover:bg-primary/15 dark:hover:bg-primary/10 transition-colors flex items-center gap-3"
        >
          <img :src="routeTypeIcon(r.route_type)" :alt="routeTypeFallback(r.route_type)" class="w-8 h-8 flex-shrink-0" />
          <div class="flex-1 min-w-0">
            <span class="inline-block px-2 py-0.5 rounded font-bold text-sm" :style="routeBadgeStyle(r)">{{ r.short_name }}</span>
            <span v-if="r.variant_count > 1" class="ml-2 inline-block px-1.5 py-0.5 rounded text-xs font-medium bg-neutral-100 dark:bg-neutral-800 text-neutral-500 dark:text-neutral-400">{{ $t('transit.percursos_count', { n: r.variant_count }) }}</span>
            <div class="text-sm text-neutral-600 dark:text-neutral-400 truncate mt-0.5">{{ r.long_name }}</div>
          </div>
        </button>
      </div>
    </template>

    <!-- Nearby Results -->
    <template v-else-if="nearbyStops">
      <div v-if="!nearbyStops.length" class="text-center text-neutral-500 dark:text-neutral-400 py-8">
        {{ $t('transit.no_results') }}
      </div>
      <div v-else class="border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700">
        <template v-for="f in nearbyStops" :key="f.properties.id">
          <button
            @click="f.properties.kind === 'virtual' ? toggleGroup(f.properties.id) : openStop(f.properties)"
            class="w-full text-left p-3 hover:bg-primary/15 dark:hover:bg-primary/10 transition-colors flex items-center gap-3"
          >
            <img src="/img/bus-stop.png" alt="" class="w-8 h-8 flex-shrink-0" />
            <div class="flex-1 min-w-0">
              <div class="font-medium text-neutral-900 dark:text-neutral-100">
                {{ f.properties.name }}
                <span v-if="f.properties.kind === 'virtual'" class="ml-1 inline-block px-1.5 py-0.5 rounded text-xs font-medium bg-neutral-100 dark:bg-neutral-800 text-neutral-500 dark:text-neutral-400">{{ $t('transit.stops_count', { count: f.properties.member_count }) }}</span>
              </div>
              <div v-if="f.properties.routes?.length" class="flex flex-wrap gap-1 mt-1">
                <span v-for="r in f.properties.routes" :key="r.short_name" class="px-1.5 py-0.5 text-xs rounded font-medium" :style="routeBadgeStyle(r)">{{ r.short_name }}</span>
              </div>
            </div>
            <ChevronDown v-if="f.properties.kind === 'virtual'" class="w-4 h-4 flex-shrink-0 text-neutral-400 transition-transform" :class="expandedGroups.has(f.properties.id) ? 'rotate-180' : ''" />
          </button>
          <template v-if="f.properties.kind === 'virtual' && expandedGroups.has(f.properties.id)">
            <button
              v-for="m in f.properties.stops"
              :key="m.id"
              @click="openStop(m)"
              class="w-full text-left py-2 pr-3 pl-14 hover:bg-primary/15 dark:hover:bg-primary/10 transition-colors bg-neutral-50 dark:bg-neutral-800/50"
            >
              <div class="text-sm text-neutral-700 dark:text-neutral-300">{{ m.name }}</div>
              <div v-if="m.routes?.length" class="flex flex-wrap gap-1 mt-1">
                <span v-for="r in m.routes" :key="r.short_name" class="px-1.5 py-0.5 text-xs rounded font-medium" :style="routeBadgeStyle(r)">{{ r.short_name }}</span>
              </div>
            </button>
          </template>
        </template>
      </div>
    </template>

    <!-- Discovery (default) -->
    <template v-else-if="discover">
      <div class="border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700">
        <button
          v-for="item in discoverMixed"
          :key="item.type + item.id"
          @click="item.type === 'stop' ? openStop(item) : openRoute(item)"
          class="w-full text-left p-3 hover:bg-primary/15 dark:hover:bg-primary/10 transition-colors flex items-center gap-3"
        >
          <template v-if="item.type === 'stop'">
            <img src="/img/bus-stop.png" alt="" class="w-8 h-8 flex-shrink-0" />
            <div class="flex-1 min-w-0">
              <div class="font-medium text-neutral-900 dark:text-neutral-100">{{ item.name }}</div>
              <div v-if="item.routes?.length" class="flex flex-wrap gap-1 mt-1">
                <span v-for="r in item.routes" :key="r.short_name" class="px-1.5 py-0.5 text-xs rounded font-medium" :style="routeBadgeStyle(r)">{{ r.short_name }}</span>
              </div>
            </div>
          </template>
          <template v-else>
            <img :src="routeTypeIcon(item.route_type)" :alt="routeTypeFallback(item.route_type)" class="w-8 h-8 flex-shrink-0" />
            <div class="flex-1 min-w-0">
              <span class="inline-block px-2 py-0.5 rounded font-bold text-sm" :style="routeBadgeStyle(item)">{{ item.short_name }}</span>
              <div class="text-sm text-neutral-600 dark:text-neutral-400 truncate mt-0.5">{{ item.long_name }}</div>
            </div>
          </template>
        </button>
      </div>
    </template>

    <!-- Loading -->
    <div v-else class="flex justify-center py-12" role="status" aria-live="polite">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" aria-hidden="true"></div>
      <span class="sr-only">{{ $t('common.loading') }}</span>
    </div>

    <!-- Feeds Section -->
    <div v-if="feeds.length" class="mt-8 border-t border-neutral-200 dark:border-neutral-700 pt-4">
      <button
        @click="feedsOpen = !feedsOpen"
        class="flex items-center gap-2 text-sm font-medium text-neutral-500 dark:text-neutral-400 mb-3 hover:text-neutral-700 dark:hover:text-neutral-300 transition-colors"
      >
        <Database class="w-4 h-4" />
        {{ $t('transit.feeds.title') }}
        <ChevronDown class="w-4 h-4 transition-transform" :class="feedsOpen ? 'rotate-180' : ''" />
      </button>
      <div v-if="feedsOpen" class="space-y-3">
        <div
          v-for="feed in feeds"
          :key="feed.id"
          class="p-3 bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg text-sm"
        >
          <div class="flex items-center justify-between gap-2 mb-2">
            <a
              :href="feed.url"
              target="_blank"
              rel="noopener"
              class="font-medium text-link truncate"
            >{{ feed.name }}</a>
            <div class="flex items-center gap-1.5 flex-shrink-0">
              <span
                class="w-2 h-2 rounded-full"
                :class="feed.is_active ? (feed.last_error ? 'bg-warning' : 'bg-success') : 'bg-neutral-400'"
              />
              <span class="text-xs text-neutral-500 dark:text-neutral-400">
                {{ feed.is_active ? (feed.last_error ? $t('transit.feeds.error') : $t('transit.feeds.active')) : $t('transit.feeds.inactive') }}
              </span>
            </div>
          </div>
          <div class="flex flex-wrap gap-x-4 gap-y-1 text-xs text-neutral-600 dark:text-neutral-400">
            <span>{{ $t('transit.feeds.routes') }}: <strong>{{ feed.routes_count }}</strong></span>
            <span>{{ $t('transit.feeds.stops') }}: <strong>{{ feed.stops_count }}</strong></span>
            <span>{{ $t('transit.feeds.trips') }}: <strong>{{ feed.trips_count }}</strong></span>
            <span v-if="feed.last_imported_at">{{ $t('transit.feeds.imported') }}: {{ timeAgo(feed.last_imported_at) }}</span>
          </div>
          <div v-if="feed.agencies.length" class="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
            {{ feed.agencies.join(', ') }}
          </div>
          <div
            v-if="feed.last_error && expandedError === feed.id"
            class="mt-2 p-2 bg-error/10 dark:bg-error/20 text-error dark:text-red-300 rounded text-xs font-mono break-all"
          >{{ feed.last_error }}</div>
          <button
            v-else-if="feed.last_error"
            @click="expandedError = feed.id"
            class="mt-1 text-xs text-error hover:underline"
          >{{ $t('transit.feeds.show_error') }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const localePath = useLocalePath()
import { ref, computed, onMounted } from 'vue'
import { Search, LocateFixed, Car, Radio, Database, ChevronDown, MapPin } from 'lucide-vue-next'

const { t, locale } = useI18n()
const authStore = useAuthStore()
const { routeTypeIcon, routeTypeFallback, routeBadgeStyle } = useTransitHelpers()

useSeoMeta({
  title: () => t('transit.title') + ' - Parahub',
  ogTitle: () => t('transit.title') + ' - Parahub',
  description: () => t('transit.meta_description', 'Public transit routes, stops and real-time vehicles'),
  ogDescription: () => t('transit.meta_description', 'Public transit routes, stops and real-time vehicles'),
  ogImage: '/og-image.jpg',
  ogType: 'website',
  twitterCard: 'summary_large_image',
})

// City selection
const cities = ref<any[]>([])
const selectedCity = ref('')
const selectedCountry = ref('')
const showAllCities = ref(false)
const citySearch = ref('')
const citySelectorOpen = ref(false)
const SMALL_VISIBLE = 15

const TOP_CITIES = 6 // cards for top N cities by stops

// Detect duplicate city names within same country (e.g. Lisboa city + Lisboa region)
const duplicateNames = computed(() => {
  const counts = new Map<string, number>()
  for (const c of cities.value) {
    const key = `${c.name}|${c.country_code}`
    counts.set(key, (counts.get(key) || 0) + 1)
  }
  return counts
})

function cityDisplayName(c: any): string {
  const key = `${c.name}|${c.country_code}`
  if ((duplicateNames.value.get(key) || 0) > 1 && c.place_type === 'region') {
    return `${c.name} ${t('transit.cities.region_suffix')}`
  }
  return c.name
}

const selectedCityName = computed(() => {
  const c = cities.value.find((c: any) => c.slug === selectedCity.value)
  return c ? cityDisplayName(c) : ''
})

// Country flag emoji from code
function countryFlag(code: string): string {
  return [...code.toUpperCase()].map(c => String.fromCodePoint(0x1F1E6 + c.charCodeAt(0) - 65)).join('')
}

// Derived: unique countries sorted by total stops
const countries = computed(() => {
  const map = new Map<string, { code: string; totalStops: number }>()
  for (const c of cities.value) {
    const entry = map.get(c.country_code)
    if (entry) {
      entry.totalStops += c.stops_count
    } else {
      map.set(c.country_code, { code: c.country_code, totalStops: c.stops_count })
    }
  }
  return [...map.values()].sort((a, b) => b.totalStops - a.totalStops)
})

// Cities for selected country, sorted by stops desc
const countryCities = computed(() => {
  if (!selectedCountry.value) return []
  return cities.value
    .filter(c => c.country_code === selectedCountry.value)
    .sort((a: any, b: any) => b.stops_count - a.stops_count)
})

// Filtered by search
const filteredCities = computed(() => {
  if (!citySearch.value) return countryCities.value
  const q = citySearch.value.toLowerCase()
  return countryCities.value.filter((c: any) => c.name.toLowerCase().includes(q))
})

// Top cities (shown as cards)
const topCities = computed(() => {
  return filteredCities.value.slice(0, TOP_CITIES)
})

// Rest of cities (shown as compact pills)
const smallCities = computed(() => {
  return filteredCities.value.slice(TOP_CITIES)
})

const visibleSmallCities = computed(() => {
  if (showAllCities.value || citySearch.value) return smallCities.value
  return smallCities.value.slice(0, SMALL_VISIBLE)
})

// Home screen data
const searchQuery = ref('')
const searchResults = ref<any>(null)
const nearbyStops = ref<any>(null)
const expandedGroups = ref<Set<string>>(new Set())

function toggleGroup(id: string) {
  const next = new Set(expandedGroups.value)
  next.has(id) ? next.delete(id) : next.add(id)
  expandedGroups.value = next
}
const discover = ref<any>(null)
const gpsError = ref('')

// Feeds
const feeds = ref<any[]>([])
const feedsOpen = ref(false)
const expandedError = ref<string | null>(null)

// Computed
const discoverMixed = computed(() => {
  if (!discover.value) return []
  const stops = (discover.value.stops || []).map((s: any) => ({ ...s, type: 'stop', _sortName: s.name }))
  const routes = (discover.value.routes || []).map((r: any) => ({ ...r, type: 'route', _sortName: r.long_name || r.short_name }))
  return [...stops, ...routes].sort((a, b) => a._sortName.localeCompare(b._sortName))
})

// Biggest place by stop count — used for the default-city landing. For a metro split into a
// city + region polygon (Lisboa, Praha) the region wins by stop count, which is intended: the
// landing favours broad metro-area coverage (the region includes suburban feeders) over the
// narrower city centre. Both stay selectable in the list.
function biggestPlace(list: any[]): string {
  if (!list.length) return ''
  return [...list].sort((a: any, b: any) => b.stops_count - a.stops_count)[0].slug
}

// Pick best default city when no saved preference exists
function pickDefaultCity(allCities: any[]): string {
  const biggestInCountry = (code: string) =>
    biggestPlace(allCities.filter((c: any) => c.country_code === code))

  // 1. User's profile country
  const profileCountry = authStore.profile?.country_code
  if (profileCountry) {
    const city = biggestInCountry(profileCountry)
    if (city) return city
  }

  // 2. Nuxt i18n locale → country hint (e.g. /pt/transit → PT)
  const localeCountry: Record<string, string> = {
    pt: 'PT', es: 'ES', fr: 'FR', de: 'DE', ru: 'RU',
  }
  const countryFromLocale = localeCountry[locale.value]
  if (countryFromLocale) {
    const city = biggestInCountry(countryFromLocale)
    if (city) return city
  }

  // 3. Browser locale hint (e.g. "pt-PT" → "PT", "fi-FI" → "FI")
  if (process.client) {
    const lang = navigator.language || ''
    const parts = lang.split('-')
    if (parts.length >= 2) {
      const country = parts[parts.length - 1].toUpperCase()
      if (country.length === 2) {
        const city = biggestInCountry(country)
        if (city) return city
      }
    }
  }

  // 4. Fallback to Portugal (platform's home base)
  const ptCity = biggestInCountry('PT')
  if (ptCity) return ptCity

  // 5. Last resort: biggest place globally
  return biggestPlace(allCities)
}

// City persistence (localStorage, migrates from old cookie)
function loadSavedCity(): string {
  if (!process.client) return ''
  const ls = localStorage.getItem('transit_city')
  if (ls) return ls
  // Migrate from old cookie
  const match = document.cookie.match(/transit_city=([^;]+)/)
  if (match) {
    localStorage.setItem('transit_city', match[1])
    document.cookie = 'transit_city=; path=/; max-age=0'
    return match[1]
  }
  return ''
}

function saveCity(slug: string) {
  if (process.client) {
    localStorage.setItem('transit_city', slug)
  }
}

// Actions
function selectCountry(code: string) {
  selectedCountry.value = code
  showAllCities.value = false
  citySearch.value = ''
  // Auto-select first city of this country if current city is from different country
  const currentCityObj = cities.value.find((c: any) => c.slug === selectedCity.value)
  if (!currentCityObj || currentCityObj.country_code !== code) {
    const slug = biggestPlace(cities.value.filter((c: any) => c.country_code === code))
    if (slug) selectCity(slug)
  }
}

function selectCity(slug: string) {
  selectedCity.value = slug
  saveCity(slug)
  // Sync country tab
  const cityObj = cities.value.find((c: any) => c.slug === slug)
  if (cityObj && cityObj.country_code !== selectedCountry.value) {
    selectedCountry.value = cityObj.country_code
  }
  searchResults.value = null
  nearbyStops.value = null
  loadDiscover()
}

function openStop(item: any) {
  navigateTo(localePath(`/transit/stop/${item.place_slug}/${item.slug}`))
}

function openRoute(item: any) {
  navigateTo(localePath(`/transit/route/${item.place_slug}/${item.slug}`))
}

// Search with debounce
let searchTimer: ReturnType<typeof setTimeout> | null = null
function debouncedSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  nearbyStops.value = null

  if (!searchQuery.value || searchQuery.value.length < 2) {
    searchResults.value = null
    return
  }
  searchTimer = setTimeout(async () => {
    try {
      const params = new URLSearchParams({ q: searchQuery.value })
      if (selectedCity.value) params.set('city', selectedCity.value)
      searchResults.value = await $fetch(`/api/v1/geo/transit/search/?${params}`)
    } catch (e) {
      console.error('Search failed:', e)
    }
  }, 300)
}

async function findNearest() {
  gpsError.value = ''
  searchResults.value = null

  if (!navigator.geolocation) {
    gpsError.value = t('transit.gps_unavailable')
    return
  }

  navigator.geolocation.getCurrentPosition(
    async (pos) => {
      try {
        const data = await $fetch<any>(`/api/v1/geo/transit/stops/nearby/?lat=${pos.coords.latitude}&lon=${pos.coords.longitude}&r=1000&group=1`)
        nearbyStops.value = data.features || []
      } catch (e) {
        console.error('Nearby failed:', e)
      }
    },
    () => {
      gpsError.value = t('transit.gps_unavailable')
    },
    { enableHighAccuracy: true, timeout: 10000 }
  )
}

async function loadDiscover() {
  if (!selectedCity.value) return
  discover.value = null
  try {
    discover.value = await $fetch(`/api/v1/geo/transit/discover/?city=${selectedCity.value}`)
  } catch (e) {
    console.error('Discover failed:', e)
  }
}

function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `${mins}m`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h`
  return `${Math.floor(hrs / 24)}d`
}

// Init
onMounted(async () => {
  // Preload maplibre-gl so "Show on map" transition is instant
  import('maplibre-gl')

  // Load cities
  try {
    cities.value = await $fetch('/api/v1/geo/transit/cities/')
  } catch (e) {
    console.error('Failed to load cities:', e)
  }

  // Select city: saved → profile country → i18n locale → browser locale → PT fallback → biggest
  const saved = loadSavedCity()
  if (saved && cities.value.some((c: any) => c.slug === saved)) {
    selectedCity.value = saved
  } else if (cities.value.length) {
    selectedCity.value = pickDefaultCity(cities.value)
  }

  // Set country from selected city
  if (selectedCity.value) {
    const cityObj = cities.value.find((c: any) => c.slug === selectedCity.value)
    if (cityObj) selectedCountry.value = cityObj.country_code
    saveCity(selectedCity.value)
    loadDiscover()
  }

  // Load feeds
  try {
    feeds.value = await $fetch('/api/v1/geo/transit/feeds/')
  } catch (e) {
    console.error('Failed to load feeds:', e)
  }
})
</script>

