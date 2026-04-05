<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" @click.self="$emit('close')">
    <div class="bg-white dark:bg-neutral-800 rounded-xl shadow-2xl w-full max-w-md p-6">
      <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4">
        {{ $t('mesh.vpn_title') }}
      </h3>

      <!-- Loading state -->
      <div v-if="statusLoading" class="flex items-center gap-3 py-8 justify-center text-neutral-500 dark:text-neutral-400">
        <Loader2 class="w-5 h-5 animate-spin" />
        {{ $t('mesh.mullvad_loading') }}
      </div>

      <!-- Status loaded -->
      <template v-else>
        <!-- Current mode indicator -->
        <div class="mb-4 p-3 rounded-lg border" :class="modeClass">
          <div class="font-medium text-sm">
            {{ mullvadStatus?.mode === 'mullvad' ? $t('mesh.mullvad_mode_mullvad') : $t('mesh.mullvad_mode_vps') }}
          </div>
          <div class="text-xs mt-1 opacity-80">
            {{ mullvadStatus?.mode === 'mullvad' ? $t('mesh.mullvad_mode_mullvad_desc') : $t('mesh.mullvad_mode_vps_desc') }}
          </div>
        </div>

        <!-- Mullvad details (when active) -->
        <div v-if="mullvadStatus?.mode === 'mullvad'" class="space-y-2 mb-4">
          <div v-if="mullvadStatus.account" class="flex justify-between text-sm">
            <span class="text-neutral-500 dark:text-neutral-400">{{ $t('mesh.mullvad_account') }}:</span>
            <span class="font-mono text-neutral-900 dark:text-neutral-100">{{ mullvadStatus.account }}</span>
          </div>
          <div v-if="mullvadStatus.country" class="flex justify-between text-sm">
            <span class="text-neutral-500 dark:text-neutral-400">{{ $t('mesh.mullvad_country') }}:</span>
            <span class="text-neutral-900 dark:text-neutral-100 uppercase">{{ mullvadStatus.country }}</span>
          </div>
          <div v-if="mullvadStatus.server" class="flex justify-between text-sm">
            <span class="text-neutral-500 dark:text-neutral-400">{{ $t('mesh.mullvad_server') }}:</span>
            <span class="font-mono text-xs text-neutral-900 dark:text-neutral-100">{{ mullvadStatus.server }}</span>
          </div>
          <div v-if="mullvadStatus.local_ip" class="flex justify-between text-sm">
            <span class="text-neutral-500 dark:text-neutral-400">{{ $t('mesh.mullvad_local_ip') }}:</span>
            <span class="font-mono text-neutral-900 dark:text-neutral-100">{{ mullvadStatus.local_ip }}</span>
          </div>
        </div>

        <!-- Setup form (when VPS mode) -->
        <div v-if="mullvadStatus?.mode === 'vps' && !setupDone" class="mb-4">
          <p class="text-sm text-neutral-600 dark:text-neutral-400 mb-3">
            {{ $t('mesh.mullvad_setup_desc') }}
          </p>

          <div class="mb-3">
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              {{ $t('mesh.mullvad_account_key') }}
            </label>
            <input
              v-model="accountKey"
              type="text"
              maxlength="16"
              inputmode="numeric"
              pattern="[0-9]*"
              class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 font-mono focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
              :placeholder="$t('mesh.mullvad_account_placeholder')"
            />
          </div>

          <div class="mb-3">
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              {{ $t('mesh.mullvad_country') }}
            </label>
            <input
              v-model="country"
              type="text"
              maxlength="2"
              class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
              :placeholder="$t('mesh.mullvad_country_placeholder')"
            />
          </div>
        </div>

        <!-- Success messages -->
        <UiAlert v-if="successMessage" variant="success" class="mb-4">{{ successMessage }}</UiAlert>

        <!-- Error -->
        <UiAlert v-if="error" variant="error" class="mb-4">{{ error }}</UiAlert>

        <!-- Remove confirmation -->
        <UiAlert v-if="confirmRemove" variant="warning" class="mb-4">{{ $t('mesh.mullvad_remove_confirm') }}</UiAlert>

        <!-- Actions -->
        <div class="flex justify-end gap-3">
          <button
            @click="$emit('close')"
            class="px-4 py-2 text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded-lg"
            :disabled="actionLoading"
          >
            {{ $t('mesh.cancel') }}
          </button>

          <!-- Setup button (VPS mode) -->
          <button
            v-if="mullvadStatus?.mode === 'vps' && !setupDone"
            @click="handleSetup"
            :disabled="actionLoading || accountKey.length !== 16"
            class="btn-secondary btn-sm flex items-center gap-2"
          >
            <Loader2 v-if="actionLoading" class="w-4 h-4 animate-spin" />
            {{ actionLoading ? $t('mesh.mullvad_setting_up') : $t('mesh.mullvad_setup') }}
          </button>

          <!-- Remove button (Mullvad mode) -->
          <template v-if="mullvadStatus?.mode === 'mullvad'">
            <button
              v-if="!confirmRemove"
              @click="confirmRemove = true"
              :disabled="actionLoading"
              class="btn-error btn-sm"
            >
              {{ $t('mesh.mullvad_remove') }}
            </button>
            <button
              v-else
              @click="handleRemove"
              :disabled="actionLoading"
              class="btn-error btn-sm flex items-center gap-2"
            >
              <Loader2 v-if="actionLoading" class="w-4 h-4 animate-spin" />
              {{ actionLoading ? $t('mesh.mullvad_removing') : $t('mesh.mullvad_remove') }}
            </button>
          </template>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Loader2 } from 'lucide-vue-next'

interface Props {
  deviceId: string
}

interface Emits {
  (e: 'close'): void
}

const props = defineProps<Props>()
defineEmits<Emits>()
const { t } = useI18n()
const store = useIoTStore()

const statusLoading = ref(true)
const actionLoading = ref(false)
const error = ref<string | null>(null)
const successMessage = ref<string | null>(null)
const confirmRemove = ref(false)
const setupDone = ref(false)

const mullvadStatus = ref<{
  mode: string
  account?: string
  country?: string
  server?: string
  server_ip?: string
  local_ip?: string
} | null>(null)

// Setup form
const accountKey = ref('')
const country = ref('')

// Computed mode class
const modeClass = computed(() => {
  if (mullvadStatus.value?.mode === 'mullvad') {
    return 'bg-success/10 dark:bg-success/20 border-success/30 dark:border-success/40 text-success dark:text-success-400'
  }
  return 'bg-secondary-50 dark:bg-secondary-900/20 border-secondary-200 dark:border-secondary-800 text-secondary-800 dark:text-secondary-200'
})

// Load status on mount
onMounted(async () => {
  try {
    mullvadStatus.value = await store.getMullvadStatus(props.deviceId)
  } catch (err: any) {
    error.value = err.message
  } finally {
    statusLoading.value = false
  }
})

const handleSetup = async () => {
  if (actionLoading.value) return
  actionLoading.value = true
  error.value = null
  successMessage.value = null

  try {
    const result = await store.setupMullvad(props.deviceId, accountKey.value, country.value)
    mullvadStatus.value = {
      mode: 'mullvad',
      country: result.country ?? undefined,
      server: result.server ?? undefined,
    }
    successMessage.value = t('mesh.mullvad_setup_success')
    setupDone.value = true
    // Refresh status to get full details
    try {
      mullvadStatus.value = await store.getMullvadStatus(props.deviceId)
    } catch { /* ignore, we already have basic info */ }
  } catch (err: any) {
    error.value = err.message
  } finally {
    actionLoading.value = false
  }
}

const handleRemove = async () => {
  if (actionLoading.value) return
  actionLoading.value = true
  error.value = null
  successMessage.value = null
  confirmRemove.value = false

  try {
    await store.removeMullvad(props.deviceId)
    mullvadStatus.value = { mode: 'vps' }
    successMessage.value = t('mesh.mullvad_remove_success')
    setupDone.value = false
  } catch (err: any) {
    error.value = err.message
  } finally {
    actionLoading.value = false
  }
}
</script>
