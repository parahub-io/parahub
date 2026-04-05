<template>
  <div class="py-6">
    <div class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
      <PageHeader
        :title="$t('barter.title')"
        :subtitle="$t('barter.description')"
      />

      <!-- Stats -->
      <div v-if="!loading && opportunities" class="mb-6">
        <div class="card p-4 max-w-sm">
          <div class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t('barter.stats.chains_found') }}</div>
          <div class="text-2xl font-bold text-neutral-900 dark:text-neutral-100">
            {{ opportunities.chains_count }}
          </div>
        </div>
      </div>

      <!-- Loading -->
      <div v-if="loading" class="text-center py-12" role="status" aria-live="polite">
        <div class="inline-block animate-spin rounded-full h-12 w-12 border-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-white" aria-hidden="true"></div>
        <p class="mt-4 text-neutral-600 dark:text-neutral-400">{{ $t('barter.loading') }}</p>
      </div>

      <!-- Error -->
      <UiAlert v-else-if="error" variant="error">{{ error }}</UiAlert>

      <!-- No opportunities -->
      <div v-else-if="!opportunities || opportunities.chains_count === 0" class="text-center py-12">
        <img src="/images/para/searching.png" alt="Para" class="mx-auto h-32 w-auto mb-4" />
        <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-2">
          {{ $t('barter.empty.title') }}
        </h3>
        <p class="text-neutral-600 dark:text-neutral-400 mb-4">
          {{ $t('barter.empty.description') }}
        </p>
        <UiButton variant="primary" size="sm" :icon="Plus" :to="localePath('/market/create')">
          {{ $t('barter.empty.create_listing') }}
        </UiButton>
      </div>

      <!-- Barter chains list -->
      <div v-else class="space-y-6">
        <div
          v-for="(chain, idx) in opportunities.chains"
          :key="idx"
          class="card p-6"
        >
          <!-- Chain header -->
          <div class="mb-4">
            <!-- Only show badge for 3+ way exchanges -->
            <UiBadge v-if="chain.users.length > 3" variant="secondary" type="solid">
              {{ chain.users.length - 1 }}-way exchange
            </UiBadge>
            <!-- Desktop: Propose button on top-right -->
            <UiButton
              variant="primary"
              size="sm"
              :icon="ArrowRightLeft"
              class="hidden md:inline-flex float-right"
              @click="initiateExchange(chain)"
            >
              {{ $t('barter.chain.propose') }}
            </UiButton>
          </div>

          <!-- Chain visualization -->
          <div class="flex items-center gap-2 mb-6 overflow-x-auto pb-2">
            <template v-for="(user, userIdx) in chain.users" :key="userIdx">
              <div class="flex items-center gap-2">
                <NuxtLink
                  :to="`/u/${user.id}`"
                  class="px-3 py-2 bg-neutral-100 dark:bg-neutral-700 rounded-lg text-sm font-medium whitespace-nowrap hover:bg-primary/10 transition-colors"
                >
                  {{ user.display_name || user.hna.split('@')[0] }}
                </NuxtLink>
                <ArrowRight v-if="userIdx < chain.users.length - 1" class="w-4 h-4 text-neutral-400 flex-shrink-0" />
              </div>
            </template>
          </div>

          <!-- Exchange details -->
          <div v-if="is2WayExchange(chain)" class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <!-- What you can offer -->
            <div class="bg-neutral-50 dark:bg-neutral-900 rounded-lg p-4">
              <div class="text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-3">
                {{ $t('barter.exchange.you_can_offer') }}
              </div>
              <div class="space-y-2">
                <div v-for="item in getYourOffers(chain)" :key="item.id">
                  <div @click="openItemModal(item.id)" @keydown.enter="openItemModal(item.id)" @keydown.space.prevent="openItemModal(item.id)" role="button" tabindex="0" class="flex items-start gap-2 hover:bg-neutral-100 dark:hover:bg-neutral-800 p-2 rounded transition-colors cursor-pointer focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:outline-none">
                    <div class="w-16 h-16 bg-neutral-200 dark:bg-neutral-700 rounded flex-shrink-0 overflow-hidden">
                      <img v-if="item.image" :src="item.image" :alt="item.title" class="w-full h-full object-cover" />
                      <Package v-else class="w-8 h-8 text-neutral-400 m-auto mt-4" />
                    </div>
                    <div class="flex-1">
                      <div class="font-medium text-sm text-neutral-900 dark:text-neutral-100">{{ item.title }}</div>
                      <!-- Category breadcrumb -->
                      <div v-if="item.category_path && item.category_path.length" class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
                        <span v-for="(cat, idx) in item.category_path" :key="cat.id">
                          <button
                            @click.stop="goToMarketCategory(cat.slug)"
                            class="hover:text-secondary hover:underline"
                          >
                            {{ getCategoryName(cat.slug, cat.name) }}
                          </button>
                          <span v-if="idx < item.category_path.length - 1"> / </span>
                        </span>
                      </div>
                      <!-- Price -->
                      <div v-if="item.pricing_options && item.pricing_options.length > 0" class="text-xs mt-1">
                        <div
                          v-for="(opt, idx) in item.pricing_options.slice(0, 2)"
                          :key="idx"
                          class="font-semibold text-neutral-900 dark:text-neutral-100"
                        >
                          {{ formatPricingOption(opt) }}
                        </div>
                        <div v-if="item.pricing_options.length > 2" class="text-xs text-neutral-500">
                          +{{ item.pricing_options.length - 2 }} {{ $t('market.item.more_options') }}
                        </div>
                      </div>
                      <div v-else class="text-xs font-semibold text-success-600 dark:text-success-400 mt-1">
                        {{ $t('market.item.free') }}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- What partner can offer -->
            <div class="bg-neutral-50 dark:bg-neutral-900 rounded-lg p-4">
              <div class="text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-3">
                {{ $t('barter.exchange.they_can_offer') }}
              </div>
              <div class="space-y-2">
                <div v-for="item in getPartnerOffers(chain)" :key="item.id">
                  <div @click="openItemModal(item.id)" @keydown.enter="openItemModal(item.id)" @keydown.space.prevent="openItemModal(item.id)" role="button" tabindex="0" class="flex items-start gap-2 hover:bg-neutral-100 dark:hover:bg-neutral-800 p-2 rounded transition-colors cursor-pointer focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:outline-none">
                    <div class="w-16 h-16 bg-neutral-200 dark:bg-neutral-700 rounded flex-shrink-0 overflow-hidden">
                      <img v-if="item.image" :src="item.image" :alt="item.title" class="w-full h-full object-cover" />
                      <Package v-else class="w-8 h-8 text-neutral-400 m-auto mt-4" />
                    </div>
                    <div class="flex-1">
                      <div class="font-medium text-sm text-neutral-900 dark:text-neutral-100">{{ item.title }}</div>
                      <!-- Category breadcrumb -->
                      <div v-if="item.category_path && item.category_path.length" class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
                        <span v-for="(cat, idx) in item.category_path" :key="cat.id">
                          <button
                            @click.stop="goToMarketCategory(cat.slug)"
                            class="hover:text-secondary hover:underline"
                          >
                            {{ getCategoryName(cat.slug, cat.name) }}
                          </button>
                          <span v-if="idx < item.category_path.length - 1"> / </span>
                        </span>
                      </div>
                      <!-- Price -->
                      <div v-if="item.pricing_options && item.pricing_options.length > 0" class="text-xs mt-1">
                        <div
                          v-for="(opt, idx) in item.pricing_options.slice(0, 2)"
                          :key="idx"
                          class="font-semibold text-neutral-900 dark:text-neutral-100"
                        >
                          {{ formatPricingOption(opt) }}
                        </div>
                        <div v-if="item.pricing_options.length > 2" class="text-xs text-neutral-500">
                          +{{ item.pricing_options.length - 2 }} {{ $t('market.item.more_options') }}
                        </div>
                      </div>
                      <div v-else class="text-xs font-semibold text-success-600 dark:text-success-400 mt-1">
                        {{ $t('market.item.free') }}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Multi-way swaps (3+ participants) -->
          <div v-else class="space-y-3">
            <div
              v-for="(swap, swapIdx) in chain.swaps"
              :key="swapIdx"
              class="bg-neutral-50 dark:bg-neutral-900 rounded-lg p-4"
            >
              <div class="text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-3">
                <NuxtLink :to="`/u/${swap.from_user}`" class="hover:text-secondary">
                  {{ getUserName(swap.from_user) }}
                </NuxtLink>
                →
                <NuxtLink :to="`/u/${swap.to_user}`" class="hover:text-secondary">
                  {{ getUserName(swap.to_user) }}
                </NuxtLink>
              </div>
              <div class="space-y-2">
                <div v-for="item in swap.offered_items" :key="item.id">
                  <div @click="openItemModal(item.id)" @keydown.enter="openItemModal(item.id)" @keydown.space.prevent="openItemModal(item.id)" role="button" tabindex="0" class="flex items-start gap-2 hover:bg-neutral-100 dark:hover:bg-neutral-800 p-2 rounded transition-colors cursor-pointer focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:outline-none">
                    <div class="w-16 h-16 bg-neutral-200 dark:bg-neutral-700 rounded flex-shrink-0 overflow-hidden">
                      <img v-if="item.image" :src="item.image" :alt="item.title" class="w-full h-full object-cover" />
                      <Package v-else class="w-8 h-8 text-neutral-400 m-auto mt-4" />
                    </div>
                    <div class="flex-1">
                      <div class="font-medium text-sm text-neutral-900 dark:text-neutral-100">{{ item.title }}</div>
                      <!-- Category breadcrumb -->
                      <div v-if="item.category_path && item.category_path.length" class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
                        <span v-for="(cat, idx) in item.category_path" :key="cat.id">
                          <button
                            @click.stop="goToMarketCategory(cat.slug)"
                            class="hover:text-secondary hover:underline"
                          >
                            {{ getCategoryName(cat.slug, cat.name) }}
                          </button>
                          <span v-if="idx < item.category_path.length - 1"> / </span>
                        </span>
                      </div>
                      <!-- Price -->
                      <div v-if="item.pricing_options && item.pricing_options.length > 0" class="text-xs mt-1">
                        <div
                          v-for="(opt, idx) in item.pricing_options.slice(0, 2)"
                          :key="idx"
                          class="font-semibold text-neutral-900 dark:text-neutral-100"
                        >
                          {{ formatPricingOption(opt) }}
                        </div>
                        <div v-if="item.pricing_options.length > 2" class="text-xs text-neutral-500">
                          +{{ item.pricing_options.length - 2 }} {{ $t('market.item.more_options') }}
                        </div>
                      </div>
                      <div v-else class="text-xs font-semibold text-success-600 dark:text-success-400 mt-1">
                        {{ $t('market.item.free') }}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Mobile: Propose button at bottom -->
          <UiButton
            variant="primary"
            :icon="ArrowRightLeft"
            class="md:hidden w-full mt-4"
            @click="initiateExchange(chain)"
          >
            {{ $t('barter.chain.propose') }}
          </UiButton>
        </div>
      </div>
    </div>

    <!-- Item Detail Modal -->
    <div v-if="selectedItem" class="fixed inset-0 z-50 overflow-y-auto">
      <div class="flex items-center justify-center min-h-screen px-4 pt-4 pb-20 text-center sm:p-0">
        <div @click="selectedItem = null" class="fixed inset-0 bg-neutral-900 bg-opacity-75" aria-hidden="true"></div>

        <div class="relative inline-block w-full max-w-2xl px-4 pt-5 pb-4 overflow-hidden text-left align-bottom transform bg-white dark:bg-neutral-800 rounded-lg shadow-xl sm:my-8 sm:align-middle sm:p-6" role="dialog" aria-modal="true">
          <div class="absolute top-0 right-0 pt-4 pr-4">
            <button @click="selectedItem = null" class="text-neutral-400 hover:text-neutral-500" :aria-label="$t('common.close')">
              <X class="w-6 h-6" aria-hidden="true" />
            </button>
          </div>

          <div class="sm:flex sm:items-start">
            <div class="w-full">
              <!-- Image -->
              <div v-if="selectedItem.images && selectedItem.images.length > 0" class="mb-4">
                <div class="w-full aspect-video bg-neutral-200 dark:bg-neutral-700 rounded-lg overflow-hidden">
                  <img :src="selectedItem.images[0].url" :alt="selectedItem.title" class="w-full h-full object-cover">
                </div>
              </div>

              <div class="flex items-start justify-between mb-4">
                <div class="flex flex-wrap items-center gap-2">
                  <UiBadge :variant="selectedItem.item_type === 'CREDIT' ? 'success' : 'secondary'" type="soft">
                    {{ selectedItem.item_type === 'CREDIT' ? $t('market.item.offer') : $t('market.item.request') }}
                  </UiBadge>
                  <span v-if="selectedItem.category_name" class="text-xs text-neutral-500 dark:text-neutral-400">
                    {{ selectedItem.category_name }}
                  </span>
                </div>
              </div>

              <h3 class="text-xl font-semibold text-neutral-900 dark:text-neutral-100 mb-3">
                {{ selectedItem.title }}
              </h3>

              <p class="text-neutral-600 dark:text-neutral-400 mb-4 whitespace-pre-wrap">
                {{ selectedItem.description || $t('market.detail_modal.no_description') }}
              </p>

              <div class="mb-4">
                <span class="text-sm text-neutral-500 dark:text-neutral-400 block mb-2">{{ $t('market.detail_modal.price_label') }}</span>
                <div v-if="selectedItem.pricing_options && selectedItem.pricing_options.length > 0" class="space-y-1">
                  <div
                    v-for="(opt, idx) in selectedItem.pricing_options"
                    :key="idx"
                    class="font-semibold text-neutral-900 dark:text-neutral-100"
                  >
                    {{ formatPricingOption(opt) }}
                  </div>
                </div>
                <div v-else class="font-semibold text-success-600 dark:text-success-400">
                  {{ $t('market.item.free') }}
                </div>
              </div>

              <div class="border-t border-neutral-200 dark:border-neutral-700 pt-4">
                <div class="flex items-center justify-between mb-2">
                  <div>
                    <span class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('market.detail_modal.listed_by') }}</span>
                    <div class="text-neutral-900 dark:text-neutral-100">
                      {{ selectedItem.owner_display_name || selectedItem.owner_hna?.split('@')[0] || selectedItem.owner_id }}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ArrowRight, ArrowRightLeft, Package, Plus, X } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'
import { useToastStore } from '~/stores/toast'

definePageMeta({
  middleware: 'auth',
  keepalive: true  // Enable KeepAlive caching for instant switching
})

const authStore = useAuthStore()
const toastStore = useToastStore()
const localePath = useLocalePath()
const { t: $t } = useI18n()
const { fetchCategoryTree } = useCategories()
const { formatPricingOption } = usePricingFormat()

useSeoMeta({
  title: () => $t('barter.title'),
  description: () => $t('barter.description'),
  ogTitle: () => $t('barter.title'),
  ogDescription: () => $t('barter.description'),
})

// Category slug -> translated name map
const categoryNames = ref(new Map<string, string>())

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

interface UserInfo {
  id: string
  hna: string
  display_name: string
}

interface BarterItem {
  id: string
  title: string
  category: string
  image?: string
}

interface BarterSwap {
  from_user: string
  to_user: string
  offered_items: BarterItem[]
  wanted_items: BarterItem[]
  category_id: string
}

interface BarterChain {
  users: UserInfo[]
  swaps: BarterSwap[]
}

interface BarterOpportunities {
  user_id: string
  chains_count: number
  chains: BarterChain[]
}

const opportunities = ref<BarterOpportunities | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)
const selectedItem = ref<any>(null)

const twoWayChains = computed(() => {
  if (!opportunities.value) return []
  return opportunities.value.chains.filter(c => c.users.length === 3)
})

const threeWayChains = computed(() => {
  if (!opportunities.value) return []
  return opportunities.value.chains.filter(c => c.users.length === 4)
})

async function fetchOpportunities() {
  loading.value = true
  error.value = null

  try {
    await authStore.ensureToken()

    const response = await $fetch<BarterOpportunities>('/api/v1/barter/opportunities', {
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`
      }
    })

    opportunities.value = response
  } catch (e: any) {
    console.error('Failed to fetch barter opportunities:', e)
    error.value = $t('barter.errors.load_failed')
  } finally {
    loading.value = false
  }
}

function is2WayExchange(chain: BarterChain): boolean {
  // 2-way exchange has exactly 3 users: [you, partner, you]
  return chain.users.length === 3
}

function getYourOffers(chain: BarterChain): BarterItem[] {
  if (!authStore.profile?.id) return []
  const yourSwap = chain.swaps.find(s => s.from_user === authStore.profile.id)
  return yourSwap?.offered_items || []
}

function getPartnerOffers(chain: BarterChain): BarterItem[] {
  if (!authStore.profile?.id) return []
  const partnerSwap = chain.swaps.find(s => s.from_user !== authStore.profile.id)
  return partnerSwap?.offered_items || []
}

function getUserName(userId: string): string {
  if (!opportunities.value) return userId.substring(0, 8) + '...'

  // Find user in chain data
  for (const chain of opportunities.value.chains) {
    const user = chain.users.find(u => u.id === userId)
    if (user) {
      return user.display_name || user.hna.split('@')[0]
    }
  }

  return userId.substring(0, 8) + '...'
}

async function openItemModal(itemId: string) {
  try {
    const response = await $fetch(`/api/v1/items/${itemId}`, {
      credentials: 'include'
    })
    selectedItem.value = response
  } catch (e: any) {
    console.error('Failed to fetch item:', e)
  }
}

async function initiateExchange(chain: BarterChain) {
  if (!authStore.isAuthenticated) {
    navigateTo(localePath('/login') + '?redirect=' + encodeURIComponent(localePath('/barter')))
    return
  }

  try {
    // Extract unique participant IDs (excluding last as it's a repeat of the first)
    const uniqueUsers = chain.users.slice(0, -1)
    const participantIds = uniqueUsers.map(u => u.id)

    // Get display names for room name
    const participantNames = uniqueUsers.map(u => u.display_name || u.hna.split('@')[0])
    const roomName = `Barter: ${participantNames.join(' ↔ ')}`

    // Create group chat
    await authStore.ensureToken()
    const response = await $fetch('/api/v1/matrix/create-group-chat', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`,
        'Content-Type': 'application/json'
      },
      body: {
        participant_account_ids: participantIds,
        room_name: roomName
      }
    })

    if (response.success && response.room_id) {
      // Navigate to chat with the created room
      navigateTo({
        path: localePath('/chat'),
        query: {
          room_id: response.room_id
        }
      })
    } else {
      toastStore.error($t('barter.errors.chat_failed'))
    }
  } catch (e: any) {
    console.error('Failed to create barter chat:', e)
    toastStore.error($t('barter.errors.chat_failed'))
  }
}

function goToMarketCategory(categorySlug: string) {
  navigateTo(localePath(`/market?category=${categorySlug}`))
}

// ESC key handler
function handleEscape(event) {
  if (event.key === 'Escape' && selectedItem.value) {
    selectedItem.value = null
  }
}

onMounted(async () => {
  if (!authStore.isAuthenticated) {
    navigateTo(localePath('/login') + '?redirect=' + encodeURIComponent(localePath('/barter')))
    return
  }
  fetchOpportunities()

  // Load translated category names
  try {
    const tree = await fetchCategoryTree()
    buildCategoryNames(tree)
  } catch (e) {
    // Fallback to English names from API
  }

  // Add ESC key listener
  window.addEventListener('keydown', handleEscape)
})

onUnmounted(() => {
  // Remove ESC key listener
  window.removeEventListener('keydown', handleEscape)
})
</script>
