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
import { PLACE_SQUARE_SIZE } from '~/composables/useMapToggleableLayer'
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

// Snapshot marker glyphs — lucide 24×24 path data mirroring typeIcon above
// (rect/circle primitives converted to path arcs for Path2D stroking)
const TYPE_GLYPHS: Record<string, string[]> = {
  house: ['M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8', 'M3 10a2 2 0 0 1 .709-1.528l7-6a2 2 0 0 1 2.582 0l7 6A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z'],
  apartment: ['M12 10h.01', 'M12 14h.01', 'M12 6h.01', 'M16 10h.01', 'M16 14h.01', 'M16 6h.01', 'M8 10h.01', 'M8 14h.01', 'M8 6h.01', 'M9 22v-3a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v3', 'M6 2h12a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z'],
  office: ['M10 18v-7', 'M11.12 2.198a2 2 0 0 1 1.76.006l7.866 3.847c.476.233.31.949-.22.949H3.474c-.53 0-.695-.716-.22-.949z', 'M14 18v-7', 'M18 18v-7', 'M3 22h18', 'M6 18v-7'],
  dacha: ['M10 10v.2A3 3 0 0 1 8.9 16H5a3 3 0 0 1-1-5.8V10a3 3 0 0 1 6 0Z', 'M7 16v6', 'M13 19v3', 'M12 19h8.3a1 1 0 0 0 .7-1.7L18 14h.3a1 1 0 0 0 .7-1.7L16 9h.2a1 1 0 0 0 .8-1.7L13 3l-1.4 1.5'],
  garage: ['M18 21V10a1 1 0 0 0-1-1H7a1 1 0 0 0-1 1v11', 'M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V8a2 2 0 0 1 1.132-1.803l7.95-3.974a2 2 0 0 1 1.837 0l7.948 3.974A2 2 0 0 1 22 8z', 'M6 13h12', 'M6 17h12'],
  land: ['M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0', 'M15 10a3 3 0 1 1-6 0a3 3 0 1 1 6 0'],
}
TYPE_GLYPHS.other = TYPE_GLYPHS.land

const typeGlyph = computed(() => TYPE_GLYPHS[props.property.property_type] || TYPE_GLYPHS.land)

// Map snapshot (shared single MapLibre instance across all cards)
const { capture } = useMapSnapshots()
const snapshotUrl = ref<string | null>(null)

onMounted(async () => {
  if (props.property.latitude == null || props.property.longitude == null) return
  snapshotUrl.value = await capture(props.property.latitude, props.property.longitude)
})
</script>

