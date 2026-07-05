<template>
  <div v-if="item" class="fixed inset-0 z-50 overflow-y-auto">
    <div class="flex items-center justify-center min-h-screen px-4 pt-4 pb-20 text-center sm:p-0">
      <div @click="$emit('update:modelValue', null)" class="fixed inset-0 bg-neutral-900 bg-opacity-75" aria-hidden="true"></div>

      <div class="relative inline-block w-full max-w-2xl px-4 pt-5 pb-4 overflow-hidden text-left align-bottom transform bg-white dark:bg-neutral-800 rounded-lg shadow-xl sm:my-8 sm:align-middle sm:p-6" role="dialog" aria-modal="true">
        <div class="absolute top-0 right-0 pt-4 pr-4">
          <button @click="$emit('update:modelValue', null)" class="text-neutral-400 hover:text-neutral-500 dark:text-neutral-500 dark:hover:text-neutral-400" :aria-label="$t('common.close')">
            <X class="w-6 h-6" aria-hidden="true" />
          </button>
        </div>

        <div class="sm:flex sm:items-start">
          <div class="w-full">
            <h3 class="text-lg font-medium leading-6 text-neutral-900 dark:text-neutral-100 mb-4">
              {{ $t('market.edit_modal.title') }}
            </h3>

            <form @submit.prevent="updateItem" class="space-y-4">
              <!-- Title -->
              <div>
                <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                  {{ $t('market.edit_modal.title_label') }}
                </label>
                <input
                  v-model="editForm.title"
                  type="text"
                  required
                  maxlength="255"
                  class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700"
                >
              </div>

              <!-- Description -->
              <div>
                <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                  {{ $t('market.edit_modal.description_label') }}
                </label>
                <textarea
                  v-model="editForm.description"
                  rows="3"
                  maxlength="5000"
                  class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700"
                ></textarea>
              </div>

              <!-- Pricing Options -->
              <div>
                <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
                  {{ $t('market.edit_modal.pricing_label') }}
                </label>
                <div class="space-y-3">
                  <div
                    v-for="(opt, index) in editForm.pricing_options"
                    :key="index"
                    class="p-3 border border-neutral-300 dark:border-neutral-600 rounded-lg"
                  >
                    <div class="flex justify-between items-start mb-2">
                      <div class="text-sm font-medium text-neutral-700 dark:text-neutral-300">
                        {{ $t('market.edit_modal.pricing_option_number', { number: index + 1 }) }}
                      </div>
                      <button
                        type="button"
                        @click="editForm.pricing_options.splice(index, 1)"
                        class="text-red-500 hover:text-red-700"
                      >
                        <X class="w-4 h-4" />
                      </button>
                    </div>

                    <!-- Type selector -->
                    <div class="grid grid-cols-3 gap-2 mb-2">
                      <label class="text-xs">
                        <input
                          v-model="opt.type"
                          type="radio"
                          :name="`edit-type-${index}`"
                          value="sale"
                          class="mr-1"
                        >
                        {{ $t('market.edit_modal.pricing_type_sale') }}
                      </label>
                      <label class="text-xs">
                        <input
                          v-model="opt.type"
                          type="radio"
                          :name="`edit-type-${index}`"
                          value="rent"
                          class="mr-1"
                        >
                        {{ $t('market.edit_modal.pricing_type_rent') }}
                      </label>
                      <label class="text-xs">
                        <input
                          v-model="opt.type"
                          type="radio"
                          :name="`edit-type-${index}`"
                          value="free"
                          class="mr-1"
                        >
                        {{ $t('market.edit_modal.pricing_type_free') }}
                      </label>
                    </div>

                    <!-- Amount and currency (if not free) -->
                    <div v-if="opt.type !== 'free'" class="grid grid-cols-2 gap-2 mb-2">
                      <input
                        v-model.number="opt.amount"
                        type="number"
                        step="0.01"
                        min="0"
                        :placeholder="$t('market.edit_modal.amount_placeholder')"
                        class="px-2 py-1 text-sm border border-neutral-300 dark:border-neutral-600 rounded bg-white dark:bg-neutral-700"
                      >
                      <select
                        v-model="opt.currency"
                        class="px-2 py-1 text-sm border border-neutral-300 dark:border-neutral-600 rounded bg-white dark:bg-neutral-700"
                      >
                        <option value="EUR">EUR</option>
                        <option value="USD">USD</option>
                        <option value="RUB">RUB</option>
                        <option value="BTC">BTC</option>
                      </select>
                    </div>

                    <!-- Unit (e.g. kg, hour, day, pcs) — localized labels, canonical value -->
                    <div v-if="opt.type !== 'free'" class="mb-2">
                      <MarketUnitSelect
                        v-model="opt.unit"
                        select-class="w-full px-2 py-1 text-sm border border-neutral-300 dark:border-neutral-600 rounded bg-white dark:bg-neutral-700"
                        input-class="w-full px-2 py-1 text-sm border border-neutral-300 dark:border-neutral-600 rounded bg-white dark:bg-neutral-700"
                      />
                    </div>

                    <!-- Note -->
                    <input
                      v-model="opt.note"
                      type="text"
                      maxlength="100"
                      :placeholder="$t('market.edit_modal.note_placeholder')"
                      class="w-full px-2 py-1 text-sm border border-neutral-300 dark:border-neutral-600 rounded bg-white dark:bg-neutral-700"
                    >
                  </div>

                  <button
                    type="button"
                    @click="editForm.pricing_options.push({ type: 'sale', amount: null, currency: 'EUR', unit: '', note: '' })"
                    class="w-full px-3 py-2 border-2 border-dashed border-neutral-300 dark:border-neutral-600 rounded-lg hover:border-primary text-sm text-neutral-600 dark:text-neutral-400"
                  >
                    {{ $t('market.edit_modal.add_pricing_option') }}
                  </button>
                </div>
              </div>

              <!-- Location -->
              <div>
                <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                  {{ $t('market.edit_modal.location_label') }}
                </label>
                <div class="grid grid-cols-2 gap-3">
                  <input
                    v-model.number="editForm.location.latitude"
                    type="number"
                    step="0.000001"
                    min="-90"
                    max="90"
                    :placeholder="$t('market.edit_modal.latitude_placeholder')"
                    class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700"
                  >
                  <input
                    v-model.number="editForm.location.longitude"
                    type="number"
                    step="0.000001"
                    min="-180"
                    max="180"
                    :placeholder="$t('market.edit_modal.longitude_placeholder')"
                    class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700"
                  >
                </div>
              </div>

              <!-- Submit buttons -->
              <div class="flex justify-end gap-3 pt-4">
                <button
                  type="button"
                  @click="$emit('update:modelValue', null)"
                  class="px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-700"
                >
                  {{ $t('market.edit_modal.cancel') }}
                </button>
                <button
                  type="submit"
                  :disabled="updating"
                  class="px-4 py-2 bg-primary text-black font-medium rounded-lg hover:bg-opacity-90 disabled:opacity-50"
                >
                  {{ updating ? $t('market.edit_modal.saving') : $t('market.edit_modal.save') }}
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useAuthStore } from '~/stores/auth'
import { useNotification } from '~/composables/useNotification'
import { X } from 'lucide-vue-next'

const props = defineProps({
  modelValue: { type: Object, default: null }
})

const emit = defineEmits(['update:modelValue', 'updated'])

const item = computed(() => props.modelValue)

const authStore = useAuthStore()
const { showSuccess, showError } = useNotification()
const { t: $t } = useI18n()

const userCurrency = useLocalPref('preferred_currency', 'EUR')

const updating = ref(false)
const editForm = ref({
  title: '',
  description: '',
  pricing_options: [],
  location: { latitude: null, longitude: null }
})

watch(() => props.modelValue, (newItem) => {
  if (newItem) {
    editForm.value = {
      title: newItem.title,
      description: newItem.description || '',
      pricing_options: newItem.pricing_options?.length > 0
        ? JSON.parse(JSON.stringify(newItem.pricing_options))
        : [{ type: 'sale', amount: null, currency: userCurrency.value, unit: '', note: '' }],
      location: {
        latitude: newItem.location?.coordinates?.[1] || null,
        longitude: newItem.location?.coordinates?.[0] || null
      }
    }
  }
}, { immediate: true })

const updateItem = async () => {
  updating.value = true
  try {
    await authStore.ensureToken()

    if (!authStore.accessToken) {
      showError($t('market.notifications.login_required_action'))
      return
    }

    const cleanPricingOptions = editForm.value.pricing_options
      .filter(opt => {
        if (opt.type === 'free') return true
        if (!opt.amount || opt.amount <= 0) return false
        return true
      })
      .map(opt => {
        const cleaned = { type: opt.type }
        if (opt.type !== 'free') {
          cleaned.amount = opt.amount
          cleaned.currency = opt.currency
        }
        if (opt.unit) cleaned.unit = opt.unit
        if (opt.note) cleaned.note = opt.note
        return cleaned
      })

    const payload = {
      title: editForm.value.title,
      description: editForm.value.description,
      pricing_options: cleanPricingOptions,
      expected_version: props.modelValue.version
    }

    if (editForm.value.location.latitude && editForm.value.location.longitude) {
      payload.location = editForm.value.location
    }

    await $fetch(`/api/v1/items/${props.modelValue.id}/`, {
      method: 'PUT',
      headers: {
        Authorization: `Bearer ${authStore.accessToken}`,
        'Content-Type': 'application/json'
      },
      credentials: 'include',
      body: payload
    })

    showSuccess($t('market.notifications.updated'))
    emit('update:modelValue', null)
    emit('updated')
  } catch (error) {
    console.error('Failed to update item:', error)
    showError($t('market.notifications.update_error'))
  } finally {
    updating.value = false
  }
}
</script>
