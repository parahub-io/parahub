<template>
  <div class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-3 transition-shadow hover:shadow-sm">
    <div class="flex items-center justify-between gap-2">
      <!-- Icon + name -->
      <div class="flex items-center gap-2 min-w-0 flex-1">
        <component :is="domainIcon" class="w-5 h-5 shrink-0" :class="stateColor" />
        <div class="min-w-0">
          <div class="text-sm font-medium text-neutral-900 dark:text-neutral-100 truncate">{{ entity.friendly_name }}</div>
          <div class="text-xs text-neutral-500 truncate">{{ entity.entity_id }}</div>
        </div>
      </div>

      <!-- State -->
      <div class="text-right shrink-0">
        <div class="text-sm font-semibold" :class="stateColor">{{ displayState }}</div>
        <div v-if="entity.last_synced" class="text-xs text-neutral-400">{{ timeAgo(entity.last_synced) }}</div>
      </div>
    </div>

    <!-- Controls for controllable entities -->
    <HAControlPanel v-if="entity.is_controllable" :entity="entity" class="mt-2" />

    <!-- Energy signal role -->
    <div v-if="canHaveEnergyRole" class="flex items-center gap-2 mt-2 pt-2 border-t border-neutral-100 dark:border-neutral-700">
      <Zap class="w-3.5 h-3.5 text-primary-500 shrink-0" />
      <select
        :value="entity.energy_signal_role || ''"
        @change="setEnergyRole(($event.target as HTMLSelectElement).value)"
        class="text-xs bg-transparent border border-neutral-200 dark:border-neutral-600 rounded px-1.5 py-0.5 text-neutral-700 dark:text-neutral-300 flex-1"
      >
        <option value="">{{ $t('ha.energy_signal_none') }}</option>
        <option value="SURPLUS_BOOL">{{ $t('ha.energy_signal_bool') }}</option>
        <option value="SURPLUS_POWER">{{ $t('ha.energy_signal_power') }}</option>
        <option value="SURPLUS_PRICE">{{ $t('ha.energy_signal_price') }}</option>
      </select>
    </div>

    <!-- Actions -->
    <div class="flex items-center gap-2 mt-2 pt-2 border-t border-neutral-100 dark:border-neutral-700">
      <button @click="refresh" :disabled="refreshing" class="text-xs text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300 flex items-center gap-1">
        <RefreshCw class="w-3 h-3" :class="{ 'animate-spin': refreshing }" />
        {{ $t('ha.refresh') }}
      </button>
      <button @click="$emit('delete', entity)" class="text-xs text-red-500 hover:text-red-700 dark:hover:text-red-400 flex items-center gap-1 ml-auto">
        <Trash2 class="w-3 h-3" />
        {{ $t('ha.remove') }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import {
  Lightbulb, Thermometer, ToggleLeft, Lock, Fan, MonitorSpeaker,
  Gauge, Eye as EyeIcon, RefreshCw, Trash2, CircleDot, Zap
} from 'lucide-vue-next'
import type { HAEntity, EnergySignalRole } from '~/stores/ha'

const props = defineProps<{
  entity: HAEntity
}>()

defineEmits<{
  delete: [entity: HAEntity]
}>()

const haStore = useHAStore()
const refreshing = ref(false)

const domainIcon = computed(() => {
  const map: Record<string, any> = {
    light: Lightbulb,
    climate: Thermometer,
    switch: ToggleLeft,
    lock: Lock,
    fan: Fan,
    media_player: MonitorSpeaker,
    sensor: Gauge,
    binary_sensor: EyeIcon,
  }
  return map[props.entity.domain] || CircleDot
})

const stateColor = computed(() => {
  const s = props.entity.state
  if (s === 'on' || s === 'unlocked' || s === 'open') return 'text-primary-600 dark:text-primary-400'
  if (s === 'off' || s === 'locked' || s === 'closed') return 'text-neutral-500 dark:text-neutral-400'
  if (s === 'unavailable') return 'text-red-500'
  return 'text-neutral-700 dark:text-neutral-300'
})

const displayState = computed(() => {
  const s = props.entity.state
  const attrs = props.entity.attributes
  if (props.entity.domain === 'sensor' && attrs.unit_of_measurement) {
    return `${s} ${attrs.unit_of_measurement}`
  }
  return s
})

const canHaveEnergyRole = computed(() =>
  ['input_boolean', 'input_number', 'switch'].includes(props.entity.domain)
)

async function setEnergyRole(value: string) {
  const role = value || null
  try {
    await haStore.setEnergySignalRole(props.entity.id, props.entity.home_id, role as EnergySignalRole | null)
  } catch {}
}

function timeAgo(dt: string) {
  const diff = (Date.now() - new Date(dt).getTime()) / 1000
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

async function refresh() {
  refreshing.value = true
  try {
    await haStore.getEntityState(props.entity.id)
  } catch {} finally {
    refreshing.value = false
  }
}
</script>
