<template>
  <div>
    <!-- Localized labels, canonical English value (so cross-locale display stays correct) -->
    <select
      :value="selectValue"
      :class="selectClass"
      @change="onSelect($event.target.value)"
    >
      <option value="">{{ $t('market.pricing.unit_none') }}</option>
      <option v-for="key in UNIT_KEYS" :key="key" :value="key">
        {{ $t(`market.pricing.units.${key}`, key) }}
      </option>
      <option value="__custom__">{{ $t('market.pricing.unit_custom') }}</option>
    </select>
    <!-- Free-text fallback for units outside the presets -->
    <input
      v-if="custom"
      :value="modelValue"
      type="text"
      maxlength="50"
      :placeholder="$t('market.pricing.unit_custom_placeholder')"
      :class="[inputClass, 'mt-2']"
      @input="$emit('update:modelValue', $event.target.value)"
    >
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

// Canonical unit keys — must match the keys under market.pricing.units in the locales.
const UNIT_KEYS = [
  'kg', 'g', 't', 'l', 'ml', 'm', 'm²', 'm³',
  'pcs', 'pair', 'box', 'set',
  'hour', 'half_day', 'day', 'weekend', 'week', 'month', 'year',
  'session', 'project', 'page', 'consultation',
]

const props = defineProps({
  modelValue: { type: String, default: '' },
  selectClass: { type: String, default: '' },
  inputClass: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])

const { t: $t } = useI18n()

// Custom mode when a non-empty value isn't one of the presets (e.g. editing a
// legacy listing whose unit was typed by hand).
const custom = ref(!!props.modelValue && !UNIT_KEYS.includes(props.modelValue))

// Reconcile when the bound value changes externally (edit-form load). Leave the
// flag untouched on an empty value so the user can be mid-custom-entry.
watch(() => props.modelValue, (v) => {
  if (v && !UNIT_KEYS.includes(v)) custom.value = true
  else if (v && UNIT_KEYS.includes(v)) custom.value = false
})

const selectValue = computed(() => {
  if (custom.value) return '__custom__'
  return UNIT_KEYS.includes(props.modelValue) ? props.modelValue : ''
})

const onSelect = (val) => {
  if (val === '__custom__') {
    custom.value = true
    // Don't carry a preset key into the custom field — start blank.
    if (UNIT_KEYS.includes(props.modelValue)) emit('update:modelValue', '')
  } else {
    custom.value = false
    emit('update:modelValue', val)
  }
}
</script>
