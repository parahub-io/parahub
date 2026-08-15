/**
 * Recording, sending and playing voice notes.
 *
 * The socket (`ws/v1/voice/notes/`) carries a JSON header naming the recipient
 * and then the raw audio; the server answers with progress and, ~2 s later, the
 * finished note. Playback goes through a queue rather than one `Audio` element:
 * with autoplay on and two notes landing together, a singleton player cuts the
 * first one off mid-word.
 *
 * The microphone itself lives in `useAudioRecorder`, shared with live mode.
 */

import { buildWsUrl, clearWsAuthCookie, setWsAuthCookie, shouldRetryWithToken } from '~/utils/wsAuth'

export interface VoiceNote {
  id: string
  object_type: string
  sender_id: string
  recipient_id: string
  direction: 'in' | 'out'
  source_lang: string
  target_lang: string
  source_text: string
  target_text: string
  audio_seconds: number
  has_audio: boolean
  audio_expires_at: string | null
  synthetic_voice: boolean
  cloned_voice: boolean
  played_at: string | null
  created_at: string | null
}

export interface VoiceQuota {
  used_seconds: number
  limit_seconds: number
  unlimited: boolean
  resets_at: string
}

export function useVoiceNotes(options: { onNote?: (note: VoiceNote) => void } = {}) {
  const { t } = useI18n()
  const authStore = useAuthStore()

  const isConnected = ref(false)
  const isReady = ref(false)
  const isProcessing = ref(false)
  const status = ref<'idle' | 'transcribing' | 'transcribed' | 'translating' | 'speaking'>('idle')
  const error = ref('')
  const errorCode = ref('')
  const quota = ref<VoiceQuota | null>(null)
  const myLanguage = ref('')
  const recipientReady = ref(false)
  const needsInteraction = ref(false)
  const playingNoteId = ref('')

  let socket: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let closing = false
  let retries = 0
  let currentRecipient = ''
  // Android WebView fallback, armed only after a handshake actually came back
  // unauthenticated — see the comment on `connect()`.
  let tokenInUrl = false

  const { isRecording, elapsedMs, countdown, start: startRecorder, stop: stopRecording }
    = useAudioRecorder({
      onRecording: sendRecording,
      onError: (code) => { error.value = t(`voice_notes.errors.${code}`) },
    })

  const quotaExhausted = computed(() =>
    !!quota.value && !quota.value.unlimited
    && quota.value.used_seconds >= quota.value.limit_seconds)

  const canRecord = computed(() =>
    isReady.value && recipientReady.value && !isProcessing.value && !quotaExhausted.value)

  // ===== Socket =====

  async function connect(recipientRef: string) {
    currentRecipient = recipientRef
    // Until the server confirms this recipient, the button must not be armed —
    // switching threads reuses the same open socket.
    recipientReady.value = false
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
      if (socket.readyState === WebSocket.OPEN) begin()
      return
    }
    closing = false

    // Same handshake as every other authed socket — cookie first, query string
    // only where the WebView has already proved it eats the cookie. The whole
    // rule lives in `utils/wsAuth`.
    await authStore.ensureToken()
    if (!authStore.token) {
      error.value = t('voice_notes.errors.not_signed_in')
      return
    }
    setWsAuthCookie(authStore.token)

    socket = new WebSocket(buildWsUrl('/ws/v1/voice/notes/', authStore.token, tokenInUrl))
    socket.binaryType = 'arraybuffer'

    socket.onopen = () => {
      isConnected.value = true
      retries = 0
    }
    socket.onmessage = (event) => {
      if (typeof event.data !== 'string') return
      try {
        handleMessage(JSON.parse(event.data))
      } catch {
        /* a frame we cannot read is a frame we ignore */
      }
    }
    socket.onclose = (event) => {
      isConnected.value = false
      isReady.value = false
      recipientReady.value = false
      socket = null
      // A socket that dies mid-note must not leave the button spinning.
      isProcessing.value = false
      if (closing) return
      // The server saw no valid token. On a native build that means the
      // WebView withheld the cookie; retry once with it in the query string.
      if (shouldRetryWithToken(event.code, tokenInUrl)) {
        tokenInUrl = true
        reconnectTimer = setTimeout(() => connect(currentRecipient), 200)
        return
      }
      retries += 1
      if (retries > 5) {
        error.value = t('voice_notes.errors.connection')
        return
      }
      reconnectTimer = setTimeout(() => connect(currentRecipient),
                                  Math.min(2000 * 2 ** (retries - 1), 20000))
    }
    socket.onerror = () => { /* onclose does the recovery */ }
  }

  function disconnect() {
    closing = true
    if (reconnectTimer) clearTimeout(reconnectTimer)
    reconnectTimer = null
    stopRecording()
    socket?.close(1000)
    socket = null
    clearWsAuthCookie()
  }

  function begin() {
    if (!socket || socket.readyState !== WebSocket.OPEN || !currentRecipient) return
    socket.send(JSON.stringify({ type: 'note.begin', recipient_id: currentRecipient }))
  }

  function handleMessage(data: any) {
    switch (data.type) {
      case 'ready':
        isReady.value = true
        quota.value = data.quota
        myLanguage.value = data.language || ''
        begin()
        break
      case 'note.ready':
        recipientReady.value = true
        break
      case 'status':
        status.value = data.status
        isProcessing.value = true
        break
      case 'note':
        isProcessing.value = false
        status.value = 'idle'
        quota.value = data.quota
        options.onNote?.(data.note as VoiceNote)
        break
      case 'error':
        isProcessing.value = false
        status.value = 'idle'
        errorCode.value = data.code || ''
        error.value = errorMessage(data)
        break
    }
  }

  function errorMessage(data: any): string {
    const code = data.code || ''
    if (code === 'quota_exceeded') {
      return t('voice_notes.errors.quota_exceeded', {
        used: data.minutes_used, limit: data.minutes_limit,
      })
    }
    const known = ['no_recipient', 'recipient_not_found', 'self_note', 'blocked', 'busy',
      'audio_too_short', 'audio_too_large', 'note_too_long', 'empty_transcription',
      'rate_limited', 'invalid_audio', 'pipeline_failed']
    // Unknown future codes fall back to the server's English text rather than
    // rendering a raw key at the user.
    return known.includes(code) ? t(`voice_notes.errors.${code}`) : (data.message || '')
  }

  // ===== Recording =====

  async function startRecording() {
    if (!canRecord.value || isRecording.value) return
    error.value = ''
    errorCode.value = ''
    unlockAudio()
    await startRecorder()
  }

  async function sendRecording(blob: Blob) {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      error.value = t('voice_notes.errors.connection')
      return
    }
    isProcessing.value = true
    status.value = 'transcribing'
    socket.send(await blob.arrayBuffer())
  }

  // ===== Playback =====
  //
  // One queue, one player. Two notes arriving together (or an autoplay landing
  // on top of a tapped replay) would otherwise cut each other off.

  const queue: Array<{ id: string; url: string }> = []
  let player: HTMLAudioElement | null = null
  const blobCache = new Map<string, string>()

  function unlockAudio() {
    // Playing anything at all inside a user gesture lifts the autoplay block for
    // the rest of the page's life; recording is the gesture we always have.
    needsInteraction.value = false
  }

  async function fetchAudioUrl(noteId: string): Promise<string> {
    const cached = blobCache.get(noteId)
    if (cached) return cached
    await authStore.ensureToken()
    const blob = await $fetch<Blob>(`/api/v1/voice/notes/${noteId}/audio`, {
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
      responseType: 'blob',
    })
    const url = URL.createObjectURL(blob)
    blobCache.set(noteId, url)
    return url
  }

  async function play(noteId: string) {
    try {
      const url = await fetchAudioUrl(noteId)
      queue.push({ id: noteId, url })
      if (!player) void advanceQueue()
    } catch {
      error.value = t('voice_notes.errors.audio_unavailable')
    }
  }

  async function advanceQueue() {
    const next = queue.shift()
    if (!next) {
      player = null
      playingNoteId.value = ''
      return
    }
    player = new Audio(next.url)
    playingNoteId.value = next.id
    const done = () => { player = null; void advanceQueue() }
    player.onended = done
    player.onerror = done
    try {
      await player.play()
    } catch {
      // Autoplay refused: the page has had no gesture yet. Say so instead of
      // silently doing nothing, and keep the clip for the tap that follows.
      needsInteraction.value = true
      queue.unshift(next)
      player = null
      playingNoteId.value = ''
    }
  }

  function stopPlayback() {
    player?.pause()
    player = null
    playingNoteId.value = ''
    queue.length = 0
  }

  async function markPlayed(noteId: string) {
    try {
      await authStore.ensureToken()
      await $fetch(`/api/v1/voice/notes/${noteId}/played`, {
        method: 'POST',
        credentials: 'include',
        headers: { Authorization: `Bearer ${authStore.token}` },
      })
    } catch {
      /* a missed read receipt is not worth an error in front of the user */
    }
  }

  onUnmounted(() => {
    disconnect()
    stopPlayback()
    blobCache.forEach(url => URL.revokeObjectURL(url))
    blobCache.clear()
  })

  return {
    // state
    isConnected, isReady, isRecording, isProcessing, status, error, errorCode,
    quota, myLanguage, quotaExhausted, canRecord, elapsedMs, countdown,
    needsInteraction, playingNoteId,
    // actions
    connect, disconnect, startRecording, stopRecording, play, stopPlayback, markPlayed,
  }
}
