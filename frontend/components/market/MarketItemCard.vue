<template>
  <NuxtLink
    :to="localePath(`/market/${item.slug || item.id}`)"
    class="card overflow-hidden relative block hover:border-primary transition-colors"
    data-testid="market-item-card"
  >
    <!-- Owner/Match/Demo badge -->
    <div class="absolute top-2 right-2 z-10 flex items-center gap-1">
      <DemoBadge :is-demo="item.is_demo" />
      <span v-if="isMyItem" class="px-2 py-1 text-xs font-medium bg-primary text-black rounded-full">
        {{ $t('market.item.mine_badge') }}
      </span>
      <span v-else-if="isMatchItem" class="px-2 py-1 text-xs font-medium bg-orange-500 text-white rounded-full">
        {{ $t('market.item.match_badge') }}
      </span>
    </div>

    <!-- Item image carousel -->
    <div class="relative group">
      <div v-if="item.images && item.images.length > 0" class="w-full aspect-video bg-neutral-200 dark:bg-neutral-700">
        <img
          :src="item.images[item.currentImageIndex || 0].url"
          :alt="item.title"
          class="w-full h-full object-cover"
          loading="lazy"
          decoding="async"
        >
      </div>
      <div v-else class="w-full aspect-video bg-neutral-200 dark:bg-neutral-700 flex items-center justify-center">
        <Package class="w-12 h-12 text-neutral-400 dark:text-neutral-500" />
      </div>

      <!-- Carousel navigation (shown when multiple images) -->
      <template v-if="item.images && item.images.length > 1">
        <!-- Previous button -->
        <button
          @click.stop="previousImage"
          class="absolute left-2 top-1/2 -translate-y-1/2 w-8 h-8 bg-black/50 hover:bg-black/70 text-white rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none group-hover:pointer-events-auto"
        >
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
          </svg>
        </button>

        <!-- Next button -->
        <button
          @click.stop="nextImage"
          class="absolute right-2 top-1/2 -translate-y-1/2 w-8 h-8 bg-black/50 hover:bg-black/70 text-white rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none group-hover:pointer-events-auto"
        >
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
          </svg>
        </button>

        <!-- Image indicators (dots) -->
        <div class="absolute bottom-2 left-1/2 -translate-x-1/2 flex gap-1.5">
          <button
            v-for="(img, idx) in item.images"
            :key="idx"
            @click.stop="setImageIndex(idx)"
            class="w-2 h-2 rounded-full transition-all"
            :aria-label="$t('market.item.image_n', { n: idx + 1, total: item.images.length })"
            :class="(item.currentImageIndex || 0) === idx ? 'bg-white w-6' : 'bg-white/70 hover:bg-white/90'"
          ></button>
        </div>
      </template>
    </div>

    <!-- Item type badge -->
    <div class="px-4 pt-4 pb-2">
      <div class="flex justify-between items-start mb-2">
        <span
          :class="item.item_type === 'CREDIT' ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200' : 'bg-secondary-100 text-secondary-800 dark:bg-secondary-900 dark:text-secondary-200'"
          class="text-xs font-medium px-2 py-1 rounded"
        >
          {{ item.item_type === 'CREDIT' ? $t('market.item.offer') : $t('market.item.request') }}
        </span>
        <!-- Demand badge: opposite-type count in same category -->
        <span
          v-if="item.demand_count"
          class="text-xs font-medium px-2 py-1 rounded bg-primary-100 text-primary-800 dark:bg-primary-900 dark:text-primary-200"
        >
          {{ item.item_type === 'CREDIT'
            ? $t('market.item.demand_need', item.demand_count, { n: item.demand_count })
            : $t('market.item.demand_offers', item.demand_count, { n: item.demand_count })
          }}
        </span>
        <!-- Category breadcrumbs -->
        <div v-if="item.category_path && item.category_path.length" class="text-xs text-neutral-600 dark:text-neutral-300 flex items-center gap-1">
          <button
            @click.stop="$emit('filter-category', item.category_path[item.category_path.length - 1].slug)"
            class="hover:text-secondary hover:underline"
          >
            {{ getCategoryName(item.category_path[item.category_path.length - 1].slug) }}
          </button>
        </div>
        <span v-else class="text-xs text-neutral-600 dark:text-neutral-300">
          {{ item.category_name || '' }}
        </span>
      </div>

      <!-- Title -->
      <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-1 line-clamp-2">
        {{ item.title }}
      </h3>

      <!-- Description -->
      <p class="text-sm text-neutral-600 dark:text-neutral-300 line-clamp-2 mb-3">
        {{ item.description || $t('market.item.no_description') }}
      </p>

      <!-- Price and details -->
      <div class="flex justify-between items-center">
        <div>
          <div v-if="item.pricing_options && item.pricing_options.length > 0" class="text-sm">
            <div
              v-for="(opt, idx) in item.pricing_options.slice(0, 2)"
              :key="idx"
              class="font-semibold text-neutral-900 dark:text-neutral-100"
            >
              {{ formatPricingOption(opt) }}
            </div>
            <div v-if="item.pricing_options.length > 2" class="text-xs text-neutral-600 dark:text-neutral-300">
              +{{ item.pricing_options.length - 2 }} {{ $t('market.item.more_options') }}
            </div>
          </div>
          <div v-else class="font-semibold text-green-700 dark:text-green-400">
            {{ $t('market.item.free') }}
          </div>
        </div>

        <div class="flex items-center gap-2">
          <!-- Distance indicator (when sorting by distance) -->
          <span v-if="item.distance_meters" class="text-xs font-medium text-neutral-700 dark:text-neutral-300 flex items-center gap-1">
            <span>📍</span>
            <span>{{ formatDistance(item.distance_meters) }}</span>
          </span>
          <!-- Location indicator with icon (no lone emoji without context) -->
          <MapPin v-else-if="item.location" class="w-3.5 h-3.5 text-neutral-400 dark:text-neutral-500" />
        </div>
      </div>

      <!-- Owner info -->
      <div class="mt-3 pt-3 border-t border-neutral-200 dark:border-neutral-700 flex items-center justify-between text-xs">
        <div class="flex items-center gap-1.5 min-w-0">
          <template v-if="item.establishment_name">
            <NuxtLink
              :to="localePath(`/org/${item.establishment_slug || item.establishment_id}`)"
              @click.stop
              class="text-neutral-700 dark:text-neutral-200 hover:text-secondary dark:hover:text-secondary hover:underline font-medium truncate"
            >
              {{ item.establishment_name }}
            </NuxtLink>
            <span class="text-neutral-400">·</span>
            <NuxtLink
              :to="`/u/${item.owner_id}`"
              @click.stop
              class="text-neutral-400 dark:text-neutral-500 hover:text-secondary dark:hover:text-secondary hover:underline shrink-0"
            >
              {{ item.owner_display_name || item.owner_hna?.split('@')[0] || item.owner_id }}
            </NuxtLink>
          </template>
          <NuxtLink
            v-else
            :to="`/u/${item.owner_id}`"
            @click.stop
            class="text-neutral-600 dark:text-neutral-300 hover:text-secondary dark:hover:text-secondary hover:underline"
          >
            {{ item.owner_display_name || item.owner_hna?.split('@')[0] || item.owner_id }}
          </NuxtLink>
        </div>
        <span class="text-neutral-600 dark:text-neutral-300 shrink-0">
          {{ formatDate(item.created_at) }}
        </span>
      </div>
    </div>
  </NuxtLink>
</template>

<script setup>
import { computed } from 'vue'
import { Package, MapPin } from 'lucide-vue-next'

const props = defineProps({
  item: { type: Object, required: true },
  authProfileId: { type: String, default: null },
  myItemCategories: { type: Object, default: () => ({ credit: [], debit: [] }) },
  categoryMap: { type: Map, default: () => new Map() }
})

defineEmits(['filter-category'])

const { t: $t, locale } = useI18n()
const localePath = useLocalePath()
const { formatPricingOption } = usePricingFormat()

const isMyItem = computed(() => {
  return props.item.owner_id === props.authProfileId
})

const isMatchItem = computed(() => {
  if (!props.authProfileId || !props.item.category_id) return false

  if (props.item.item_type === 'CREDIT') {
    return props.myItemCategories.debit.includes(props.item.category_id)
  }
  if (props.item.item_type === 'DEBIT') {
    return props.myItemCategories.credit.includes(props.item.category_id)
  }
  return false
})

const getCategoryName = (slug) => {
  if (!slug) return ''
  const cat = props.categoryMap.get(slug)
  return cat ? cat.name : slug
}

const formatDate = (dateString) => {
  const date = new Date(dateString)
  const now = new Date()
  const diff = Math.floor((now - date) / 1000)

  if (diff < 60) return $t('market.time.just_now')
  if (diff < 3600) return $t('market.time.minutes_ago', { n: Math.floor(diff / 60) })
  if (diff < 86400) return $t('market.time.hours_ago', { n: Math.floor(diff / 3600) })
  if (diff < 604800) return $t('market.time.days_ago', { n: Math.floor(diff / 86400) })

  return date.toLocaleDateString(locale.value, { day: 'numeric', month: 'short', year: 'numeric' })
}

const formatDistance = (meters) => {
  if (!meters) return ''

  if (meters < 1000) {
    return `${Math.round(meters)} ${$t('market.distance.meters')}`
  } else {
    const km = meters / 1000
    if (km < 10) {
      return `${km.toFixed(1)} ${$t('market.distance.km')}`
    } else {
      return `${Math.round(km)} ${$t('market.distance.km')}`
    }
  }
}

function previousImage() {
  const item = props.item
  if (!item.currentImageIndex) item.currentImageIndex = 0
  item.currentImageIndex = (item.currentImageIndex - 1 + item.images.length) % item.images.length
}

function nextImage() {
  const item = props.item
  if (!item.currentImageIndex) item.currentImageIndex = 0
  item.currentImageIndex = (item.currentImageIndex + 1) % item.images.length
}

function setImageIndex(index) {
  props.item.currentImageIndex = index
}
</script>
