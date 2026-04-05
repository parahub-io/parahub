<script setup lang="ts">
import { ArrowLeft, MessageCircle, FileSignature, Edit, EyeOff, Eye, Trash2, X, ChevronLeft, ChevronRight, Share2, MapPin, LayoutGrid, Maximize2, ShieldCheck, Clock, Handshake, Send } from 'lucide-vue-next'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const localePath = useLocalePath()
const authStore = useAuthStore()
const toastStore = useToastStore()
const { fetchCategoryTree } = useCategories()
const { formatPricingOption } = usePricingFormat()

// Category slug -> translated name map
const categoryNames = ref(new Map<string, string>())

const itemId = computed(() => route.params.id as string)

// Fetch item with SSR support
const { data: item, pending: loading, error: fetchError, refresh: refreshItem } = await useAsyncData(
  `item-${itemId.value}`,
  () => $fetch(`/api/v1/items/${itemId.value}/`)
)
const error = computed(() => {
  if (!fetchError.value) return null
  return (fetchError.value as any).data?.message || 'Item not found'
})

const currentImageIndex = ref(0)
const fullscreenImage = ref(false)
const showDeleteItemConfirm = ref(false)

// Check if came from market list (has referrer from /market)
const cameFromMarket = ref(false)

// Navigate back to market
function goBackToMarket() {
  // If user came from market, use browser back to preserve filters
  if (cameFromMarket.value) {
    router.back()
  } else {
    // Otherwise navigate to market home
    router.push(localePath('/market'))
  }
}

// Image navigation
function nextImage() {
  if (item.value?.images?.length > 1) {
    currentImageIndex.value = (currentImageIndex.value + 1) % item.value.images.length
  }
}

function previousImage() {
  if (item.value?.images?.length > 1) {
    currentImageIndex.value = (currentImageIndex.value - 1 + item.value.images.length) % item.value.images.length
  }
}

// Format price

// Format date
function formatDate(dateStr: string) {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return date.toLocaleDateString(locale.value, { day: 'numeric', month: 'short', year: 'numeric' })
}

// Contact seller
async function contactSeller() {
  if (!authStore.isAuthenticated) {
    toastStore.warning(t('login_required'))
    return
  }

  try {
    await authStore.ensureToken()
    const res = await $fetch<any>('/api/v1/matrix/create-dm', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
      body: {
        target_account_id: item.value.owner_account_id,
        item_id: item.value.id,
        item_title: item.value.title
      }
    })

    if (res.room_id) {
      router.push(localePath(`/chat?room_id=${res.room_id}`))
    }
  } catch (e: any) {
    console.error('Failed to create DM:', e)
    toastStore.error(e.data?.message || 'Failed to start chat')
  }
}

// Propose Deal modal
const showProposeDeal = ref(false)
const proposalMessage = ref('')
const proposalSending = ref(false)

function openProposeDeal() {
  if (!authStore.isAuthenticated) {
    toastStore.warning(t('login_required'))
    return
  }
  proposalMessage.value = ''
  showProposeDeal.value = true
}

async function sendProposal() {
  if (!proposalMessage.value.trim()) return
  proposalSending.value = true

  try {
    await authStore.ensureToken()

    // Build a structured deal message
    const pricing = item.value.pricing_options?.[0]
    let dealHeader = `📦 **${item.value.title}**`
    if (pricing) {
      dealHeader += `\n💰 ${formatPricingOption(pricing)}`
    }

    const fullMessage = `${dealHeader}\n\n${proposalMessage.value.trim()}`

    const res = await $fetch<any>('/api/v1/matrix/create-dm', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
      body: {
        target_account_id: item.value.owner_account_id,
        item_id: item.value.id,
        item_title: item.value.title,
        initial_message: fullMessage
      }
    })

    if (res.room_id) {
      toastStore.success(t('market.propose_deal.success'))
      showProposeDeal.value = false
      router.push(localePath(`/chat?room_id=${res.room_id}`))
    }
  } catch (e: any) {
    console.error('Failed to send proposal:', e)
    toastStore.error(e.data?.message || t('market.propose_deal.error'))
  } finally {
    proposalSending.value = false
  }
}

function goToContract() {
  router.push(localePath(`/contracts?partner=${item.value.owner_id}&item=${item.value.id}`))
}

// Owner actions
async function toggleActive() {
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/items/${item.value.id}/${item.value.is_active ? 'deactivate' : 'activate'}/`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })
    item.value.is_active = !item.value.is_active
    toastStore.success(item.value.is_active ? t('market.messages.activated') : t('market.messages.deactivated'))
  } catch (e: any) {
    toastStore.error(e.data?.message || 'Failed to update item')
  }
}

async function deleteItem() {
  showDeleteItemConfirm.value = false
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/items/${item.value.id}/`, {
      method: 'DELETE',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })
    toastStore.success(t('market.messages.deleted'))
    useState('marketDirty', () => false).value = true
    router.push(localePath('/market'))
  } catch (e: any) {
    toastStore.error(e.data?.message || 'Failed to delete item')
  }
}

function editItem() {
  router.push(localePath(`/market/create?edit=${item.value.slug || item.value.id}`))
}

// Share
async function shareItem() {
  const url = window.location.href
  if (navigator.share) {
    await navigator.share({ title: item.value.title, url })
  } else {
    await navigator.clipboard.writeText(url)
    toastStore.success(t('link_copied'))
  }
}

// Build category name lookup from translated tree
function buildCategoryNames(categories: any[]) {
  for (const cat of categories) {
    categoryNames.value.set(cat.slug, cat.name)
    if (cat.children?.length) {
      buildCategoryNames(cat.children)
    }
  }
}

function getCategoryName(slug: string, fallback: string) {
  return categoryNames.value.get(slug) || fallback
}

// Real-time updates
useObjectSubscription(item)

// Init (client-side only)
onMounted(async () => {
  // Check if previous page was market
  if (document.referrer) {
    cameFromMarket.value = document.referrer.includes('/market')
  }
  // Load translated category names
  try {
    const tree = await fetchCategoryTree()
    buildCategoryNames(tree)
  } catch (e) {
    // Fallback to English names from API
  }
})

// SEO - comprehensive meta tags for sharing
useSeoMeta({
  title: () => item.value?.title || t('market.item_detail'),
  ogTitle: () => item.value?.title || t('market.item_detail'),
  description: () => item.value?.description?.slice(0, 160) || t('market.item_detail'),
  ogDescription: () => item.value?.description?.slice(0, 160) || t('market.item_detail'),
  ogImage: () => item.value?.images?.[0]?.url || '/og-image.jpg',
  ogType: 'product',
  twitterCard: 'summary_large_image',
})

// JSON-LD Product structured data
const _baseUrl = useRuntimeConfig().public.siteUrl || 'https://parahub.io'
useHead({
  script: computed(() => {
    if (!item.value) return []
    const baseUrl = _baseUrl
    const pricing = item.value.pricing_options?.[0]
    const jsonLd: Record<string, any> = {
      '@context': 'https://schema.org',
      '@type': 'Product',
      'name': item.value.title,
      'url': `${baseUrl}/market/${item.value.slug || item.value.id}`,
    }
    if (item.value.description) jsonLd.description = item.value.description
    if (item.value.images?.[0]?.url) jsonLd.image = item.value.images[0].url
    if (item.value.owner_hna) {
      jsonLd.seller = { '@type': 'Person', 'name': item.value.owner_hna }
    }
    if (pricing && pricing.amount) {
      jsonLd.offers = {
        '@type': 'Offer',
        'price': pricing.amount,
        'priceCurrency': pricing.currency || 'EUR',
        'availability': item.value.is_active ? 'https://schema.org/InStock' : 'https://schema.org/Discontinued',
      }
    } else if (pricing?.type === 'free') {
      jsonLd.offers = {
        '@type': 'Offer',
        'price': '0',
        'priceCurrency': 'EUR',
        'availability': 'https://schema.org/InStock',
      }
    }
    return [{ type: 'application/ld+json', innerHTML: JSON.stringify(jsonLd) }]
  })
})

definePageMeta({
  middleware: 'auth',
})
</script>

<template>
  <div class="min-h-screen bg-neutral-50 dark:bg-neutral-900">
    <!-- Header -->
    <div class="bg-white dark:bg-neutral-800 border-b border-neutral-200 dark:border-neutral-700 sticky top-0 z-10">
      <div class="max-w-4xl mx-auto px-4 py-3 flex items-center justify-between">
        <button
          @click="goBackToMarket"
          class="flex items-center gap-2 text-neutral-500 hover:text-primary transition-colors"
        >
          <LayoutGrid :size="20" />
          <span class="hidden sm:inline">{{ t('market.back_to_market') }}</span>
          <span class="sm:hidden">{{ t('market.title') }}</span>
        </button>

        <div v-if="item" class="flex items-center gap-1">
          <LikeButton :target-id="item.id" target-type="item" />
          <UiButton variant="ghost" :icon="Share2" icon-only :aria-label="t('common.share')" @click="shareItem" />
        </div>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="py-12 text-center" role="status" aria-live="polite">
      <div class="h-12 w-12 mx-auto border-4 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100 rounded-full animate-spin"></div>
      <span class="sr-only">{{ t('common.loading') }}</span>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="max-w-4xl mx-auto px-4 py-20 text-center">
      <p class="text-red-500 mb-4">{{ error }}</p>
      <NuxtLink :to="localePath('/market')" class="text-link">
        {{ t('market.back_to_market') }}
      </NuxtLink>
    </div>

    <!-- Item Content -->
    <div v-else-if="item" class="max-w-4xl mx-auto px-4 py-6">
      <div class="card rounded-xl overflow-hidden">
        <!-- Images -->
        <div v-if="item.images?.length > 0" class="relative">
          <!-- Main Image -->
          <div
            class="aspect-video bg-neutral-100 dark:bg-neutral-700 relative"
          >
            <img
              :src="item.images[currentImageIndex].url"
              :alt="item.title"
              class="w-full h-full object-contain"
            />
            <!-- Zoom button -->
            <button
              @click="fullscreenImage = true"
              class="absolute top-3 right-3 p-2 bg-black/50 hover:bg-black/70 text-white rounded-full transition-opacity"
              :title="t('market.zoom_image')"
            >
              <Maximize2 :size="18" />
            </button>
          </div>

          <!-- Navigation -->
          <template v-if="item.images.length > 1">
            <button
              @click.stop="previousImage"
              class="absolute left-2 top-1/2 -translate-y-1/2 w-10 h-10 bg-black/50 hover:bg-black/70 text-white rounded-full flex items-center justify-center"
            >
              <ChevronLeft :size="24" />
            </button>
            <button
              @click.stop="nextImage"
              class="absolute right-2 top-1/2 -translate-y-1/2 w-10 h-10 bg-black/50 hover:bg-black/70 text-white rounded-full flex items-center justify-center"
            >
              <ChevronRight :size="24" />
            </button>

            <!-- Dots -->
            <div class="absolute bottom-4 left-1/2 -translate-x-1/2 flex gap-2">
              <button
                v-for="(_, idx) in item.images"
                :key="idx"
                @click.stop="currentImageIndex = idx"
                class="w-2 h-2 rounded-full transition-all"
                :class="currentImageIndex === idx ? 'bg-white w-6' : 'bg-white/50 hover:bg-white/70'"
              />
            </div>
          </template>

          <!-- Thumbnails -->
          <div v-if="item.images.length > 1" class="p-3 flex gap-2 overflow-x-auto">
            <button
              v-for="(img, idx) in item.images"
              :key="img.id"
              @click="currentImageIndex = idx"
              class="w-16 h-16 flex-shrink-0 rounded overflow-hidden border-2 transition"
              :class="currentImageIndex === idx ? 'border-secondary' : 'border-transparent hover:border-neutral-300'"
            >
              <img :src="img.url" :alt="`${item.title} ${idx + 1}`" class="w-full h-full object-cover" />
            </button>
          </div>
        </div>

        <!-- No Image Placeholder -->
        <div v-else class="h-48 bg-neutral-100 dark:bg-neutral-700 flex items-center justify-center">
          <span class="text-neutral-400 text-lg">{{ t('market.no_image') }}</span>
        </div>

        <!-- Videos -->
        <div v-if="item.id" class="px-6 pt-4">
          <ObjectVideos :object-id="item.id" />
          <VideoUpload
            v-if="item.owner_id === authStore.profile?.id"
            :object-id="item.id"
            class="mt-3"
          />
        </div>

        <!-- Content -->
        <div class="p-6">
          <!-- Type & Category -->
          <div class="flex flex-wrap items-center gap-2 mb-3">
            <span
              :class="item.item_type === 'CREDIT' ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200' : 'bg-secondary-100 text-secondary-800 dark:bg-secondary-900 dark:text-secondary-200'"
              class="text-sm font-medium px-3 py-1 rounded-full"
            >
              {{ item.item_type === 'CREDIT' ? t('market.item.offer') : t('market.item.request') }}
            </span>

            <template v-if="item.category_path?.length">
              <span class="text-neutral-400">|</span>
              <div class="text-sm text-neutral-500 dark:text-neutral-400 flex items-center gap-1">
                <template v-for="(cat, idx) in item.category_path" :key="cat.id">
                  <span v-if="idx > 0" class="text-neutral-400">›</span>
                  <NuxtLink
                    :to="`/market?category=${cat.slug}`"
                    class="hover:text-secondary hover:underline"
                  >
                    {{ getCategoryName(cat.slug, cat.name) }}
                  </NuxtLink>
                </template>
              </div>
            </template>
          </div>

          <!-- Title -->
          <div class="flex items-start gap-2 mb-4">
            <h1 class="text-2xl font-bold text-neutral-900 dark:text-white">
              {{ item.title }}
            </h1>
            <DemoBadge :is-demo="item.is_demo" class="mt-1.5" />
          </div>

          <!-- Description -->
          <p class="text-neutral-600 dark:text-neutral-300 whitespace-pre-wrap mb-6">
            {{ item.description || t('market.detail_modal.no_description') }}
          </p>

          <!-- Price -->
          <div class="mb-6">
            <h3 class="text-sm font-medium text-neutral-500 dark:text-neutral-400 mb-2">
              {{ t('market.detail_modal.price_label') }}
            </h3>
            <div v-if="item.pricing_options?.length > 0" class="space-y-1">
              <div
                v-for="(opt, idx) in item.pricing_options"
                :key="idx"
                class="text-xl font-semibold text-neutral-900 dark:text-white"
              >
                {{ formatPricingOption(opt) }}
              </div>
            </div>
            <div v-else class="text-xl font-semibold text-green-600 dark:text-green-400">
              {{ t('market.item.free') }}
            </div>
          </div>

          <!-- Location -->
          <div v-if="item.location_name" class="mb-6 flex items-center gap-2 text-neutral-600 dark:text-neutral-400">
            <MapPin :size="18" />
            <span>{{ item.location_name }}</span>
          </div>

          <!-- Tags -->
          <div v-if="item.tags?.length" class="mb-6">
            <div class="flex flex-wrap gap-2">
              <span
                v-for="tag in item.tags"
                :key="tag"
                class="px-3 py-1 bg-neutral-100 dark:bg-neutral-700 rounded-full text-sm text-neutral-700 dark:text-neutral-300"
              >
                {{ tag }}
              </span>
            </div>
          </div>

          <!-- Demand indicator -->
          <div
            v-if="item.demand_count"
            class="mb-6 p-4 rounded-lg border border-primary/30 bg-primary-100/50 dark:bg-primary-900/20"
          >
            <p class="text-sm font-medium text-neutral-800 dark:text-neutral-200 mb-2">
              {{ item.item_type === 'CREDIT'
                ? t('market.item.demand_people_need', item.demand_count, { n: item.demand_count })
                : t('market.item.demand_offers_available', item.demand_count, { n: item.demand_count })
              }}
            </p>
            <NuxtLink
              :to="localePath(`/market?item_type=${item.item_type === 'CREDIT' ? 'DEBIT' : 'CREDIT'}&category=${item.category_path?.[item.category_path.length - 1]?.slug || ''}`)"
              class="text-sm font-medium text-secondary hover:underline"
            >
              {{ item.item_type === 'CREDIT'
                ? t('market.item.demand_view_requests')
                : t('market.item.demand_view_offers')
              }}
            </NuxtLink>
          </div>

          <!-- Owner & Trust Signals -->
          <div class="border-t border-neutral-200 dark:border-neutral-700 pt-6 mb-6">
            <div class="flex items-start gap-4">
              <!-- Avatar -->
              <NuxtLink :to="`/u/${item.owner_id}`" class="shrink-0">
                <img
                  v-if="item.owner_avatar_url"
                  :src="item.owner_avatar_url"
                  :alt="item.owner_display_name || item.owner_hna"
                  class="w-12 h-12 rounded-full object-cover"
                />
                <div v-else class="w-12 h-12 rounded-full bg-neutral-200 dark:bg-neutral-700 flex items-center justify-center">
                  <span class="text-lg font-medium text-neutral-500 dark:text-neutral-400">
                    {{ (item.owner_display_name || item.owner_hna || '?')[0].toUpperCase() }}
                  </span>
                </div>
              </NuxtLink>

              <!-- Info -->
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 flex-wrap">
                  <template v-if="item.establishment_name">
                    <NuxtLink
                      :to="localePath(`/org/${item.establishment_slug || item.establishment_id}`)"
                      class="font-medium text-neutral-900 dark:text-white hover:text-secondary dark:hover:text-secondary-400"
                    >
                      {{ item.establishment_name }}
                    </NuxtLink>
                    <span class="text-neutral-400">·</span>
                    <NuxtLink
                      :to="`/u/${item.owner_id}`"
                      class="text-sm text-neutral-500 dark:text-neutral-400 hover:text-secondary"
                    >
                      {{ item.owner_display_name || item.owner_hna?.split('@')[0] || item.owner_id }}
                    </NuxtLink>
                  </template>
                  <NuxtLink
                    v-else
                    :to="`/u/${item.owner_id}`"
                    class="font-medium text-neutral-900 dark:text-white hover:text-secondary dark:hover:text-secondary-400"
                  >
                    {{ item.owner_display_name || item.owner_hna?.split('@')[0] || item.owner_id }}
                  </NuxtLink>
                </div>

                <!-- Trust badges -->
                <div class="flex items-center gap-3 mt-1.5 text-sm">
                  <!-- WoT badge -->
                  <span
                    class="inline-flex items-center gap-1"
                    :class="item.owner_is_verified ? 'text-green-600 dark:text-green-400' : 'text-neutral-400 dark:text-neutral-500'"
                  >
                    <ShieldCheck :size="14" />
                    <span v-if="item.owner_is_verified">
                      {{ t('market.trust.wot_verified', { count: item.owner_verifications_count || 3 }) }}
                    </span>
                    <span v-else>
                      {{ t('market.trust.wot_badge', { count: item.owner_verifications_count || 0 }) }}
                    </span>
                  </span>

                  <!-- Member since -->
                  <span v-if="item.owner_created_at" class="inline-flex items-center gap-1 text-neutral-500 dark:text-neutral-400">
                    <Clock :size="14" />
                    {{ t('market.trust.member_since', { date: formatDate(item.owner_created_at) }) }}
                  </span>
                </div>
              </div>

              <!-- Posted date -->
              <div class="text-right shrink-0">
                <span class="text-sm text-neutral-500 dark:text-neutral-400">{{ t('market.detail_modal.posted') }}</span>
                <div class="text-neutral-900 dark:text-white">{{ formatDate(item.created_at) }}</div>
              </div>
            </div>
          </div>

          <!-- Actions -->
          <div v-if="item.owner_id === authStore.profile?.id" class="grid grid-cols-3 gap-3">
            <UiButton variant="outline" :icon="Edit" @click="editItem">
              {{ t('market.actions.edit') }}
            </UiButton>
            <UiButton variant="outline" :icon="item.is_active ? EyeOff : Eye" @click="toggleActive">
              {{ item.is_active ? t('market.actions.hide') : t('market.actions.activate') }}
            </UiButton>
            <UiButton variant="outline-error" :icon="Trash2" @click="showDeleteItemConfirm = true">
              {{ t('market.actions.delete') }}
            </UiButton>
          </div>
          <div v-else class="grid grid-cols-2 gap-3">
            <UiButton :icon="Handshake" @click="openProposeDeal">
              {{ item.item_type === 'DEBIT' ? t('market.actions.respond') : t('market.actions.make_offer') }}
            </UiButton>
            <UiButton variant="secondary" :icon="MessageCircle" @click="contactSeller">
              {{ t('directory.users.message') }}
            </UiButton>
          </div>
        </div>
      </div>
    </div>

    <!-- Propose Deal Modal -->
    <Teleport to="body">
      <div
        v-if="showProposeDeal && item"
        class="fixed inset-0 z-50 flex items-end sm:items-center justify-center"
      >
        <!-- Backdrop -->
        <div
          class="absolute inset-0 bg-black/50"
          @click="showProposeDeal = false"
        />

        <!-- Modal -->
        <div class="relative w-full sm:max-w-lg bg-white dark:bg-neutral-800 rounded-t-2xl sm:rounded-xl shadow-xl max-h-[90vh] overflow-y-auto" @click.stop>
          <!-- Header -->
          <div class="flex items-center justify-between p-4 border-b border-neutral-200 dark:border-neutral-700">
            <h2 class="text-lg font-semibold text-neutral-900 dark:text-white">
              {{ t('market.propose_deal.title') }}
            </h2>
            <button
              @click="showProposeDeal = false"
              :aria-label="t('common.close')"
              class="p-1 hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded-lg"
            >
              <X :size="20" />
            </button>
          </div>

          <!-- Item summary -->
          <div class="p-4 border-b border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-900/50">
            <div class="flex items-center gap-3">
              <img
                v-if="item.images?.[0]?.url"
                :src="item.images[0].url"
                :alt="item.title"
                class="w-16 h-16 rounded-lg object-cover"
              />
              <div class="flex-1 min-w-0">
                <h3 class="font-medium text-neutral-900 dark:text-white truncate">{{ item.title }}</h3>
                <div v-if="item.pricing_options?.length" class="text-sm font-semibold text-neutral-700 dark:text-neutral-300 mt-0.5">
                  {{ formatPricingOption(item.pricing_options[0]) }}
                </div>
                <div v-else class="text-sm font-semibold text-green-600 dark:text-green-400 mt-0.5">
                  {{ t('market.item.free') }}
                </div>
              </div>
            </div>
          </div>

          <!-- Message form -->
          <div class="p-4 space-y-4">
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">
                {{ t('market.propose_deal.message_label') }}
              </label>
              <textarea
                v-model="proposalMessage"
                :placeholder="item.item_type === 'DEBIT' ? t('market.propose_deal.message_placeholder_request') : t('market.propose_deal.message_placeholder')"
                rows="4"
                class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent resize-none"
              />
            </div>

            <!-- Send button -->
            <UiButton
              class="w-full"
              :icon="Send"
              :loading="proposalSending"
              :disabled="!proposalMessage.trim()"
              @click="sendProposal"
            >
              {{ proposalSending ? t('market.propose_deal.sending') : t('market.propose_deal.send') }}
            </UiButton>

            <!-- Contract escalation link -->
            <div class="text-center text-sm text-neutral-500 dark:text-neutral-400">
              {{ t('market.propose_deal.or_formalize') }}
              <button
                @click="showProposeDeal = false; goToContract()"
                class="text-secondary hover:underline ml-1"
              >
                {{ t('market.propose_deal.formalize_link') }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Fullscreen Image Modal -->
    <div
      v-if="fullscreenImage && item?.images?.length"
      class="fixed inset-0 z-50 bg-black flex items-center justify-center"
      @click="fullscreenImage = false"
    >
      <button
        @click="fullscreenImage = false"
        class="absolute top-4 right-4 p-2 text-white hover:bg-white/20 rounded-full"
      >
        <X :size="24" />
      </button>

      <img
        :src="item.images[currentImageIndex].url"
        :alt="item.title"
        class="max-w-full max-h-full object-contain"
        @click.stop
      />

      <template v-if="item.images.length > 1">
        <button
          @click.stop="previousImage"
          class="absolute left-4 top-1/2 -translate-y-1/2 p-3 bg-white/20 hover:bg-white/30 rounded-full"
        >
          <ChevronLeft :size="32" class="text-white" />
        </button>
        <button
          @click.stop="nextImage"
          class="absolute right-4 top-1/2 -translate-y-1/2 p-3 bg-white/20 hover:bg-white/30 rounded-full"
        >
          <ChevronRight :size="32" class="text-white" />
        </button>
      </template>
    </div>
  </div>

  <UiConfirmModal
    v-model="showDeleteItemConfirm"
    :title="t('market.actions.delete')"
    :message="t('market.confirm_delete')"
    :icon="Trash2"
    variant="error"
    :confirm-label="t('market.actions.delete')"
    @confirm="deleteItem"
  />
</template>
