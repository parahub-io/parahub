<template>
  <div class="flex flex-wrap items-center justify-between gap-2 p-3 bg-neutral-100 dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700">
    <!-- Left: running state info -->
    <div class="flex items-center gap-3 text-sm min-w-0">
      <template v-if="agent.status === 'running'">
        <div class="flex items-center gap-1.5 text-success dark:text-success-300">
          <div class="w-2 h-2 rounded-full bg-success animate-pulse"></div>
          {{ $t('yellow_hive.status_running') }}
        </div>
        <span v-if="runningTime" class="text-neutral-500">{{ runningTime }}</span>
        <div v-if="progress && progress.total > 1" class="text-xs font-mono text-neutral-900 dark:text-neutral-100 bg-primary/10 px-2 py-0.5 rounded">
          {{ progress.current }}/{{ progress.total }}
        </div>
      </template>
      <template v-else-if="agent.last_session">
        <span class="text-neutral-500 truncate">
          {{ $t('yellow_hive.last_run') }}: {{ formatDate(agent.last_session.started_at) }}
        </span>
        <span v-if="agent.last_session.exit_code === 0" class="text-success dark:text-success-300 text-xs font-mono">exit 0</span>
        <span v-else-if="agent.last_session.exit_code != null" class="text-error text-xs font-mono">exit {{ agent.last_session.exit_code }}</span>
      </template>
      <span v-else class="text-neutral-500">{{ $t('yellow_hive.no_sessions_yet') }}</span>
    </div>

    <!-- Right: action buttons -->
    <div v-if="isStaff" class="flex items-center gap-2 flex-shrink-0">
      <!-- Stop button (when running with autoplay) -->
      <UiButton
        v-if="agent.status === 'running' && progress && progress.total > 1"
        variant="error"
        size="sm"
        :icon="Square"
        :loading="stopping"
        :disabled="stopping"
        @click="handleStop"
      >
        {{ $t('yellow_hive.stop') }}
      </UiButton>

      <!-- Autoplay dropdown (not for kevin — single planning session) -->
      <div v-if="!isKevin" class="relative" ref="dropdownRef">
        <UiButton
          variant="outline"
          size="sm"
          :disabled="launching || agent.status === 'running'"
          @click="showDropdown = !showDropdown"
        >
          <ListOrdered class="w-4 h-4" />
          <ChevronDown class="w-3 h-3" />
        </UiButton>
        <div
          v-if="showDropdown && agent.status !== 'running'"
          class="absolute right-0 bottom-full mb-1 bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg shadow-lg z-50 py-1 min-w-[140px]"
        >
          <button
            v-for="n in [3, 5, 10, 20, 50]"
            :key="n"
            @click="handleAutoplay(n)"
            class="w-full text-left px-3 py-1.5 text-sm text-neutral-700 dark:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-neutral-700 transition-colors"
          >
            {{ $t('yellow_hive.autoplay_n', { n }) }}
          </button>
        </div>
      </div>

      <!-- Single launch button -->
      <UiButton
        :variant="agent.voice_enabled ? 'outline' : 'primary'"
        size="sm"
        :icon="Play"
        :loading="launching"
        :disabled="launching || agent.status === 'running'"
        @click="handleLaunch"
      >
        {{ launching ? $t('yellow_hive.launching') : $t('yellow_hive.launch') }}
      </UiButton>

      <!-- Voice chat button (agents with voice enabled) — primary CTA for voice agents -->
      <UiButton
        v-if="agent.voice_enabled"
        variant="primary"
        size="sm"
        :icon="Mic"
        @click="navigateTo(localePath(`/voice/${agent.name}`))"
      >
        {{ $t('voice_chat.title') }}
      </UiButton>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Play, Square, ListOrdered, ChevronDown, Mic } from 'lucide-vue-next'
import type { AgentData } from '~/stores/agents'

const props = defineProps<{ agent: AgentData }>()
const emit = defineEmits<{ launched: [] }>()

const { t: $t } = useI18n()
const authStore = useAuthStore()
const agentsStore = useAgentsStore()
const toastStore = useToastStore()

const isStaff = computed(() => authStore.user?.is_staff ?? false)
const isKevin = computed(() => props.agent.name === 'kevin')
const localePath = useLocalePath()
const launching = ref(false)
const stopping = ref(false)
const showDropdown = ref(false)
const dropdownRef = ref<HTMLElement | null>(null)
const progress = ref<{ current: number; total: number } | null>(null)

const runningTime = computed(() => {
  if (props.agent.status !== 'running' || !props.agent.last_session?.started_at) return ''
  const started = new Date(props.agent.last_session.started_at)
  const diff = Math.floor((Date.now() - started.getTime()) / 1000)
  if (diff < 60) return `${diff}s`
  return `${Math.floor(diff / 60)}m`
})

function formatDate(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

// Close dropdown on outside click
function onClickOutside(e: MouseEvent) {
  if (dropdownRef.value && !dropdownRef.value.contains(e.target as Node)) {
    showDropdown.value = false
  }
}
onMounted(() => document.addEventListener('click', onClickOutside))
onUnmounted(() => document.removeEventListener('click', onClickOutside))

// Poll progress when running
let progressInterval: ReturnType<typeof setInterval> | null = null
watch(() => props.agent.status, (status) => {
  if (status === 'running') {
    pollProgress()
    progressInterval = setInterval(pollProgress, 10000)
  } else {
    progress.value = null
    if (progressInterval) { clearInterval(progressInterval); progressInterval = null }
  }
}, { immediate: true })
onUnmounted(() => { if (progressInterval) clearInterval(progressInterval) })

async function pollProgress() {
  const p = await agentsStore.fetchProgress()
  const mine = p.agents?.find(a => a.agent === props.agent.name)
  if (mine) {
    progress.value = { current: mine.current, total: mine.total }
  } else {
    progress.value = null
  }
}

async function handleLaunch() {
  launching.value = true
  const result = await agentsStore.launchAgent(props.agent.name)
  if (result.ok) {
    toastStore.success(result.message)
    emit('launched')
  } else {
    toastStore.error(result.message)
  }
  launching.value = false
}

async function handleAutoplay(count: number) {
  showDropdown.value = false
  launching.value = true
  const result = await agentsStore.launchAgent(props.agent.name, undefined, count)
  if (result.ok) {
    toastStore.success(result.message)
    emit('launched')
  } else {
    toastStore.error(result.message)
  }
  launching.value = false
}

async function handleStop() {
  stopping.value = true
  const result = await agentsStore.stopAgent(props.agent.name)
  if (result.ok) {
    toastStore.success(result.message)
  } else {
    toastStore.error(result.message)
  }
  stopping.value = false
}
</script>
