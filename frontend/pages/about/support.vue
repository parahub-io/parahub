<template>
  <div>
    <Head>
      <Title>{{ t('support_voice.title') }} — Parahub</Title>
    </Head>

    <div class="voice-page">
      <!-- Header -->
      <div class="voice-header">
        <div class="flex items-center gap-3">
          <img src="/logo.svg" alt="Parahub" class="h-10 w-10" />
          <div>
            <h1 class="text-lg font-semibold leading-tight">{{ t('support_voice.title') }}</h1>
            <p class="text-xs text-neutral-500 dark:text-neutral-400">{{ t('support_voice.subtitle') }}</p>
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
          <Headphones class="w-12 h-12 mx-auto mb-3 text-primary opacity-60" />
          <p class="text-sm">{{ t('support_voice.empty') }}</p>
          <p class="text-xs text-neutral-400 dark:text-neutral-500 mt-2">{{ t('support_voice.hint') }}</p>
        </div>

        <div
          v-for="(msg, i) in messages"
          :key="i"
          class="voice-message"
          :class="msg.role"
        >
          <span class="voice-role">{{ msg.role === 'user' ? t('voice_chat.you') : t('support_voice.bot_name') }}</span>
          <div class="voice-text-row">
            <span class="voice-text" v-html="linkify(msg.text)" />
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
          <span class="voice-role">{{ t('support_voice.bot_name') }}</span>
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
        <template v-else>
          <!-- Text input -->
          <form @submit.prevent="sendText" class="flex gap-2 mb-2">
            <input
              v-model="textInput"
              type="text"
              :placeholder="t('support_voice.type_placeholder')"
              :disabled="!isReady || isProcessing || !isOnline"
              class="flex-1 px-3 py-2.5 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent text-sm placeholder:text-neutral-400 dark:placeholder:text-neutral-500"
              maxlength="500"
            />
            <UiButton
              type="submit"
              variant="primary"
              :icon="Send"
              :disabled="!isReady || isProcessing || !textInput.trim() || !isOnline"
              :loading="isProcessing && !isRecording"
            />
          </form>
          <!-- Voice button -->
          <UiButton
            size="lg"
            :variant="isRecording ? 'error' : 'secondary'"
            :icon="isRecording ? MicOff : Mic"
            :disabled="!isReady || isProcessing || !isOnline"
            class="w-full"
            @click.prevent="toggleRecording"
          >
            {{ isRecording ? t('voice_chat.stop_recording') : t('voice_chat.tap_to_talk') }}
          </UiButton>
        </template>
        <NuxtLink
          :to="localePath('/about')"
          class="block text-center text-xs text-neutral-400 dark:text-neutral-500 mt-3 hover:text-neutral-600 dark:hover:text-neutral-300"
        >
          &larr; {{ t('support_voice.back_to_about') }}
        </NuxtLink>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Mic, MicOff, RotateCcw, WifiOff, RefreshCw, Headphones, Send } from 'lucide-vue-next'

definePageMeta({
  layout: 'default',
})

const { t } = useI18n()
const localePath = useLocalePath()

function linkify(text: string): string {
  const escaped = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  // Convert internal paths (/market/create, /docs/barter, etc.) to clickable links
  return escaped.replace(
    /(?:parahub\.io)?(\/(?:market|barter|contracts|debts|directory|events|governance|energy|map|transit|driver|chat|sos|ads|condo|tickets|shipments|iot|mesh|federation|profile|wallet|register|login|pgp-setup|seed-setup|docs)(?:\/[\w-]*)*)/g,
    (_, path) => `<a href="${path}" class="text-link underline">${path}</a>`
  )
}

// Map backend error messages to i18n keys
const errorMap: Record<string, string> = {
  'Voice service initialization failed': 'support_voice.errors.init_failed',
  'Too many requests. Please wait a moment.': 'support_voice.errors.rate_limit',
  'Still processing': 'support_voice.errors.busy',
  'Still processing previous request': 'support_voice.errors.busy',
  'Empty message': 'support_voice.errors.empty_message',
  'Nothing to replay': 'support_voice.errors.nothing_to_replay',
  'Text too long': 'support_voice.errors.text_long',
  'Replay failed. Please try again.': 'support_voice.errors.replay_failed',
  'Processing failed. Please try again.': 'support_voice.errors.processing_failed',
  'Voice processing failed. Please try again.': 'support_voice.errors.voice_failed',
  'Pipeline not ready': 'support_voice.errors.not_ready',
  'Audio too short': 'support_voice.errors.audio_short',
}
function translateError(msg: string): string {
  if (errorMap[msg]) return t(errorMap[msg])
  if (msg.startsWith('Daily limit reached')) return t('support_voice.errors.daily_limit')
  if (msg.startsWith('Audio too large')) return t('support_voice.errors.audio_large')
  if (msg.startsWith('Message too long')) return t('support_voice.errors.text_long')
  return msg
}

// State
const isConnected = ref(false)
const isReady = ref(false)
const isRecording = ref(false)
const isProcessing = ref(false)
const isOnline = ref(true)
const connectionFailed = ref(false)
const status = ref('connecting')
const error = ref('')
const messages = ref<Array<{ role: 'user' | 'agent'; text: string }>>([])
const replayingIndex = ref(-1)
const textInput = ref('')

const statusText = computed(() => {
  if (!isOnline.value) return t('voice_chat.offline')
  if (isRecording.value) return t('voice_chat.listening')
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

onMounted(() => {
  isOnline.value = navigator.onLine
  window.addEventListener('online', onOnline)
  window.addEventListener('offline', onOffline)
  document.addEventListener('visibilitychange', onVisibilityChange)
  connectWS()
})

onUnmounted(() => {
  document.removeEventListener('visibilitychange', onVisibilityChange)
  window.removeEventListener('online', onOnline)
  window.removeEventListener('offline', onOffline)
  intentionalClose = true
  if (reconnectTimer) clearTimeout(reconnectTimer)
  disconnectWS()
})

function onOnline() {
  isOnline.value = true
  error.value = ''
  if (!ws || ws.readyState === WebSocket.CLOSED || ws.readyState === WebSocket.CLOSING) {
    connectionFailed.value = false
    scheduleReconnect(500)
  }
}

function onOffline() {
  isOnline.value = false
  if (isRecording.value) stopRecording()
}

function onVisibilityChange() {
  if (document.visibilityState !== 'visible') return
  if (!ws || ws.readyState === WebSocket.CLOSED || ws.readyState === WebSocket.CLOSING) {
    scheduleReconnect(0)
  }
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
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    if (intentionalClose) return
    connectWS()
  }, delayMs)
}

function connectWS() {
  intentionalClose = false
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  ws = new WebSocket(`${protocol}//${location.host}/ws/v1/support/voice/`)
  ws.binaryType = 'arraybuffer'

  ws.onopen = () => {
    isConnected.value = true
    connectionFailed.value = false
    wsRetryCount = 0
    status.value = 'connecting'
  }

  ws.onmessage = (event) => {
    if (event.data instanceof ArrayBuffer) {
      playAudio(event.data)
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
    if (intentionalClose) {
      status.value = 'disconnected'
      return
    }
    if (event.code === 4029) {
      // Too many connections
      connectionFailed.value = true
      status.value = 'disconnected'
      error.value = t('support_voice.error_too_many')
      return
    }
    wsRetryCount++
    if (wsRetryCount <= MAX_WS_RETRIES) {
      const delay = Math.min(2000 * Math.pow(1.5, wsRetryCount - 1), 15000)
      status.value = 'connecting'
      scheduleReconnect(delay)
    } else {
      connectionFailed.value = true
      status.value = 'disconnected'
      error.value = t('voice_chat.error_connection')
    }
  }

  ws.onerror = () => {}
}

function disconnectWS() {
  if (mediaRecorder?.state === 'recording') mediaRecorder.stop()
  ws?.close(1000)
  ws = null
}

function handleMessage(data: any) {
  switch (data.type) {
    case 'connected':
      status.value = 'connecting'
      break
    case 'history':
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
      } else if (data.status === 'thinking') {
        status.value = 'thinking'
      } else if (data.status === 'response') {
        messages.value.push({ role: 'agent', text: data.text })
        status.value = 'speaking'
      } else if (data.status === 'speaking') {
        status.value = 'speaking'
      }
      break
    case 'done':
      isProcessing.value = false
      replayingIndex.value = -1
      status.value = 'ready'
      break
    case 'cleared':
      messages.value = []
      break
    case 'error':
      error.value = translateError(data.message)
      isProcessing.value = false
      replayingIndex.value = -1
      status.value = 'ready'
      break
  }
}

function sendText() {
  const text = textInput.value.trim()
  if (!text || !ws || ws.readyState !== WebSocket.OPEN || !isReady.value || isProcessing.value) return
  ws.send(JSON.stringify({ type: 'text', text }))
  textInput.value = ''
}

function toggleRecording() {
  if (isRecording.value) stopRecording()
  else startRecording()
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
  border-bottom: 1px solid rgb(212 212 216 / 0.3);
  flex-shrink: 0;
}
:root.dark .voice-header {
  border-color: rgb(82 82 91 / 0.5);
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
  color: rgb(115 115 115);
  text-align: center;
  margin-top: 3rem;
}
:root.dark .voice-empty {
  color: rgb(163 163 163);
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
