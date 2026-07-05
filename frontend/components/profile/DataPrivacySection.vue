<template>
  <AccordionSection
    section-id="data-privacy"
    :title="$t('profile.data_privacy.title')"
    :icon="Shield"
    :open-sections="openSections"
    :animation-enabled="animationEnabled"
    @toggle="emit('toggle', $event)"
  >
    <div class="space-y-6">
      <!-- Export Info -->
      <UiAlert variant="info" :title="$t('profile.data_privacy.info_title')">
        {{ $t('profile.data_privacy.info_description') }}
      </UiAlert>

      <!-- Export Button -->
      <div>
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
          {{ $t('profile.data_privacy.export_label') }}
        </label>
        <UiButton variant="primary" :icon="Download" :loading="exporting" :disabled="exporting" @click="exportAllData">
          {{ exporting ? $t('profile.data_privacy.exporting') : $t('profile.data_privacy.export_button') }}
        </UiButton>
        <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-2">
          {{ $t('profile.data_privacy.export_hint') }}
        </p>
      </div>

      <!-- Export History -->
      <div v-if="exportHistory.length > 0">
        <h3 class="text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-3">
          {{ $t('profile.data_privacy.history_title') }}
        </h3>
        <div class="space-y-2">
          <div
            v-for="export_ in exportHistory"
            :key="export_.created_at"
            class="flex items-center justify-between p-3 bg-neutral-50 dark:bg-neutral-700/50 rounded-lg text-sm"
          >
            <div class="flex items-center gap-3">
              <FileArchive class="w-4 h-4 text-neutral-600 dark:text-neutral-400" />
              <div>
                <p class="font-medium text-neutral-900 dark:text-neutral-100">
                  {{ getExportTypeLabel(export_.export_type) }}
                </p>
                <p class="text-xs text-neutral-500 dark:text-neutral-400">
                  {{ formatDate(export_.created_at) }} · {{ export_.object_count }} {{ $t('profile.data_privacy.items') }}
                </p>
              </div>
            </div>
            <Check class="w-4 h-4 text-green-600 dark:text-green-400" />
          </div>
        </div>
      </div>

      <!-- GDPR Notice -->
      <div class="bg-neutral-50 dark:bg-neutral-700/50 border border-neutral-200 dark:border-neutral-600 rounded-lg p-4">
        <div class="flex items-start gap-3">
          <Scale class="w-5 h-5 text-neutral-600 dark:text-neutral-400 flex-shrink-0 mt-0.5" />
          <div class="text-xs text-neutral-600 dark:text-neutral-400">
            <p class="font-medium mb-1">{{ $t('profile.data_privacy.gdpr_title') }}</p>
            <p>{{ $t('profile.data_privacy.gdpr_description') }}</p>
          </div>
        </div>
      </div>

      <!-- Delete Account Section -->
      <div class="border-t border-neutral-200 dark:border-neutral-700 pt-6 mt-6">
        <h3 class="text-sm font-medium text-red-600 dark:text-red-400 mb-3">
          {{ $t('profile.data_privacy.danger_zone') }}
        </h3>

        <UiAlert variant="error" :title="$t('profile.data_privacy.delete_account_title')">
          <p class="text-xs mb-3">{{ $t('profile.data_privacy.delete_account_warning') }}</p>
          <UiButton variant="error" size="sm" :icon="Trash2" @click="showDeleteDialog = true">
            {{ $t('profile.data_privacy.delete_account_button') }}
          </UiButton>
        </UiAlert>
      </div>
    </div>

    <!-- Delete Account Confirmation Dialog -->
    <Teleport to="body">
      <div
        v-if="showDeleteDialog"
        class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50"
        @click.self="showDeleteDialog = false"
      >
        <div class="bg-white dark:bg-neutral-800 rounded-xl shadow-xl max-w-md w-full p-6">
          <div class="flex items-center gap-3 mb-4">
            <div class="w-10 h-10 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
              <AlertTriangle class="w-5 h-5 text-red-600 dark:text-red-400" />
            </div>
            <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
              {{ $t('profile.data_privacy.delete_confirm_title') }}
            </h3>
          </div>

          <p class="text-sm text-neutral-600 dark:text-neutral-400 mb-4">
            {{ $t('profile.data_privacy.delete_confirm_message') }}
          </p>

          <div class="mb-4">
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
              {{ $t('profile.data_privacy.delete_confirm_label') }}
            </label>
            <input
              v-model="deleteConfirmation"
              type="text"
              :placeholder="$t('profile.data_privacy.delete_confirm_placeholder')"
              class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-error"
            />
          </div>

          <UiAlert v-if="deleteError" variant="error" class="mb-4">{{ deleteError }}</UiAlert>

          <div class="flex gap-3">
            <UiButton variant="outline" class="flex-1" @click="showDeleteDialog = false; deleteConfirmation = ''; deleteError = ''">
              {{ $t('common.cancel') }}
            </UiButton>
            <UiButton variant="error" class="flex-1" :loading="deleting" :disabled="deleteConfirmation !== 'DELETE' || deleting" @click="deleteAccount">
              {{ deleting ? $t('profile.data_privacy.deleting') : $t('profile.data_privacy.delete_confirm_button') }}
            </UiButton>
          </div>
        </div>
      </div>
    </Teleport>
  </AccordionSection>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Shield, Download, Info, FileArchive, Check, Scale, AlertTriangle, Trash2 } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'
import { useToastStore } from '~/stores/toast'
import AccordionSection from './AccordionSection.vue'

const props = defineProps<{
  openSections: string[]
  animationEnabled?: boolean
}>()

const emit = defineEmits<{
  'toggle': [sectionId: string]
}>()

const { t: $t } = useI18n()
const localePath = useLocalePath()
const authStore = useAuthStore()
const toastStore = useToastStore()

const exporting = ref(false)
const exportHistory = ref<any[]>([])

// Delete account state
const showDeleteDialog = ref(false)
const deleteConfirmation = ref('')
const deleting = ref(false)
const deleteError = ref('')

onMounted(async () => {
  await loadExportHistory()
})

async function loadExportHistory() {
  try {
    // Ensure we have a JWT token before making the request
    await authStore.ensureToken()
    if (!authStore.token) return

    const response = await $fetch('/api/v1/audit/export/history', {
      method: 'GET',
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`
      }
    })
    exportHistory.value = response.exports || []
  } catch (error) {
    console.error('Failed to load export history:', error)
  }
}

async function exportAllData() {
  try {
    exporting.value = true

    // Ensure we have a JWT token before making the request
    await authStore.ensureToken()
    if (!authStore.token) {
      toastStore.error($t('profile.data_privacy.export_failed'))
      return
    }

    const response = await $fetch('/api/v1/audit/export/full', {
      method: 'GET',
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`
      },
      responseType: 'blob'
    })

    // Create download link
    const url = window.URL.createObjectURL(response)
    const a = document.createElement('a')
    a.href = url
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5)
    a.download = `parahub_export_${timestamp}.zip`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)

    toastStore.success($t('profile.data_privacy.export_success'))

    // Reload history
    await loadExportHistory()
  } catch (error) {
    console.error('Failed to export data:', error)
    toastStore.error($t('profile.data_privacy.export_failed'))
  } finally {
    exporting.value = false
  }
}

function getExportTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    'full': $t('profile.data_privacy.export_type_full'),
    'contract': $t('profile.data_privacy.export_type_contract'),
    'debt': $t('profile.data_privacy.export_type_debt'),
    'verifications': $t('profile.data_privacy.export_type_verifications'),
  }
  return labels[type] || type
}

function formatDate(dateString: string): string {
  const date = new Date(dateString)
  return date.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}

async function deleteAccount() {
  if (deleteConfirmation.value !== 'DELETE') return

  try {
    deleting.value = true
    deleteError.value = ''

    await $fetch('/api/v1/auth/delete-account/', {
      method: 'POST',
      credentials: 'include',
      body: { confirmation: 'DELETE' }
    })

    // Account deleted - redirect to home
    toastStore.success($t('profile.data_privacy.delete_success'))

    // Clear auth store and redirect
    authStore.logout()
    window.location.href = localePath('/about')

  } catch (err) {
    deleteError.value = err?.data?.detail || $t('profile.data_privacy.delete_failed')
  } finally {
    deleting.value = false
  }
}
</script>
