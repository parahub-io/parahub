<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" @click.self="$emit('close')">
    <div class="bg-white dark:bg-neutral-800 rounded-xl shadow-2xl w-full max-w-md p-6">
      <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4">
        {{ $t('mesh.network_settings') }}
      </h3>

      <!-- Loading state -->
      <div v-if="loading" class="flex items-center gap-3 py-8 justify-center text-neutral-500 dark:text-neutral-400">
        <Loader2 class="w-5 h-5 animate-spin" />
        {{ $t('mesh.mullvad_loading') }}
      </div>

      <template v-else>
        <!-- Speed Limit Toggle -->
        <div class="mb-4 p-4 rounded-lg border border-neutral-200 dark:border-neutral-700">
          <div class="flex items-center justify-between">
            <div class="flex-1 mr-3">
              <div class="font-medium text-sm text-neutral-900 dark:text-neutral-100">
                {{ $t('mesh.speed_limit') }}
              </div>
              <div class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
                {{ $t('mesh.speed_limit_desc') }}
              </div>
            </div>
            <button
              @click="handleToggleSpeedLimit"
              :disabled="speedLimitToggling"
              class="relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
              :class="speedLimitEnabled ? 'bg-green-500' : 'bg-neutral-300 dark:bg-neutral-600'"
              role="switch"
              :aria-checked="speedLimitEnabled"
            >
              <span
                class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out"
                :class="speedLimitEnabled ? 'translate-x-5' : 'translate-x-0'"
              />
            </button>
          </div>
          <div v-if="speedLimitToggling" class="flex items-center gap-2 mt-2 text-xs text-neutral-500 dark:text-neutral-400">
            <Loader2 class="w-3 h-3 animate-spin" />
            {{ $t('mesh.toggling') }}
          </div>
          <div v-else-if="speedLimitEnabled !== null" class="text-xs mt-2" :class="speedLimitEnabled ? 'text-green-600 dark:text-green-400' : 'text-neutral-500 dark:text-neutral-400'">
            {{ speedLimitEnabled ? $t('mesh.speed_limit_enabled') : $t('mesh.speed_limit_disabled') }}
          </div>
          <div v-if="speedLimitError" class="text-xs text-red-600 dark:text-red-400 mt-2">
            {{ speedLimitError }}
          </div>
        </div>

        <!-- LAN VPN Toggle -->
        <div class="mb-4 p-4 rounded-lg border border-neutral-200 dark:border-neutral-700">
          <div class="flex items-center justify-between">
            <div class="flex-1 mr-3">
              <div class="font-medium text-sm text-neutral-900 dark:text-neutral-100">
                {{ $t('mesh.lan_vpn') }}
              </div>
              <div class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
                {{ $t('mesh.lan_vpn_desc') }}
              </div>
            </div>
            <button
              @click="handleToggleLanVpn"
              :disabled="lanVpnToggling"
              class="relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
              :class="lanVpnEnabled ? 'bg-green-500' : 'bg-neutral-300 dark:bg-neutral-600'"
              role="switch"
              :aria-checked="lanVpnEnabled"
            >
              <span
                class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out"
                :class="lanVpnEnabled ? 'translate-x-5' : 'translate-x-0'"
              />
            </button>
          </div>
          <div v-if="lanVpnToggling" class="flex items-center gap-2 mt-2 text-xs text-neutral-500 dark:text-neutral-400">
            <Loader2 class="w-3 h-3 animate-spin" />
            {{ $t('mesh.toggling') }}
          </div>
          <div v-else-if="lanVpnEnabled !== null" class="text-xs mt-2" :class="lanVpnEnabled ? 'text-green-600 dark:text-green-400' : 'text-neutral-500 dark:text-neutral-400'">
            {{ lanVpnEnabled ? $t('mesh.lan_vpn_enabled') : $t('mesh.lan_vpn_disabled') }}
          </div>
          <div v-if="lanVpnError" class="text-xs text-red-600 dark:text-red-400 mt-2">
            {{ lanVpnError }}
          </div>
        </div>

        <!-- Wired Mesh Toggle -->
        <div class="mb-4 p-4 rounded-lg border border-neutral-200 dark:border-neutral-700">
          <div class="flex items-center justify-between">
            <div class="flex-1 mr-3">
              <div class="font-medium text-sm text-neutral-900 dark:text-neutral-100">
                {{ $t('mesh.wired_mesh') }}
              </div>
              <div class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
                {{ $t('mesh.wired_mesh_desc') }}
              </div>
            </div>
            <button
              @click="handleToggleWiredMesh"
              :disabled="wiredMeshToggling"
              class="relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
              :class="wiredMeshEnabled ? 'bg-green-500' : 'bg-neutral-300 dark:bg-neutral-600'"
              role="switch"
              :aria-checked="wiredMeshEnabled"
            >
              <span
                class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out"
                :class="wiredMeshEnabled ? 'translate-x-5' : 'translate-x-0'"
              />
            </button>
          </div>
          <div v-if="wiredMeshToggling" class="flex items-center gap-2 mt-2 text-xs text-neutral-500 dark:text-neutral-400">
            <Loader2 class="w-3 h-3 animate-spin" />
            {{ $t('mesh.toggling') }}
          </div>
          <div v-else-if="wiredMeshEnabled !== null" class="text-xs mt-2" :class="wiredMeshEnabled ? 'text-green-600 dark:text-green-400' : 'text-neutral-500 dark:text-neutral-400'">
            {{ wiredMeshEnabled ? $t('mesh.wired_mesh_enabled') : $t('mesh.wired_mesh_disabled') }}
          </div>
          <div v-if="wiredMeshError" class="text-xs text-red-600 dark:text-red-400 mt-2">
            {{ wiredMeshError }}
          </div>
        </div>

        <!-- Close button -->
        <div class="flex justify-end">
          <button
            @click="$emit('close')"
            class="px-4 py-2 text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded-lg"
          >
            {{ $t('mesh.cancel') }}
          </button>
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
const store = useIoTStore()

const loading = ref(true)
const speedLimitEnabled = ref<boolean | null>(null)
const speedLimitToggling = ref(false)
const speedLimitError = ref<string | null>(null)
const lanVpnEnabled = ref<boolean | null>(null)
const lanVpnToggling = ref(false)
const lanVpnError = ref<string | null>(null)
const wiredMeshEnabled = ref<boolean | null>(null)
const wiredMeshToggling = ref(false)
const wiredMeshError = ref<string | null>(null)

onMounted(async () => {
  const [speedResult, vpnResult, wiredMeshResult] = await Promise.allSettled([
    store.getSpeedLimitStatus(props.deviceId),
    store.getLanVpnStatus(props.deviceId),
    store.getWiredMeshStatus(props.deviceId),
  ])

  if (speedResult.status === 'fulfilled') {
    speedLimitEnabled.value = speedResult.value.enabled
  } else {
    speedLimitError.value = speedResult.reason?.message || 'Failed to load'
  }

  if (vpnResult.status === 'fulfilled') {
    lanVpnEnabled.value = vpnResult.value.enabled
  } else {
    lanVpnError.value = vpnResult.reason?.message || 'Failed to load'
  }

  if (wiredMeshResult.status === 'fulfilled') {
    wiredMeshEnabled.value = wiredMeshResult.value.enabled
  } else {
    wiredMeshError.value = wiredMeshResult.reason?.message || 'Failed to load'
  }

  loading.value = false
})

const handleToggleSpeedLimit = async () => {
  if (speedLimitToggling.value || speedLimitEnabled.value === null) return
  speedLimitToggling.value = true
  speedLimitError.value = null

  const newState = !speedLimitEnabled.value
  try {
    const result = await store.toggleSpeedLimit(props.deviceId, newState)
    speedLimitEnabled.value = result.enabled
  } catch (err: any) {
    speedLimitError.value = err.message
  } finally {
    speedLimitToggling.value = false
  }
}

const handleToggleLanVpn = async () => {
  if (lanVpnToggling.value || lanVpnEnabled.value === null) return
  lanVpnToggling.value = true
  lanVpnError.value = null

  const newState = !lanVpnEnabled.value
  try {
    const result = await store.toggleLanVpn(props.deviceId, newState)
    lanVpnEnabled.value = result.enabled
  } catch (err: any) {
    lanVpnError.value = err.message
  } finally {
    lanVpnToggling.value = false
  }
}

const handleToggleWiredMesh = async () => {
  if (wiredMeshToggling.value || wiredMeshEnabled.value === null) return
  wiredMeshToggling.value = true
  wiredMeshError.value = null

  const newState = !wiredMeshEnabled.value
  try {
    const result = await store.toggleWiredMesh(props.deviceId, newState)
    wiredMeshEnabled.value = result.enabled
  } catch (err: any) {
    wiredMeshError.value = err.message
  } finally {
    wiredMeshToggling.value = false
  }
}
</script>
