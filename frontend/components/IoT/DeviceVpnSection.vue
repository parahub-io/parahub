<template>
  <IoTDeviceSection :title="$t('mesh.mullvad_title')" :help="$t('iot.section_vpn_help')" :icon="Shield">
    <div v-if="loading" class="py-8 text-center text-neutral-500 dark:text-neutral-400" role="status">
      <Loader2 class="w-6 h-6 animate-spin mx-auto" aria-hidden="true" />
      <span class="sr-only">{{ $t('mesh.mullvad_loading') }}</span>
    </div>

    <template v-else>
      <!-- Which tunnel the guest traffic is leaving through right now. Only
           rendered once the router actually answered — defaulting the ternary
           to "VPS" would assert a mode nobody read. -->
      <div v-if="status" class="p-3 rounded-lg border" :class="modeClass">
        <div class="font-medium text-sm">
          {{ status?.mode === 'mullvad' ? $t('mesh.mullvad_mode_mullvad') : $t('mesh.mullvad_mode_vps') }}
        </div>
        <div class="text-xs mt-1 opacity-80">
          {{ status?.mode === 'mullvad' ? $t('mesh.mullvad_mode_mullvad_desc') : $t('mesh.mullvad_mode_vps_desc') }}
        </div>
      </div>

      <dl v-if="status?.mode === 'mullvad'" class="mt-3 space-y-1.5">
        <div v-if="status.account" class="flex justify-between gap-2 text-sm">
          <dt class="text-neutral-500 dark:text-neutral-400">{{ $t('mesh.mullvad_account') }}</dt>
          <dd class="font-mono text-neutral-900 dark:text-neutral-100 truncate">{{ status.account }}</dd>
        </div>
        <div v-if="status.country" class="flex justify-between gap-2 text-sm">
          <dt class="text-neutral-500 dark:text-neutral-400">{{ $t('mesh.mullvad_country') }}</dt>
          <dd class="text-neutral-900 dark:text-neutral-100 uppercase">{{ status.country }}</dd>
        </div>
        <div v-if="status.server" class="flex justify-between gap-2 text-sm">
          <dt class="text-neutral-500 dark:text-neutral-400">{{ $t('mesh.mullvad_server') }}</dt>
          <dd class="font-mono text-xs text-neutral-900 dark:text-neutral-100 truncate">{{ status.server }}</dd>
        </div>
        <div v-if="status.local_ip" class="flex justify-between gap-2 text-sm">
          <dt class="text-neutral-500 dark:text-neutral-400">{{ $t('mesh.mullvad_local_ip') }}</dt>
          <dd class="font-mono text-neutral-900 dark:text-neutral-100">{{ status.local_ip }}</dd>
        </div>
      </dl>

      <!-- Upgrade path: swap the shared VPS hop for the owner's own Mullvad account -->
      <form v-if="status?.mode === 'vps'" class="mt-3" @submit.prevent="setup">
        <p class="text-sm text-neutral-600 dark:text-neutral-400 mb-3">{{ $t('mesh.mullvad_setup_desc') }}</p>
        <div class="grid gap-3 sm:grid-cols-2">
          <div>
            <label for="mullvad-account" class="block text-xs font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              {{ $t('mesh.mullvad_account_key') }}
            </label>
            <input
              id="mullvad-account" v-model="accountKey" type="text" maxlength="16" inputmode="numeric" pattern="[0-9]*"
              :placeholder="$t('mesh.mullvad_account_placeholder')" class="field font-mono"
            />
          </div>
          <div>
            <label for="mullvad-country" class="block text-xs font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              {{ $t('mesh.mullvad_country') }}
            </label>
            <input
              id="mullvad-country" v-model="country" type="text" maxlength="2"
              :placeholder="$t('mesh.mullvad_country_placeholder')" class="field"
            />
          </div>
        </div>
        <UiButton type="submit" variant="secondary" size="sm" class="mt-3" :loading="busy" :disabled="accountKey.length !== 16">
          {{ busy ? $t('mesh.mullvad_setting_up') : $t('mesh.mullvad_setup') }}
        </UiButton>
      </form>

      <div v-if="status?.mode === 'mullvad'" class="mt-3">
        <UiAlert v-if="confirmRemove" variant="warning" class="mb-3">{{ $t('mesh.mullvad_remove_confirm') }}</UiAlert>
        <UiButton :variant="confirmRemove ? 'error' : 'outline-error'" size="sm" :loading="busy" @click="remove">
          {{ $t('mesh.mullvad_remove') }}
        </UiButton>
      </div>

      <UiAlert v-if="success" variant="success" class="mt-3">{{ success }}</UiAlert>
      <UiAlert v-if="error" variant="error" class="mt-3">{{ error }}</UiAlert>
    </template>
  </IoTDeviceSection>
</template>

<script setup lang="ts">
import { Loader2, Shield } from 'lucide-vue-next'

/** Rendered only for a MANAGER+ on a bumblebee — every Mullvad endpoint is MANAGER-gated. */
interface Props {
  deviceId: string
}

const props = defineProps<Props>()
const store = useIoTStore()
const { t } = useI18n()
const { deviceErrorText } = useIoT()

const loading = ref(true)
const busy = ref(false)
const error = ref<string | null>(null)
const success = ref<string | null>(null)
const confirmRemove = ref(false)
let disarmTimer: ReturnType<typeof setTimeout> | null = null

const status = ref<{
  mode: string
  account?: string
  country?: string
  server?: string
  server_ip?: string
  local_ip?: string
} | null>(null)

const accountKey = ref('')
const country = ref('')

const modeClass = computed(() =>
  status.value?.mode === 'mullvad'
    ? 'bg-success/10 dark:bg-success/20 border-success/30 dark:border-success/40 text-success dark:text-success-400'
    : 'bg-secondary-50 dark:bg-secondary-900/20 border-secondary-200 dark:border-secondary-800 text-secondary-800 dark:text-secondary-200')

async function load() {
  loading.value = true
  error.value = null
  success.value = null
  try {
    status.value = await store.getMullvadStatus(props.deviceId)
  } catch (err: any) {
    // Leave `status` null — the card must not name a tunnel mode it never read
    status.value = null
    error.value = deviceErrorText(err)
  } finally {
    loading.value = false
  }
}

onMounted(load)

onUnmounted(() => { if (disarmTimer) clearTimeout(disarmTimer) })

async function setup() {
  if (busy.value) return
  busy.value = true
  error.value = null
  success.value = null
  try {
    await store.setupMullvad(props.deviceId, accountKey.value, country.value)
    success.value = t('mesh.mullvad_setup_success')
    accountKey.value = ''
    // The setup response carries only country/server — re-read for the full block
    try { status.value = await store.getMullvadStatus(props.deviceId) } catch { status.value = { mode: 'mullvad' } }
  } catch (err: any) {
    error.value = deviceErrorText(err)
  } finally {
    busy.value = false
  }
}

async function remove() {
  if (busy.value) return
  // Two-tap: the first press arms, the second executes (design system § Destructive)
  if (!confirmRemove.value) {
    confirmRemove.value = true
    disarmTimer = setTimeout(() => { confirmRemove.value = false }, 3000)
    return
  }
  if (disarmTimer) clearTimeout(disarmTimer)
  confirmRemove.value = false
  busy.value = true
  error.value = null
  success.value = null
  try {
    await store.removeMullvad(props.deviceId)
    status.value = { mode: 'vps' }
    success.value = t('mesh.mullvad_remove_success')
  } catch (err: any) {
    error.value = deviceErrorText(err)
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.field {
  @apply w-full px-3 py-2 text-sm rounded-lg border border-neutral-300 dark:border-neutral-600;
  @apply bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100;
  @apply focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent;
}
</style>
