<template>
  <IoTDeviceSection :title="$t('mesh.network_settings')" :help="$t('iot.section_network_help')" :icon="Network">
    <div v-if="loading" class="py-8 text-center text-neutral-500 dark:text-neutral-400" role="status">
      <Loader2 class="w-6 h-6 animate-spin mx-auto" aria-hidden="true" />
      <span class="sr-only">{{ $t('mesh.mullvad_loading') }}</span>
    </div>

    <div v-else class="space-y-3">
      <!-- Guest shaping (gateway only — a bee relays, it does not terminate guests) -->
      <IoTDeviceToggleRow
        v-if="isGateway"
        :label="$t('mesh.speed_limit')"
        :description="$t('mesh.speed_limit_desc')"
        :model-value="speedLimit"
        :on-text="$t('mesh.speed_limit_enabled')"
        :off-text="$t('mesh.speed_limit_disabled')"
        :busy="speedLimitBusy"
        :error="speedLimitError"
        @toggle="toggleSpeedLimit"
      />

      <!-- Sharing budgets + uplink passport -->
      <div v-if="isGateway" class="p-3 rounded-lg border border-neutral-200 dark:border-neutral-700">
        <div class="font-medium text-sm text-neutral-900 dark:text-neutral-100">{{ $t('mesh.sharing_title') }}</div>
        <div class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">{{ $t('mesh.sharing_desc') }}</div>

        <div class="grid grid-cols-2 gap-3 mt-3">
          <div>
            <label for="guest-rate" class="block text-xs font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              {{ $t('mesh.guest_rate') }}
            </label>
            <input id="guest-rate" v-model.number="guestRateKbps" type="number" min="64" max="102400" class="field" />
          </div>
          <div>
            <label for="host-rate" class="block text-xs font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              {{ $t('mesh.host_budget') }}
            </label>
            <input id="host-rate" v-model.number="hostRateMbps" type="number" min="1" max="10000" class="field" />
          </div>
        </div>

        <div class="mt-3">
          <label for="uplink-type" class="block text-xs font-medium text-neutral-700 dark:text-neutral-300 mb-1">
            {{ $t('mesh.uplink') }}
          </label>
          <div class="grid grid-cols-3 gap-3">
            <select id="uplink-type" v-model="uplinkType" class="field">
              <option value="">{{ $t('mesh.uplink_none') }}</option>
              <option value="FIBER">{{ $t('mesh.uplink_fiber') }}</option>
              <option value="CABLE">{{ $t('mesh.uplink_cable') }}</option>
              <option value="DSL">{{ $t('mesh.uplink_dsl') }}</option>
              <option value="STARLINK">{{ $t('mesh.uplink_starlink') }}</option>
              <option value="CELLULAR">{{ $t('mesh.uplink_cellular') }}</option>
              <option value="OTHER">{{ $t('mesh.uplink_other') }}</option>
            </select>
            <input v-model.number="uplinkDownMbps" type="number" min="0" max="100000" :placeholder="$t('mesh.uplink_down')" :aria-label="$t('mesh.uplink_down')" class="field" />
            <input v-model.number="uplinkUpMbps" type="number" min="0" max="100000" :placeholder="$t('mesh.uplink_up')" :aria-label="$t('mesh.uplink_up')" class="field" />
          </div>
          <div class="grid grid-cols-3 gap-3 mt-1">
            <span></span>
            <span class="text-[10px] text-neutral-400 dark:text-neutral-500 text-center">{{ $t('mesh.uplink_down') }}</span>
            <span class="text-[10px] text-neutral-400 dark:text-neutral-500 text-center">{{ $t('mesh.uplink_up') }}</span>
          </div>
        </div>

        <div class="flex items-center justify-between gap-3 mt-3">
          <div class="text-xs min-w-0">
            <span v-if="settingsError" class="text-error dark:text-error-400">{{ settingsError }}</span>
            <span v-else-if="settingsSaved" class="text-success dark:text-success-400">{{ $t('mesh.settings_saved') }}</span>
          </div>
          <UiButton variant="secondary" size="sm" :loading="settingsSaving" :disabled="settings === null" @click="saveSettings">
            {{ $t('mesh.save') }}
          </UiButton>
        </div>
      </div>

      <!-- Private LAN over the VPN tunnel -->
      <IoTDeviceToggleRow
        v-if="isGateway"
        :label="$t('mesh.lan_vpn')"
        :description="$t('mesh.lan_vpn_desc')"
        :model-value="lanVpn"
        :on-text="$t('mesh.lan_vpn_enabled')"
        :off-text="$t('mesh.lan_vpn_disabled')"
        :busy="lanVpnBusy"
        :error="lanVpnError"
        @toggle="toggleLanVpn"
      />

      <!-- Wired backhaul — both roles -->
      <IoTDeviceToggleRow
        :label="$t('mesh.wired_mesh')"
        :description="$t('mesh.wired_mesh_desc')"
        :model-value="wiredMesh"
        :on-text="$t('mesh.wired_mesh_enabled')"
        :off-text="$t('mesh.wired_mesh_disabled')"
        :busy="wiredMeshBusy"
        :error="wiredMeshError"
        @toggle="toggleWiredMesh"
      />
    </div>
  </IoTDeviceSection>
</template>

<script setup lang="ts">
import { Loader2, Network } from 'lucide-vue-next'
import type { MeshSettings } from '~/stores/iot'

interface Props {
  deviceId: string
  firmwareRole?: string
}

const props = defineProps<Props>()
const store = useIoTStore()
const { deviceErrorText } = useIoT()

// Guest shaping, budgets and the VPN rule exist only on the L3 gateway role
const isGateway = computed(() => props.firmwareRole === 'bumblebee')

const loading = ref(true)

const speedLimit = ref<boolean | null>(null)
const speedLimitBusy = ref(false)
const speedLimitError = ref<string | null>(null)

const lanVpn = ref<boolean | null>(null)
const lanVpnBusy = ref(false)
const lanVpnError = ref<string | null>(null)

const wiredMesh = ref<boolean | null>(null)
const wiredMeshBusy = ref(false)
const wiredMeshError = ref<string | null>(null)

const settings = ref<MeshSettings | null>(null)
const guestRateKbps = ref<number | ''>('')
const hostRateMbps = ref<number | ''>('')
const uplinkType = ref('')
const uplinkDownMbps = ref<number | ''>('')
const uplinkUpMbps = ref<number | ''>('')
const settingsSaving = ref(false)
const settingsSaved = ref(false)
const settingsError = ref<string | null>(null)

async function load() {
  loading.value = true
  speedLimitError.value = null
  lanVpnError.value = null
  wiredMeshError.value = null
  settingsError.value = null
  settingsSaved.value = false

  // Each probe is a live call to the router; one failure must not blank the rest
  const gatewayOnly = isGateway.value
  const [speed, vpn, wired, meshSettings] = await Promise.allSettled([
    gatewayOnly ? store.getSpeedLimitStatus(props.deviceId) : Promise.resolve(null),
    gatewayOnly ? store.getLanVpnStatus(props.deviceId) : Promise.resolve(null),
    store.getWiredMeshStatus(props.deviceId),
    gatewayOnly ? store.getMeshSettings(props.deviceId) : Promise.resolve(null),
  ])

  if (speed.status === 'fulfilled') speedLimit.value = speed.value?.enabled ?? null
  else speedLimitError.value = deviceErrorText(speed.reason)

  if (vpn.status === 'fulfilled') lanVpn.value = vpn.value?.enabled ?? null
  else lanVpnError.value = deviceErrorText(vpn.reason)

  if (wired.status === 'fulfilled') wiredMesh.value = wired.value?.enabled ?? null
  else wiredMeshError.value = deviceErrorText(wired.reason)

  if (meshSettings.status === 'fulfilled' && meshSettings.value) {
    settings.value = meshSettings.value
    guestRateKbps.value = meshSettings.value.guest_rate_kbps
    hostRateMbps.value = meshSettings.value.host_rate_mbps
    uplinkType.value = meshSettings.value.uplink_type || ''
    uplinkDownMbps.value = meshSettings.value.uplink_down_mbps ?? ''
    uplinkUpMbps.value = meshSettings.value.uplink_up_mbps ?? ''
  } else if (meshSettings.status === 'rejected') {
    settingsError.value = deviceErrorText(meshSettings.reason)
  }

  loading.value = false
}

onMounted(load)

async function toggleSpeedLimit(next: boolean) {
  if (speedLimitBusy.value) return
  speedLimitBusy.value = true
  speedLimitError.value = null
  try {
    speedLimit.value = (await store.toggleSpeedLimit(props.deviceId, next)).enabled
  } catch (err: any) {
    speedLimitError.value = deviceErrorText(err)
  } finally {
    speedLimitBusy.value = false
  }
}

async function toggleLanVpn(next: boolean) {
  if (lanVpnBusy.value) return
  lanVpnBusy.value = true
  lanVpnError.value = null
  try {
    lanVpn.value = (await store.toggleLanVpn(props.deviceId, next)).enabled
  } catch (err: any) {
    lanVpnError.value = deviceErrorText(err)
  } finally {
    lanVpnBusy.value = false
  }
}

async function toggleWiredMesh(next: boolean) {
  if (wiredMeshBusy.value) return
  wiredMeshBusy.value = true
  wiredMeshError.value = null
  try {
    wiredMesh.value = (await store.toggleWiredMesh(props.deviceId, next)).enabled
  } catch (err: any) {
    wiredMeshError.value = deviceErrorText(err)
  } finally {
    wiredMeshBusy.value = false
  }
}

async function saveSettings() {
  if (settingsSaving.value) return
  settingsSaving.value = true
  settingsSaved.value = false
  settingsError.value = null
  try {
    const result = await store.updateMeshSettings(props.deviceId, {
      guest_rate_kbps: Number(guestRateKbps.value) || undefined,
      host_rate_mbps: Number(hostRateMbps.value) || undefined,
      uplink_type: uplinkType.value,
      uplink_down_mbps: Number(uplinkDownMbps.value) || 0,
      uplink_up_mbps: Number(uplinkUpMbps.value) || 0,
    })
    settings.value = result
    guestRateKbps.value = result.guest_rate_kbps
    hostRateMbps.value = result.host_rate_mbps
    settingsSaved.value = true
  } catch (err: any) {
    settingsError.value = deviceErrorText(err)
  } finally {
    settingsSaving.value = false
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
