<template>
  <IoTDeviceSection :title="$t('iot.section_access')" :help="$t('iot.section_access_help')" :icon="KeyRound">
    <div class="space-y-4">
      <!-- ═══ Private WiFi credentials ═══ -->
      <div class="p-3 rounded-lg border border-neutral-200 dark:border-neutral-700">
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <div class="font-medium text-sm text-neutral-900 dark:text-neutral-100">{{ $t('iot.wifi_credentials') }}</div>
            <div class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">{{ $t('iot.wifi_credentials_help') }}</div>
          </div>
          <UiButton
            v-if="!wifi"
            variant="secondary" size="sm" :icon="Wifi" :loading="wifiLoading"
            class="shrink-0" @click="revealWifi"
          >
            {{ $t('iot.show_wifi_password') }}
          </UiButton>
          <UiButton v-else variant="ghost" size="sm" :icon="EyeOff" class="shrink-0" @click="wifi = null">
            {{ $t('iot.hide') }}
          </UiButton>
        </div>

        <UiAlert v-if="wifiError" variant="error" class="mt-3">{{ wifiError }}</UiAlert>

        <!-- Revealed: readable credentials next to a scannable code -->
        <div v-if="wifi" class="mt-3 flex flex-col sm:flex-row gap-4">
          <div class="flex-1 min-w-0 space-y-2">
            <div>
              <div class="text-xs uppercase tracking-wide text-neutral-400 dark:text-neutral-500">{{ $t('mesh.wifi_ssid') }}</div>
              <div class="flex items-center gap-1">
                <span class="font-mono text-sm text-neutral-900 dark:text-neutral-100 truncate">{{ wifi.ssid }}</span>
                <button class="copy-btn" :aria-label="$t('iot.copy')" @click="copy(wifi.ssid)">
                  <Copy class="w-3.5 h-3.5" aria-hidden="true" />
                </button>
              </div>
            </div>
            <div>
              <div class="text-xs uppercase tracking-wide text-neutral-400 dark:text-neutral-500">{{ $t('mesh.wifi_password') }}</div>
              <div class="flex items-center gap-1">
                <span class="font-mono text-sm text-neutral-900 dark:text-neutral-100 break-all">{{ wifi.wifi_password }}</span>
                <button class="copy-btn" :aria-label="$t('iot.copy')" @click="copy(wifi.wifi_password)">
                  <Copy class="w-3.5 h-3.5" aria-hidden="true" />
                </button>
              </div>
            </div>
            <p class="text-xs text-neutral-500 dark:text-neutral-400">{{ $t('iot.wifi_qr_hint') }}</p>
          </div>
          <!-- White plate: a scanner needs the quiet zone light in either theme -->
          <div class="shrink-0 self-start bg-white rounded-lg p-2">
            <canvas ref="qrCanvas" class="w-40 h-40" role="img" :aria-label="$t('iot.wifi_qr_aria')" />
          </div>
        </div>
      </div>

      <!-- ═══ Router administrator password ═══ -->
      <div class="p-3 rounded-lg border border-neutral-200 dark:border-neutral-700">
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <div class="font-medium text-sm text-neutral-900 dark:text-neutral-100">{{ $t('iot.root_credentials') }}</div>
            <div class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">{{ $t('iot.root_credentials_help') }}</div>
          </div>
          <UiButton
            v-if="!root"
            variant="outline" size="sm" :icon="Lock" :loading="rootLoading"
            class="shrink-0" @click="revealRoot"
          >
            {{ $t('iot.show_root_password') }}
          </UiButton>
          <UiButton v-else variant="ghost" size="sm" :icon="EyeOff" class="shrink-0" @click="root = null">
            {{ $t('iot.hide') }}
          </UiButton>
        </div>

        <UiAlert v-if="rootError" variant="error" class="mt-3">{{ rootError }}</UiAlert>

        <div v-if="root" class="mt-3 space-y-2">
          <div>
            <div class="text-xs uppercase tracking-wide text-neutral-400 dark:text-neutral-500">{{ $t('iot.root_login') }}</div>
            <div class="flex items-center gap-1">
              <span class="font-mono text-sm text-neutral-900 dark:text-neutral-100 truncate">root@{{ root.hostname }}</span>
              <button class="copy-btn" :aria-label="$t('iot.copy')" @click="copy(`root@${root!.hostname}`)">
                <Copy class="w-3.5 h-3.5" aria-hidden="true" />
              </button>
            </div>
          </div>
          <div>
            <div class="text-xs uppercase tracking-wide text-neutral-400 dark:text-neutral-500">{{ $t('mesh.wifi_password') }}</div>
            <div class="flex items-center gap-1">
              <span class="font-mono text-sm text-neutral-900 dark:text-neutral-100 break-all">{{ root.root_password }}</span>
              <button class="copy-btn" :aria-label="$t('iot.copy')" @click="copy(root!.root_password)">
                <Copy class="w-3.5 h-3.5" aria-hidden="true" />
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- ═══ Change the private WiFi name / password ═══ -->
      <form v-if="canConfigureWifi" class="p-3 rounded-lg border border-neutral-200 dark:border-neutral-700" @submit.prevent="saveWifi">
        <div class="font-medium text-sm text-neutral-900 dark:text-neutral-100">{{ $t('mesh.wifi_settings') }}</div>
        <div class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">{{ $t('iot.wifi_settings_help') }}</div>

        <div class="grid gap-3 sm:grid-cols-2 mt-3">
          <div>
            <label for="wifi-ssid" class="block text-xs font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              {{ $t('mesh.wifi_ssid') }}
            </label>
            <input
              id="wifi-ssid" v-model="newSsid" type="text" maxlength="32" :placeholder="currentSsid"
              class="w-full px-3 py-2 text-sm rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
            />
          </div>
          <div>
            <label for="wifi-pass" class="block text-xs font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              {{ $t('mesh.wifi_password') }}
            </label>
            <div class="relative">
              <input
                id="wifi-pass" v-model="newPassword" :type="showNewPassword ? 'text' : 'password'"
                minlength="8" maxlength="63" :placeholder="$t('iot.wifi_password_placeholder')"
                class="w-full px-3 py-2 pr-10 text-sm rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
              />
              <button
                type="button"
                class="absolute right-2 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300"
                :aria-label="$t('iot.show_wifi_password')"
                @click="showNewPassword = !showNewPassword"
              >
                <Eye v-if="showNewPassword" class="w-4 h-4" aria-hidden="true" />
                <EyeOff v-else class="w-4 h-4" aria-hidden="true" />
              </button>
            </div>
          </div>
        </div>

        <label class="flex items-center gap-2 mt-3 cursor-pointer">
          <input v-model="applyToAll" type="checkbox" class="w-4 h-4 rounded border-neutral-300 dark:border-neutral-600 text-secondary focus:ring-primary" />
          <span class="text-sm text-neutral-700 dark:text-neutral-300">{{ $t('mesh.apply_to_all') }}</span>
        </label>
        <p v-if="applyToAll" class="mt-1 text-xs text-warning dark:text-warning-400">{{ $t('mesh.apply_to_all_warning') }}</p>

        <div v-if="saveResult" class="mt-3 text-sm">
          <div class="font-medium" :class="saveResult.failed === 0 ? 'text-success dark:text-success-400' : 'text-warning dark:text-warning-400'">
            {{ saveResult.failed === 0
              ? $t('mesh.wifi_updated', { updated: saveResult.updated })
              : $t('mesh.wifi_update_partial', { updated: saveResult.updated, failed: saveResult.failed }) }}
          </div>
          <div v-for="r in saveResult.results" :key="r.device_id"
               :class="r.success ? 'text-success dark:text-success-400' : 'text-error dark:text-error-400'" class="text-xs mt-0.5">
            {{ r.name }}: {{ r.success ? '✓' : r.error }}
          </div>
        </div>

        <UiAlert v-if="saveError" variant="error" class="mt-3">{{ saveError }}</UiAlert>

        <UiButton
          type="submit" variant="secondary" size="sm" class="mt-3"
          :loading="saving" :disabled="!newSsid && !newPassword"
        >
          {{ saving ? $t('mesh.updating_wifi') : $t('mesh.save') }}
        </UiButton>
      </form>
    </div>
  </IoTDeviceSection>
</template>

<script setup lang="ts">
import { Copy, Eye, EyeOff, KeyRound, Lock, Wifi } from 'lucide-vue-next'
import QRCode from 'qrcode'
import { wifiJoinPayload } from '~/utils/wifiQr'
import type { WifiConfigResponse } from '~/stores/iot'

/** Rendered only for a MANAGER+ — both password endpoints require that role. */
interface Props {
  deviceId: string
  firmwareRole?: string
  currentSsid?: string
}

const props = defineProps<Props>()

const store = useIoTStore()
const toastStore = useToastStore()
const { t } = useI18n()
const { deviceErrorText } = useIoT()

// A bee mirrors its bumblebee's credentials — the fleet-wide form only makes
// sense from a gateway.
const canConfigureWifi = computed(() => props.firmwareRole !== 'bee')

const wifi = ref<{ ssid: string; wifi_password: string } | null>(null)
const wifiLoading = ref(false)
const wifiError = ref<string | null>(null)
const qrCanvas = ref<HTMLCanvasElement | null>(null)

const root = ref<{ root_password: string; hostname: string } | null>(null)
const rootLoading = ref(false)
const rootError = ref<string | null>(null)

const newSsid = ref('')
const newPassword = ref('')
const showNewPassword = ref(false)
const applyToAll = ref(true)
const saving = ref(false)
const saveError = ref<string | null>(null)
const saveResult = ref<WifiConfigResponse | null>(null)

async function revealWifi() {
  if (wifiLoading.value) return
  wifiLoading.value = true
  wifiError.value = null
  try {
    wifi.value = await store.getWifiPassword(props.deviceId)
    await nextTick()
    if (qrCanvas.value && wifi.value) {
      // One explicit byte segment, never the library's automatic split: an
      // ASCII prefix + a non-ASCII SSID auto-segments into Alphanumeric+Byte,
      // and decoders differ on those (OpenCV returns an empty string for one).
      // A single UTF-8 byte segment costs a few modules and every reader takes it.
      await QRCode.toCanvas(
        qrCanvas.value,
        [{ data: wifiJoinPayload(wifi.value.ssid, wifi.value.wifi_password), mode: 'byte' }],
        { width: 160, margin: 1, color: { dark: '#000000', light: '#FFFFFF' } },
      )
    }
  } catch (err: any) {
    wifiError.value = deviceErrorText(err) || t('iot.wifi_reveal_failed')
  } finally {
    wifiLoading.value = false
  }
}

async function revealRoot() {
  if (rootLoading.value) return
  rootLoading.value = true
  rootError.value = null
  try {
    root.value = await store.getRootPassword(props.deviceId)
  } catch (err: any) {
    rootError.value = deviceErrorText(err) || t('iot.root_reveal_failed')
  } finally {
    rootLoading.value = false
  }
}

async function copy(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    toastStore.success(t('iot.copied'))
  } catch { /* clipboard unavailable */ }
}

async function saveWifi() {
  if (saving.value) return
  const config: Record<string, any> = { apply_to_all: applyToAll.value }
  if (newSsid.value && newSsid.value !== props.currentSsid) config.wifi_ssid = newSsid.value
  if (newPassword.value) config.wifi_password = newPassword.value
  if (!config.wifi_ssid && !config.wifi_password) {
    saveError.value = t('iot.wifi_no_changes')
    return
  }

  saving.value = true
  saveError.value = null
  saveResult.value = null
  try {
    saveResult.value = await store.updateWifiConfig(props.deviceId, config)
    newPassword.value = ''
    // The revealed pair is now stale — a second reveal re-reads the router
    wifi.value = null
  } catch (err: any) {
    saveError.value = deviceErrorText(err) || t('iot.wifi_save_failed')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.copy-btn {
  @apply p-1 rounded text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 hover:bg-neutral-200 dark:hover:bg-neutral-700 transition-colors shrink-0;
}
</style>
