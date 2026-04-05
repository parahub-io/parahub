<template>
  <div
    class="fixed bottom-0 left-0 right-0 w-full md:top-[calc(5rem+72px)] md:bottom-auto md:right-auto md:left-0 md:h-[calc(100vh-5rem-72px)] md:w-96 bg-white dark:bg-neutral-900 shadow-2xl z-50 flex flex-col rounded-t-2xl md:rounded-none"
    :style="isMobile ? sheetStyle : {}"
  >
      <!-- Mobile drag handle -->
      <div
        class="md:hidden flex justify-center pt-3 pb-2 touch-none cursor-grab"
        v-bind="dragHandleAttrs"
      >
        <div class="w-12 h-1 bg-neutral-300 dark:bg-neutral-600 rounded-full"></div>
      </div>

      <!-- Header -->
      <div class="p-4 border-b border-neutral-200 dark:border-neutral-700 flex items-center justify-between flex-shrink-0">
        <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
          <Building2 :size="20" />
          {{ $t('map.browse.title') }}
        </h2>
        <button
          @click="hidePreviewMarker(); emit('close')"
          class="p-2 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded-full transition"
          :aria-label="$t('map.browse.title')"
        >
          <X :size="20" class="text-neutral-600 dark:text-neutral-400" />
        </button>
      </div>

      <!-- Active category indicator -->
      <div v-if="activeCategoryName" class="px-4 py-2 border-b border-neutral-200 dark:border-neutral-700 flex items-center gap-2 flex-shrink-0">
        <span v-if="activeCategoryIcon" class="text-lg">{{ activeCategoryIcon }}</span>
        <span class="text-sm font-medium text-neutral-900 dark:text-neutral-100 flex-1 truncate">{{ activeCategoryName }}</span>
        <button
          @click="clearCategory"
          class="p-1 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded transition"
        >
          <X :size="14" class="text-neutral-500" />
        </button>
      </div>


      <!-- Results -->
      <div class="flex-1 overflow-y-auto">
        <!-- Loading -->
        <div v-if="loading" class="flex justify-center py-12">
          <div class="animate-spin rounded-full h-10 w-10 border-b-2 border-neutral-900 dark:border-neutral-100"></div>
        </div>

        <!-- Establishment list -->
        <div v-else-if="establishments.length > 0" class="divide-y divide-neutral-100 dark:divide-neutral-800">
          <button
            v-for="est in establishments"
            :key="est.id"
            @click="selectEstablishment(est)"
            @mouseenter="onEstHover(est)"
            @mouseleave="hidePreviewMarker()"
            class="w-full text-left px-4 py-3 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition"
          >
            <div class="flex items-start gap-3">
              <span v-if="est.category_icon" class="text-xl flex-shrink-0 mt-0.5">{{ est.category_icon }}</span>
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-1.5">
                  <span class="font-medium text-sm text-neutral-900 dark:text-neutral-100 truncate">{{ est.name }}</span>
                  <ShieldCheck v-if="est.is_verified" :size="14" class="text-secondary flex-shrink-0" />
                </div>
                <p v-if="est.category_name" class="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">{{ est.category_name }}</p>
                <p v-if="est.full_address" class="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5 line-clamp-1">{{ est.full_address }}</p>
                <a v-if="est.phone" :href="`tel:${est.phone}`" class="text-xs text-link mt-0.5 flex items-center gap-1" @click.stop>
                  <Phone :size="12" />
                  {{ est.phone }}
                </a>
              </div>
            </div>
          </button>
        </div>

        <!-- Empty state -->
        <div v-else class="text-center py-12 px-4">
          <Building2 class="w-12 h-12 mx-auto text-neutral-300 dark:text-neutral-600 mb-3" />
          <h3 class="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-1">
            {{ $t('map.browse.empty_title') }}
          </h3>
          <p class="text-xs text-neutral-500 dark:text-neutral-400">
            {{ $t('map.browse.empty_subtitle') }}
          </p>
        </div>

        <!-- Load more -->
        <div v-if="hasMore && establishments.length > 0" class="p-4">
          <button
            @click="loadMore"
            :disabled="loadingMore"
            class="w-full py-2 px-4 border border-neutral-300 dark:border-neutral-600 rounded-lg text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:bg-neutral-50 dark:hover:bg-neutral-800 transition disabled:opacity-50"
          >
            <span v-if="loadingMore" class="animate-spin inline-block w-4 h-4 border-2 border-neutral-400 border-t-transparent rounded-full mr-2"></span>
            {{ $t('map.browse.load_more') }}
          </button>
        </div>
      </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { X, Phone, ShieldCheck, Building2 } from 'lucide-vue-next'
import { useBottomSheet } from '~/composables/useBottomSheet'

const props = defineProps<{
  mapInstance: any
  initialCategoryId?: string | null
  initialCategoryName?: string | null
  initialCategoryIcon?: string | null
}>()

const emit = defineEmits<{
  close: []
  results: [establishments: any[]]
  select: [establishment: any]
  'category-cleared': []
}>()

const mapStore = useMapStore()

// Mobile detection
const isMobile = ref(false)
if (import.meta.client) {
  isMobile.value = window.innerWidth < 768
  window.addEventListener('resize', () => {
    isMobile.value = window.innerWidth < 768
  })
}

// Bottom sheet drag
const { sheetStyle, dragHandleAttrs } = useBottomSheet({
  initialSnap: 'half',
  onDismiss: () => emit('close')
})

const establishments = ref<any[]>([])
const loading = ref(false)
const loadingMore = ref(false)
const selectedCategory = ref(props.initialCategoryId || '')
const activeCategoryName = ref(props.initialCategoryName || '')
const activeCategoryIcon = ref(props.initialCategoryIcon || '')
const currentPage = ref(1)
const totalPages = ref(1)
const hasMore = ref(false)
let moveEndHandler: (() => void) | null = null
let moveDebounceTimer: ReturnType<typeof setTimeout> | null = null

// Watch for external category changes
watch(() => props.initialCategoryId, (newId) => {
  selectedCategory.value = newId || ''
  fetchEstablishments()
})

watch(() => props.initialCategoryName, (newName) => {
  activeCategoryName.value = newName || ''
})

watch(() => props.initialCategoryIcon, (newIcon) => {
  activeCategoryIcon.value = newIcon || ''
})

const clearCategory = () => {
  selectedCategory.value = ''
  activeCategoryName.value = ''
  activeCategoryIcon.value = ''
  emit('category-cleared')
  fetchEstablishments()
}

// Get map viewport center and radius
const getViewportParams = () => {
  const map = mapStore.mapInstance
  if (!map) return { lat: 0, lon: 0, radius_km: 50 }

  const center = map.getCenter()
  const bounds = map.getBounds()

  const lat1 = center.lat * Math.PI / 180
  const lat2 = bounds.getNorthEast().lat * Math.PI / 180
  const dLat = (bounds.getNorthEast().lat - center.lat) * Math.PI / 180
  const dLon = (bounds.getNorthEast().lng - center.lng) * Math.PI / 180
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
  const radius_km = Math.max(1, Math.min(100, 6371 * c))

  return {
    lat: center.lat,
    lon: center.lng,
    radius_km: Math.round(radius_km * 10) / 10
  }
}

const fetchEstablishments = async (append = false) => {
  if (append) {
    loadingMore.value = true
  } else {
    loading.value = true
    currentPage.value = 1
  }

  try {
    const params = new URLSearchParams({
      page: String(currentPage.value),
    })

    // Geographic filter — always use viewport for browse panel
    const viewport = getViewportParams()
    params.set('lat', String(viewport.lat))
    params.set('lon', String(viewport.lon))
    params.set('radius_km', String(viewport.radius_km))

    if (selectedCategory.value) {
      params.append('category_id', selectedCategory.value)
    }

    const response = await $fetch(`/api/v1/geo/establishments/?${params}`)
    const items = (response as any).items || []
    totalPages.value = (response as any).pages || 1
    hasMore.value = currentPage.value < totalPages.value

    if (append) {
      establishments.value = [...establishments.value, ...items]
    } else {
      establishments.value = items
    }

    emit('results', establishments.value)
  } catch (error) {
    console.error('[MapBrowse] Error fetching establishments:', error)
  } finally {
    loading.value = false
    loadingMore.value = false
  }
}

const loadMore = () => {
  currentPage.value++
  fetchEstablishments(true)
}

const selectEstablishment = (est: any) => {
  const coords = getEstCoords(est)
  if (coords) showPreviewMarker(coords)
  emit('select', est)
}

// --- Preview marker (lock-on brackets) + edge indicator ---
let previewMarker: any = null
let maplibreglCache: any = null
let markerSeq = 0
let edgeIndicatorEl: HTMLElement | null = null

const getEstCoords = (est: any): { lat: number; lon: number } | null => {
  if (est.lat && est.lon) return { lat: est.lat, lon: est.lon }
  if (est.location?.lat && est.location?.lon) return { lat: est.location.lat, lon: est.location.lon }
  return null
}

const showPreviewMarker = async (coords: { lat: number; lon: number }) => {
  hidePreviewMarker()
  const map = mapStore.mapInstance
  if (!map) return
  const seq = ++markerSeq
  if (!maplibreglCache) maplibreglCache = await import('maplibre-gl').then(m => m.default || m)
  if (seq !== markerSeq) return
  const { createLockOnElement } = await import('~/utils/lockOnMarker')
  if (seq !== markerSeq) return
  previewMarker = new maplibreglCache.Marker({ element: createLockOnElement(), anchor: 'center' })
    .setLngLat([coords.lon, coords.lat])
    .addTo(map)
}

const hidePreviewMarker = () => {
  if (previewMarker) { previewMarker.remove(); previewMarker = null }
  hideEdgeIndicator()
}

// --- Edge distance indicator (off-screen direction hint) ---
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

  const bounds = map.getBounds()
  if (bounds.contains([coords.lon, coords.lat] as [number, number])) return

  const container = map.getContainer()
  const w = container.clientWidth
  const h = container.clientHeight
  const cx = w / 2
  const cy = h / 2

  const px = map.project([coords.lon, coords.lat])
  const dx = px.x - cx
  const dy = px.y - cy
  if (Math.abs(dx) < 1 && Math.abs(dy) < 1) return

  const padL = 60, padR = 60, padT = 80, padB = 60
  const sx = dx > 0 ? (w - padR - cx) / dx : dx < 0 ? (padL - cx) / dx : Infinity
  const sy = dy > 0 ? (h - padB - cy) / dy : dy < 0 ? (padT - cy) / dy : Infinity
  const s = Math.min(sx, sy)
  const ex = cx + dx * s
  const ey = cy + dy * s

  const center = map.getCenter()
  const dist = haversineKm(center.lat, center.lng, coords.lat, coords.lon)
  const distText = dist >= 1 ? `${Math.round(dist)} km` : `${Math.round(dist * 1000)} m`

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

const onEstHover = (est: any) => {
  const coords = getEstCoords(est)
  if (coords) {
    showPreviewMarker(coords)
    showEdgeIndicator(coords)
  } else {
    hidePreviewMarker()
  }
}

// Watch map movements
const setupMapListeners = () => {
  const map = mapStore.mapInstance
  if (!map) return

  moveEndHandler = () => {
    if (moveDebounceTimer) clearTimeout(moveDebounceTimer)
    moveDebounceTimer = setTimeout(() => fetchEstablishments(), 500)
  }
  map.on('moveend', moveEndHandler)
}

const cleanupMapListeners = () => {
  const map = mapStore.mapInstance
  if (!map || !moveEndHandler) return
  map.off('moveend', moveEndHandler)
  moveEndHandler = null
  if (moveDebounceTimer) { clearTimeout(moveDebounceTimer); moveDebounceTimer = null }
}

onMounted(() => {
  setupMapListeners()
  fetchEstablishments()
})

onBeforeUnmount(() => {
  cleanupMapListeners()
  hidePreviewMarker()
})
</script>
