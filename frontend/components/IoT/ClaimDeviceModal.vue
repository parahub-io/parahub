<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" @click.self="$emit('close')">
    <div class="bg-white dark:bg-neutral-800 rounded-xl shadow-2xl w-full max-w-md p-6">
      <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-1">
        {{ $t('iot.claim_title') }}
      </h3>
      <p class="text-sm text-neutral-500 dark:text-neutral-400 mb-4">
        {{ $t('iot.claim_intro') }}
      </p>

      <!-- Step 1: MAC input -->
      <template v-if="!preview">
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1" for="claim-mac">
          {{ $t('iot.claim_mac_label') }}
        </label>
        <input
          id="claim-mac"
          v-model="mac"
          type="text"
          placeholder="AA:BB:CC:DD:EE:FF"
          class="w-full px-3 py-2 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 font-mono focus:ring-2 focus:ring-primary focus:border-transparent outline-none"
          @keydown.enter="handlePreview"
        />
        <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
          {{ $t('iot.claim_mac_hint') }}
        </p>

        <div v-if="error" class="mt-3 text-sm text-red-600 dark:text-red-400">{{ error }}</div>

        <div class="flex justify-end gap-2 mt-5">
          <UiButton variant="ghost" size="sm" @click="$emit('close')">{{ $t('iot.cancel') }}</UiButton>
          <UiButton variant="primary" size="sm" :loading="busy" :disabled="!mac.trim()" @click="handlePreview">
            {{ $t('iot.claim_find') }}
          </UiButton>
        </div>
      </template>

      <!-- Step 2: preview + confirm -->
      <template v-else>
        <div class="p-4 rounded-lg border border-neutral-200 dark:border-neutral-700 mb-4">
          <div class="flex items-center justify-between mb-2">
            <span class="font-semibold text-neutral-900 dark:text-neutral-100">{{ preview.name }}</span>
            <span class="flex items-center gap-1.5 text-xs" role="status">
              <span class="w-2 h-2 rounded-full" :class="preview.online ? 'bg-green-500' : 'bg-red-500'" />
              {{ preview.online ? $t('iot.status_online') : $t('iot.status_offline') }}
            </span>
          </div>
          <div class="space-y-1 text-sm text-neutral-500 dark:text-neutral-400">
            <div v-if="preview.hardware_profile" class="flex justify-between">
              <span>{{ $t('iot.claim_hardware') }}</span>
              <span class="text-neutral-900 dark:text-neutral-100">{{ getHardwareName(preview.hardware_profile) }}</span>
            </div>
            <div v-if="preview.last_seen" class="flex justify-between">
              <span>{{ $t('iot.last_heartbeat') }}</span>
              <span class="text-neutral-900 dark:text-neutral-100">{{ formatRelativeTime(preview.last_seen) }}</span>
            </div>
          </div>
        </div>

        <div v-if="error" class="mb-3 text-sm text-red-600 dark:text-red-400">{{ error }}</div>

        <div class="flex justify-end gap-2">
          <UiButton variant="ghost" size="sm" @click="preview = null; error = null">{{ $t('iot.back') }}</UiButton>
          <UiButton variant="primary" size="sm" :loading="busy" @click="handleClaim">
            {{ $t('iot.claim_confirm') }}
          </UiButton>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { ClaimPreview } from '~/stores/iot'

interface Emits {
  (e: 'close'): void
  (e: 'claimed'): void
}

const emit = defineEmits<Emits>()
const store = useIoTStore()
const toastStore = useToastStore()
const { t } = useI18n()
const { getHardwareName, formatRelativeTime } = useIoT()

const mac = ref('')
const preview = ref<ClaimPreview | null>(null)
const busy = ref(false)
const error = ref<string | null>(null)

function claimError(err: any): string {
  const status = err?.status || err?.statusCode
  if (status === 404) return t('iot.claim_not_found')
  if (status === 429) return t('iot.claim_rate_limited')
  if (status === 400) return t('iot.claim_bad_mac')
  return err?.data?.detail || err?.message || t('iot.claim_failed')
}

async function handlePreview() {
  if (busy.value || !mac.value.trim()) return
  busy.value = true
  error.value = null
  try {
    preview.value = await store.claimPreview(mac.value)
  } catch (err: any) {
    error.value = claimError(err)
  } finally {
    busy.value = false
  }
}

async function handleClaim() {
  if (busy.value) return
  busy.value = true
  error.value = null
  try {
    const res = await store.claimDevice(mac.value)
    toastStore.success(t('iot.claim_success', { name: res.name }))
    emit('claimed')
    emit('close')
  } catch (err: any) {
    error.value = claimError(err)
  } finally {
    busy.value = false
  }
}
</script>
