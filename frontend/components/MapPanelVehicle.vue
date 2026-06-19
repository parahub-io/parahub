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

      <!-- Route page link -->
      <NuxtLink
        v-if="routeLink"
        :to="routeLink"
        class="block w-full px-4 py-2.5 bg-primary hover:bg-primary-400 text-neutral-900 font-medium rounded-lg transition text-sm text-center"
      >
        {{ t('map.transit.view_route') }}
      </NuxtLink>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Pause, Gauge, Clock, ArrowRight } from 'lucide-vue-next'

const localePath = useLocalePath()
const { t } = useI18n()

const props = defineProps<{
  vehicleData: any
}>()

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
