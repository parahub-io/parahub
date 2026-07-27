<template>
  <div class="px-4 pt-2 space-y-4">
    <template v-if="vehicleData">
      <!-- Route badge with link -->
      <div class="flex items-center gap-2">
        <span v-if="vehicleData.route_color" class="inline-block w-4 h-4 rounded-full flex-shrink-0" :style="{ backgroundColor: `#${vehicleData.route_color}` }"></span>
        <NuxtLink
          v-if="routeLink"
          :to="routeLink"
          class="text-sm font-medium text-secondary-600 dark:text-secondary-400 hover:underline"
        >
          {{ vehicleData.route_name || vehicleData.route_id }}
        </NuxtLink>
        <span v-else class="text-sm font-medium text-neutral-700 dark:text-neutral-300">
          {{ vehicleData.route_name || vehicleData.route_id }}
        </span>
        <!-- Vehicle type badge -->
        <span class="px-1.5 py-0.5 text-xs rounded bg-neutral-100 dark:bg-neutral-800 text-neutral-500 dark:text-neutral-400">
          {{ vehicleTypeLabel }}
        </span>
      </div>

      <!-- Speed & Status -->
      <div class="flex items-center gap-3 flex-wrap">
        <div v-if="vehicleData.zombie" class="flex items-center gap-2 px-3 py-1.5 bg-neutral-100 dark:bg-neutral-800 rounded-full text-sm text-neutral-500 dark:text-neutral-400">
          <Pause :size="14" />
          {{ t('map.transit.stationary') }}
        </div>
        <div v-else-if="vehicleData.speed > 0" class="flex items-center gap-2 px-3 py-1.5 bg-secondary-50 dark:bg-secondary-900/30 rounded-full text-sm font-medium text-secondary-700 dark:text-secondary-300">
          <Gauge :size="14" />
          {{ Math.round(vehicleData.speed) }} {{ t('map.transit.kmh') }}
        </div>
        <div v-if="!vehicleData.zombie && vehicleData.eta > 0" class="flex items-center gap-2 px-3 py-1.5 bg-secondary-50 dark:bg-secondary-900/30 rounded-full text-sm text-secondary-700 dark:text-secondary-300">
          <Clock :size="14" />
          {{ Math.round(vehicleData.eta / 60) < 1 ? '< 1' : Math.round(vehicleData.eta / 60) }} {{ t('map.transit.min_to_next') }}
        </div>
        <!-- Camera-follow toggle — same grammar as the tracker panel's button -->
        <button
          @click="emit('toggle-follow')"
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium transition ml-auto"
          :class="following
            ? 'bg-secondary-50 dark:bg-secondary-900/30 text-secondary-700 dark:text-secondary-300'
            : 'border border-neutral-200 dark:border-neutral-700 text-neutral-600 dark:text-neutral-400 hover:border-neutral-300 dark:hover:border-neutral-600'"
        >
          <Crosshair :size="14" :class="{ 'animate-pulse': following }" />
          {{ following ? t('map.iot.following') : t('map.iot.recenter') }}
        </button>
      </div>

      <!-- Headsign -->
      <div v-if="vehicleData.headsign" class="flex items-center gap-2 text-sm text-neutral-600 dark:text-neutral-400">
        <ArrowRight :size="14" class="flex-shrink-0" />
        {{ vehicleData.headsign }}
      </div>

      <!-- Vehicle details -->
      <div class="space-y-0 text-sm">
        <!-- Vehicle ID -->
        <div v-if="vehicleData.vehicle_id" class="flex items-center justify-between py-1.5 border-b border-neutral-100 dark:border-neutral-800">
          <span class="text-neutral-500 dark:text-neutral-400">{{ t('map.transit.vehicle_id') }}</span>
          <span class="font-mono text-neutral-900 dark:text-neutral-100">{{ vehicleData.vehicle_id }}</span>
        </div>

        <!-- Status -->
        <div v-if="statusLabel" class="flex items-center justify-between py-1.5 border-b border-neutral-100 dark:border-neutral-800">
          <span class="text-neutral-500 dark:text-neutral-400">{{ t('map.transit.status') }}</span>
          <span class="text-neutral-900 dark:text-neutral-100">{{ statusLabel }}</span>
        </div>

        <!-- Direction -->
        <div v-if="vehicleData.direction_id != null" class="flex items-center justify-between py-1.5 border-b border-neutral-100 dark:border-neutral-800">
          <span class="text-neutral-500 dark:text-neutral-400">{{ t('map.transit.direction') }}</span>
          <span class="text-neutral-900 dark:text-neutral-100">{{ vehicleData.direction_id === 0 ? t('map.transit.outbound') : t('map.transit.inbound') }}</span>
        </div>

        <!-- Bearing — shown only when the feed gives a real heading (0°/north included) -->
        <div v-if="vehicleData.has_bearing" class="flex items-center justify-between py-1.5 border-b border-neutral-100 dark:border-neutral-800">
          <span class="text-neutral-500 dark:text-neutral-400">{{ t('map.transit.bearing') }}</span>
          <span class="text-neutral-900 dark:text-neutral-100">{{ Math.round(vehicleData.bearing) }}° {{ compassDir }}</span>
        </div>

        <!-- Last update -->
        <div v-if="lastUpdateText" class="flex items-center justify-between py-1.5 border-b border-neutral-100 dark:border-neutral-800">
          <span class="text-neutral-500 dark:text-neutral-400">{{ t('map.transit.last_update') }}</span>
          <span class="text-neutral-900 dark:text-neutral-100">{{ lastUpdateText }}</span>
        </div>

        <!-- Coordinates -->
        <div class="flex items-center justify-between py-1.5">
          <span class="text-neutral-500 dark:text-neutral-400">{{ t('map.transit.coordinates') }}</span>
          <span class="font-mono text-xs text-neutral-900 dark:text-neutral-100">{{ vehicleData.lngLat?.lat?.toFixed(5) }}, {{ vehicleData.lngLat?.lng?.toFixed(5) }}</span>
        </div>
      </div>

      <!-- Vehicle metadata (accessibility, propulsion, model) — fetched on demand -->
      <div v-if="hasMeta" class="space-y-2">
        <div v-if="meta.wheelchair_accessible || meta.bikes_allowed || propulsionLabel" class="flex flex-wrap gap-1.5">
          <span v-if="meta.wheelchair_accessible" class="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full bg-secondary-50 dark:bg-secondary-900/30 text-secondary-700 dark:text-secondary-300">
            <Accessibility :size="13" /> {{ t('map.transit.wheelchair') }}
          </span>
          <span v-if="meta.bikes_allowed" class="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full bg-secondary-50 dark:bg-secondary-900/30 text-secondary-700 dark:text-secondary-300">
            <Bike :size="13" /> {{ t('map.transit.bikes') }}
          </span>
          <span v-if="propulsionLabel" class="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-300">
            <component :is="propulsionIcon" :size="13" /> {{ propulsionLabel }}
          </span>
        </div>
        <div class="space-y-0 text-sm">
          <div v-if="modelText" class="flex items-center justify-between py-1.5 border-b border-neutral-100 dark:border-neutral-800">
            <span class="text-neutral-500 dark:text-neutral-400">{{ t('map.transit.model') }}</span>
            <span class="text-neutral-900 dark:text-neutral-100">{{ modelText }}</span>
          </div>
          <div v-if="meta.license_plate" class="flex items-center justify-between py-1.5 border-b border-neutral-100 dark:border-neutral-800">
            <span class="text-neutral-500 dark:text-neutral-400">{{ t('map.transit.plate') }}</span>
            <span class="font-mono text-neutral-900 dark:text-neutral-100">{{ meta.license_plate }}</span>
          </div>
          <div v-if="meta.owner" class="flex items-center justify-between py-1.5">
            <span class="text-neutral-500 dark:text-neutral-400">{{ t('map.transit.operator') }}</span>
            <span class="text-neutral-900 dark:text-neutral-100">{{ meta.owner }}</span>
          </div>
        </div>
      </div>

      <!-- Route page link -->
      <UiButton
        v-if="routeLink"
        variant="primary"
        :to="routeLink"
        class="w-full"
      >
        {{ t('map.transit.view_route') }}
      </UiButton>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Pause, Gauge, Clock, ArrowRight, Accessibility, Bike, Zap, Fuel, Leaf, Crosshair } from 'lucide-vue-next'

const localePath = useLocalePath()
const { t } = useI18n()

const props = defineProps<{
  vehicleData: any
  following?: boolean
}>()

const emit = defineEmits<{
  (e: 'toggle-follow'): void
}>()

// Static per-vehicle metadata (make/model/plate/accessibility/propulsion) —
// kept off the live WS payload, fetched on demand when a vehicle is selected.
const meta = ref<Record<string, any>>({})
const hasMeta = computed(() => Object.keys(meta.value).length > 0)

async function fetchMeta(vid?: string, routeId?: string, dsId?: string) {
  meta.value = {}
  if (!vid) return
  try {
    const params: Record<string, string> = { vehicle_id: vid }
    // Prefer the exact feed (ds_id) — a raw vehicle_id is not unique across
    // operators, so route_id is only a fallback when the feed id is unknown.
    if (dsId) params.ds_id = dsId
    else if (routeId) params.route_id = routeId
    const res = await $fetch<Record<string, any>>('/api/v1/geo/transit/vehicles/meta/', { params })
    meta.value = res || {}
  } catch {
    meta.value = {}
  }
}

// Watch the feed-namespaced uid, not the raw vehicle_id: clicking a Lisbon 2963
// then a Porto 2963 keeps vehicle_id constant and would skip the refetch.
watch(
  () => props.vehicleData?.uid || props.vehicleData?.vehicle_id,
  () => fetchMeta(props.vehicleData?.vehicle_id, props.vehicleData?.route_id, props.vehicleData?.ds_id),
  { immediate: true },
)

const modelText = computed(() => [meta.value.make, meta.value.model].filter(Boolean).join(' '))

// Normalize CM propulsion codes → a small labelled set (unknowns fall back to raw)
function normPropulsion(p: any): string {
  const s = String(p || '').toLowerCase()
  if (['electricity', 'electric'].includes(s)) return 'electricity'
  if (['cng', 'lpg', 'gas', 'natural_gas'].includes(s)) return 'gas'
  return s
}
const PROPULSION_ICON: Record<string, any> = {
  electricity: Zap, hybrid: Leaf, hydrogen: Leaf, diesel: Fuel, gas: Fuel,
}
const propulsionIcon = computed(() => PROPULSION_ICON[normPropulsion(meta.value.propulsion)] || Fuel)
const propulsionLabel = computed(() => {
  const s = normPropulsion(meta.value.propulsion)
  if (!s) return ''
  const known = ['electricity', 'diesel', 'hybrid', 'gas', 'hydrogen']
  return known.includes(s) ? t(`map.transit.propulsion_${s}`) : String(meta.value.propulsion)
})

const ROUTE_TYPE_LABELS: Record<number, string> = {
  0: 'Tram', 1: 'Metro', 2: 'Rail', 3: 'Bus',
  4: 'Ferry', 5: 'Cable car', 6: 'Gondola',
  7: 'Funicular', 11: 'Trolleybus', 12: 'Monorail',
}

const vehicleTypeLabel = computed(() => {
  const rt = props.vehicleData?.route_type
  return ROUTE_TYPE_LABELS[rt] ?? 'Bus'
})

const routeLink = computed(() => {
  const ps = props.vehicleData?.place_slug
  const rs = props.vehicleData?.route_slug
  if (ps && rs) return localePath(`/transit/route/${ps}/${rs}`)
  return null
})

const statusLabel = computed(() => {
  const st = props.vehicleData?.status
  if (!st) return null
  const map: Record<string, string> = {
    'IN_TRANSIT_TO': t('map.transit.in_transit'),
    'STOPPED_AT': t('map.transit.stopped'),
    'INCOMING_AT': t('map.transit.arriving'),
  }
  return map[st] || null
})

const compassDir = computed(() => {
  const b = props.vehicleData?.bearing
  if (b == null) return ''
  const dirs = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
  return dirs[Math.round(b / 45) % 8]
})

const lastUpdateText = computed(() => {
  const ts = props.vehicleData?.timestamp
  if (!ts) return null
  const d = new Date(ts * 1000)
  const diff = Math.floor((Date.now() - d.getTime()) / 1000)
  if (diff < 10) return t('map.transit.just_now')
  if (diff < 60) return `${diff}s`
  if (diff < 3600) return `${Math.floor(diff / 60)}m`
  // Show absolute time if stale
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
})
</script>
