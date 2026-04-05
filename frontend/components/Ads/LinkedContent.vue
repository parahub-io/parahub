<template>
  <div class="space-y-3">
    <!-- Currently linked content -->
    <div
      v-if="linkedItem || linkedEstablishment"
      class="flex items-center gap-3 p-3 rounded-xl border border-primary/30 bg-primary-100/50 dark:bg-primary-900/20"
    >
      <img
        v-if="linkedImage"
        :src="linkedImage"
        :alt="linkedTitle"
        class="w-12 h-12 rounded-lg object-cover flex-shrink-0"
      />
      <div v-else class="w-12 h-12 rounded-lg bg-neutral-200 dark:bg-neutral-700 flex items-center justify-center flex-shrink-0">
        <Package v-if="linkedItem" class="w-5 h-5 text-neutral-400" />
        <Building2 v-else class="w-5 h-5 text-neutral-400" />
      </div>
      <div class="flex-1 min-w-0">
        <p class="text-sm font-medium text-neutral-900 dark:text-neutral-100 truncate">{{ linkedTitle }}</p>
        <p class="text-xs text-neutral-500 dark:text-neutral-400">
          {{ linkedItem ? $t('ads.create_campaign.link_item') : $t('ads.create_campaign.link_establishment') }}
        </p>
      </div>
      <button type="button" @click="unlink" class="p-1.5 text-neutral-400 hover:text-red-500 transition-colors">
        <X class="w-4 h-4" />
      </button>
    </div>

    <!-- Picker tabs -->
    <div v-else class="space-y-3">
      <div class="flex gap-2">
        <button
          type="button"
          @click="activeTab = 'item'"
          :class="[
            'flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-colors',
            activeTab === 'item'
              ? 'bg-primary text-black'
              : 'text-neutral-500 dark:text-neutral-400 hover:bg-neutral-100 dark:hover:bg-neutral-800',
          ]"
        >
          <Package class="w-3.5 h-3.5" />
          {{ $t('ads.create_campaign.link_item') }}
        </button>
        <button
          type="button"
          @click="activeTab = 'establishment'"
          :class="[
            'flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-colors',
            activeTab === 'establishment'
              ? 'bg-primary text-black'
              : 'text-neutral-500 dark:text-neutral-400 hover:bg-neutral-100 dark:hover:bg-neutral-800',
          ]"
        >
          <Building2 class="w-3.5 h-3.5" />
          {{ $t('ads.create_campaign.link_establishment') }}
        </button>
      </div>

      <!-- Search -->
      <div class="relative">
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400" />
        <input
          v-model="searchQuery"
          type="text"
          :placeholder="activeTab === 'item' ? $t('ads.create_campaign.search_items') : $t('ads.create_campaign.search_establishments')"
          class="w-full pl-9 pr-3 py-2 text-sm border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 focus:ring-2 focus:ring-primary/40 focus:border-primary"
        />
      </div>

      <!-- Results -->
      <div v-if="loading" class="flex justify-center py-4">
        <Loader2 class="w-5 h-5 animate-spin text-neutral-400" />
      </div>
      <div v-else-if="results.length > 0" class="max-h-[200px] overflow-y-auto space-y-1 rounded-lg border border-neutral-200 dark:border-neutral-700">
        <button
          v-for="item in results"
          :key="item.id"
          type="button"
          @click="selectItem(item)"
          class="w-full flex items-center gap-3 px-3 py-2 text-left hover:bg-primary-100 dark:hover:bg-primary-900/30 transition-colors"
        >
          <img
            v-if="item.image_url"
            :src="item.image_url"
            :alt="item.title || item.name"
            class="w-10 h-10 rounded-lg object-cover flex-shrink-0"
          />
          <div v-else class="w-10 h-10 rounded-lg bg-neutral-100 dark:bg-neutral-800 flex items-center justify-center flex-shrink-0">
            <Package v-if="activeTab === 'item'" class="w-4 h-4 text-neutral-400" />
            <Building2 v-else class="w-4 h-4 text-neutral-400" />
          </div>
          <div class="flex-1 min-w-0">
            <p class="text-sm font-medium text-neutral-900 dark:text-neutral-100 truncate">{{ item.title || item.name }}</p>
            <p v-if="item.price_label" class="text-xs text-neutral-500 dark:text-neutral-400">{{ item.price_label }}</p>
            <p v-if="item.category_name" class="text-xs text-neutral-500 dark:text-neutral-400">{{ item.category_name }}</p>
          </div>
        </button>
      </div>
      <p v-else-if="searchQuery.length >= 2" class="text-xs text-neutral-400 text-center py-3">
        {{ activeTab === 'item' ? $t('ads.create_campaign.no_items_found') : $t('ads.create_campaign.no_establishments_found') }}
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Package, Building2, Search, X, Loader2 } from 'lucide-vue-next'

interface LinkedResult {
  id: string
  title?: string
  name?: string
  image_url?: string | null
  price_label?: string
  category_name?: string
  pricing_options?: any[]
  slug?: string
  logo_url?: string
}

const props = defineProps<{
  linkedItemId?: string | null
  linkedEstablishmentId?: string | null
}>()

const emit = defineEmits<{
  'update:linkedItemId': [id: string | null]
  'update:linkedEstablishmentId': [id: string | null]
  'linked-item': [item: LinkedResult | null]
  'linked-establishment': [est: LinkedResult | null]
}>()

const activeTab = ref<'item' | 'establishment'>('item')
const searchQuery = ref('')
const results = ref<LinkedResult[]>([])
const loading = ref(false)
const linkedItem = ref<LinkedResult | null>(null)
const linkedEstablishment = ref<LinkedResult | null>(null)

const linkedTitle = computed(() =>
  linkedItem.value?.title || linkedEstablishment.value?.name || ''
)
const linkedImage = computed(() =>
  linkedItem.value?.image_url || linkedEstablishment.value?.logo_url || null
)

let searchTimer: ReturnType<typeof setTimeout> | null = null

watch(searchQuery, (q) => {
  if (searchTimer) clearTimeout(searchTimer)
  if (q.length < 2) {
    results.value = []
    return
  }
  searchTimer = setTimeout(() => doSearch(q), 300)
})

watch(activeTab, () => {
  searchQuery.value = ''
  results.value = []
})

async function doSearch(q: string) {
  loading.value = true
  try {
    const authStore = useAuthStore()
    await authStore.ensureToken()
    const headers = {
      'Authorization': `Bearer ${authStore.token}`,
    }

    if (activeTab.value === 'item') {
      const res = await $fetch<any>('/api/v1/items/', {
        credentials: 'include',
        headers,
        params: { q, mine: true, page_size: 10 },
      })
      const items = res.items || res || []
      results.value = items.map((it: any) => ({
        id: it.id,
        title: it.title,
        image_url: it.images?.[0]?.image_url || it.image_url || null,
        price_label: formatPrice(it.pricing_options),
      }))
    } else {
      const res = await $fetch<any>('/api/v1/directory/', {
        credentials: 'include',
        headers,
        params: { q, page_size: 10 },
      })
      const items = res.items || res || []
      results.value = items.map((it: any) => ({
        id: it.id,
        name: it.name,
        slug: it.slug,
        image_url: it.logo_url || null,
        logo_url: it.logo_url || null,
        category_name: it.category_name || it.organization_type || null,
      }))
    }
  } catch (err) {
    console.error('Search failed:', err)
    results.value = []
  } finally {
    loading.value = false
  }
}

function formatPrice(options: any[]): string {
  if (!options?.length) return ''
  const first = options[0]
  if (first.type === 'free') return 'Free'
  return first.amount ? `${first.amount} ${first.currency || ''}`.trim() : ''
}

function selectItem(item: LinkedResult) {
  if (activeTab.value === 'item') {
    linkedItem.value = item
    linkedEstablishment.value = null
    emit('update:linkedItemId', item.id)
    emit('update:linkedEstablishmentId', null)
    emit('linked-item', item)
  } else {
    linkedEstablishment.value = item
    linkedItem.value = null
    emit('update:linkedEstablishmentId', item.id)
    emit('update:linkedItemId', null)
    emit('linked-establishment', item)
  }
  searchQuery.value = ''
  results.value = []
}

function unlink() {
  linkedItem.value = null
  linkedEstablishment.value = null
  emit('update:linkedItemId', null)
  emit('update:linkedEstablishmentId', null)
  emit('linked-item', null)
  emit('linked-establishment', null)
}
</script>
