<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" @click.self="$emit('close')">
    <div class="bg-white dark:bg-neutral-800 rounded-xl shadow-2xl w-full max-w-lg p-6 max-h-[85vh] flex flex-col">
      <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4">
        {{ $t('mesh.diagnostics_title') }}
      </h3>

      <!-- Tab buttons -->
      <div class="flex gap-1 mb-4 overflow-x-auto">
        <button
          v-for="tab in availableTabs"
          :key="tab"
          @click="selectTab(tab)"
          class="px-3 py-1.5 rounded-md text-sm font-medium whitespace-nowrap transition-colors"
          :class="activeTab === tab
            ? 'bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-200'
            : 'text-neutral-600 dark:text-neutral-400 hover:bg-neutral-100 dark:hover:bg-neutral-700'"
        >
          {{ $t(`mesh.tab_${tab}`) }}
        </button>
      </div>

      <!-- Content area -->
      <div class="flex-1 overflow-y-auto min-h-0">
        <!-- Loading -->
        <div v-if="loading" class="flex items-center gap-3 py-8 justify-center text-neutral-500 dark:text-neutral-400">
          <Loader2 class="w-5 h-5 animate-spin" />
          {{ $t('mesh.diagnostics_loading') }}
        </div>

        <!-- Error -->
        <UiAlert v-else-if="error" variant="error">{{ error }}</UiAlert>

        <!-- Sections -->
        <div v-else-if="sections.length" class="space-y-3">
          <div v-for="(section, i) in sections" :key="i"
               class="border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden">
            <div class="flex items-center justify-between px-3 py-1.5 bg-neutral-50 dark:bg-neutral-700/50">
              <span class="text-xs font-medium text-neutral-600 dark:text-neutral-300">{{ section.title }}</span>
              <button @click="copySection(section)"
                      class="text-xs text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-200 transition-colors">
                <ClipboardCopy v-if="copiedIdx !== i" class="w-3.5 h-3.5" />
                <Check v-else class="w-3.5 h-3.5 text-green-500" />
              </button>
            </div>
            <pre class="px-3 py-2 text-xs font-mono text-neutral-800 dark:text-neutral-200 overflow-x-auto whitespace-pre-wrap break-all">{{ section.output || '(empty)' }}</pre>
          </div>
        </div>

        <!-- No data yet -->
        <div v-else class="text-center py-8 text-neutral-500 dark:text-neutral-400 text-sm">
          {{ $t('mesh.diagnostics_loading') }}
        </div>
      </div>

      <!-- Footer -->
      <div class="flex justify-between items-center mt-4 pt-3 border-t border-neutral-200 dark:border-neutral-700">
        <button
          @click="refresh"
          :disabled="loading"
          class="px-3 py-1.5 text-sm font-medium text-neutral-600 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded-lg disabled:opacity-50 flex items-center gap-1.5"
        >
          <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': loading }" />
          {{ $t('mesh.diagnostics_refresh') }}
        </button>
        <button
          @click="$emit('close')"
          class="px-4 py-2 text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded-lg"
        >
          {{ $t('mesh.cancel') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Loader2, RefreshCw, ClipboardCopy, Check } from 'lucide-vue-next'

interface Props {
  deviceId: string
  firmwareRole: string
}

interface Emits {
  (e: 'close'): void
}

const props = defineProps<Props>()
defineEmits<Emits>()

const store = useIoTStore()

const BEE_TABS = ['mesh', 'wifi', 'system']
const BUMBLEBEE_TABS = ['mesh', 'wifi', 'network', 'vpn', 'system']

const availableTabs = computed(() =>
  props.firmwareRole === 'bumblebee' ? BUMBLEBEE_TABS : BEE_TABS
)

const activeTab = ref(availableTabs.value[0])
const loading = ref(false)
const error = ref<string | null>(null)
const sections = ref<Array<{ title: string; output: string }>>([])
const copiedIdx = ref<number | null>(null)

// Cache: tab -> sections
const cache = new Map<string, Array<{ title: string; output: string }>>()

async function fetchTab(tab: string) {
  // Check cache
  if (cache.has(tab)) {
    sections.value = cache.get(tab)!
    return
  }

  loading.value = true
  error.value = null
  sections.value = []

  try {
    const data = await store.getDiagnostics(props.deviceId, tab)
    cache.set(tab, data.sections)
    sections.value = data.sections
  } catch (err: any) {
    error.value = err.message || 'Failed to load diagnostics'
  } finally {
    loading.value = false
  }
}

function selectTab(tab: string) {
  activeTab.value = tab
  fetchTab(tab)
}

function refresh() {
  cache.delete(activeTab.value)
  fetchTab(activeTab.value)
}

async function copySection(section: { title: string; output: string }) {
  const idx = sections.value.indexOf(section)
  try {
    await navigator.clipboard.writeText(section.output)
    copiedIdx.value = idx
    setTimeout(() => { copiedIdx.value = null }, 1500)
  } catch {
    // ignore
  }
}

// Load first tab on mount
onMounted(() => {
  fetchTab(activeTab.value)
})
</script>
