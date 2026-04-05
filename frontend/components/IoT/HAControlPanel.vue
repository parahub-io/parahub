<template>
  <div class="flex items-center gap-2">
    <!-- Toggle for on/off domains (light, switch, fan) -->
    <template v-if="isToggleable">
      <button @click="toggle" :disabled="controlling"
              class="px-3 py-1 rounded-full text-xs font-medium transition-colors"
              :class="isOn
                ? 'bg-primary-100 text-primary-700 dark:bg-primary-900/40 dark:text-primary-300 hover:bg-primary-200 dark:hover:bg-primary-900/60'
                : 'bg-neutral-100 text-neutral-600 dark:bg-neutral-700 dark:text-neutral-400 hover:bg-neutral-200 dark:hover:bg-neutral-600'">
        <Loader2 v-if="controlling" class="w-3 h-3 animate-spin inline mr-1" />
        {{ isOn ? $t('ha.turn_off') : $t('ha.turn_on') }}
      </button>
    </template>

    <!-- Lock domain -->
    <template v-else-if="entity.domain === 'lock'">
      <button @click="callService(isLocked ? 'unlock' : 'lock')" :disabled="controlling"
              class="px-3 py-1 rounded-full text-xs font-medium transition-colors"
              :class="isLocked
                ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300'
                : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'">
        <Loader2 v-if="controlling" class="w-3 h-3 animate-spin inline mr-1" />
        {{ isLocked ? $t('ha.unlock') : $t('ha.lock') }}
      </button>
    </template>

    <!-- Brightness slider for lights -->
    <template v-if="entity.domain === 'light' && isOn && entity.attributes.brightness !== undefined">
      <input type="range" min="1" max="255" :value="entity.attributes.brightness"
             @change="setBrightness($event)"
             class="flex-1 h-1.5 accent-primary cursor-pointer" />
      <span class="text-xs text-neutral-500 w-8 text-right">{{ brightnessPercent }}%</span>
    </template>

    <!-- Climate target temperature -->
    <template v-if="entity.domain === 'climate' && entity.attributes.temperature !== undefined">
      <div class="flex items-center gap-1 ml-auto">
        <button @click="adjustTemp(-0.5)" :disabled="controlling"
                class="w-6 h-6 rounded bg-neutral-100 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-400 flex items-center justify-center text-sm hover:bg-neutral-200 dark:hover:bg-neutral-600">
          −
        </button>
        <span class="text-xs font-medium text-neutral-700 dark:text-neutral-300 w-10 text-center">
          {{ entity.attributes.temperature }}°
        </span>
        <button @click="adjustTemp(0.5)" :disabled="controlling"
                class="w-6 h-6 rounded bg-neutral-100 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-400 flex items-center justify-center text-sm hover:bg-neutral-200 dark:hover:bg-neutral-600">
          +
        </button>
      </div>
    </template>

    <!-- Button / Scene / Script → just a run button -->
    <template v-if="entity.domain === 'button' || entity.domain === 'scene' || entity.domain === 'script'">
      <button @click="callService(entity.domain === 'button' ? 'press' : 'turn_on')" :disabled="controlling"
              class="btn-outline btn-sm text-xs gap-1">
        <Loader2 v-if="controlling" class="w-3 h-3 animate-spin" />
        <Play v-else class="w-3 h-3" />
        {{ $t('ha.activate') }}
      </button>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Loader2, Play } from 'lucide-vue-next'
import type { HAEntity } from '~/stores/ha'

const props = defineProps<{
  entity: HAEntity
}>()

const haStore = useHAStore()
const controlling = ref(false)

const isToggleable = computed(() =>
  ['light', 'switch', 'fan', 'cover', 'humidifier', 'water_heater', 'valve', 'siren', 'vacuum', 'media_player'].includes(props.entity.domain)
)

const isOn = computed(() => props.entity.state === 'on' || props.entity.state === 'open')
const isLocked = computed(() => props.entity.state === 'locked')

const brightnessPercent = computed(() =>
  Math.round(((props.entity.attributes.brightness || 0) / 255) * 100)
)

async function callService(service: string, data?: Record<string, any>) {
  controlling.value = true
  try {
    const result = await haStore.controlEntity(props.entity.id, service, data)
    // Update local state
    if (result.new_state) {
      props.entity.state = result.new_state
    }
  } catch {} finally {
    controlling.value = false
  }
}

function toggle() {
  const service = isOn.value ? 'turn_off' : 'turn_on'
  callService(service)
}

function setBrightness(event: Event) {
  const val = parseInt((event.target as HTMLInputElement).value)
  callService('turn_on', { brightness: val })
}

function adjustTemp(delta: number) {
  const current = props.entity.attributes.temperature || 20
  callService('set_temperature', { temperature: current + delta })
}
</script>
