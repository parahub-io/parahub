<template>
  <div>
    <!-- Loading -->
    <div v-if="loading" class="text-center py-12" role="status" aria-live="polite">
      <div class="inline-block animate-spin rounded-full h-12 w-12 border-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-white" aria-hidden="true"></div>
      <p class="mt-4 text-neutral-600 dark:text-neutral-400">{{ $t('barter.loading') }}</p>
    </div>

    <!-- Error -->
    <UiAlert v-else-if="error" variant="error">{{ error }}</UiAlert>

    <template v-else>
      <!-- Barter profile: offers · requests · chains -->
      <div class="card p-4 mb-6">
        <div class="flex flex-wrap gap-x-10 gap-y-3">
          <div>
            <div class="text-xs uppercase tracking-wide text-neutral-500 dark:text-neutral-400">{{ $t('barter.diagnosis.stat_offers') }}</div>
            <div class="text-2xl font-bold text-neutral-900 dark:text-neutral-100">{{ offerItems.length }}</div>
          </div>
          <div>
            <div class="text-xs uppercase tracking-wide text-neutral-500 dark:text-neutral-400">{{ $t('barter.diagnosis.stat_requests') }}</div>
            <div class="text-2xl font-bold text-neutral-900 dark:text-neutral-100">{{ requestItems.length }}</div>
          </div>
          <div>
            <div class="text-xs uppercase tracking-wide text-neutral-500 dark:text-neutral-400">{{ $t('barter.diagnosis.stat_chains') }}</div>
            <div class="text-2xl font-bold" :class="chainsCount > 0 ? 'text-success-600 dark:text-success-400' : 'text-neutral-900 dark:text-neutral-100'">{{ chainsCount }}</div>
          </div>
        </div>
      </div>

      <!-- Barter chains list -->
      <div v-if="chainsCount > 0" class="space-y-6">
        <div
          v-for="(chain, idx) in opportunities.chains"
          :key="idx"
          class="card p-6"
        >
          <!-- Chain header -->
          <div class="mb-4">
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
                  :to="localePath(`/u/${user.hna?.split('@')[0] || user.id}`)"
                  class="px-3 py-2 bg-neutral-100 dark:bg-neutral-700 rounded-lg text-sm font-medium whitespace-nowrap hover:bg-primary/10 transition-colors"
                >
                  {{ user.display_name || user.hna.split('@')[0] }}
                </NuxtLink>
                <ArrowRight v-if="userIdx < chain.users.length - 1" class="w-4 h-4 text-neutral-400 flex-shrink-0" />
              </div>
            </template>
          </div>

          <!-- Exchange details (2-way) -->
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
                      <div v-if="item.category_path && item.category_path.length" class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
                        <span v-for="(cat, i) in item.category_path" :key="cat.id">
                          <button @click.stop="goToMarketCategory(cat.slug)" class="hover:text-secondary hover:underline">
                            {{ getCategoryName(cat.slug, cat.name) }}
                          </button>
                          <span v-if="i < item.category_path.length - 1"> / </span>
                        </span>
                      </div>
                      <div v-if="item.pricing_options && item.pricing_options.length > 0" class="text-xs mt-1">
                        <div v-for="(opt, i) in item.pricing_options.slice(0, 2)" :key="i" class="font-semibold text-neutral-900 dark:text-neutral-100">
                          {{ formatPricingOption(opt, { withNote: false }) }}
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
                      <div v-if="item.category_path && item.category_path.length" class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
                        <span v-for="(cat, i) in item.category_path" :key="cat.id">
                          <button @click.stop="goToMarketCategory(cat.slug)" class="hover:text-secondary hover:underline">
                            {{ getCategoryName(cat.slug, cat.name) }}
                          </button>
                          <span v-if="i < item.category_path.length - 1"> / </span>
                        </span>
                      </div>
                      <div v-if="item.pricing_options && item.pricing_options.length > 0" class="text-xs mt-1">
                        <div v-for="(opt, i) in item.pricing_options.slice(0, 2)" :key="i" class="font-semibold text-neutral-900 dark:text-neutral-100">
                          {{ formatPricingOption(opt, { withNote: false }) }}
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
                <NuxtLink :to="localePath(`/u/${getUserSlug(swap.from_user)}`)" class="hover:text-secondary">
                  {{ getUserName(swap.from_user) }}
                </NuxtLink>
                →
                <NuxtLink :to="localePath(`/u/${getUserSlug(swap.to_user)}`)" class="hover:text-secondary">
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
                      <div v-if="item.category_path && item.category_path.length" class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
                        <span v-for="(cat, i) in item.category_path" :key="cat.id">
                          <button @click.stop="goToMarketCategory(cat.slug)" class="hover:text-secondary hover:underline">
                            {{ getCategoryName(cat.slug, cat.name) }}
                          </button>
                          <span v-if="i < item.category_path.length - 1"> / </span>
                        </span>
                      </div>
                      <div v-if="item.pricing_options && item.pricing_options.length > 0" class="text-xs mt-1">
                        <div v-for="(opt, i) in item.pricing_options.slice(0, 2)" :key="i" class="font-semibold text-neutral-900 dark:text-neutral-100">
                          {{ formatPricingOption(opt, { withNote: false }) }}
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

      <!-- No chains yet — diagnosis -->
      <div v-else class="space-y-4">
        <UiAlert variant="info" :icon="RefreshCw">{{ $t('barter.diagnosis.explainer') }}</UiAlert>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <!-- What you offer → who's looking -->
          <div class="card p-4 flex flex-col">
            <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-3 flex items-center gap-2">
              <Package class="w-4 h-4 text-success-600 dark:text-success-400" />
              {{ $t('barter.diagnosis.your_offers') }}
              <span class="text-neutral-400 font-normal">{{ offerItems.length }}</span>
            </h3>
            <ul v-if="offerItems.length" class="divide-y divide-neutral-200 dark:divide-neutral-700">
              <li v-for="item in offerItems" :key="item.id" class="flex items-center justify-between gap-3 py-2">
                <div class="min-w-0">
                  <div class="font-medium text-sm text-neutral-900 dark:text-neutral-100 truncate">{{ item.title }}</div>
                  <div class="text-xs text-neutral-500 dark:text-neutral-400 truncate">{{ itemCategory(item) }}</div>
                </div>
                <span v-if="item.demand_count" class="shrink-0 inline-flex items-center gap-1 text-xs font-medium text-secondary dark:text-secondary-400">
                  <Search class="w-3.5 h-3.5" /> {{ $t('barter.diagnosis.seekers', item.demand_count, { n: item.demand_count }) }}
                </span>
                <span v-else class="shrink-0 text-xs text-neutral-400 dark:text-neutral-500">{{ $t('barter.diagnosis.no_seekers') }}</span>
              </li>
            </ul>
            <p v-else class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('barter.diagnosis.no_offers_hint') }}</p>
            <UiButton variant="outline" size="sm" :icon="Plus" class="mt-3 w-full" :to="createLink('CREDIT')">
              {{ $t('barter.diagnosis.add_offer') }}
            </UiButton>
          </div>

          <!-- What you're looking for → who offers it -->
          <div class="card p-4 flex flex-col">
            <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-3 flex items-center gap-2">
              <Search class="w-4 h-4 text-secondary dark:text-secondary-400" />
              {{ $t('barter.diagnosis.your_requests') }}
              <span class="text-neutral-400 font-normal">{{ requestItems.length }}</span>
            </h3>
            <ul v-if="requestItems.length" class="divide-y divide-neutral-200 dark:divide-neutral-700">
              <li v-for="item in requestItems" :key="item.id" class="flex items-center justify-between gap-3 py-2">
                <div class="min-w-0">
                  <div class="font-medium text-sm text-neutral-900 dark:text-neutral-100 truncate">{{ item.title }}</div>
                  <div class="text-xs text-neutral-500 dark:text-neutral-400 truncate">{{ itemCategory(item) }}</div>
                </div>
                <span v-if="item.demand_count" class="shrink-0 inline-flex items-center gap-1 text-xs font-medium text-success-600 dark:text-success-400">
                  <Package class="w-3.5 h-3.5" /> {{ $t('barter.diagnosis.offerers', item.demand_count, { n: item.demand_count }) }}
                </span>
                <span v-else class="shrink-0 text-xs text-neutral-400 dark:text-neutral-500">{{ $t('barter.diagnosis.no_offerers') }}</span>
              </li>
            </ul>
            <p v-else class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('barter.diagnosis.no_requests_hint') }}</p>
            <UiButton variant="primary" size="sm" :icon="Plus" class="mt-3 w-full" :to="createLink('DEBIT')">
              {{ $t('barter.diagnosis.add_request') }}
            </UiButton>
          </div>
        </div>
      </div>
    </template>

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
              <div v-if="selectedItem.images && selectedItem.images.length > 0" class="mb-4">
                <div class="w-full aspect-video bg-neutral-200 dark:bg-neutral-700 rounded-lg overflow-hidden">
                  <img :src="selectedItem.images[0].url" :alt="selectedItem.title" class="w-full h-full object-cover">
                </div>
              </div>

              <div class="flex items-start justify-between mb-4">
                <div class="flex flex-wrap items-center gap-2">
                  <MarketListingType :item-type="selectedItem.item_type" />
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
                  <div v-for="(opt, i) in selectedItem.pricing_options" :key="i" class="font-semibold text-neutral-900 dark:text-neutral-100">
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
import { ArrowRight, ArrowRightLeft, Package, Plus, Search, RefreshCw, X } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'
import { useToastStore } from '~/stores/toast'

const authStore = useAuthStore()
const toastStore = useToastStore()
const localePath = useLocalePath()
const { t: $t } = useI18n()
const { fetchCategoryTree } = useCategories()
const { formatPricingOption } = usePricingFormat()

interface BarterItem {
  id: string
  title: string
  image?: string
  category_path?: { id: string; name: string; slug: string }[]
  pricing_options?: any[]
}

interface BarterSwap {
  from_user: string
  to_user: string
  offered_items: BarterItem[]
  wanted_items: BarterItem[]
  category_id: string
}

interface BarterChain {
  users: { id: string; hna: string; display_name: string }[]
  swaps: BarterSwap[]
}

interface BarterOpportunities {
  user_id: string
  chains_count: number
  chains: BarterChain[]
}

const opportunities = ref<BarterOpportunities | null>(null)
const myItems = ref<any[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const selectedItem = ref<any>(null)
const myProfileId = ref<string | null>(null)

// Category slug -> translated name
const categoryNames = ref(new Map<string, string>())

const offerItems = computed(() => myItems.value.filter(i => i.item_type === 'CREDIT'))
const requestItems = computed(() => myItems.value.filter(i => i.item_type === 'DEBIT'))
const chainsCount = computed(() => opportunities.value?.chains_count || 0)

function buildCategoryNames(categories: any[]) {
  for (const cat of categories) {
    categoryNames.value.set(cat.slug, cat.name)
    if (cat.children?.length) buildCategoryNames(cat.children)
  }
}

function getCategoryName(slug: string, fallback: string) {
  return categoryNames.value.get(slug) || fallback
}

// Leaf category label for a market item row
function itemCategory(item: any): string {
  const leaf = item.category_path?.[item.category_path.length - 1]
  if (leaf) return getCategoryName(leaf.slug, leaf.name)
  return item.category_name || ''
}

// Create form pre-set to offer (CREDIT) or request (DEBIT)
function createLink(type: 'CREDIT' | 'DEBIT') {
  return localePath({ path: '/market/create', query: { type } })
}

async function fetchAll() {
  loading.value = true
  error.value = null

  try {
    await authStore.ensureToken()
    const headers = { Authorization: `Bearer ${authStore.token}` }

    let profileId = authStore.profile?.id
    if (!profileId) {
      const me: any = await $fetch('/api/v1/profiles/me/', { credentials: 'include', headers })
      profileId = me?.id
    }
    myProfileId.value = profileId || null

    const [opps, items] = await Promise.all([
      $fetch<BarterOpportunities>('/api/v1/barter/opportunities', { credentials: 'include', headers }),
      profileId
        ? $fetch<any>(`/api/v1/items/?owner_id=${profileId}&is_active=true&page_size=1000`, { credentials: 'include', headers })
        : Promise.resolve({ items: [] }),
    ])

    opportunities.value = opps
    myItems.value = Array.isArray(items) ? items : (items.items || items.results || [])
  } catch (e: any) {
    console.error('Failed to fetch barter panel data:', e)
    error.value = $t('barter.errors.load_failed')
  } finally {
    loading.value = false
  }
}

function is2WayExchange(chain: BarterChain): boolean {
  return chain.users.length === 3
}

function getYourOffers(chain: BarterChain): BarterItem[] {
  if (!myProfileId.value) return []
  const yourSwap = chain.swaps.find(s => s.from_user === myProfileId.value)
  return yourSwap?.offered_items || []
}

function getPartnerOffers(chain: BarterChain): BarterItem[] {
  if (!myProfileId.value) return []
  const partnerSwap = chain.swaps.find(s => s.from_user !== myProfileId.value)
  return partnerSwap?.offered_items || []
}

function getUserName(userId: string): string {
  if (!opportunities.value) return userId.substring(0, 8) + '...'
  for (const chain of opportunities.value.chains) {
    const user = chain.users.find(u => u.id === userId)
    if (user) return user.display_name || user.hna?.split('@')[0] || userId.substring(0, 8) + '...'
  }
  return userId.substring(0, 8) + '...'
}

function getUserSlug(userId: string): string {
  if (!opportunities.value) return userId
  for (const chain of opportunities.value.chains) {
    const user = chain.users.find(u => u.id === userId)
    if (user) return user.hna?.split('@')[0] || user.id
  }
  return userId
}

async function openItemModal(itemId: string) {
  try {
    const response = await $fetch(`/api/v1/items/${itemId}`, { credentials: 'include' })
    selectedItem.value = response
  } catch (e: any) {
    console.error('Failed to fetch item:', e)
  }
}

async function initiateExchange(chain: BarterChain) {
  if (!authStore.isAuthenticated) {
    navigateTo(localePath('/login') + '?redirect=' + encodeURIComponent(localePath('/market/my')))
    return
  }

  try {
    const uniqueUsers = chain.users.slice(0, -1)
    const participantIds = uniqueUsers.map(u => u.id)
    const participantNames = uniqueUsers.map(u => u.display_name || u.hna.split('@')[0])
    const roomName = `Barter: ${participantNames.join(' ↔ ')}`

    await authStore.ensureToken()
    const response: any = await $fetch('/api/v1/matrix/create-group-chat', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`,
        'Content-Type': 'application/json'
      },
      body: { participant_account_ids: participantIds, room_name: roomName }
    })

    if (response.success && response.room_id) {
      navigateTo({ path: localePath('/chat'), query: { room_id: response.room_id } })
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

function handleEscape(event: KeyboardEvent) {
  if (event.key === 'Escape' && selectedItem.value) {
    selectedItem.value = null
  }
}

onMounted(async () => {
  fetchAll()
  try {
    const tree = await fetchCategoryTree()
    buildCategoryNames(tree)
  } catch (e) {
    // Fallback to English names from API
  }
  window.addEventListener('keydown', handleEscape)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleEscape)
})
</script>
