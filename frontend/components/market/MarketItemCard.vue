<template>
  <NuxtLink
    :to="localePath(`/market/${item.slug || item.id}`)"
    class="card group relative isolate overflow-hidden flex flex-col"
    data-testid="market-item-card"
  >
    <!-- Owner/Match/Demo badge. `isolate` on the card keeps this z-20 inside the
         card's own stacking context — otherwise it ties with the sticky market
         toolbar (also z-20) and, being later in DOM order, paints over it. -->
    <div class="absolute top-2 right-2 z-20 flex items-center gap-1">
      <DemoBadge :is-demo="item.is_demo" />
      <span v-if="isMyItem" class="px-2 py-1 text-xs font-medium bg-primary text-black rounded-full">
        {{ $t('market.item.mine_badge') }}
      </span>
      <span v-else-if="isMatchItem" class="px-2 py-1 text-xs font-medium bg-orange-500 text-white rounded-full">
        {{ $t('market.item.match_badge') }}
      </span>
    </div>

    <!-- Lock-on corner brackets: the map/nav targeting grammar as list hover.
         Instant like the nav reticle (no transition); indigo on light, yellow
         on dark (yellow washes out on light bg). -->
    <span aria-hidden="true" class="pointer-events-none absolute inset-0 z-10 opacity-0 group-hover:opacity-100">
      <span class="absolute top-0 left-0 h-3.5 w-3.5 border-t-2 border-l-2 border-secondary dark:border-primary"></span>
      <span class="absolute top-0 right-0 h-3.5 w-3.5 border-t-2 border-r-2 border-secondary dark:border-primary"></span>
      <span class="absolute bottom-0 left-0 h-3.5 w-3.5 border-b-2 border-l-2 border-secondary dark:border-primary"></span>
      <span class="absolute bottom-0 right-0 h-3.5 w-3.5 border-b-2 border-r-2 border-secondary dark:border-primary"></span>
    </span>

    <!-- Item image carousel -->
    <div class="relative">
      <!-- The image is absolutely positioned so a portrait photo's intrinsic
           size can't floor the flex item's min-height and override the ratio. -->
      <div class="relative w-full aspect-[4/3] overflow-hidden bg-neutral-200 dark:bg-neutral-700">
        <img
          v-if="hasImages"
          :src="item.images[currentImageIndex].url"
          :alt="item.title"
          class="absolute inset-0 w-full h-full object-cover"
          :class="!isOffer && 'grayscale-[35%] opacity-90'"
          loading="lazy"
          decoding="async"
        >
        <div v-else class="absolute inset-0 flex items-center justify-center">
          <Package class="w-10 h-10 text-neutral-400 dark:text-neutral-500" />
        </div>
      </div>
      <!-- Want treatment: a violet wash keeps aspirational stock photos of
           sought goods from reading as supply -->
      <span v-if="!isOffer" aria-hidden="true" class="pointer-events-none absolute inset-0 bg-want-600/15"></span>
      <!-- A photoless want is literally an empty slot: the dashed frame says
           "to be filled". Over a real photo it only adds noise, so it stays off. -->
      <span
        v-if="!isOffer && !hasImages"
        aria-hidden="true"
        class="pointer-events-none absolute inset-2 rounded border border-dashed border-want-600/40 dark:border-want-400/40"
      ></span>

      <!-- Carousel navigation (shown when multiple images) -->
      <template v-if="item.images && item.images.length > 1">
        <button
          @click.stop.prevent="previousImage"
          class="absolute left-2 top-1/2 -translate-y-1/2 w-8 h-8 bg-black/50 hover:bg-black/70 text-white rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none group-hover:pointer-events-auto"
        >
          <ChevronLeft class="w-5 h-5" />
        </button>
        <button
          @click.stop.prevent="nextImage"
          class="absolute right-2 top-1/2 -translate-y-1/2 w-8 h-8 bg-black/50 hover:bg-black/70 text-white rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none group-hover:pointer-events-auto"
        >
          <ChevronRight class="w-5 h-5" />
        </button>

        <!-- Image indicators (dots) -->
        <div class="absolute bottom-2 left-1/2 -translate-x-1/2 flex gap-1.5">
          <button
            v-for="(img, idx) in item.images"
            :key="idx"
            @click.stop.prevent="currentImageIndex = idx"
            class="w-2 h-2 rounded-full transition-all"
            :aria-label="$t('market.item.image_n', { n: idx + 1, total: item.images.length })"
            :class="currentImageIndex === idx ? 'bg-white w-6' : 'bg-white/70 hover:bg-white/90'"
          ></button>
        </div>
      </template>
    </div>

    <!-- Direction rail: the card's structural accent -->
    <span aria-hidden="true" class="block h-0.5 w-full" :class="isOffer ? 'bg-offer-500' : 'bg-want-500'"></span>

    <div class="px-3 pt-2.5 pb-3 flex-1 flex flex-col">
      <!-- Eyebrow: direction + leaf category (filters the list when it comes
           from the taxonomy path) -->
      <div class="flex items-center gap-2">
        <button
          @click.stop.prevent="$emit('filter-type', item.item_type)"
          class="group/dir shrink-0"
          :title="isOffer ? $t('market.filters.offers') : $t('market.filters.requests')"
        >
          <MarketListingType
            :item-type="item.item_type"
            display="eyebrow"
            size="sm"
            class="font-mono tracking-wider group-hover/dir:underline underline-offset-2"
          />
        </button>
        <button
          v-if="categoryFilterSlug"
          @click.stop.prevent="$emit('filter-category', categoryFilterSlug)"
          class="ml-auto min-w-0 truncate font-mono text-[10px] uppercase tracking-wider text-neutral-500 dark:text-neutral-400 hover:text-secondary dark:hover:text-secondary-400 hover:underline"
          :title="categoryLabel"
        >
          {{ categoryLabel }}
        </button>
        <span
          v-else-if="categoryLabel"
          class="ml-auto min-w-0 truncate font-mono text-[10px] uppercase tracking-wider text-neutral-500 dark:text-neutral-400"
          :title="categoryLabel"
        >{{ categoryLabel }}</span>
      </div>

      <!-- Title -->
      <h3 class="mt-1 text-[15px] font-semibold text-neutral-900 dark:text-neutral-100 leading-snug line-clamp-2">
        {{ item.translated_title || item.title }}
      </h3>

      <!-- Price: the strongest text on the card. Full option string (unit,
           note, conversion hint) stays reachable as the tooltip. -->
      <div class="mt-2 flex items-baseline gap-1.5">
        <span
          class="text-xl font-extrabold tabular-nums tracking-tight"
          :class="isFree ? 'text-green-700 dark:text-green-400' : 'text-neutral-900 dark:text-neutral-50'"
          :title="mainOpt ? formatPricingOption(mainOpt) : undefined"
        >{{ mainAmount }}</span>
        <span v-if="mainPeriod" class="font-mono text-xs text-neutral-500 dark:text-neutral-400">/{{ mainPeriod }}</span>
        <!-- Demand: opposite-type count in the same category -->
        <span
          v-if="demandLabel"
          class="ml-auto shrink-0 rounded bg-primary-100 dark:bg-primary-900/40 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-neutral-800 dark:text-neutral-200"
        >{{ demandLabel }}</span>
      </div>
      <div v-if="secondLine" class="text-xs text-neutral-500 dark:text-neutral-400 tabular-nums">
        {{ secondLine }}<template v-if="moreCount"> · +{{ moreCount }}</template>
      </div>

      <!-- Footer: service meta as quiet glyphs, owner links, age/distance.
           Pinned to the bottom so footers line up across a grid row. -->
      <div class="mt-auto pt-2.5 flex items-center gap-1.5 font-mono text-[11px] tabular-nums text-neutral-500 dark:text-neutral-400">
        <Hand v-if="item.self_made" class="w-3.5 h-3.5 shrink-0 text-neutral-400" :title="$t('market.item.self_made_badge')" />
        <Lock v-if="item.visibility === 'REGISTERED'" class="w-3.5 h-3.5 shrink-0 text-neutral-400" :title="$t('market.item.registered_badge')" />
        <Languages v-if="item.is_translated" class="w-3.5 h-3.5 shrink-0 text-neutral-400" :title="$t('market.translation.auto_translated')" />
        <template v-if="item.establishment_name">
          <NuxtLink
            :to="localePath(`/org/${item.establishment_slug || item.establishment_id}`)"
            @click.stop
            class="min-w-0 truncate text-neutral-700 dark:text-neutral-200 hover:text-secondary dark:hover:text-secondary-400 hover:underline"
          >
            {{ item.establishment_name }}
          </NuxtLink>
          <span class="text-neutral-400">·</span>
          <NuxtLink
            :to="localePath(`/@${item.owner_hna?.split('@')[0] || item.owner_id}`)"
            @click.stop
            class="shrink-0 text-neutral-400 dark:text-neutral-500 hover:text-secondary dark:hover:text-secondary-400 hover:underline"
          >
            {{ item.owner_display_name || item.owner_hna?.split('@')[0] || item.owner_id }}
          </NuxtLink>
        </template>
        <NuxtLink
          v-else
          :to="localePath(`/@${item.owner_hna?.split('@')[0] || item.owner_id}`)"
          @click.stop
          class="min-w-0 truncate hover:text-secondary dark:hover:text-secondary-400 hover:underline"
        >
          {{ item.owner_display_name || item.owner_hna?.split('@')[0] || item.owner_id }}
        </NuxtLink>
        <span class="ml-auto shrink-0">{{ formatDistance(item.distance_meters) || formatDate(item.created_at) }}</span>
      </div>
    </div>
  </NuxtLink>
</template>

<script setup>
import { computed, ref } from 'vue'
import { Package, Hand, Lock, Languages, ChevronLeft, ChevronRight } from 'lucide-vue-next'

const props = defineProps({
  item: { type: Object, required: true },
  authProfileId: { type: String, default: null },
  myItemCategories: { type: Object, default: () => ({ credit: [], debit: [] }) },
  categoryMap: { type: Map, default: () => new Map() }
})

defineEmits(['filter-category', 'filter-type'])

const { t: $t, locale } = useI18n()
const localePath = useLocalePath()
const { formatPricingOption, priceAmount, pricingTypeLabel, pricingPeriod } = usePricingFormat()

const currentImageIndex = ref(0)

const isOffer = computed(() => props.item.item_type === 'CREDIT')
const hasImages = computed(() => !!props.item.images?.length)

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

// Leaf of the taxonomy path — only that one is clickable as a filter; a bare
// `category_name` (free-form, no slug) is shown as plain text.
const categoryFilterSlug = computed(() => {
  const path = props.item.category_path
  return path && path.length ? path[path.length - 1].slug : null
})

const categoryLabel = computed(() =>
  categoryFilterSlug.value ? getCategoryName(categoryFilterSlug.value) : (props.item.category_name || '')
)

const opts = computed(() => props.item.pricing_options || [])
const mainOpt = computed(() => opts.value[0] || null)
const isFree = computed(() => !mainOpt.value || mainOpt.value.type === 'free')
const mainAmount = computed(() => priceAmount(mainOpt.value))
const mainPeriod = computed(() => (mainOpt.value ? pricingPeriod(mainOpt.value) : ''))

// Second pricing option compressed to "Rent · 1 750 €/month"; anything beyond
// collapses into "+N".
const secondLine = computed(() => {
  const opt = opts.value[1]
  if (!opt) return ''
  const period = pricingPeriod(opt)
  const amount = priceAmount(opt) + (period ? `/${period}` : '')
  return [pricingTypeLabel(opt, props.item.item_type), amount].filter(Boolean).join(' · ')
})
const moreCount = computed(() => Math.max(0, opts.value.length - 2))

const demandLabel = computed(() => {
  const n = props.item.demand_count
  if (!n) return ''
  return props.item.item_type === 'CREDIT'
    ? $t('market.item.demand_need', n, { n })
    : $t('market.item.demand_offers', n, { n })
})

const formatDate = (dateString) => {
  const date = new Date(dateString)
  const now = new Date()
  const diff = Math.floor((now - date) / 1000)

  if (diff < 60) return $t('market.time.just_now')
  if (diff < 3600) return $t('market.time.minutes_ago', { n: Math.floor(diff / 60) })
  if (diff < 86400) return $t('market.time.hours_ago', { n: Math.floor(diff / 3600) })
  if (diff < 604800) return $t('market.time.days_ago', { n: Math.floor(diff / 86400) })

  // Compact absolute date: the year only when it differs from the current one.
  const sameYear = date.getFullYear() === now.getFullYear()
  return date.toLocaleDateString(locale.value, sameYear
    ? { day: 'numeric', month: 'short' }
    : { day: 'numeric', month: 'short', year: 'numeric' })
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
  const total = props.item.images.length
  currentImageIndex.value = (currentImageIndex.value - 1 + total) % total
}

function nextImage() {
  const total = props.item.images.length
  currentImageIndex.value = (currentImageIndex.value + 1) % total
}
</script>
