<template>
  <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
    <div>
      <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
        {{ $t('civic.residency.country') }}
      </label>
      <select v-model="countryId" class="w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 px-3 py-2 text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent">
        <option value="">—</option>
        <option v-for="t in countries" :key="t.id" :value="t.id">{{ t.name }}</option>
      </select>
    </div>

    <div>
      <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
        {{ $t('civic.residency.municipality') }}
      </label>
      <select v-model="municipalityId" :disabled="!countryId || municipalities.length === 0"
              class="w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 px-3 py-2 text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent disabled:opacity-50">
        <option value="">—</option>
        <option v-for="t in municipalities" :key="t.id" :value="t.id">{{ t.name }}</option>
      </select>
    </div>

    <div>
      <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
        {{ $t('civic.residency.parish') }}
      </label>
      <select v-model="parishId" :disabled="!municipalityId || parishes.length === 0"
              class="w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 px-3 py-2 text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent disabled:opacity-50">
        <option value="">—</option>
        <option v-for="t in parishes" :key="t.id" :value="t.id">{{ t.name }}</option>
      </select>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'

// Cascading territory picker. modelValue = deepest selected territory ULID
// (parish > municipality > country). Optional initialChain preselects levels.
const props = defineProps<{
  modelValue?: string | null
  initialChain?: Array<{ id: string; level: string; code: string }>
}>()
const emit = defineEmits<{ 'update:modelValue': [id: string] }>()

const { t: $t } = useI18n()

const countries = ref<any[]>([])
const municipalities = ref<any[]>([])
const parishes = ref<any[]>([])
const countryId = ref('')
const municipalityId = ref('')
const parishId = ref('')
let initializing = false

const selectedId = computed(() => parishId.value || municipalityId.value || countryId.value)
watch(selectedId, (id) => emit('update:modelValue', id))

async function fetchTerritories(params: Record<string, string>) {
  try {
    return await $fetch<any[]>('/api/v1/geo/territories/', { query: { ...params, page_size: '200' } })
  } catch {
    return []
  }
}

watch(countryId, async (id, old) => {
  if (initializing || id === old) return
  municipalityId.value = ''
  parishId.value = ''
  municipalities.value = []
  parishes.value = []
  if (id) {
    const country = countries.value.find(t => t.id === id)
    if (country) municipalities.value = await fetchTerritories({ level: 'municipality', country: country.code })
  }
})

watch(municipalityId, async (id, old) => {
  if (initializing || id === old) return
  parishId.value = ''
  parishes.value = []
  if (id) parishes.value = await fetchTerritories({ level: 'parish', parent_id: id })
})

onMounted(async () => {
  countries.value = await fetchTerritories({ level: 'country' })
  const chain = props.initialChain || []
  if (chain.length) {
    initializing = true
    const byLevel: Record<string, any> = {}
    for (const t of chain) byLevel[t.level] = t
    if (byLevel.country) {
      countryId.value = byLevel.country.id
      municipalities.value = await fetchTerritories({ level: 'municipality', country: byLevel.country.code })
      if (byLevel.municipality) {
        municipalityId.value = byLevel.municipality.id
        parishes.value = await fetchTerritories({ level: 'parish', parent_id: byLevel.municipality.id })
        if (byLevel.parish) parishId.value = byLevel.parish.id
      }
    }
    initializing = false
  }
})
</script>
