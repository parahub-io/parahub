<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" @click.self="$emit('close')">
    <div class="bg-white dark:bg-neutral-800 rounded-xl shadow-2xl w-full max-w-md p-6">
      <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4">
        {{ $t('mesh.wifi_settings') }}
      </h3>

      <!-- SSID -->
      <div class="mb-4">
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
          {{ $t('mesh.wifi_ssid') }}
        </label>
        <input
          v-model="ssid"
          type="text"
          maxlength="32"
          class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
          :placeholder="currentSsid"
        />
      </div>

      <!-- Password -->
      <div class="mb-4">
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
          {{ $t('mesh.wifi_password') }}
        </label>
        <div class="relative">
          <input
            v-model="password"
            :type="showPassword ? 'text' : 'password'"
            minlength="8"
            maxlength="63"
            class="w-full px-3 py-2 pr-10 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
            placeholder="8-63 characters"
          />
          <button
            type="button"
            @click="showPassword = !showPassword"
            class="absolute right-2 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300"
          >
            <Eye v-if="showPassword" class="w-4 h-4" />
            <EyeOff v-else class="w-4 h-4" />
          </button>
        </div>
      </div>

      <!-- Apply to all -->
      <div class="mb-4">
        <label class="flex items-center gap-2 cursor-pointer">
          <input
            v-model="applyToAll"
            type="checkbox"
            class="w-4 h-4 text-secondary border-neutral-300 rounded focus:ring-primary"
          />
          <span class="text-sm text-neutral-700 dark:text-neutral-300">
            {{ $t('mesh.apply_to_all') }}
          </span>
        </label>
        <p v-if="applyToAll" class="mt-1 text-xs text-amber-600 dark:text-amber-400">
          {{ $t('mesh.apply_to_all_warning') }}
        </p>
      </div>

      <!-- Result -->
      <div v-if="result" class="mb-4 p-3 rounded-lg text-sm" :class="resultClass">
        <div v-if="result.failed === 0" class="font-medium">
          {{ $t('mesh.wifi_updated', { updated: result.updated }) }}
        </div>
        <div v-else class="font-medium">
          {{ $t('mesh.wifi_update_partial', { updated: result.updated, failed: result.failed }) }}
        </div>
        <div v-for="r in result.results" :key="r.device_id" class="mt-1">
          <span :class="r.success ? 'text-green-700 dark:text-green-400' : 'text-red-700 dark:text-red-400'">
            {{ r.name }}: {{ r.success ? '✓' : r.error }}
          </span>
        </div>
      </div>

      <!-- Error -->
      <UiAlert v-if="error" variant="error" class="mb-4">{{ error }}</UiAlert>

      <!-- Actions -->
      <div class="flex justify-end gap-3">
        <button
          @click="$emit('close')"
          class="px-4 py-2 text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded-lg"
          :disabled="loading"
        >
          {{ $t('mesh.cancel') }}
        </button>
        <button
          @click="handleSave"
          :disabled="loading || (!ssid && !password)"
          class="btn-secondary btn-sm flex items-center gap-2"
        >
          <Loader2 v-if="loading" class="w-4 h-4 animate-spin" />
          {{ loading ? $t('mesh.updating_wifi') : $t('mesh.save') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Eye, EyeOff, Loader2 } from 'lucide-vue-next'
import type { WifiConfigResponse } from '~/stores/iot'

interface Props {
  deviceId: string
  currentSsid?: string
}

interface Emits {
  (e: 'close'): void
  (e: 'updated'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()
const store = useIoTStore()

const ssid = ref(props.currentSsid || '')
const password = ref('')
const showPassword = ref(false)
const applyToAll = ref(true)
const loading = ref(false)
const error = ref<string | null>(null)
const result = ref<WifiConfigResponse | null>(null)

const resultClass = computed(() => {
  if (!result.value) return ''
  if (result.value.failed === 0) return 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400'
  return 'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400'
})

const handleSave = async () => {
  if (loading.value) return
  loading.value = true
  error.value = null
  result.value = null

  try {
    const config: Record<string, any> = { apply_to_all: applyToAll.value }
    if (ssid.value && ssid.value !== props.currentSsid) config.wifi_ssid = ssid.value
    if (password.value) config.wifi_password = password.value

    if (!config.wifi_ssid && !config.wifi_password) {
      error.value = 'No changes to apply'
      loading.value = false
      return
    }

    result.value = await store.updateWifiConfig(props.deviceId, config)
    emit('updated')
  } catch (err: any) {
    error.value = err.message || 'Failed to update WiFi config'
  } finally {
    loading.value = false
  }
}
</script>
