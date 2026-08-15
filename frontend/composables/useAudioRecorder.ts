/**
 * One microphone, taken and given back cleanly.
 *
 * Extracted so voice notes and live translation share a single copy of the
 * recording discipline, learned the hard way in the project this was ported
 * from: **every exit path must put the button back**. A denied microphone, a
 * stop-tap that races `getUserMedia`, a recorder that never started — each of
 * those leaves the UI stuck in "recording" forever unless it is unwound
 * explicitly, and each was a separate bug there.
 *
 * Errors come back as stable codes rather than sentences: the caller owns the
 * i18n namespace and the surface the message lands on.
 */

/** The recorder stops itself here; the server accepts a little more (clock skew). */
export const MAX_RECORD_MS = 60_000
const COUNTDOWN_FROM_MS = 5_000
const MIN_BLOB_BYTES = 1000

export type RecorderErrorCode = 'mic_denied' | 'mic_unavailable' | 'audio_too_short'

export interface AudioRecorderOptions {
  /** Called with the finished recording; short blobs never reach it. */
  onRecording: (blob: Blob) => void | Promise<void>
  onError: (code: RecorderErrorCode) => void
  maxMs?: number
}

export function useAudioRecorder(options: AudioRecorderOptions) {
  const maxMs = options.maxMs ?? MAX_RECORD_MS

  const isRecording = ref(false)
  const elapsedMs = ref(0)

  let recorder: MediaRecorder | null = null
  let stream: MediaStream | null = null
  let chunks: Blob[] = []
  let tickTimer: ReturnType<typeof setInterval> | null = null

  const countdown = computed(() => {
    const left = maxMs - elapsedMs.value
    return left <= COUNTDOWN_FROM_MS ? Math.max(0, Math.ceil(left / 1000)) : 0
  })

  async function start() {
    if (isRecording.value) return

    // Set before awaiting: the button has to show it is live from the tap, and
    // a stop-tap arriving during `getUserMedia` is detected by this flag.
    isRecording.value = true
    elapsedMs.value = 0

    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      })
    } catch (e: any) {
      isRecording.value = false
      stream = null
      options.onError(e?.name === 'NotAllowedError' || e?.name === 'PermissionDeniedError'
        ? 'mic_denied'
        : 'mic_unavailable')
      return
    }

    if (!isRecording.value) {
      // The user tapped stop while the microphone was still being handed over.
      release()
      return
    }

    chunks = []
    const mimeType = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4']
      .find(type => MediaRecorder.isTypeSupported(type))
    recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
    recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data) }
    recorder.onstop = () => {
      const blob = new Blob(chunks, { type: chunks[0]?.type || 'audio/webm' })
      chunks = []
      release()
      if (blob.size < MIN_BLOB_BYTES) {
        options.onError('audio_too_short')
        return
      }
      void options.onRecording(blob)
    }
    recorder.start()

    const startedAt = Date.now()
    tickTimer = setInterval(() => {
      elapsedMs.value = Date.now() - startedAt
      if (elapsedMs.value >= maxMs) stop()
    }, 100)
  }

  function stop() {
    if (!isRecording.value) return
    isRecording.value = false
    if (tickTimer) { clearInterval(tickTimer); tickTimer = null }
    if (recorder && recorder.state === 'recording') {
      recorder.stop()  // `onstop` releases the stream and hands the blob over
    } else {
      // The recorder never started (mic grab failed, or this tap raced it):
      // stop() would no-op and nothing would ever put the UI back.
      release()
    }
  }

  function release() {
    stream?.getTracks().forEach(track => track.stop())
    stream = null
    recorder = null
    if (tickTimer) { clearInterval(tickTimer); tickTimer = null }
    elapsedMs.value = 0
  }

  // A page left mid-recording must not keep the microphone light on.
  onUnmounted(() => {
    isRecording.value = false
    release()
  })

  return { isRecording, elapsedMs, countdown, start, stop, release }
}
