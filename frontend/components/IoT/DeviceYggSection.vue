<template>
  <IoTDeviceSection :title="$t('mesh.ygg_access_title')" :help="$t('mesh.ygg_access_desc')" :icon="Globe">
    <div v-if="loading" class="py-8 text-center text-neutral-500 dark:text-neutral-400" role="status">
      <Loader2 class="w-6 h-6 animate-spin mx-auto" aria-hidden="true" />
      <span class="sr-only">{{ $t('mesh.mullvad_loading') }}</span>
    </div>

    <template v-else>
      <form class="flex gap-2" @submit.prevent="add">
        <input
          v-model="newIp" type="text" :placeholder="$t('mesh.ygg_access_placeholder')" :aria-label="$t('mesh.ygg_access_title')"
          class="flex-1 min-w-0 px-3 py-2 text-sm font-mono rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 placeholder:text-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
        />
        <UiButton type="submit" variant="primary" size="sm" :icon="Plus" :loading="adding" :disabled="!newIp.trim()">
          {{ $t('iot.ygg_allow') }}
        </UiButton>
      </form>

      <UiAlert v-if="error" variant="error" class="mt-3">{{ error }}</UiAlert>

      <!-- Flush list (design system § Item Lists) -->
      <div v-if="allowedIps.length" class="mt-3 border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700">
        <div v-for="ip in allowedIps" :key="ip" class="flex items-center justify-between gap-2 px-3 py-2">
          <span class="font-mono text-sm text-neutral-900 dark:text-neutral-100 truncate">{{ ip }}</span>
          <UiButton
            variant="ghost" size="sm" :icon="X" icon-only :loading="removing === ip"
            :aria-label="$t('iot.delete')" @click="remove(ip)"
          />
        </div>
      </div>

      <div v-else class="mt-3 py-6 text-center text-neutral-500 dark:text-neutral-400">
        <ShieldOff class="w-8 h-8 mx-auto mb-2 opacity-50" aria-hidden="true" />
        <p class="text-sm">{{ $t('mesh.ygg_access_empty') }}</p>
      </div>

      <p class="text-xs text-neutral-400 dark:text-neutral-500 mt-3">{{ $t('mesh.ygg_access_sync') }}</p>
    </template>
  </IoTDeviceSection>
</template>

<script setup lang="ts">
import { Globe, Loader2, Plus, ShieldOff, X } from 'lucide-vue-next'

/** Rendered only for a MANAGER+ on a bumblebee — the ygg-access endpoints are MANAGER-gated. */
interface Props {
  deviceId: string
}

const props = defineProps<Props>()
const store = useIoTStore()
const { deviceErrorText } = useIoT()

const loading = ref(true)
const error = ref<string | null>(null)
const allowedIps = ref<string[]>([])
const newIp = ref('')
const adding = ref(false)
const removing = ref<string | null>(null)

async function load() {
  loading.value = true
  error.value = null
  try {
    allowedIps.value = (await store.getYggAccess(props.deviceId)).ygg_allowed_ips
  } catch (err: any) {
    error.value = deviceErrorText(err)
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function add() {
  const ip = newIp.value.trim()
  if (!ip || adding.value) return
  adding.value = true
  error.value = null
  try {
    allowedIps.value = (await store.addYggAccess(props.deviceId, ip)).ygg_allowed_ips
    newIp.value = ''
  } catch (err: any) {
    error.value = deviceErrorText(err)
  } finally {
    adding.value = false
  }
}

async function remove(ip: string) {
  if (removing.value) return
  removing.value = ip
  error.value = null
  try {
    allowedIps.value = (await store.removeYggAccess(props.deviceId, ip)).ygg_allowed_ips
  } catch (err: any) {
    error.value = deviceErrorText(err)
  } finally {
    removing.value = null
  }
}
</script>
