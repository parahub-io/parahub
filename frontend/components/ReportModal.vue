<template>
  <Modal
    v-model="visible"
    :title="t('moderation.report_title')"
    :icon="Flag"
    icon-class="text-error"
    size="md"
  >
    <div class="space-y-4">
      <p class="text-sm text-neutral-600 dark:text-neutral-400">
        {{ t('moderation.report_intro') }}
      </p>

      <fieldset class="space-y-1.5">
        <legend class="sr-only">{{ t('moderation.report_reason_label') }}</legend>
        <label
          v-for="reason in REASONS"
          :key="reason"
          class="flex items-center gap-3 px-3 py-2 border rounded-lg cursor-pointer transition-colors"
          :class="selectedReason === reason
            ? 'border-secondary bg-secondary-50 dark:bg-secondary-900/20'
            : 'border-neutral-300 dark:border-neutral-600 hover:bg-primary-100 dark:hover:bg-primary-900/40'"
        >
          <input
            v-model="selectedReason"
            type="radio"
            name="report-reason"
            :value="reason"
            class="accent-secondary"
          />
          <span class="text-sm text-neutral-900 dark:text-neutral-100">{{ t(`moderation.reasons.${reason.toLowerCase()}`) }}</span>
        </label>
      </fieldset>

      <div>
        <label for="report-details" class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
          {{ t('moderation.report_details_label') }}
        </label>
        <textarea
          id="report-details"
          v-model="details"
          :placeholder="t('moderation.report_details_placeholder')"
          maxlength="2000"
          rows="3"
          class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
        ></textarea>
      </div>
    </div>

    <template #footer>
      <UiButton variant="outline" @click="visible = false">
        {{ t('common.cancel') }}
      </UiButton>
      <UiButton variant="error" :icon="Flag" :loading="submitting" :disabled="!selectedReason" @click="submit">
        {{ t('moderation.report_submit') }}
      </UiButton>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { Flag } from 'lucide-vue-next'

const props = defineProps<{
  modelValue: boolean
  /** ULID of the reported object (item, profile, comment, post, ...) */
  objectId: string
}>()
const emit = defineEmits<{ 'update:modelValue': [boolean]; 'reported': [] }>()

const { t } = useI18n()
const route = useRoute()
const authStore = useAuthStore()
const toastStore = useToastStore()
const { apiErrorMessage } = useApiError()

// Mirrors core.models.ContentReport.Reason
const REASONS = ['SPAM', 'FRAUD', 'HARASSMENT', 'SEXUAL', 'VIOLENCE', 'ILLEGAL', 'OTHER'] as const

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v)
})

const selectedReason = ref('')
const details = ref('')
const submitting = ref(false)

watch(visible, (show) => {
  if (show) {
    selectedReason.value = ''
    details.value = ''
  }
})

const submit = async () => {
  if (!selectedReason.value || submitting.value) return
  submitting.value = true
  try {
    await authStore.ensureToken()
    await $fetch('/api/v1/core/reports/', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
      body: {
        object_id: props.objectId,
        reason: selectedReason.value,
        details: details.value,
        context_url: route.fullPath
      }
    })
    visible.value = false
    toastStore.success(t('moderation.report_sent'))
    emit('reported')
  } catch (error: any) {
    toastStore.error(apiErrorMessage(error, 'moderation.error_codes', t('moderation.report_error')))
  } finally {
    submitting.value = false
  }
}
</script>
