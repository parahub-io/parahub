<template>
  <div>
    <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-3">
      {{ $t('market.create_modal.pricing_label') }}
    </label>
    <div ref="pricingContainer" class="space-y-3">
      <!-- Existing pricing options -->
      <div
        v-for="(opt, index) in modelValue"
        :key="index"
        class="p-4 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-neutral-50 dark:bg-neutral-800"
      >
        <div class="flex justify-between items-start mb-3">
          <div class="text-sm font-medium text-neutral-700 dark:text-neutral-300">
            {{ $t('market.create_modal.pricing_option_number', { number: index + 1 }) }}
          </div>
          <UiButton type="button" variant="ghost" :icon="X" icon-only size="sm" class="text-error hover:bg-error/10" :aria-label="$t('common.remove')" @click="removePricingOption(index)" />
        </div>

        <!-- Type selector -->
        <div class="grid gap-2 mb-3" :class="canRent ? 'grid-cols-3' : 'grid-cols-2'">
          <label class="text-xs text-neutral-900 dark:text-neutral-100">
            <input
              v-model="opt.type"
              type="radio"
              :name="`type-${index}`"
              value="sale"
              class="mr-1"
            >
            {{ $t('market.create_modal.pricing_type_sale') }}
          </label>
          <label v-if="canRent" class="text-xs text-neutral-900 dark:text-neutral-100">
            <input
              v-model="opt.type"
              type="radio"
              :name="`type-${index}`"
              value="rent"
              class="mr-1"
            >
            {{ $t('market.create_modal.pricing_type_rent') }}
          </label>
          <label class="text-xs text-neutral-900 dark:text-neutral-100">
            <input
              v-model="opt.type"
              type="radio"
              :name="`type-${index}`"
              value="free"
              class="mr-1"
            >
            {{ $t('market.create_modal.pricing_type_free') }}
          </label>
        </div>

        <!-- Amount and currency (if not free) -->
        <div v-if="opt.type !== 'free'" class="grid grid-cols-2 gap-2 mb-3">
          <input
            v-model.number="opt.amount"
            type="number"
            step="0.01"
            min="0"
            :placeholder="$t('market.create_modal.amount_placeholder')"
            class="px-3 py-2 text-sm border border-neutral-300 dark:border-neutral-600 rounded bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
          >
          <div class="px-3 py-2 text-sm border border-neutral-200 dark:border-neutral-600 rounded bg-neutral-100 dark:bg-neutral-900 flex items-center justify-center font-medium text-neutral-900 dark:text-neutral-100">
            {{ opt.currency }}
          </div>
        </div>

        <!-- Unit (e.g. kg, hour, day, pcs) — localized labels, canonical value -->
        <div v-if="opt.type !== 'free'" class="mb-3">
          <MarketUnitSelect
            v-model="opt.unit"
            select-class="w-full px-3 py-2 text-sm border border-neutral-300 dark:border-neutral-600 rounded bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
            input-class="w-full px-3 py-2 text-sm border border-neutral-300 dark:border-neutral-600 rounded bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
          />
        </div>

        <!-- Note -->
        <input
          v-model="opt.note"
          type="text"
          maxlength="100"
          :placeholder="$t('market.create_modal.note_placeholder')"
          class="w-full px-3 py-2 text-sm border border-neutral-300 dark:border-neutral-600 rounded bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
        >
      </div>

      <!-- Add pricing option button (hidden if free option exists) -->
      <button
        v-if="!hasOnlyFreeOptions"
        type="button"
        @click="addPricingOption"
        class="btn-outline w-full border-dashed border-2 hover:border-primary"
      >
        {{ $t('market.create_modal.add_pricing_option') }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { X } from 'lucide-vue-next'

const props = defineProps({
  modelValue: {
    type: Array,
    required: true
  },
  canRent: {
    type: Boolean,
    default: true
  },
  currency: {
    type: String,
    default: 'EUR'
  }
})

const emit = defineEmits(['update:modelValue'])

const { t: $t } = useI18n()

const pricingContainer = ref(null)

const hasOnlyFreeOptions = computed(() => {
  if (props.modelValue.length === 0) return false
  return props.modelValue.every(opt => opt.type === 'free')
})

const addPricingOption = () => {
  const updated = [...props.modelValue, {
    type: 'sale',
    amount: null,
    currency: props.currency,
    unit: '',
    note: ''
  }]
  emit('update:modelValue', updated)
}

const removePricingOption = (index) => {
  const updated = [...props.modelValue]
  updated.splice(index, 1)
  emit('update:modelValue', updated)
}

// Expose container ref for flash animation from parent
defineExpose({ pricingContainer })
</script>
