<template>
  <div :class="['map-unified-search', { 'panel-open': panelOpen }]" ref="rootEl">
    <div class="search-container">
      <div class="search-input-wrapper bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100">
        <Search class="search-icon text-neutral-500" :size="20" />
        <input
          v-model="query"
          @input="onInput"
          @keydown.enter="selectFirstResult"
          @keydown.down.prevent="navigateResults(1)"
          @keydown.up.prevent="navigateResults(-1)"
          @keydown.escape="clearSearch"
          type="text"
          role="combobox"
          aria-autocomplete="list"
          :aria-expanded="dropdownOpen && (hasResults || isLoading)"
          aria-controls="search-results-listbox"
          :aria-activedescendant="activeDescendantId"
          :placeholder="$t('map.search.unified_placeholder')"
          :aria-label="$t('map.search.unified_placeholder')"
          class="search-input placeholder-neutral-400 focus-visible:ring-2 focus-visible:ring-primary"
          autocomplete="off"
        />
        <button
          v-if="query"
          @click="clearSearch"
          class="clear-button text-neutral-500 hover:bg-neutral-100 dark:hover:bg-neutral-700"
          aria-label="Clear search"
        >
          <X :size="16" />
        </button>
      </div>

      <!-- Unified dropdown -->
      <!-- Screen reader results announcement -->
      <div class="sr-only" aria-live="polite" aria-atomic="true">
        <span v-if="!isLoading && dropdownOpen && flatItems.length > 0">
          {{ $t('map.search.results_count', flatItems.length) }}
        </span>
      </div>

      <transition name="dropdown">
        <div v-if="dropdownOpen && (hasResults || isLoading)" id="search-results-listbox" role="listbox" :aria-label="$t('map.search.unified_placeholder')" class="search-results bg-white dark:bg-neutral-800">
          <!-- Loading -->
          <div v-if="isLoading && !hasResults" class="loading-state text-neutral-500" role="status" aria-live="polite">
            <div class="w-4 h-4 border-2 border-neutral-200 border-t-secondary rounded-full animate-spin" aria-hidden="true"></div>
            <span>{{ $t('map.search.searching') }}</span>
          </div>

          <!-- Categories section -->
          <div v-if="categoryResults.length" role="group" :aria-label="$t('map.search.categories_section')">
            <div class="section-label text-neutral-400" aria-hidden="true">{{ $t('map.search.categories_section') }}</div>
            <button
              v-for="(cat, i) in categoryResults"
              :key="'cat-' + cat.id"
              :id="`search-result-${flatIndex('cat', i)}`"
              role="option"
              :aria-selected="flatIndex('cat', i) === selectedIndex"
              :class="['result-item hover:bg-primary-100 dark:hover:bg-primary-900/40', { 'bg-primary-100 dark:bg-primary-900/40': flatIndex('cat', i) === selectedIndex }]"
              @click="selectCategory(cat)"
              @mouseenter="selectedIndex = flatIndex('cat', i); onResultHover(cat)"
              @mouseleave="hidePreviewMarker()"
            >
              <span class="result-icon" aria-hidden="true">{{ cat.icon || '📁' }}</span>
              <div class="result-content">
                <div class="result-name text-neutral-900 dark:text-neutral-100">{{ cat.name }}</div>
                <div v-if="cat.breadcrumbs && cat.breadcrumbs.length > 1" class="result-address text-neutral-500">
                  {{ cat.breadcrumbs.map(b => b.name).join(' › ') }}
                </div>
              </div>
            </button>
          </div>

          <!-- Establishments section -->
          <div v-if="establishmentResults.length" role="group" :aria-label="$t('map.search.places_section')">
            <div class="section-label text-neutral-400" aria-hidden="true">{{ $t('map.search.places_section') }}</div>
            <button
              v-for="(est, i) in establishmentResults"
              :key="'est-' + est.id"
              :id="`search-result-${flatIndex('est', i)}`"
              role="option"
              :aria-selected="flatIndex('est', i) === selectedIndex"
              :class="['result-item hover:bg-primary-100 dark:hover:bg-primary-900/40', { 'bg-primary-100 dark:bg-primary-900/40': flatIndex('est', i) === selectedIndex }]"
              @click="selectEstablishment(est)"
              @mouseenter="selectedIndex = flatIndex('est', i); onResultHover(est)"
              @mouseleave="hidePreviewMarker()"
            >
              <span class="result-icon" aria-hidden="true">{{ est.category_icon || '🏢' }}</span>
              <div class="result-content">
                <div class="result-name text-neutral-900 dark:text-neutral-100">{{ est.name }}</div>
                <div v-if="est.full_address" class="result-address text-neutral-500">{{ est.full_address }}</div>
              </div>
            </button>
          </div>

          <!-- Addresses section -->
          <div v-if="addressResults.length" role="group" :aria-label="$t('map.search.addresses_section')">
            <div class="section-label text-neutral-400" aria-hidden="true">{{ $t('map.search.addresses_section') }}</div>
            <button
              v-for="(addr, i) in addressResults"
              :key="'addr-' + (addr.osm_id || i)"
              :id="`search-result-${flatIndex('addr', i)}`"
              role="option"
              :aria-selected="flatIndex('addr', i) === selectedIndex"
              :class="['result-item hover:bg-primary-100 dark:hover:bg-primary-900/40', { 'bg-primary-100 dark:bg-primary-900/40': flatIndex('addr', i) === selectedIndex }]"
              @click="selectAddress(addr)"
              @mouseenter="selectedIndex = flatIndex('addr', i); onResultHover(addr)"
              @mouseleave="hidePreviewMarker()"
            >
              <span class="result-icon" aria-hidden="true">{{ getIconForType(addr.properties?.osm_value) }}</span>
              <div class="result-content">
                <div class="result-name text-neutral-900 dark:text-neutral-100">{{ addr.name || addr.display_name }}</div>
                <div v-if="addr.display_name" class="result-address text-neutral-500">{{ addr.display_name }}</div>
              </div>
            </button>
          </div>

          <!-- No results -->
          <div v-if="!isLoading && !hasResults && query.length >= 2" class="loading-state text-neutral-500">
            <span>{{ $t('map.search.no_results') }}</span>
          </div>
        </div>
      </transition>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { debounce } from '~/utils/debounce'
import { Search, X } from 'lucide-vue-next'

const mapStore = useMapStore()

const props = defineProps<{
  lang?: string
  panelOpen?: boolean
}>()

const emit = defineEmits<{
  'category-selected': [category: any]
  'establishment-selected': [establishment: any]
  'location-selected': [location: any]
  'search-cleared': []
}>()

const { t: $t } = useI18n()
const { searchCategories } = useCategories()
const { searchQuery, setSearchQuery, mapCenter } = useMapState()

const rootEl = ref<HTMLElement | null>(null)
const query = ref(searchQuery.value || '')
const dropdownOpen = ref(false)
const isLoading = ref(false)
const selectedIndex = ref(-1)

const categoryResults = ref<any[]>([])
const establishmentResults = ref<any[]>([])
const addressResults = ref<any[]>([])

const MAX_PER_SECTION = 3

const hasResults = computed(() =>
  categoryResults.value.length > 0 ||
  establishmentResults.value.length > 0 ||
  addressResults.value.length > 0
)

// Flat index calculation for keyboard navigation
const flatItems = computed(() => {
  const items: Array<{ type: string; index: number; item: any }> = []
  categoryResults.value.forEach((item, i) => items.push({ type: 'cat', index: i, item }))
  establishmentResults.value.forEach((item, i) => items.push({ type: 'est', index: i, item }))
  addressResults.value.forEach((item, i) => items.push({ type: 'addr', index: i, item }))
  return items
})

const flatIndex = (type: string, i: number): number => {
  return flatItems.value.findIndex(f => f.type === type && f.index === i)
}

const activeDescendantId = computed(() => {
  if (selectedIndex.value < 0 || selectedIndex.value >= flatItems.value.length) return undefined
  return `search-result-${selectedIndex.value}`
})

const formatAddress = (result: any) => {
  const parts: string[] = []
  if (result.properties) {
    const p = result.properties
    if (p.street) parts.push(p.street)
    if (p.housenumber) parts.push(p.housenumber)
    const locationName = p.locality || p.localadmin || p.city || p.town || p.village
    if (locationName && locationName !== result.name) parts.push(locationName)
    if (p.region || p.state) parts.push(p.region || p.state)
    if (p.country) parts.push(p.country)
  }
  return parts.filter(Boolean).join(', ')
}

const getIconForType = (osmValue: string) => {
  const icons: Record<string, string> = {
    venue: '🏪', address: '🏠', street: '🛣️', neighbourhood: '🗺️',
    borough: '📍', locality: '🏙️', localadmin: '🏛️', county: '🏞️',
    region: '🌍', country: '🚩', shop: '🛍️', restaurant: '🍽️',
    cafe: '☕', hotel: '🏨', hospital: '🏥', school: '🎓',
    bank: '🏦', fuel: '⛽', park: '🌳'
  }
  return icons[osmValue] || '📍'
}

const search = async (q: string) => {
  if (!q || q.length < 2) {
    categoryResults.value = []
    establishmentResults.value = []
    addressResults.value = []
    dropdownOpen.value = false
    return
  }

  isLoading.value = true
  dropdownOpen.value = true

  // Fire all three sources in parallel
  const [cats, ests, addrs] = await Promise.allSettled([
    searchCategories(q).then(r => r.slice(0, MAX_PER_SECTION)),
    $fetch(`/api/v1/geo/establishments/?search=${encodeURIComponent(q)}&page_size=3`).then((r: any) => (r.items || []).slice(0, MAX_PER_SECTION)),
    $fetch(`/api/v1/geo/geocode/search?q=${encodeURIComponent(q)}&limit=3&lang=${props.lang || 'en'}&focus_lat=${mapCenter.value[1]}&focus_lon=${mapCenter.value[0]}`).then((r: any) => {
      if (!r.features) return []
      return r.features.slice(0, MAX_PER_SECTION).map((f: any) => ({
        ...f,
        name: f.properties.name || f.properties.street || f.properties.city,
        display_name: formatAddress(f),
        lat: f.geometry.coordinates[1],
        lon: f.geometry.coordinates[0],
        osm_id: f.properties.osm_id
      }))
    })
  ])

  categoryResults.value = cats.status === 'fulfilled' ? cats.value : []
  establishmentResults.value = ests.status === 'fulfilled' ? ests.value : []
  addressResults.value = addrs.status === 'fulfilled' ? addrs.value : []

  isLoading.value = false
}

const debouncedSearch = debounce(search, 300)

const onInput = () => {
  selectedIndex.value = -1
  setSearchQuery(query.value)
  debouncedSearch(query.value)
}

const selectCategory = (cat: any) => {
  emit('category-selected', cat)
  closeDropdown()
}

const selectEstablishment = (est: any) => {
  emit('establishment-selected', est)
  closeDropdown()
}

const selectAddress = (addr: any) => {
  const location = {
    lat: addr.lat || addr.geometry?.coordinates[1],
    lon: addr.lon || addr.geometry?.coordinates[0],
    name: addr.name,
    address: addr.display_name || formatAddress(addr),
    raw: addr
  }
  emit('location-selected', location)
  closeDropdown()
}

const selectFirstResult = () => {
  const idx = selectedIndex.value >= 0 ? selectedIndex.value : 0
  const item = flatItems.value[idx]
  if (!item) return
  if (item.type === 'cat') selectCategory(item.item)
  else if (item.type === 'est') selectEstablishment(item.item)
  else if (item.type === 'addr') selectAddress(item.item)
}

const navigateResults = (direction: number) => {
  const total = flatItems.value.length
  if (total === 0) return
  if (selectedIndex.value === -1) {
    selectedIndex.value = direction > 0 ? 0 : total - 1
  } else {
    selectedIndex.value += direction
    if (selectedIndex.value < 0) selectedIndex.value = total - 1
    else if (selectedIndex.value >= total) selectedIndex.value = 0
  }
}

// --- Preview marker (lock-on brackets) ---
let previewMarker: any = null
let maplibreglCache: any = null
let markerSeq = 0

const getItemCoords = (item: any): { lat: number; lon: number } | null => {
  if (item.lat && item.lon) return { lat: item.lat, lon: item.lon }
  if (item.location?.lat && item.location?.lon) return { lat: item.location.lat, lon: item.location.lon }
  return null
}

const showPreviewMarker = async (coords: { lat: number; lon: number }) => {
  hidePreviewMarker()
  if (!mapStore.mapInstance) return
  const seq = ++markerSeq
  if (!maplibreglCache) maplibreglCache = await import('maplibre-gl').then(m => m.default || m)
  if (seq !== markerSeq) return // stale call
  const { createLockOnElement } = await import('~/utils/lockOnMarker')
  if (seq !== markerSeq) return
  previewMarker = new maplibreglCache.Marker({ element: createLockOnElement(), anchor: 'center' })
    .setLngLat([coords.lon, coords.lat])
    .addTo(mapStore.mapInstance)
}

const hidePreviewMarker = () => {
  if (previewMarker) { previewMarker.remove(); previewMarker = null }
  hideEdgeIndicator()
}

const onResultHover = (item: any) => {
  const coords = getItemCoords(item)
  if (coords) {
    showPreviewMarker(coords)
    showEdgeIndicator(coords)
  } else {
    hidePreviewMarker()
  }
}

// --- Edge distance indicator (off-screen direction hint) ---
let edgeIndicatorEl: HTMLElement | null = null

const haversineKm = (lat1: number, lon1: number, lat2: number, lon2: number): number => {
  const R = 6371
  const toRad = (d: number) => d * Math.PI / 180
  const dLat = toRad(lat2 - lat1)
  const dLon = toRad(lon2 - lon1)
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
}

const showEdgeIndicator = (coords: { lat: number; lon: number }) => {
  hideEdgeIndicator()
  const map = mapStore.mapInstance
  if (!map) return

  // Only show when point is outside visible bounds
  const bounds = map.getBounds()
  if (bounds.contains([coords.lon, coords.lat] as [number, number])) return

  const container = map.getContainer()
  const w = container.clientWidth
  const h = container.clientHeight
  const cx = w / 2
  const cy = h / 2

  // Project target to pixel coords (works for off-screen points too)
  const px = map.project([coords.lon, coords.lat])
  const dx = px.x - cx
  const dy = px.y - cy
  if (Math.abs(dx) < 1 && Math.abs(dy) < 1) return

  // Find intersection with viewport edge (asymmetric padding to avoid UI overlaps)
  const padL = 60, padR = 60, padT = 80, padB = 60
  const sx = dx > 0 ? (w - padR - cx) / dx : dx < 0 ? (padL - cx) / dx : Infinity
  const sy = dy > 0 ? (h - padB - cy) / dy : dy < 0 ? (padT - cy) / dy : Infinity
  const s = Math.min(sx, sy)
  const ex = cx + dx * s
  const ey = cy + dy * s

  // Haversine distance from map center
  const center = map.getCenter()
  const dist = haversineKm(center.lat, center.lng, coords.lat, coords.lon)
  const distText = dist >= 1 ? `${Math.round(dist)} km` : `${Math.round(dist * 1000)} m`

  // Arrow rotation angle (screen space)
  const angle = Math.atan2(dy, dx) * 180 / Math.PI

  edgeIndicatorEl = document.createElement('div')
  edgeIndicatorEl.className = 'edge-distance-indicator'
  edgeIndicatorEl.style.cssText = `left:${ex}px;top:${ey}px`
  edgeIndicatorEl.innerHTML = `
    <div class="edge-ind-lock edge-ind-lock-b1"></div>
    <div class="edge-ind-lock edge-ind-lock-b2"></div>
    <div class="edge-ind-pill">
      <svg class="edge-ind-arrow" viewBox="0 0 16 16" width="14" height="14" style="transform:rotate(${angle}deg)">
        <path d="M2 8h10M8 4l4 4-4 4" stroke="currentColor" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      <span class="edge-ind-dist">${distText}</span>
    </div>
  `
  container.appendChild(edgeIndicatorEl)
}

const hideEdgeIndicator = () => {
  if (edgeIndicatorEl) { edgeIndicatorEl.remove(); edgeIndicatorEl = null }
}

// Show marker for keyboard-selected item
watch(selectedIndex, (idx) => {
  if (idx < 0 || idx >= flatItems.value.length) { hidePreviewMarker(); return }
  onResultHover(flatItems.value[idx].item)
})

const clearSearch = () => {
  query.value = ''
  setSearchQuery('')
  categoryResults.value = []
  establishmentResults.value = []
  addressResults.value = []
  selectedIndex.value = -1
  dropdownOpen.value = false
  hidePreviewMarker()
  emit('search-cleared')
}

const closeDropdown = () => {
  query.value = ''
  setSearchQuery('')
  categoryResults.value = []
  establishmentResults.value = []
  addressResults.value = []
  dropdownOpen.value = false
  selectedIndex.value = -1
  hidePreviewMarker()
}

const handleClickOutside = (event: MouseEvent) => {
  if (rootEl.value && !rootEl.value.contains(event.target as Node)) {
    dropdownOpen.value = false
    hidePreviewMarker()
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
  hidePreviewMarker()
})
</script>

<style scoped>
.map-unified-search {
  position: relative;
  z-index: 1001;
}

.search-container {
  position: relative;
}

.search-input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.15);
}

.search-input-wrapper:focus-within {
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
}

.search-icon {
  position: absolute;
  left: 12px;
  font-size: 20px;
  pointer-events: none;
}

.search-input {
  width: 100%;
  padding: 12px 40px 12px 40px;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  outline: none;
  background: transparent;
  color: inherit;
}

.search-input:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: -2px;
  border-radius: 8px;
}

.clear-button {
  position: absolute;
  right: 8px;
  padding: 6px;
  background: none;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
}

.search-results {
  position: absolute;
  top: calc(100% + 8px);
  left: 0;
  right: 0;
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
  max-height: 400px;
  overflow-y: auto;
}

:root.dark .search-results {
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
}

.section-label {
  padding: 8px 16px 4px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.loading-state {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
}

.result-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  cursor: pointer;
  border: none;
  width: 100%;
  text-align: left;
  color: inherit;
  font: inherit;
  transition: background-color 0.15s ease;
}

.result-icon {
  flex-shrink: 0;
  font-size: 18px;
}

.result-content {
  flex: 1;
  min-width: 0;
}

.result-name {
  font-weight: 500;
  font-size: 14px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.result-address {
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 1px;
}

/* Transition */
.dropdown-enter-active,
.dropdown-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

/* Mobile: dropdown full width */
@media (max-width: 640px) {
  .map-unified-search {
    max-width: none;
  }
}
</style>

<!-- Unscoped: edge indicator lives on map container, outside component DOM -->
<style>
.edge-distance-indicator {
  position: absolute;
  z-index: 1100;
  pointer-events: none;
  transform: translate(-50%, -50%);
  animation: edge-ind-fade-in 0.2s ease;
}

.edge-ind-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px 6px 8px;
  background: rgba(0, 0, 0, 0.85);
  border-radius: 20px;
  backdrop-filter: blur(4px);
  box-shadow: 0 0 12px rgba(255, 226, 22, 0.4), 0 2px 8px rgba(0, 0, 0, 0.3);
  border: 1.5px solid #FFE216;
}

.edge-ind-arrow {
  color: #FFE216;
  flex-shrink: 0;
}

.edge-ind-dist {
  color: white;
  font-size: 13px;
  font-weight: 700;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
  line-height: 1;
}

/* Lock-on brackets */
.edge-ind-lock {
  position: absolute;
  top: 50%;
  left: 50%;
  border: 2px solid #FFE216;
  border-radius: 12px;
  opacity: 0;
  pointer-events: none;
}

.edge-ind-lock-b1 {
  animation: edge-lock-in 0.5s 0s cubic-bezier(0, 0.55, 0.45, 1) forwards,
             edge-lock-pulse 2s 0.8s ease-in-out infinite;
}

.edge-ind-lock-b2 {
  animation: edge-lock-in 0.5s 0.1s cubic-bezier(0, 0.55, 0.45, 1) forwards,
             edge-lock-pulse 2s 0.9s ease-in-out infinite;
}

@keyframes edge-lock-in {
  0% {
    width: 200px;
    height: 200px;
    transform: translate(-50%, -50%);
    opacity: 0.3;
  }
  60% { opacity: 0.9; }
  100% {
    width: calc(100% + 16px);
    height: calc(100% + 16px);
    transform: translate(-50%, -50%);
    opacity: 0.9;
  }
}

@keyframes edge-lock-pulse {
  0%, 100% {
    width: calc(100% + 16px);
    height: calc(100% + 16px);
    transform: translate(-50%, -50%);
    opacity: 0.9;
    border-color: #FFE216;
  }
  50% {
    width: calc(100% + 24px);
    height: calc(100% + 24px);
    transform: translate(-50%, -50%);
    opacity: 0.4;
    border-color: #FFE216;
  }
}

@keyframes edge-ind-fade-in {
  from { opacity: 0; transform: translate(-50%, -50%) scale(0.8); }
  to { opacity: 1; transform: translate(-50%, -50%) scale(1); }
}
</style>
