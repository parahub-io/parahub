<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" @click.self="$emit('close')">
    <div class="bg-white dark:bg-neutral-800 rounded-xl shadow-2xl w-full max-w-md p-6">
      <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-1">
        {{ $t('mesh.ygg_access_title') }}
      </h3>
      <p class="text-xs text-neutral-500 dark:text-neutral-400 mb-4">
        {{ $t('mesh.ygg_access_desc') }}
      </p>

      <!-- Loading -->
      <div v-if="loading" class="flex items-center gap-3 py-8 justify-center text-neutral-500 dark:text-neutral-400">
        <Loader2 class="w-5 h-5 animate-spin" />
        {{ $t('mesh.mullvad_loading') }}
      </div>

      <template v-else>
        <!-- Add new address -->
        <div class="flex gap-2 mb-4">
          <input
            v-model="newIp"
            type="text"
            :placeholder="$t('mesh.ygg_access_placeholder')"
            class="flex-1 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-700 px-3 py-2 text-sm font-mono text-neutral-900 dark:text-neutral-100 placeholder:text-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary"
            @keydown.enter="handleAdd"
          />
          <button
            @click="handleAdd"
            :disabled="adding || !newIp.trim()"
            class="btn-primary text-sm shrink-0 px-3"
          >
            <Loader2 v-if="adding" class="w-4 h-4 animate-spin" />
            <Plus v-else class="w-4 h-4" />
          </button>
        </div>

        <!-- Error -->
        <div v-if="error" class="text-xs text-red-600 dark:text-red-400 mb-3">
          {{ error }}
        </div>

        <!-- Allowed list -->
        <div v-if="allowedIps.length" class="space-y-2 mb-4 max-h-64 overflow-y-auto">
          <div
            v-for="ip in allowedIps"
            :key="ip"
            class="flex items-center justify-between gap-2 p-2.5 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-700/50"
          >
            <span class="font-mono text-sm text-neutral-900 dark:text-neutral-100 truncate">{{ ip }}</span>
            <button
              @click="handleRemove(ip)"
              :disabled="removingIp === ip"
              class="p-1 rounded text-neutral-400 hover:text-red-500 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors shrink-0"
              :aria-label="$t('iot.delete')"
            >
              <Loader2 v-if="removingIp === ip" class="w-4 h-4 animate-spin" />
              <X v-else class="w-4 h-4" />
            </button>
          </div>
        </div>

        <!-- Empty state -->
        <div v-else class="text-center py-6 text-neutral-500 dark:text-neutral-400">
          <ShieldOff class="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p class="text-sm">{{ $t('mesh.ygg_access_empty') }}</p>
        </div>

        <!-- Sync notice -->
        <p class="text-xs text-neutral-400 dark:text-neutral-500 mb-4">
          {{ $t('mesh.ygg_access_sync') }}
        </p>

        <!-- Close -->
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
import { Loader2, Plus, X, ShieldOff } from 'lucide-vue-next'

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
const error = ref<string | null>(null)
const allowedIps = ref<string[]>([])
const newIp = ref('')
const adding = ref(false)
const removingIp = ref<string | null>(null)

onMounted(async () => {
  try {
    const data = await store.getYggAccess(props.deviceId)
    allowedIps.value = data.ygg_allowed_ips
  } catch (err: any) {
    error.value = err.data?.detail || err.message || 'Failed to load'
  } finally {
    loading.value = false
  }
})

const handleAdd = async () => {
  const ip = newIp.value.trim()
  if (!ip || adding.value) return
  adding.value = true
  error.value = null

  try {
    const data = await store.addYggAccess(props.deviceId, ip)
    allowedIps.value = data.ygg_allowed_ips
    newIp.value = ''
  } catch (err: any) {
    error.value = err.data?.detail || err.message || 'Invalid address'
  } finally {
    adding.value = false
  }
}

const handleRemove = async (ip: string) => {
  if (removingIp.value) return
  removingIp.value = ip
  error.value = null

  try {
    const data = await store.removeYggAccess(props.deviceId, ip)
    allowedIps.value = data.ygg_allowed_ips
  } catch (err: any) {
    error.value = err.data?.detail || err.message || 'Failed to remove'
  } finally {
    removingIp.value = null
  }
}
</script>
