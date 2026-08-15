<template>
  <IoTDeviceSection :title="$t('iot.sharing_title')" :help="$t('iot.section_sharing_help')" :icon="Users">
    <div v-if="loading" class="py-8 text-center text-neutral-500 dark:text-neutral-400" role="status">
      <Loader2 class="w-6 h-6 animate-spin mx-auto" aria-hidden="true" />
      <span class="sr-only">{{ $t('iot.loading') }}</span>
    </div>

    <template v-else-if="access">
      <!-- Owner + grantees as one flush list -->
      <div class="border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700">
        <div class="flex items-center justify-between gap-2 px-3 py-2 text-sm">
          <div class="min-w-0">
            <span class="text-neutral-900 dark:text-neutral-100 font-medium">{{ access.owner_name }}</span>
            <span v-if="access.owner_hna" class="text-neutral-500 dark:text-neutral-400 ml-1.5 text-xs">{{ access.owner_hna }}</span>
          </div>
          <UiBadge variant="neutral" type="soft" size="sm">{{ $t('iot.role_owner') }}</UiBadge>
        </div>

        <div v-for="g in access.grants" :key="g.id" class="flex items-center justify-between gap-2 px-3 py-2 text-sm">
          <div class="min-w-0 flex-1">
            <span class="text-neutral-900 dark:text-neutral-100">{{ g.profile_name }}</span>
            <span v-if="g.profile_hna" class="text-neutral-500 dark:text-neutral-400 ml-1.5 text-xs">{{ g.profile_hna }}</span>
          </div>
          <div class="flex items-center gap-2 shrink-0">
            <UiBadge :variant="g.role === 'MANAGER' ? 'secondary' : 'neutral'" type="soft" size="sm">
              {{ g.role === 'MANAGER' ? $t('iot.role_manager') : $t('iot.role_viewer') }}
            </UiBadge>
            <UiButton
              v-if="access.is_owner || g.profile_id === myProfileId"
              variant="ghost" size="sm" :icon="X" icon-only
              :aria-label="$t('iot.sharing_revoke')" @click="revoke(g)"
            />
          </div>
        </div>
      </div>

      <p v-if="!access.grants.length" class="text-sm text-neutral-500 dark:text-neutral-400 mt-2">
        {{ $t('iot.sharing_empty') }}
      </p>

      <UiAlert v-if="error" variant="error" class="mt-3">{{ error }}</UiAlert>

      <!-- Grant access -->
      <form v-if="access.is_owner" class="mt-4" @submit.prevent="grant">
        <label for="share-handle" class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
          {{ $t('iot.sharing_add_label') }}
        </label>
        <div class="flex gap-2">
          <input
            id="share-handle" v-model="handle" type="text" :placeholder="$t('iot.sharing_handle_placeholder')"
            class="flex-1 min-w-0 px-3 py-2 text-sm rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
          />
          <select
            v-model="role" :aria-label="$t('iot.sharing_role')"
            class="px-2 py-2 text-sm rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
          >
            <option value="VIEWER">{{ $t('iot.role_viewer') }}</option>
            <option value="MANAGER">{{ $t('iot.role_manager') }}</option>
          </select>
        </div>
        <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
          {{ role === 'MANAGER' ? $t('iot.role_manager_hint') : $t('iot.role_viewer_hint') }}
        </p>
        <UiButton type="submit" variant="primary" size="sm" class="mt-3" :loading="busy" :disabled="!handle.trim()">
          {{ $t('iot.sharing_add') }}
        </UiButton>
      </form>

      <!-- Hand the device over for good -->
      <div v-if="access.is_owner" class="mt-6 pt-4 border-t border-neutral-200 dark:border-neutral-700">
        <div class="font-medium text-sm text-neutral-900 dark:text-neutral-100">{{ $t('iot.transfer_title') }}</div>
        <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-1 mb-2">{{ $t('iot.transfer_desc') }}</p>
        <input
          v-model="transferHandle" type="text" :placeholder="$t('iot.sharing_handle_placeholder')" :aria-label="$t('iot.transfer_title')"
          class="w-full px-3 py-2 text-sm rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
        />
        <label class="flex items-center gap-2 mt-2 text-sm text-neutral-700 dark:text-neutral-300">
          <input v-model="keepAccess" type="checkbox" class="w-4 h-4 rounded border-neutral-300 dark:border-neutral-600 text-secondary focus:ring-primary" />
          {{ $t('iot.transfer_keep_access') }}
        </label>
        <UiAlert v-if="transferError" variant="error" class="mt-2">{{ transferError }}</UiAlert>
        <UiButton
          :variant="transferArmed ? 'error' : 'outline-error'" size="sm" class="mt-3"
          :loading="busy" :disabled="!transferHandle.trim()" @click="transfer"
        >
          {{ transferArmed ? $t('iot.transfer_sure') : $t('iot.transfer_button') }}
        </UiButton>
      </div>
    </template>

    <UiAlert v-else-if="error" variant="error">{{ error }}</UiAlert>
  </IoTDeviceSection>
</template>

<script setup lang="ts">
import { Loader2, Users, X } from 'lucide-vue-next'
import type { AccessGrant, DeviceAccess } from '~/stores/iot'

interface Props {
  deviceId: string
}

const props = defineProps<Props>()
// Ownership left this account (transfer, or a grantee leaving) — the device is
// gone from our list, so the page has to leave too.
const emit = defineEmits<{ (e: 'detached'): void }>()

const store = useIoTStore()
const toastStore = useToastStore()
const authStore = useAuthStore()
const { t } = useI18n()

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
  loading.value = true
  error.value = null
  try {
    access.value = await store.getDeviceAccess(props.deviceId)
  } catch (err: any) {
    error.value = grantError(err)
  } finally {
    loading.value = false
  }
}

onMounted(load)
onUnmounted(() => { if (disarmTimer) clearTimeout(disarmTimer) })

function grantError(err: any): string {
  const status = err?.status || err?.statusCode
  if (status === 404) return t('iot.sharing_profile_not_found')
  return err?.data?.detail || err?.message || t('iot.sharing_failed')
}

async function grant() {
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

async function revoke(g: AccessGrant) {
  if (busy.value) return
  busy.value = true
  error.value = null
  try {
    await store.revokeDeviceAccess(props.deviceId, g.id)
    if (!access.value?.is_owner && g.profile_id === myProfileId.value) {
      await store.fetchDevices()
      emit('detached')
      return
    }
    await load()
  } catch (err: any) {
    error.value = grantError(err)
  } finally {
    busy.value = false
  }
}

async function transfer() {
  if (busy.value || !transferHandle.value.trim()) return
  // Two-tap: the first press arms, the second executes
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
    emit('detached')
  } catch (err: any) {
    transferError.value = grantError(err)
    transferArmed.value = false
  } finally {
    busy.value = false
  }
}
</script>
