<template>
  <div class="bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700 px-4 sm:px-6 py-4">
    <div class="flex items-center justify-between mb-3">
      <h2 class="text-sm font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
        <Package class="w-4 h-4 text-neutral-400" />
        {{ $t('shipments.hub.title') }}
      </h2>
      <!-- Toggle -->
      <button
        @click="toggleHub"
        :disabled="saving"
        :class="[
          'relative inline-flex h-6 w-11 items-center rounded-full transition-colors',
          isHub ? 'bg-primary' : 'bg-neutral-300 dark:bg-neutral-600'
        ]"
        :aria-label="isHub ? $t('shipments.hub.deactivate') : $t('shipments.hub.activate')"
      >
        <span
          :class="[
            'inline-block h-4 w-4 transform rounded-full bg-white transition-transform',
            isHub ? 'translate-x-6' : 'translate-x-1'
          ]"
        />
      </button>
    </div>

    <!-- WoT warning (shown when not hub and can't activate) -->
    <p v-if="!isHub && !canActivate" class="text-xs text-amber-600 dark:text-amber-400 mb-2">
      {{ $t('shipments.hub.wot_required') }}
    </p>

    <!-- Hub settings form (only when hub is active) -->
    <div v-if="isHub" class="space-y-3 mt-3 pt-3 border-t border-neutral-100 dark:border-neutral-800">
      <!-- Accepted sizes -->
      <div>
        <label class="text-xs font-medium text-neutral-600 dark:text-neutral-400 block mb-1.5">
          {{ $t('shipments.hub.accepted_sizes') }}
        </label>
        <div class="flex flex-wrap gap-2">
          <button
            v-for="size in allSizes"
            :key="size"
            type="button"
            @click="toggleSize(size)"
            :class="[
              'px-2.5 py-1 text-xs rounded-lg border transition-colors',
              acceptedSizes.includes(size)
                ? 'bg-primary/10 border-primary text-primary-800 dark:text-primary-200 font-medium'
                : 'border-neutral-200 dark:border-neutral-700 text-neutral-500 dark:text-neutral-400 hover:bg-neutral-50 dark:hover:bg-neutral-800'
            ]"
          >
            {{ $t(`shipments.size.${size}`) }}
          </button>
        </div>
      </div>

      <!-- Capacity -->
      <div>
        <label class="text-xs font-medium text-neutral-600 dark:text-neutral-400 block mb-1">
          {{ $t('shipments.hub.capacity') }}
        </label>
        <input
          v-model.number="capacity"
          type="number"
          min="0"
          :placeholder="$t('shipments.hub.capacity_unlimited')"
          class="w-full text-sm border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-1.5 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100"
        />
        <p class="text-[10px] text-neutral-400 mt-0.5">{{ $t('shipments.hub.capacity_hint') }}</p>
      </div>

      <!-- Max days -->
      <div>
        <label class="text-xs font-medium text-neutral-600 dark:text-neutral-400 block mb-1">
          {{ $t('shipments.hub.max_days') }}
        </label>
        <input
          v-model.number="maxDays"
          type="number"
          min="1"
          max="90"
          class="w-full text-sm border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-1.5 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100"
        />
      </div>

      <!-- Storage fee -->
      <div>
        <label class="text-xs font-medium text-neutral-600 dark:text-neutral-400 block mb-1">
          {{ $t('shipments.hub.storage_fee') }}
        </label>
        <div class="flex items-center gap-2">
          <input
            v-model.number="storageFee"
            type="number"
            min="0"
            class="flex-1 text-sm border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-1.5 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100"
          />
          <span class="text-xs text-neutral-400 shrink-0">{{ $t('shipments.sats_per_day') }}</span>
        </div>
        <p v-if="storageFee === 0" class="text-[10px] text-green-600 dark:text-green-400 mt-0.5">{{ $t('shipments.hub.free') }}</p>
      </div>

      <!-- Instructions -->
      <div>
        <label class="text-xs font-medium text-neutral-600 dark:text-neutral-400 block mb-1">
          {{ $t('shipments.hub.instructions') }}
        </label>
        <textarea
          v-model="instructions"
          rows="2"
          :placeholder="$t('shipments.hub.instructions_placeholder')"
          class="w-full text-sm border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-1.5 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 resize-none"
        />
      </div>

      <!-- Save button -->
      <button
        @click="saveSettings"
        :disabled="saving || !hasChanges"
        :class="[
          'w-full px-4 py-2 text-sm font-medium rounded-lg transition-colors',
          hasChanges
            ? 'btn-primary'
            : 'bg-neutral-100 dark:bg-neutral-800 text-neutral-400 cursor-not-allowed'
        ]"
      >
        <Loader2 v-if="saving" class="w-4 h-4 inline animate-spin mr-1" />
        {{ $t('common.save') }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Package, Loader2 } from 'lucide-vue-next'
import { useShipments } from '~/composables/useShipments'

const props = defineProps<{
  establishmentId: string
  isHub: boolean
  hubCapacity: number | null
  hubMaxDays: number
  hubStorageFeeDailyProp: number
  hubAcceptedSizes: string[]
  hubInstructions: string
  canActivate: boolean
}>()

const emit = defineEmits<{
  updated: []
}>()

const { t } = useI18n()
const { updateHubSettings } = useShipments()

const allSizes = ['S', 'M', 'L', 'XL']

// Local form state
const isHub = ref(props.isHub)
const capacity = ref<number | null>(props.hubCapacity)
const maxDays = ref(props.hubMaxDays || 14)
const storageFee = ref(props.hubStorageFeeDailyProp || 0)
const acceptedSizes = ref<string[]>([...(props.hubAcceptedSizes || [])])
const instructions = ref(props.hubInstructions || '')
const saving = ref(false)

// Watch for prop changes
watch(() => props.isHub, (v) => { isHub.value = v })
watch(() => props.hubCapacity, (v) => { capacity.value = v })
watch(() => props.hubMaxDays, (v) => { maxDays.value = v || 14 })
watch(() => props.hubStorageFeeDailyProp, (v) => { storageFee.value = v || 0 })
watch(() => props.hubAcceptedSizes, (v) => { acceptedSizes.value = [...(v || [])] })
watch(() => props.hubInstructions, (v) => { instructions.value = v || '' })

const hasChanges = computed(() => {
  if (!isHub.value) return false
  const sizesSame = JSON.stringify([...acceptedSizes.value].sort()) === JSON.stringify([...(props.hubAcceptedSizes || [])].sort())
  return (
    capacity.value !== props.hubCapacity ||
    maxDays.value !== (props.hubMaxDays || 14) ||
    storageFee.value !== (props.hubStorageFeeDailyProp || 0) ||
    !sizesSame ||
    instructions.value !== (props.hubInstructions || '')
  )
})

const toggleSize = (size: string) => {
  const idx = acceptedSizes.value.indexOf(size)
  if (idx >= 0) {
    acceptedSizes.value.splice(idx, 1)
  } else {
    acceptedSizes.value.push(size)
  }
}

const toggleHub = async () => {
  if (!isHub.value && !props.canActivate) return
  saving.value = true
  try {
    await updateHubSettings(props.establishmentId, {
      is_hub: !isHub.value,
      // When activating, set default accepted sizes
      ...(!isHub.value ? { hub_accepted_sizes: ['S', 'M', 'L', 'XL'] } : {}),
    })
    isHub.value = !isHub.value
    if (isHub.value) {
      acceptedSizes.value = ['S', 'M', 'L', 'XL']
    }
    emit('updated')
  } catch (err: any) {
    console.error('Failed to toggle hub:', err)
  } finally {
    saving.value = false
  }
}

const saveSettings = async () => {
  saving.value = true
  try {
    await updateHubSettings(props.establishmentId, {
      hub_capacity: capacity.value || null,
      hub_max_days: maxDays.value,
      hub_storage_fee_daily: storageFee.value,
      hub_accepted_sizes: acceptedSizes.value,
      hub_instructions: instructions.value,
    })
    emit('updated')
  } catch (err: any) {
    console.error('Failed to save hub settings:', err)
  } finally {
    saving.value = false
  }
}
</script>
