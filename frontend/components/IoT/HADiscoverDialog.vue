<template>
  <div v-if="show" class="fixed inset-0 z-50 flex items-center justify-center p-4">
    <!-- Backdrop -->
    <div class="absolute inset-0 bg-black/50" @click="$emit('close')" />

    <!-- Dialog -->
    <div class="relative bg-white dark:bg-neutral-800 rounded-xl shadow-xl max-w-2xl w-full max-h-[80vh] flex flex-col">
      <!-- Header -->
      <div class="flex items-center justify-between px-6 py-4 border-b border-neutral-200 dark:border-neutral-700">
        <div>
          <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100">{{ $t('ha.discover_title') }}</h3>
          <p class="text-sm text-neutral-500">{{ home.name }} — {{ entities.length }} {{ $t('ha.entities_found') }}</p>
        </div>
        <button @click="$emit('close')" class="p-1.5 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-700 text-neutral-500">
          <X class="w-5 h-5" />
        </button>
      </div>

      <!-- Search & Filter -->
      <div class="px-6 py-3 border-b border-neutral-200 dark:border-neutral-700 flex items-center gap-3">
        <div class="relative flex-1">
          <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400" />
          <input v-model="search" type="text" :placeholder="$t('ha.search_entities')"
                 class="input-base w-full pl-9 text-sm" />
        </div>
        <select v-model="domainFilter" class="input-base text-sm py-1.5 px-2">
          <option value="">{{ $t('ha.all_domains') }}</option>
          <option v-for="d in domains" :key="d" :value="d">{{ d }} ({{ domainCounts[d] }})</option>
        </select>
      </div>

      <!-- Entity list -->
      <div class="flex-1 overflow-y-auto px-6 py-3 space-y-1">
        <div v-if="loading" class="text-center text-neutral-500 py-8">
          <Loader2 class="w-6 h-6 animate-spin mx-auto mb-2" />
          {{ $t('ha.discovering') }}
        </div>

        <label v-for="entity in filteredEntities" :key="entity.entity_id"
               class="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-700/50 cursor-pointer transition-colors"
               :class="{ 'opacity-50': entity.already_imported }">
          <input type="checkbox" :value="entity.entity_id" v-model="selected"
                 :disabled="entity.already_imported"
                 class="rounded border-neutral-300 text-primary focus:ring-primary" />
          <div class="flex-1 min-w-0">
            <div class="text-sm font-medium text-neutral-900 dark:text-neutral-100 truncate">{{ entity.friendly_name }}</div>
            <div class="text-xs text-neutral-500">{{ entity.entity_id }} · {{ entity.state }}</div>
          </div>
          <span class="text-xs px-2 py-0.5 rounded-full shrink-0"
                :class="entity.is_controllable
                  ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300'
                  : 'bg-neutral-100 text-neutral-600 dark:bg-neutral-700 dark:text-neutral-400'">
            {{ entity.domain }}
          </span>
          <span v-if="entity.already_imported" class="text-xs text-green-600 dark:text-green-400 shrink-0">
            {{ $t('ha.imported') }}
          </span>
        </label>

        <p v-if="!loading && filteredEntities.length === 0" class="text-center text-neutral-500 py-8">
          {{ $t('ha.no_entities') }}
        </p>
      </div>

      <!-- Footer -->
      <div class="px-6 py-4 border-t border-neutral-200 dark:border-neutral-700 flex items-center justify-between">
        <span class="text-sm text-neutral-500">{{ selected.length }} {{ $t('ha.selected') }}</span>
        <div class="flex items-center gap-3">
          <button @click="$emit('close')" class="btn-outline btn-sm">{{ $t('ha.cancel') }}</button>
          <button @click="importSelected" :disabled="selected.length === 0 || importing" class="btn-primary btn-sm gap-1">
            <Loader2 v-if="importing" class="w-3.5 h-3.5 animate-spin" />
            <Download v-else class="w-3.5 h-3.5" />
            {{ $t('ha.import') }} ({{ selected.length }})
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { X, Search, Loader2, Download } from 'lucide-vue-next'
import type { HAHome, HAEntityDiscover } from '~/stores/ha'

const props = defineProps<{
  show: boolean
  home: HAHome
}>()

const emit = defineEmits<{
  close: []
  imported: [count: number]
}>()

const haStore = useHAStore()
const { t } = useI18n()

const entities = ref<HAEntityDiscover[]>([])
const loading = ref(false)
const importing = ref(false)
const search = ref('')
const domainFilter = ref('')
const selected = ref<string[]>([])

const domains = computed(() => {
  const set = new Set(entities.value.map(e => e.domain))
  return [...set].sort()
})

const domainCounts = computed(() => {
  const counts: Record<string, number> = {}
  for (const e of entities.value) {
    counts[e.domain] = (counts[e.domain] || 0) + 1
  }
  return counts
})

const filteredEntities = computed(() => {
  let list = entities.value
  if (domainFilter.value) list = list.filter(e => e.domain === domainFilter.value)
  if (search.value) {
    const q = search.value.toLowerCase()
    list = list.filter(e =>
      e.friendly_name.toLowerCase().includes(q) ||
      e.entity_id.toLowerCase().includes(q)
    )
  }
  return list
})

watch(() => props.show, async (val) => {
  if (val) {
    loading.value = true
    selected.value = []
    search.value = ''
    domainFilter.value = ''
    try {
      entities.value = await haStore.discoverEntities(props.home.id)
    } catch (e: any) {
      entities.value = []
    } finally {
      loading.value = false
    }
  }
})

async function importSelected() {
  importing.value = true
  try {
    const result = await haStore.importEntities(props.home.id, selected.value)
    emit('imported', result.imported)
    emit('close')
  } catch (e: any) {
    // Error handled by store
  } finally {
    importing.value = false
  }
}
</script>
