/**
 * Live mode: one phone between two people, each speaking into their own half.
 *
 * The same socket as voice notes (`ws/v1/voice/notes/`), addressed differently:
 * a turn names a language pair and which half was tapped instead of naming a
 * recipient, because the person across the table has no account here. The
 * answer comes back as metadata and then the audio it describes — nothing is
 * stored server-side, so frame order is what pairs them, and once the clip has
 * played the only trace of the exchange is the seconds it cost.
 *
 * The microphone is `useAudioRecorder`, shared with voice notes; there is one
 * of it, because there is one phone.
 */

import type { VoiceQuota } from '~/composables/useVoiceNotes'
import { buildWsUrl, clearWsAuthCookie, setWsAuthCookie, shouldRetryWithToken } from '~/utils/wsAuth'

export type LiveSide = 'HOST' | 'GUEST'

export interface LiveTurn {
  spoken_by: LiveSide
  source_lang: string
  target_lang: string
  source_text: string
  target_text: string
  seconds: number
  synthetic_voice: boolean
  cloned_voice: boolean
}

/** The languages the pipeline speaks — the six the platform is translated into. */
export const LIVE_LANGUAGES = ['en', 'es', 'fr', 'de', 'pt', 'ru'] as const

export function useLiveTranslate() {
  const { t } = useI18n()
  const authStore = useAuthStore()

  const isConnected = ref(false)
  const isReady = ref(false)
  const isProcessing = ref(false)
  const status = ref<'idle' | 'transcribing' | 'transcribed' | 'translating' | 'speaking'>('idle')
  const error = ref('')
  const quota = ref<VoiceQuota | null>(null)
  const needsInteraction = ref(false)
  const isPlaying = ref(false)

  // The pair persists between conversations: the same two people usually meet
  // again, and re-picking two languages every time is the friction this mode
  // exists to remove.
  const hostLang = useLocalPref('voice_live_host_lang', '')
  const guestLang = useLocalPref('voice_live_guest_lang', 'pt')

  // Which half is speaking right now, '' between turns.
  const activeSide = ref<LiveSide | ''>('')
  // What each half currently has to read, always in that half's own language.
  const hostText = ref('')
  const guestText = ref('')
  const lastTurn = ref<LiveTurn | null>(null)

  let socket: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let closing = false
  let retries = 0
  let tokenInUrl = false
  // Set by `live.turn`, consumed by the binary frame that follows it.
  let awaitingAudio = false

  const { isRecording, elapsedMs, countdown, start: startRecorder, stop: stopRecording }
    = useAudioRecorder({
      onRecording: sendTurn,
      onError: (code) => {
        activeSide.value = ''
        error.value = t(`voice_notes.errors.${code}`)
      },
    })

  const quotaExhausted = computed(() =>
    !!quota.value && !quota.value.unlimited
    && quota.value.used_seconds >= quota.value.limit_seconds)

  const sameLanguage = computed(() => !!hostLang.value && hostLang.value === guestLang.value)

  const canRecord = computed(() =>
    isReady.value && !isProcessing.value && !quotaExhausted.value && !sameLanguage.value)

  // ===== Socket =====

  async function connect() {
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
      return
    }
    closing = false

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
      if (typeof event.data !== 'string') {
        playIncoming(event.data as ArrayBuffer)
        return
      }
      try {
        handleMessage(JSON.parse(event.data))
      } catch {
        /* a frame we cannot read is a frame we ignore */
      }
    }
    socket.onclose = (event) => {
      isConnected.value = false
      isReady.value = false
      socket = null
      // A socket that dies mid-turn must not leave the button spinning.
      isProcessing.value = false
      activeSide.value = ''
      awaitingAudio = false
      if (closing) return
      // The server saw no valid token. On a native build that means the
      // WebView withheld the cookie; retry once with it in the query string.
      if (shouldRetryWithToken(event.code, tokenInUrl)) {
        tokenInUrl = true
        reconnectTimer = setTimeout(() => connect(), 200)
        return
      }
      retries += 1
      if (retries > 5) {
        error.value = t('voice_notes.errors.connection')
        return
      }
      reconnectTimer = setTimeout(() => connect(),
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

  function handleMessage(data: any) {
    switch (data.type) {
      case 'ready':
        isReady.value = true
        quota.value = data.quota
        // The server owns the account's language; the guest's is the user's to
        // pick. Portugal is the audience, so the other half of a first
        // conversation is Portuguese unless that is already this half.
        if (!hostLang.value) hostLang.value = data.language || 'en'
        if (guestLang.value === hostLang.value) {
          guestLang.value = hostLang.value === 'pt' ? 'en' : 'pt'
        }
        break
      case 'live.ready':
        break  // the audio frame is already on its way
      case 'status':
        status.value = data.status
        isProcessing.value = true
        // Detection can hand the turn to the other half — the phone is shared,
        // and whoever actually spoke is who the answer belongs to.
        if (data.spoken_by) activeSide.value = data.spoken_by
        break
      case 'live.turn':
        applyTurn(data.turn as LiveTurn)
        quota.value = data.quota
        awaitingAudio = true
        break
      case 'error':
        isProcessing.value = false
        status.value = 'idle'
        activeSide.value = ''
        awaitingAudio = false
        error.value = errorMessage(data)
        break
    }
  }

  function applyTurn(turn: LiveTurn) {
    lastTurn.value = turn
    // Each half reads its own language, whichever direction the turn ran.
    if (turn.spoken_by === 'HOST') {
      hostText.value = turn.source_text
      guestText.value = turn.target_text
    } else {
      guestText.value = turn.source_text
      hostText.value = turn.target_text
    }
  }

  function errorMessage(data: any): string {
    const code = data.code || ''
    if (code === 'quota_exceeded') {
      return t('voice_notes.errors.quota_exceeded', {
        used: data.minutes_used, limit: data.minutes_limit,
      })
    }
    const known = ['busy', 'audio_too_short', 'audio_too_large', 'note_too_long',
      'empty_transcription', 'rate_limited', 'invalid_audio', 'pipeline_failed',
      'same_language', 'unsupported_language', 'invalid_side', 'no_direction']
    return known.includes(code) ? t(`voice_notes.errors.${code}`) : (data.message || '')
  }

  // ===== Speaking =====

  async function speak(side: LiveSide) {
    if (!canRecord.value || isRecording.value) return
    error.value = ''
    needsInteraction.value = false
    stopPlayback()
    activeSide.value = side
    await startRecorder()
  }

  function stop() {
    stopRecording()
  }

  async function sendTurn(blob: Blob) {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      activeSide.value = ''
      error.value = t('voice_notes.errors.connection')
      return
    }
    const side = activeSide.value || 'HOST'
    isProcessing.value = true
    status.value = 'transcribing'
    socket.send(JSON.stringify({
      type: 'live.begin',
      spoken_by: side,
      source_lang: side === 'HOST' ? hostLang.value : guestLang.value,
      target_lang: side === 'HOST' ? guestLang.value : hostLang.value,
    }))
    socket.send(await blob.arrayBuffer())
  }

  // ===== Playback =====
  //
  // One clip at a time, kept only until the next turn replaces it: the whole
  // point of live mode is that nothing is filed away.

  let player: HTMLAudioElement | null = null
  let currentUrl = ''

  function playIncoming(buffer: ArrayBuffer) {
    if (!awaitingAudio) return
    awaitingAudio = false
    isProcessing.value = false
    status.value = 'idle'
    activeSide.value = ''
    replaceClip(new Blob([buffer], { type: 'audio/mpeg' }))
    void playClip()
  }

  function replaceClip(blob: Blob) {
    if (currentUrl) URL.revokeObjectURL(currentUrl)
    currentUrl = URL.createObjectURL(blob)
  }

  async function playClip() {
    if (!currentUrl) return
    stopPlayback()
    player = new Audio(currentUrl)
    isPlaying.value = true
    const done = () => { player = null; isPlaying.value = false }
    player.onended = done
    player.onerror = done
    try {
      await player.play()
    } catch {
      // Autoplay refused: this page has had no gesture yet. Say so instead of
      // silently doing nothing — the clip stays for the tap that follows.
      needsInteraction.value = true
      done()
    }
  }

  function replay() {
    needsInteraction.value = false
    void playClip()
  }

  function stopPlayback() {
    player?.pause()
    player = null
    isPlaying.value = false
  }

  const canReplay = computed(() => !!lastTurn.value)

  onUnmounted(() => {
    disconnect()
    stopPlayback()
    if (currentUrl) URL.revokeObjectURL(currentUrl)
  })

  return {
    // state
    isConnected, isReady, isProcessing, status, error, quota, quotaExhausted,
    canRecord, isRecording, elapsedMs, countdown, needsInteraction, isPlaying,
    activeSide, hostLang, guestLang, hostText, guestText, lastTurn, sameLanguage,
    canReplay,
    // actions
    connect, disconnect, speak, stop, replay, stopPlayback,
  }
}
