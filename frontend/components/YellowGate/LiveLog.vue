<template>
  <div class="bg-neutral-900 rounded-lg p-4 h-96 overflow-y-auto font-mono text-sm" ref="logContainer" role="log" aria-live="polite">
    <div v-if="lines.length === 0" class="text-neutral-500 italic">
      No log output yet
    </div>
    <div v-for="(line, i) in lines" :key="i" class="whitespace-pre-wrap break-all leading-relaxed" :class="lineClass(line)">
      <span v-if="lineBadge(line)" class="inline-block text-xs font-bold px-1.5 py-0.5 rounded mr-2" :class="lineBadge(line)!.cls">{{ lineBadge(line)!.label }}</span>
      <span v-html="highlight(line)"></span>
    </div>
  </div>
</template>

<script setup lang="ts">
const props = defineProps<{ agentName: string }>()

const agentsStore = useAgentsStore()
const lines = ref<string[]>([])
const logContainer = ref<HTMLElement | null>(null)
let wsConn: WebSocket | null = null
let pollInterval: ReturnType<typeof setInterval> | null = null

type Badge = { label: string; cls: string }

function lineBadge(line: string): Badge | null {
  if (line.startsWith('[tool]')) return { label: 'TOOL', cls: 'bg-warning/20 text-warning-400' }
  if (line.includes('[AUTOPLAY]')) return { label: 'AUTO', cls: 'bg-secondary/20 text-secondary-400' }
  if (line.includes('[FINISHED]')) return { label: 'DONE', cls: 'bg-success/20 text-success-400' }
  if (line.includes('[STOPPED]')) return { label: 'STOP', cls: 'bg-error/20 text-error-400' }
  if (line.includes('[CRASHED]')) return { label: 'CRASH', cls: 'bg-error/30 text-error-300' }
  if (line.includes('[REFUSED]')) return { label: 'REFUSED', cls: 'bg-warning/30 text-warning-300' }
  if (line.includes('[TIMEOUT]')) return { label: 'TIMEOUT', cls: 'bg-warning/20 text-warning-400' }
  return null
}

function lineClass(line: string): string {
  if (line.startsWith('[tool]')) return 'text-warning-400/80 border-l-2 border-warning/30 pl-2 my-0.5'
  if (line.includes('[FINISHED]')) return 'text-success-400'
  if (line.includes('[STOPPED]') || line.includes('[CRASHED]') || line.includes('ERROR')) return 'text-error-400'
  if (line.includes('[REFUSED]')) return 'text-warning-300'
  if (line.includes('[TIMEOUT]')) return 'text-warning-400'
  if (line.includes('[AUTOPLAY]')) return 'text-secondary-400'
  if (line.startsWith('**') && line.endsWith('**')) return 'text-neutral-100 font-bold'
  if (/^\d+\.\s/.test(line)) return 'text-neutral-200 pl-2'
  return 'text-neutral-400'
}

function highlight(raw: string): string {
  let line = raw
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  // Strip badge prefixes from displayed text
  line = line
    .replace(/^\[tool\]\s*/, '')
    .replace(/\[AUTOPLAY\]\s*/, '')
    .replace(/\[FINISHED\]\s*/, '')
    .replace(/\[STOPPED\]\s*/, '')
    .replace(/\[CRASHED\]\s*/, '')
    .replace(/\[REFUSED\]\s*[^\]]*/, '')
    .replace(/\[TIMEOUT\]\s*/, '')

  // Bold **text**
  line = line.replace(/\*\*(.+?)\*\*/g, '<span class="text-neutral-100 font-bold">$1</span>')

  // Backtick `code`
  line = line.replace(/`([^`]+)`/g, '<span class="text-secondary-400 bg-secondary/10 px-1 rounded">$1</span>')

  // File paths with line numbers (word.ext L123 or word.ext:123)
  line = line.replace(/(\S+\.\w{1,4})\s+L(\d+[\-\d]*)/g, '<span class="text-secondary-300">$1</span> <span class="text-neutral-500">L$2</span>')

  return line
}

async function loadInitialLog() {
  lines.value = await agentsStore.fetchLog(props.agentName, 100)
  scrollToBottom()
}

function scrollToBottom() {
  nextTick(() => {
    if (logContainer.value) {
      logContainer.value.scrollTop = logContainer.value.scrollHeight
    }
  })
}

async function connectWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const authStore = useAuthStore()
  await authStore.ensureToken()
  if (!authStore.token) return startPolling()
  const wsUrl = `${protocol}//${window.location.host}/ws/v1/realtime/?token=${authStore.token}`

  try {
    wsConn = new WebSocket(wsUrl)

    wsConn.onopen = () => {
      wsConn?.send(JSON.stringify({
        type: 'join',
        room: 'agent_log',
        id: props.agentName,
      }))
    }

    wsConn.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'agent_log.initial_state' && data.backfill) {
          lines.value = data.backfill
          scrollToBottom()
        }
        else if (data.raw && typeof data.raw === 'string') {
          lines.value.push(data.raw)
          if (lines.value.length > 500) lines.value = lines.value.slice(-500)
          scrollToBottom()
        }
      } catch {}
    }

    wsConn.onclose = () => {
      startPolling()
    }

    wsConn.onerror = () => {
      wsConn?.close()
    }
  } catch {
    startPolling()
  }
}

function startPolling() {
  if (pollInterval) return
  pollInterval = setInterval(async () => {
    const newLines = await agentsStore.fetchLog(props.agentName, 100)
    if (newLines.length !== lines.value.length || (newLines.length > 0 && newLines[newLines.length - 1] !== lines.value[lines.value.length - 1])) {
      lines.value = newLines
      scrollToBottom()
    }
  }, 5000)
}

watch(() => props.agentName, () => {
  lines.value = []
  loadInitialLog()
})

onMounted(() => {
  loadInitialLog()
  connectWebSocket()
})

onUnmounted(() => {
  wsConn?.close()
  if (pollInterval) clearInterval(pollInterval)
})
</script>
