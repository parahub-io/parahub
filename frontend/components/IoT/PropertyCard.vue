<template>
  <div class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4 transition-shadow hover:shadow-md">
    <!-- Header -->
    <div class="flex justify-between items-start mb-3">
      <div class="flex-1 min-w-0">
        <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 truncate">{{ prop.name }}</h3>
        <p v-if="prop.address" class="text-xs text-neutral-500 dark:text-neutral-400 truncate">{{ prop.address }}</p>
      </div>

      <!-- Type badge -->
      <span class="shrink-0 ml-2 inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium"
            :class="typeBadgeClass">
        <component :is="typeIcon" class="w-3.5 h-3.5" />
        {{ $t(`property.types.${prop.property_type}`) }}
      </span>
    </div>

    <!-- Stats row -->
    <div class="flex items-center gap-4 text-sm text-neutral-600 dark:text-neutral-400 mb-3">
      <div v-if="prop.device_count > 0" class="flex items-center gap-1">
        <Cpu class="w-4 h-4" />
        <span>{{ prop.device_count }} {{ $t('property.devices') }}</span>
      </div>
      <div v-if="prop.ha_home_count > 0" class="flex items-center gap-1">
        <Home class="w-4 h-4" />
        <span>{{ prop.ha_home_count }} HA</span>
      </div>
      <div v-if="prop.world_object_id" class="flex items-center gap-1">
        <Building2 class="w-4 h-4" />
        <span>{{ $t('property.linked_building') }}</span>
      </div>
    </div>

    <!-- Actions -->
    <div class="flex items-center gap-2">
      <button @click="$emit('edit', prop)" class="btn-outline btn-sm gap-1">
        <Pencil class="w-3.5 h-3.5" />
        {{ $t('property.edit') }}
      </button>

      <!-- Dropdown -->
      <div class="relative ml-auto" ref="menuRef">
        <button @click="menuOpen = !menuOpen" class="p-1.5 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-700 text-neutral-500 transition-colors">
          <MoreVertical class="w-4 h-4" />
        </button>
        <div v-if="menuOpen" class="absolute right-0 mt-1 w-36 bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg shadow-lg z-10 py-1">
          <button @click="menuOpen = false; $emit('delete', prop)" class="w-full text-left px-3 py-1.5 text-sm hover:bg-red-50 dark:hover:bg-red-900/20 text-red-600 dark:text-red-400">
            {{ $t('property.delete') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Cpu, Home, Building2, Pencil, MoreVertical, House, Building, Landmark, Trees, Warehouse, MapPin } from 'lucide-vue-next'
import type { Property } from '~/stores/property'

const props = defineProps<{
  prop: Property
}>()

defineEmits<{
  edit: [prop: Property]
  delete: [prop: Property]
}>()

const menuOpen = ref(false)
const menuRef = ref<HTMLElement>()

const typeIcon = computed(() => {
  const map: Record<string, any> = {
    house: House, apartment: Building, office: Landmark,
    dacha: Trees, garage: Warehouse, land: MapPin, other: MapPin,
  }
  return map[props.prop.property_type] || MapPin
})

const typeBadgeClass = computed(() => {
  const map: Record<string, string> = {
    house: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
    apartment: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
    office: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
    dacha: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
    garage: 'bg-neutral-100 text-neutral-700 dark:bg-neutral-700 dark:text-neutral-300',
    land: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
  }
  return map[props.prop.property_type] || 'bg-neutral-100 text-neutral-700 dark:bg-neutral-700 dark:text-neutral-300'
})

// Close menu on outside click
if (import.meta.client) {
  const handler = (e: MouseEvent) => {
    if (menuRef.value && !menuRef.value.contains(e.target as Node)) menuOpen.value = false
  }
  onMounted(() => document.addEventListener('click', handler))
  onUnmounted(() => document.removeEventListener('click', handler))
}
</script>
