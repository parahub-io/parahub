<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" @click.self="$emit('close')">
    <div class="bg-white dark:bg-neutral-800 rounded-xl shadow-2xl w-full max-w-md p-6">
      <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4">
        {{ $t('mesh.wired_mesh') }}
      </h3>

      <!-- Loading state -->
      <div v-if="loading" class="flex items-center gap-3 py-8 justify-center text-neutral-500 dark:text-neutral-400">
        <Loader2 class="w-5 h-5 animate-spin" />
        {{ $t('mesh.toggling') }}
      </div>

      <template v-else>
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
              @click="handleToggle"
              :disabled="toggling"
              class="relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
              :class="enabled ? 'bg-green-500' : 'bg-neutral-300 dark:bg-neutral-600'"
              role="switch"
              :aria-checked="enabled"
            >
              <span
                class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out"
                :class="enabled ? 'translate-x-5' : 'translate-x-0'"
              />
            </button>
          </div>
          <div v-if="toggling" class="flex items-center gap-2 mt-2 text-xs text-neutral-500 dark:text-neutral-400">
            <Loader2 class="w-3 h-3 animate-spin" />
            {{ $t('mesh.toggling') }}
          </div>
          <div v-else-if="enabled !== null" class="text-xs mt-2" :class="enabled ? 'text-green-600 dark:text-green-400' : 'text-neutral-500 dark:text-neutral-400'">
            {{ enabled ? $t('mesh.wired_mesh_enabled') : $t('mesh.wired_mesh_disabled') }}
          </div>
          <div v-if="error" class="text-xs text-red-600 dark:text-red-400 mt-2">
            {{ error }}
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
const enabled = ref<boolean | null>(null)
const toggling = ref(false)
const error = ref<string | null>(null)

onMounted(async () => {
  try {
    const result = await store.getWiredMeshStatus(props.deviceId)
    enabled.value = result.enabled
  } catch (err: any) {
    error.value = err.message || 'Failed to load'
  }
  loading.value = false
})

const handleToggle = async () => {
  if (toggling.value || enabled.value === null) return
  toggling.value = true
  error.value = null

  const newState = !enabled.value
  try {
    const result = await store.toggleWiredMesh(props.deviceId, newState)
    enabled.value = result.enabled
  } catch (err: any) {
    error.value = err.message
  } finally {
    toggling.value = false
  }
}
</script>
