/**
 * Client-side video downscale to ≤1080p before upload.
 *
 * Why: phone cameras shoot 4K (~50 Mbps), but PeerTube transcodes everything to
 * max 1080p anyway (see PK/peertube-system.md) — so the 4K resolution is pure
 * upload/storage waste with zero benefit to viewers. Downscaling on the client
 * cuts the upload ~4-5× with no visible quality loss.
 *
 * How: mediabunny drives the WebCodecs API (hardware-accelerated H.264 encode),
 * which works both in mobile browsers and inside the Capacitor WebView — one code
 * path covers both. Audio is kept and remuxed automatically.
 *
 * Fallback contract: this NEVER blocks or loses an upload. If WebCodecs is
 * unavailable, the codec can't be encoded, the input is already small enough, or
 * anything throws — we return the ORIGINAL file untouched and let the server cope.
 */

const TARGET_LONG_EDGE = 1920 // 1080p class: cap the longer side, deduce the other
const MIN_DIM = 2

export interface DownscaleResult {
  file: File
  didCompress: boolean
  originalSize: number
  newSize: number
}

function roundEven(n: number): number {
  // H.264 requires even dimensions
  const v = Math.round(n / 2) * 2
  return Math.max(MIN_DIM, v)
}

export function useVideoDownscale() {
  function supported(): boolean {
    return (
      typeof window !== 'undefined' &&
      typeof (window as any).VideoEncoder === 'function' &&
      typeof (window as any).VideoDecoder === 'function'
    )
  }

  /**
   * @param onProgress called with 0–100 during transcode (only when actually compressing)
   * @param signal aborting it cancels the in-flight transcode and resolves to the original file
   */
  async function downscale(
    file: File,
    onProgress?: (pct: number) => void,
    signal?: AbortSignal,
  ): Promise<DownscaleResult> {
    const passthrough: DownscaleResult = {
      file,
      didCompress: false,
      originalSize: file.size,
      newSize: file.size,
    }

    if (!supported()) return passthrough

    try {
      const {
        Input,
        Output,
        Conversion,
        ALL_FORMATS,
        BlobSource,
        Mp4OutputFormat,
        BufferTarget,
        QUALITY_HIGH,
        canEncodeVideo,
      } = await import('mediabunny')

      const input = new Input({ source: new BlobSource(file), formats: ALL_FORMATS })
      const videoTrack = await input.getPrimaryVideoTrack()
      if (!videoTrack) return passthrough // audio-only / unreadable → leave as is

      const w = await videoTrack.getDisplayWidth()
      const h = await videoTrack.getDisplayHeight()
      const longest = Math.max(w || 0, h || 0)
      if (!longest || longest <= TARGET_LONG_EDGE) return passthrough // already ≤1080p

      // Cap the longer edge at 1920, deduce the shorter preserving aspect ratio.
      const scale = TARGET_LONG_EDGE / longest
      const targetW = roundEven(w * scale)
      const targetH = roundEven(h * scale)

      // Capability gate — older WebViews may lack H.264 encode.
      if (!(await canEncodeVideo('avc', { width: targetW, height: targetH }))) {
        return passthrough
      }

      const output = new Output({ format: new Mp4OutputFormat(), target: new BufferTarget() })
      const conversion = await Conversion.init({
        input,
        output,
        // Constrain only the longer edge; mediabunny deduces the other and keeps aspect.
        video:
          w >= h
            ? { width: TARGET_LONG_EDGE, codec: 'avc', bitrate: QUALITY_HIGH }
            : { height: TARGET_LONG_EDGE, codec: 'avc', bitrate: QUALITY_HIGH },
      })

      if (!conversion.isValid) return passthrough

      if (signal) {
        if (signal.aborted) {
          await conversion.cancel().catch(() => {})
          return passthrough
        }
        signal.addEventListener('abort', () => void conversion.cancel().catch(() => {}), {
          once: true,
        })
      }

      if (onProgress) {
        conversion.onProgress = (p: number) => onProgress(Math.round(p * 100))
      }

      try {
        await conversion.execute()
      } catch {
        // ConversionCanceledError (or any execute failure) → upload original
        return passthrough
      }

      const buffer = output.target.buffer
      if (!buffer) return passthrough

      const baseName = file.name.replace(/\.[^.]+$/, '') || 'video'
      const newFile = new File([buffer], `${baseName}-1080p.mp4`, { type: 'video/mp4' })

      // Safety: never upload something larger than the original.
      if (newFile.size >= file.size) return passthrough

      return {
        file: newFile,
        didCompress: true,
        originalSize: file.size,
        newSize: newFile.size,
      }
    } catch (e) {
      // Any failure → upload the original, don't break the user's flow.
      console.warn('[video-downscale] skipped, uploading original:', e)
      return passthrough
    }
  }

  return { downscale, supported }
}
