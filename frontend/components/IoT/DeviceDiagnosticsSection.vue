<template>
  <IoTDeviceSection :title="$t('mesh.diagnostics_title')" :help="$t('iot.section_diagnostics_help')" :icon="Stethoscope">
    <template #actions>
      <UiButton variant="ghost" size="sm" :icon="RefreshCw" :loading="loading" class="shrink-0" @click="refresh">
        {{ $t('mesh.diagnostics_refresh') }}
      </UiButton>
    </template>

    <UiTabs v-model="activeTab" :tabs="tabs" variant="pills" />

    <div class="mt-4">
      <div v-if="loading" class="py-8 text-center text-neutral-500 dark:text-neutral-400" role="status">
        <Loader2 class="w-6 h-6 animate-spin mx-auto" aria-hidden="true" />
        <span class="sr-only">{{ $t('mesh.diagnostics_loading') }}</span>
      </div>

      <UiAlert v-else-if="error" variant="error">{{ error }}</UiAlert>

      <div v-else-if="sections.length" class="space-y-3">
        <div v-for="(section, i) in sections" :key="i" class="border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden">
          <div class="flex items-center justify-between px-3 py-1.5 bg-neutral-50 dark:bg-neutral-700/50">
            <span class="text-xs font-medium text-neutral-600 dark:text-neutral-300">{{ section.title }}</span>
            <button
              class="text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-200 transition-colors"
              :aria-label="$t('iot.copy')" @click="copySection(section, i)"
            >
              <Check v-if="copiedIdx === i" class="w-3.5 h-3.5 text-success" aria-hidden="true" />
              <ClipboardCopy v-else class="w-3.5 h-3.5" aria-hidden="true" />
            </button>
          </div>
          <pre class="px-3 py-2 text-xs font-mono text-neutral-800 dark:text-neutral-200 overflow-x-auto whitespace-pre-wrap break-all">{{ section.output || '—' }}</pre>
        </div>
      </div>

      <p v-else class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('iot.diagnostics_empty') }}</p>
    </div>
  </IoTDeviceSection>
</template>

<script setup lang="ts">
import { Check, ClipboardCopy, Loader2, RefreshCw, Stethoscope } from 'lucide-vue-next'

interface Props {
  deviceId: string
  firmwareRole?: string
}

const props = defineProps<Props>()
const store = useIoTStore()
const { t } = useI18n()
const { deviceErrorText } = useIoT()

const BEE_TABS = ['mesh', 'wifi', 'system']
const BUMBLEBEE_TABS = ['mesh', 'wifi', 'network', 'vpn', 'system']

const availableTabs = computed(() => (props.firmwareRole === 'bumblebee' ? BUMBLEBEE_TABS : BEE_TABS))
const tabs = computed(() => availableTabs.value.map(id => ({ id, label: t(`mesh.tab_${id}`) })))

const activeTab = ref(availableTabs.value[0])
const loading = ref(false)
const error = ref<string | null>(null)
const sections = ref<Array<{ title: string; output: string }>>([])
const copiedIdx = ref<number | null>(null)

// Each tab is a round trip over mesh SSH — keep what we already fetched
const cache = new Map<string, Array<{ title: string; output: string }>>()

async function fetchTab(tab: string) {
  const cached = cache.get(tab)
  if (cached) {
    sections.value = cached
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
    error.value = deviceErrorText(err)
  } finally {
    loading.value = false
  }
}

watch(activeTab, tab => fetchTab(tab))

onMounted(() => fetchTab(activeTab.value))

function refresh() {
  cache.delete(activeTab.value)
  fetchTab(activeTab.value)
}

async function copySection(section: { title: string; output: string }, idx: number) {
  try {
    await navigator.clipboard.writeText(section.output)
    copiedIdx.value = idx
    setTimeout(() => { copiedIdx.value = null }, 1500)
  } catch { /* clipboard unavailable */ }
}
</script>
