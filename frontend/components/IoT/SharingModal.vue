<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" @click.self="$emit('close')">
    <div class="bg-white dark:bg-neutral-800 rounded-xl shadow-2xl w-full max-w-md p-6">
      <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-1">
        {{ $t('iot.sharing_title') }}
      </h3>
      <p class="text-sm text-neutral-500 dark:text-neutral-400 mb-4 truncate">{{ deviceName }}</p>

      <div v-if="loading" class="flex items-center gap-3 py-8 justify-center text-neutral-500 dark:text-neutral-400" role="status">
        <Loader2 class="w-5 h-5 animate-spin" aria-hidden="true" />
        <span class="sr-only">Loading</span>
      </div>

      <template v-else-if="access">
        <!-- Owner row -->
        <div class="flex items-center justify-between py-2 text-sm">
          <div class="min-w-0">
            <span class="text-neutral-900 dark:text-neutral-100 font-medium">{{ access.owner_name }}</span>
            <span v-if="access.owner_hna" class="text-neutral-500 dark:text-neutral-400 ml-1.5 text-xs">{{ access.owner_hna }}</span>
          </div>
          <UiBadge variant="primary" type="soft" size="sm">{{ $t('iot.role_owner') }}</UiBadge>
        </div>

        <!-- Grants (flush list) -->
        <div v-if="access.grants.length" class="border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700 mb-3">
          <div v-for="g in access.grants" :key="g.id" class="flex items-center justify-between px-3 py-2 text-sm">
            <div class="min-w-0 flex-1">
              <span class="text-neutral-900 dark:text-neutral-100">{{ g.profile_name }}</span>
              <span v-if="g.profile_hna" class="text-neutral-500 dark:text-neutral-400 ml-1.5 text-xs">{{ g.profile_hna }}</span>
            </div>
            <div class="flex items-center gap-2 shrink-0 ml-2">
              <UiBadge :variant="g.role === 'MANAGER' ? 'secondary' : 'neutral'" type="soft" size="sm">
                {{ g.role === 'MANAGER' ? $t('iot.role_manager') : $t('iot.role_viewer') }}
              </UiBadge>
              <button
                v-if="access.is_owner || g.profile_id === myProfileId"
                @click="handleRevoke(g)"
                class="p-1 rounded text-neutral-400 hover:text-red-600 dark:hover:text-red-400 hover:bg-neutral-200 dark:hover:bg-neutral-700 transition-colors"
                :aria-label="$t('iot.sharing_revoke')"
              >
                <X class="w-4 h-4" aria-hidden="true" />
              </button>
            </div>
          </div>
        </div>
        <p v-else class="text-sm text-neutral-500 dark:text-neutral-400 py-2">{{ $t('iot.sharing_empty') }}</p>

        <!-- Add grant (owner only) -->
        <form v-if="access.is_owner" class="mt-2" @submit.prevent="handleGrant">
          <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1" for="share-handle">
            {{ $t('iot.sharing_add_label') }}
          </label>
          <div class="flex gap-2">
            <input
              id="share-handle"
              v-model="handle"
              type="text"
              :placeholder="$t('iot.sharing_handle_placeholder')"
              class="flex-1 min-w-0 px-3 py-2 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none"
            />
            <select
              v-model="role"
              class="px-2 py-2 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none"
              :aria-label="$t('iot.sharing_role')"
            >
              <option value="VIEWER">{{ $t('iot.role_viewer') }}</option>
              <option value="MANAGER">{{ $t('iot.role_manager') }}</option>
            </select>
          </div>
          <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
            {{ role === 'MANAGER' ? $t('iot.role_manager_hint') : $t('iot.role_viewer_hint') }}
          </p>
          <div v-if="error" class="mt-2 text-sm text-red-600 dark:text-red-400">{{ error }}</div>
          <UiButton type="submit" variant="primary" size="sm" class="mt-3 w-full" :loading="busy" :disabled="!handle.trim()">
            {{ $t('iot.sharing_add') }}
          </UiButton>
        </form>

        <!-- Transfer ownership (owner only) -->
        <details v-if="access.is_owner" class="mt-4 border border-neutral-200 dark:border-neutral-700 rounded-lg">
          <summary class="cursor-pointer px-3 py-2 text-sm font-medium text-neutral-500 dark:text-neutral-400 hover:bg-neutral-50 dark:hover:bg-neutral-700/50 rounded-lg transition-colors select-none">
            {{ $t('iot.transfer_title') }}
          </summary>
          <div class="px-3 pb-3 pt-1">
            <p class="text-xs text-neutral-500 dark:text-neutral-400 mb-2">{{ $t('iot.transfer_desc') }}</p>
            <input
              v-model="transferHandle"
              type="text"
              :placeholder="$t('iot.sharing_handle_placeholder')"
              class="w-full px-3 py-2 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none"
            />
            <label class="flex items-center gap-2 mt-2 text-sm text-neutral-700 dark:text-neutral-300">
              <input v-model="keepAccess" type="checkbox" class="rounded border-neutral-300 dark:border-neutral-600" />
              {{ $t('iot.transfer_keep_access') }}
            </label>
            <div v-if="transferError" class="mt-2 text-sm text-red-600 dark:text-red-400">{{ transferError }}</div>
            <UiButton
              :variant="transferArmed ? 'error' : 'outline-error'"
              size="sm"
              class="mt-3 w-full"
              :loading="busy"
              :disabled="!transferHandle.trim()"
              @click="handleTransfer"
            >
              {{ transferArmed ? $t('iot.transfer_sure') : $t('iot.transfer_button') }}
            </UiButton>
          </div>
        </details>
      </template>

      <div v-else-if="error" class="text-sm text-red-600 dark:text-red-400 py-4">{{ error }}</div>

      <div class="flex justify-end mt-5">
        <UiButton variant="ghost" size="sm" @click="$emit('close')">{{ $t('iot.close') }}</UiButton>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Loader2, X } from 'lucide-vue-next'
import type { AccessGrant, DeviceAccess } from '~/stores/iot'

interface Props {
  deviceId: string
  deviceName: string
}

interface Emits {
  (e: 'close'): void
  // Ownership changed (transfer) — parent must refetch the device list
  (e: 'changed'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()
const store = useIoTStore()
const toastStore = useToastStore()
const authStore = useAuthStore()
const { t } = useI18n()

// A grantee may remove their own grant ("leave" the share)
const myProfileId = computed(() => authStore.activeProfile?.id)

const loading = ref(true)
const busy = ref(false)
const access = ref<DeviceAccess | null>(null)
const error = ref<string | null>(null)

const handle = ref('')
const role = ref<'VIEWER' | 'MANAGER'>('VIEWER')

const transferHandle = ref('')
const keepAccess = ref(true)
const transferArmed = ref(false)
const transferError = ref<string | null>(null)
let disarmTimer: ReturnType<typeof setTimeout> | null = null

async function load() {
  try {
    access.value = await store.getDeviceAccess(props.deviceId)
  } catch (err: any) {
    error.value = err?.data?.detail || err?.message || 'Failed to load'
  }
  loading.value = false
}
onMounted(load)
onUnmounted(() => { if (disarmTimer) clearTimeout(disarmTimer) })

function grantError(err: any): string {
  const status = err?.status || err?.statusCode
  if (status === 404) return t('iot.sharing_profile_not_found')
  return err?.data?.detail || err?.message || t('iot.sharing_failed')
}

async function handleGrant() {
  if (busy.value || !handle.value.trim()) return
  busy.value = true
  error.value = null
  try {
    await store.grantDeviceAccess(props.deviceId, handle.value, role.value)
    handle.value = ''
    await load()
  } catch (err: any) {
    error.value = grantError(err)
  } finally {
    busy.value = false
  }
}

async function handleRevoke(g: AccessGrant) {
  if (busy.value) return
  busy.value = true
  try {
    await store.revokeDeviceAccess(props.deviceId, g.id)
    if (!access.value?.is_owner && g.profile_id === myProfileId.value) {
      // Left the share — device is gone from our list, close and refresh
      await store.fetchDevices()
      emit('changed')
      emit('close')
      return
    }
    await load()
  } catch (err: any) {
    error.value = grantError(err)
  } finally {
    busy.value = false
  }
}

async function handleTransfer() {
  if (busy.value || !transferHandle.value.trim()) return
  // Two-tap confirmation: first tap arms, second executes
  if (!transferArmed.value) {
    transferArmed.value = true
    disarmTimer = setTimeout(() => { transferArmed.value = false }, 3000)
    return
  }
  if (disarmTimer) clearTimeout(disarmTimer)
  busy.value = true
  transferError.value = null
  try {
    await store.transferDevice(props.deviceId, transferHandle.value, keepAccess.value)
    toastStore.success(t('iot.transfer_success'))
    emit('changed')
    emit('close')
  } catch (err: any) {
    transferError.value = grantError(err)
    transferArmed.value = false
  } finally {
    busy.value = false
  }
}
</script>
