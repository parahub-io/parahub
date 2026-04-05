<template>
  <div>
    <Head>
      <Title>{{ agentData ? `${agentTitle} - ${t('voice_chat.title')}` : t('voice_chat.title') }} - Parahub</Title>
    </Head>

    <!-- Staff gate -->
    <div v-if="!isStaff" class="text-center py-20">
      <p class="text-neutral-500 dark:text-neutral-400">{{ t('voice_chat.staff_only') }}</p>
    </div>

    <div v-else-if="!agentData" class="text-center py-20">
      <p class="text-neutral-500 dark:text-neutral-400">{{ t('voice_chat.agent_not_found') }}</p>
      <UiButton variant="secondary" size="sm" class="mt-4" @click="navigateTo(localePath('/yellow-gate'))">
        {{ t('voice_chat.go_back') }}
      </UiButton>
    </div>

    <div v-else-if="!agentData.voice_enabled" class="text-center py-20">
      <img
        :src="`/img/agents/${agentName}.png`"
        :alt="agentData.display_name"
        class="w-16 h-16 rounded-full object-cover object-top mx-auto mb-4 opacity-50"
      />
      <p class="text-neutral-500 dark:text-neutral-400 mb-1 font-medium">{{ agentData.display_name }}</p>
      <p class="text-neutral-400 dark:text-neutral-500 text-sm">{{ t('voice_chat.voice_not_enabled') }}</p>
      <UiButton variant="secondary" size="sm" class="mt-4" @click="navigateTo(localePath('/yellow-gate'))">
        {{ t('voice_chat.go_back') }}
      </UiButton>
    </div>

    <div v-else class="voice-page">
      <!-- Header -->
      <div class="voice-header">
        <div class="flex items-center gap-3">
          <img
            :src="`/img/agents/${agentName}.png`"
            :alt="agentData.display_name"
            class="w-10 h-10 rounded-full object-cover object-top"
          />
          <div>
            <h1 class="text-lg font-semibold leading-tight text-neutral-900 dark:text-neutral-100">{{ agentData.display_name }}</h1>
            <p class="text-xs text-neutral-500 dark:text-neutral-400">{{ agentData.role }}</p>
          </div>
        </div>
        <div class="flex items-center gap-3">
          <UiBadge :variant="statusBadgeVariant" type="soft" size="sm">
            {{ statusText }}
          </UiBadge>
          <UiButton
            v-if="messages.length"
            variant="ghost"
            size="sm"
            @click="clearHistory"
          >
            {{ t('voice_chat.clear') }}
          </UiButton>
        </div>
      </div>

      <!-- Chat area -->
      <div ref="chatRef" class="voice-chat">
        <div v-if="messages.length === 0" class="voice-empty">
          <img
            :src="`/img/agents/${agentName}.png`"
            :alt="agentData.display_name"
            class="w-20 h-20 rounded-full object-cover object-top mx-auto mb-4 opacity-50"
          />
          <p>{{ t('voice_chat.empty') }}</p>
        </div>

        <div
          v-for="(msg, i) in messages"
          :key="i"
          class="voice-message"
          :class="msg.role"
        >
          <span class="voice-role">{{ msg.role === 'user' ? t('voice_chat.you') : agentData.display_name }}</span>
          <div class="voice-text-row">
            <span class="voice-text">{{ stripSsml(msg.text) }}</span>
            <UiButton
              v-if="msg.role === 'agent'"
              variant="ghost"
              size="sm"
              icon-only
              :icon="RotateCcw"
              :disabled="replayingIndex >= 0"
              :loading="replayingIndex === i"
              class="voice-replay"
              @click="replayMessage(i)"
            />
          </div>
        </div>

        <!-- Processing indicator -->
        <div v-if="isProcessing" class="voice-message agent">
          <span class="voice-role">{{ agentData.display_name }}</span>
          <span class="voice-text text-neutral-500 dark:text-neutral-400 italic">{{ statusText }}</span>
        </div>
      </div>

      <!-- Error -->
      <UiAlert v-if="error" variant="error" dismissible class="mx-0" @dismiss="error = ''">
        {{ error }}
      </UiAlert>

      <!-- Offline banner -->
      <div v-if="!isOnline" class="voice-offline-banner">
        <WifiOff class="w-4 h-4 shrink-0" />
        <span>{{ t('voice_chat.error_offline') }}</span>
      </div>

      <!-- Controls -->
      <div class="voice-controls">
        <UiButton
          v-if="connectionFailed && !isConnected"
          size="lg"
          variant="secondary"
          :icon="RefreshCw"
          class="w-full"
          :disabled="!isOnline"
          @click.prevent="retryConnection"
        >
          {{ t('voice_chat.retry') }}
        </UiButton>
        <UiButton
          v-else
          size="lg"
          :variant="isRecording ? 'error' : 'primary'"
          :icon="isRecording ? MicOff : isProcessing ? undefined : Mic"
          :loading="isProcessing"
          :disabled="!isReady || isProcessing || !isOnline"
          class="w-full"
          @click.prevent="toggleRecording"
        >
          {{ isRecording ? t('voice_chat.stop_recording') : isProcessing ? statusText : t('voice_chat.tap_to_talk') }}
        </UiButton>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Mic, MicOff, RotateCcw, WifiOff, RefreshCw } from 'lucide-vue-next'
import { isNative } from '~/utils/capacitor'

definePageMeta({
  middleware: 'auth',
})

const { t } = useI18n()
const localePath = useLocalePath()
const route = useRoute()
const authStore = useAuthStore()
const agentsStore = useAgentsStore()

const agentName = computed(() => route.params.agent as string)
const isStaff = computed(() => authStore.user?.is_staff ?? false)

// Load agent data
const agentData = computed(() => agentsStore.getAgent(agentName.value))
const agentTitle = computed(() => agentData.value?.display_name ?? t('voice_chat.title'))

// State
const isConnected = ref(false)
const isReady = ref(false)
const isRecording = ref(false)
const isProcessing = ref(false)
const isOnline = ref(true)
const connectionFailed = ref(false)
const status = ref('connecting')
const progressDetail = ref('')
const error = ref('')
const messages = ref<Array<{ role: 'user' | 'agent'; text: string }>>([])
const replayingIndex = ref(-1)

function stripSsml(text: string): string {
  return text.replace(/<break\s+time="[^"]*"\s*\/>/gi, '').replace(/\s{2,}/g, ' ').trim()
}

const statusText = computed(() => {
  if (!isOnline.value) return t('voice_chat.offline')
  if (isRecording.value) return t('voice_chat.listening')
  if (status.value === 'progress' && progressDetail.value) return progressDetail.value
  if (connectionFailed.value && !isConnected.value) return t('voice_chat.disconnected')
  return t(`voice_chat.${status.value}`, status.value)
})

const statusBadgeVariant = computed(() => {
  if (!isOnline.value) return 'error'
  if (connectionFailed.value && !isConnected.value) return 'error'
  if (isReady.value) return 'success'
  return 'neutral'
})

// WebSocket
let ws: WebSocket | null = null
let mediaRecorder: MediaRecorder | null = null
let audioChunks: Blob[] = []
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let intentionalClose = false
let wsRetryCount = 0
const MAX_WS_RETRIES = 5
let appStateListener: { remove: () => Promise<void> } | null = null

// Chat scroll
const chatRef = ref<HTMLElement | null>(null)
watch(messages, () => {
  nextTick(() => {
    if (chatRef.value) chatRef.value.scrollTop = chatRef.value.scrollHeight
  })
}, { deep: true })
watch(isProcessing, () => {
  nextTick(() => {
    if (chatRef.value) chatRef.value.scrollTop = chatRef.value.scrollHeight
  })
})

onMounted(async () => {
  if (!isStaff.value) return
  await authStore.ensureToken()
  // Load agents if not loaded yet
  if (!agentsStore.agents.length) await agentsStore.fetchAgents()

  // Network status
  isOnline.value = navigator.onLine
  window.addEventListener('online', onOnline)
  window.addEventListener('offline', onOffline)

  // Only connect if agent exists and has voice
  if (agentData.value?.voice_enabled) {
    connectWS()
  }
  // Reconnect when returning from background (mobile browser minimize)
  document.addEventListener('visibilitychange', onVisibilityChange)

  // Capacitor: listen for native app resume (more reliable than visibilitychange in WebView)
  if (isNative()) {
    import('@capacitor/app').then(({ App }) => {
      App.addListener('appStateChange', onAppStateChange).then(handle => {
        appStateListener = handle
      })
    }).catch(() => {})
  }
})

onUnmounted(() => {
  document.removeEventListener('visibilitychange', onVisibilityChange)
  window.removeEventListener('online', onOnline)
  window.removeEventListener('offline', onOffline)
  if (appStateListener) {
    appStateListener.remove().catch(() => {})
    appStateListener = null
  }
  intentionalClose = true
  if (reconnectTimer) clearTimeout(reconnectTimer)
  disconnectWS()
})

function onOnline() {
  isOnline.value = true
  error.value = ''
  // Auto-reconnect when network comes back
  if (!ws || ws.readyState === WebSocket.CLOSED || ws.readyState === WebSocket.CLOSING) {
    connectionFailed.value = false
    scheduleReconnect(500)
  }
}

function onOffline() {
  isOnline.value = false
  // Stop recording if in progress
  if (isRecording.value) stopRecording()
}

function onVisibilityChange() {
  if (document.visibilityState !== 'visible') return
  forceReconnect()
}

function onAppStateChange(state: { isActive: boolean }) {
  if (!state.isActive) return
  forceReconnect()
}

function forceReconnect() {
  if (!agentData.value?.voice_enabled) return

  // Clear any pending reconnect
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }

  // Force-close existing WS. After app minimize/resume, ws.readyState
  // may still report OPEN even though the TCP connection is dead
  // (mobile OS suspends network, but JS state lags behind by ~45-60s).
  // Null out event handlers to prevent stale onclose from interfering.
  if (ws) {
    ws.onclose = null
    ws.onmessage = null
    ws.onerror = null
    ws.onopen = null
    try { ws.close() } catch {}
    ws = null
  }

  // Reset state for fresh connection
  wsRetryCount = 0
  connectionFailed.value = false
  isConnected.value = false
  isReady.value = false
  status.value = 'connecting'

  scheduleReconnect(100)
}

function retryConnection() {
  error.value = ''
  connectionFailed.value = false
  wsRetryCount = 0
  status.value = 'connecting'
  connectWS()
}

function scheduleReconnect(delayMs = 2000) {
  if (reconnectTimer) clearTimeout(reconnectTimer)
  if (intentionalClose) return
  status.value = 'connecting'
  reconnectTimer = setTimeout(async () => {
    reconnectTimer = null
    if (intentionalClose) return
    await authStore.ensureToken()
    connectWS()
  }, delayMs)
}

function connectWS() {
  const token = authStore.token
  if (!token) return

  intentionalClose = false
  document.cookie = `ws_token=${token}; path=/; SameSite=Lax; Secure`

  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  // In Capacitor WebView, cookies may not be sent with WS upgrade requests —
  // pass token as query param fallback (middleware supports both methods)
  const tokenParam = isNative() ? `?token=${encodeURIComponent(token)}` : ''
  ws = new WebSocket(`${protocol}//${location.host}/ws/v1/agents/voice/${agentName.value}/${tokenParam}`)
  ws.binaryType = 'arraybuffer'

  ws.onopen = () => {
    isConnected.value = true
    connectionFailed.value = false
    wsRetryCount = 0
    status.value = 'connecting'
  }

  ws.onmessage = (event) => {
    if (event.data instanceof ArrayBuffer) {
      if (expectingFillers) {
        queueFiller(event.data)
      } else {
        playAudio(event.data)
      }
    } else {
      try {
        handleMessage(JSON.parse(event.data))
      } catch (e) {
        console.error('WS parse error:', e)
      }
    }
  }

  ws.onclose = (event) => {
    isConnected.value = false
    isReady.value = false
    document.cookie = 'ws_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT'
    if (intentionalClose) {
      status.value = 'disconnected'
      return
    }
    // 4001 = auth failed, 4003 = not staff — don't retry, show error
    if (event.code === 4001 || event.code === 4003) {
      connectionFailed.value = true
      status.value = 'disconnected'
      error.value = event.code === 4001
        ? t('voice_chat.error_connection')
        : t('voice_chat.staff_only')
      return
    }
    // 4009 = concurrent connection rejection — don't auto-retry, show retry button
    if (event.code === 4009) {
      connectionFailed.value = true
      status.value = 'disconnected'
      return
    }
    wsRetryCount++
    if (wsRetryCount <= MAX_WS_RETRIES) {
      // Auto-reconnect with exponential backoff
      const delay = Math.min(2000 * Math.pow(1.5, wsRetryCount - 1), 15000)
      status.value = 'connecting'
      scheduleReconnect(delay)
    } else {
      // Give up, show retry button
      connectionFailed.value = true
      status.value = 'disconnected'
      error.value = t('voice_chat.error_connection')
    }
  }

  ws.onerror = () => {
    // onerror always fires before onclose — don't set error here,
    // let onclose handle the retry logic
  }
}

function disconnectWS() {
  if (mediaRecorder?.state === 'recording') mediaRecorder.stop()
  ws?.close(1000)
  ws = null
  document.cookie = 'ws_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT'
}

function handleMessage(data: any) {
  switch (data.type) {
    case 'connected':
      status.value = 'connecting'
      break
    case 'history':
      // Restore conversation from server
      messages.value = (data.messages || []).flatMap((m: any) => [
        { role: 'user' as const, text: m.user },
        { role: 'agent' as const, text: m.agent },
      ])
      break
    case 'ready':
      isReady.value = true
      status.value = 'ready'
      break
    case 'status':
      if (data.status === 'transcribing') {
        status.value = 'transcribing'
        isProcessing.value = true
      } else if (data.status === 'transcript') {
        messages.value.push({ role: 'user', text: data.text })
        status.value = 'thinking'
        expectingFillers = true
      } else if (data.status === 'thinking') {
        status.value = 'thinking'
        progressDetail.value = ''
      } else if (data.status === 'progress') {
        progressDetail.value = data.detail || ''
        status.value = 'progress'
      } else if (data.status === 'tool_use') {
        status.value = 'using_tool'
      } else if (data.status === 'response') {
        stopFillers()
        expectingFillers = false
        messages.value.push({ role: 'agent', text: data.text })
        status.value = 'speaking'
      } else if (data.status === 'speaking') {
        status.value = 'speaking'
      }
      break
    case 'done':
      isProcessing.value = false
      replayingIndex.value = -1
      progressDetail.value = ''
      status.value = 'ready'
      break
    case 'cleared':
      messages.value = []
      break
    case 'error':
      error.value = data.message
      isProcessing.value = false
      replayingIndex.value = -1
      progressDetail.value = ''
      status.value = 'ready'
      break
  }
}

function toggleRecording() {
  if (isRecording.value) {
    stopRecording()
  } else {
    startRecording()
  }
}

async function startRecording() {
  if (!isReady.value || isProcessing.value) return
  error.value = ''
  ensureAudioContext()

  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true }
    })

    audioChunks = []
    mediaRecorder = new MediaRecorder(stream, {
      mimeType: MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm'
    })

    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunks.push(e.data)
    }

    mediaRecorder.onstop = () => {
      stream.getTracks().forEach(t => t.stop())
      sendAudio()
    }

    mediaRecorder.start()
    isRecording.value = true
  } catch (e: any) {
    if (e.name === 'NotAllowedError' || e.name === 'PermissionDeniedError') {
      error.value = t('voice_chat.error_mic_denied')
    } else if (e.name === 'NotFoundError' || e.name === 'DevicesNotFoundError') {
      error.value = t('voice_chat.error_mic_unavailable')
    } else {
      error.value = t('voice_chat.error_mic')
    }
  }
}

function stopRecording() {
  if (mediaRecorder?.state === 'recording') {
    mediaRecorder.stop()
    isRecording.value = false
  }
}

async function sendAudio() {
  if (!audioChunks.length || !ws || ws.readyState !== WebSocket.OPEN) return

  const blob = new Blob(audioChunks, { type: 'audio/webm;codecs=opus' })
  if (blob.size < 1000) {
    error.value = t('voice_chat.error_short')
    return
  }

  const buffer = await blob.arrayBuffer()
  ws.send(buffer)
}

// Filler audio queue (tier-1 pre-recorded + tier-2 contextual)
let expectingFillers = false
let fillerQueue: ArrayBuffer[] = []
let currentFillerSource: AudioBufferSourceNode | null = null
let playingFiller = false

function queueFiller(data: ArrayBuffer) {
  fillerQueue.push(data)
  if (!playingFiller) playNextFiller()
}

function playNextFiller() {
  if (!fillerQueue.length) {
    playingFiller = false
    return
  }
  playingFiller = true
  const data = fillerQueue.shift()!
  const ctx = ensureAudioContext()
  ctx.decodeAudioData(data.slice(0))
    .then(buffer => {
      currentFillerSource = ctx.createBufferSource()
      currentFillerSource.buffer = buffer
      currentFillerSource.connect(ctx.destination)
      currentFillerSource.onended = () => {
        currentFillerSource = null
        playNextFiller()
      }
      currentFillerSource.start()
    })
    .catch(e => {
      console.warn('Filler decode error:', e)
      playNextFiller()
    })
}

function stopFillers() {
  fillerQueue = []
  if (currentFillerSource) {
    try { currentFillerSource.stop() } catch {}
    currentFillerSource = null
  }
  playingFiller = false
}

// AudioContext for reliable playback
let audioCtx: AudioContext | null = null

function ensureAudioContext() {
  if (!audioCtx) audioCtx = new AudioContext()
  if (audioCtx.state === 'suspended') audioCtx.resume()
  return audioCtx
}

function playAudio(data: ArrayBuffer) {
  const ctx = ensureAudioContext()
  ctx.decodeAudioData(data.slice(0))
    .then(buffer => {
      const source = ctx.createBufferSource()
      source.buffer = buffer
      source.connect(ctx.destination)
      source.start()
    })
    .catch(e => {
      console.warn('AudioContext decode failed, trying Audio element:', e)
      const blob = new Blob([data], { type: 'audio/mpeg' })
      const url = URL.createObjectURL(blob)
      const audio = new Audio(url)
      audio.onended = () => URL.revokeObjectURL(url)
      audio.play().catch(e2 => console.error('Audio play failed:', e2))
    })
}

function replayMessage(index: number) {
  const msg = messages.value[index]
  if (!msg || msg.role !== 'agent' || !ws || ws.readyState !== WebSocket.OPEN) return
  replayingIndex.value = index
  ws.send(JSON.stringify({ type: 'replay', text: msg.text }))
}

function clearHistory() {
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'clear' }))
  }
  messages.value = []
}
</script>

<style scoped>
.voice-page {
  display: flex;
  flex-direction: column;
  max-width: 640px;
  margin: 0 auto;
  padding: 0 1rem;
  overflow: hidden;
  /* sticky layout: fill viewport minus navbar */
  position: fixed;
  top: 3.5rem;
  bottom: var(--safe-area-inset-bottom, env(safe-area-inset-bottom, 0px));
  left: 0;
  right: 0;
}

@media (min-width: 640px) {
  .voice-page { top: 4rem; }
}
@media (min-width: 768px) {
  .voice-page { top: 5rem; }
}

.voice-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 0;
  border-bottom: 1px solid rgb(212 212 216 / 0.3); /* neutral-300 */
  flex-shrink: 0;
}
:root.dark .voice-header {
  border-color: rgb(82 82 91 / 0.5); /* neutral-600 */
}

.voice-chat {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 1rem 0;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.voice-empty {
  color: rgb(115 115 115); /* neutral-500 */
  text-align: center;
  margin-top: 3rem;
  font-size: 0.875rem;
}
:root.dark .voice-empty {
  color: rgb(163 163 163); /* neutral-400 */
}

.voice-message {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}

.voice-role {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.voice-message.user .voice-role { color: rgb(115 115 115); }
:root.dark .voice-message.user .voice-role { color: rgb(163 163 163); }
.voice-message.agent .voice-role { color: #eab308; }

.voice-text-row {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
}

.voice-text {
  font-size: 0.9375rem;
  line-height: 1.5;
  flex: 1;
  color: rgb(23 23 23); /* neutral-900 */
}
:root.dark .voice-text {
  color: rgb(229 229 229); /* neutral-200 */
}

.voice-replay {
  flex-shrink: 0;
}

.voice-offline-banner {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  border-radius: 0.375rem;
  font-size: 0.8125rem;
  color: #b91c1c;
  background: #fef2f2;
  flex-shrink: 0;
}
:root.dark .voice-offline-banner {
  color: #fca5a5;
  background: rgba(127, 29, 29, 0.3);
}

.voice-controls {
  padding: 1rem 0 1.5rem;
  flex-shrink: 0;
}
</style>
