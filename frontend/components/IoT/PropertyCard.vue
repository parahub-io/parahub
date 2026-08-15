<template>
  <NuxtLink
    :to="localePath(`/iot/${property.id}`)"
    class="group flex flex-col bg-neutral-100 dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 hover:border-primary transition-colors"
  >
    <!-- Map viewport — every property has coordinates (location is required) -->
    <div class="relative shrink-0 m-1 mb-0 aspect-[1.618/1] rounded overflow-hidden bg-neutral-200 dark:bg-neutral-700">
      <img v-if="snapshotUrl" :src="snapshotUrl" :alt="property.name" class="w-full h-full object-cover" loading="lazy" />
      <div v-else class="w-full h-full animate-pulse" />
      <IoTSnapshotMarker shape="square" :size="PLACE_SQUARE_SIZE" fill="#4E4EC8" :glyph="typeGlyph" />
      <!-- Top scrim keeps the HUD legible over map tiles -->
      <div class="absolute inset-x-0 top-0 h-9 bg-gradient-to-b from-black/55 to-transparent pointer-events-none" />
      <span class="absolute top-2 left-3 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wider text-white/80">
        <component :is="typeIcon" class="w-3.5 h-3.5" aria-hidden="true" />
        {{ $t(`property.types.${property.property_type}`) }}
      </span>
    </div>

    <div class="p-4 pt-2.5 flex-1 flex flex-col">
      <div class="flex items-start justify-between gap-2">
        <h3 class="text-base font-semibold text-neutral-900 dark:text-neutral-100 truncate">{{ property.name }}</h3>
        <ChevronRight class="w-4 h-4 mt-1 shrink-0 text-neutral-400 group-hover:text-secondary transition-colors" aria-hidden="true" />
      </div>
      <p v-if="property.address" class="text-sm text-neutral-500 dark:text-neutral-400 line-clamp-1 mt-0.5">{{ property.address }}</p>

      <!-- Counts -->
      <div class="flex flex-wrap gap-3 mt-2.5 text-xs text-neutral-500 dark:text-neutral-400">
        <span v-if="property.device_count" class="flex items-center gap-1">
          <Cpu class="w-3.5 h-3.5" aria-hidden="true" /> {{ property.device_count }} {{ $t('property.devices') }}
        </span>
        <span v-if="property.ha_entity_count" class="flex items-center gap-1">
          <Home class="w-3.5 h-3.5" aria-hidden="true" /> {{ property.ha_entity_count }} {{ $t('property.entities') }}
        </span>
        <span v-if="property.mesh_count" class="flex items-center gap-1">
          <Radio class="w-3.5 h-3.5" aria-hidden="true" /> {{ property.mesh_count }} {{ $t('property.mesh_label') }}
        </span>
        <span v-if="property.energy_producer_count" class="flex items-center gap-1">
          <Zap class="w-3.5 h-3.5 text-green-500" aria-hidden="true" /> {{ $t('property.producer') }}
        </span>
        <span v-if="property.energy_consumer_count" class="flex items-center gap-1">
          <Zap class="w-3.5 h-3.5 text-sky-500" aria-hidden="true" /> {{ $t('property.consumer') }}
        </span>
      </div>
    </div>
  </NuxtLink>
</template>

<script setup lang="ts">
import { ChevronRight, Cpu, Home, Radio, Zap, House, Building, Landmark, Trees, Warehouse, MapPin } from 'lucide-vue-next'
import { PLACE_SQUARE_SIZE, PROPERTY_TYPE_GLYPHS } from '~/composables/useMapToggleableLayer'
import type { Property } from '~/stores/property'

const props = defineProps<{ property: Property }>()

const localePath = useLocalePath()

const typeIcon = computed(() => {
  const map: Record<string, any> = {
    house: House, apartment: Building, office: Landmark,
    dacha: Trees, garage: Warehouse, land: MapPin, other: MapPin,
  }
  return map[props.property.property_type] || MapPin
})

const typeGlyph = computed(() => PROPERTY_TYPE_GLYPHS[props.property.property_type] || PROPERTY_TYPE_GLYPHS.land)

// Map snapshot (shared single MapLibre instance across all cards)
const { capture } = useMapSnapshots()
const snapshotUrl = ref<string | null>(null)

onMounted(async () => {
  if (props.property.latitude == null || props.property.longitude == null) return
  snapshotUrl.value = await capture(props.property.latitude, props.property.longitude)
})
</script>

