<template>
  <div v-if="item" class="fixed inset-0 z-50 overflow-y-auto">
    <div class="flex items-center justify-center min-h-screen px-4 pt-4 pb-20 text-center sm:p-0">
      <div @click="$emit('update:modelValue', null)" class="fixed inset-0 bg-neutral-900 bg-opacity-75" aria-hidden="true"></div>

      <div class="relative inline-block w-full max-w-md px-4 pt-5 pb-4 overflow-hidden text-left align-bottom transform bg-white dark:bg-neutral-800 rounded-lg shadow-xl sm:my-8 sm:align-middle sm:p-6" role="dialog" aria-modal="true">
        <div class="sm:flex sm:items-start">
          <div class="w-full">
            <h3 class="text-lg font-medium leading-6 text-neutral-900 dark:text-neutral-100 mb-4">
              {{ $t('market.delete_modal.title') }}
            </h3>
            <p class="text-sm text-neutral-600 dark:text-neutral-400 mb-6">
              {{ $t('market.delete_modal.confirm_message', { title: item.title }) }}
            </p>

            <div class="flex justify-end gap-3">
              <button
                @click="$emit('update:modelValue', null)"
                class="px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-700"
              >
                {{ $t('market.delete_modal.cancel') }}
              </button>
              <button
                @click="deleteItem"
                :disabled="deleting"
                class="btn-error"
              >
                {{ deleting ? $t('market.delete_modal.deleting') : $t('market.delete_modal.delete') }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useAuthStore } from '~/stores/auth'
import { useNotification } from '~/composables/useNotification'

const props = defineProps({
  modelValue: { type: Object, default: null }
})

const emit = defineEmits(['update:modelValue', 'deleted'])

const item = computed(() => props.modelValue)

const authStore = useAuthStore()
const { showSuccess, showError } = useNotification()
const { t: $t } = useI18n()

const deleting = ref(false)

const deleteItem = async () => {
  deleting.value = true
  try {
    await authStore.ensureToken()

    if (!authStore.accessToken) {
      showError($t('market.notifications.login_required_action'))
      return
    }

    await $fetch(`/api/v1/items/${props.modelValue.id}/`, {
      method: 'DELETE',
      headers: {
        Authorization: `Bearer ${authStore.accessToken}`
      },
      credentials: 'include'
    })

    showSuccess($t('market.notifications.deleted'))
    useState('marketDirty', () => false).value = true
    emit('update:modelValue', null)
    emit('deleted')
  } catch (error) {
    console.error('Failed to delete item:', error)
    const errorMsg = error.response?._data?.error || $t('market.notifications.delete_error')
    showError(errorMsg)
  } finally {
    deleting.value = false
  }
}
</script>
