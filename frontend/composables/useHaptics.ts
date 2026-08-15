import { Capacitor } from '@capacitor/core'

/**
 * Haptic feedback for navigation gestures (drag-select + tap confirm).
 *
 * Two backends, deliberately not interchangeable:
 *   - Native (Capacitor Haptics) — the only path that exists on iOS: WKWebView
 *     does not implement the Vibration API, so the web fallback is silent there.
 *   - Web (navigator.vibrate) — Android browsers. Duration is the only knob the
 *     API exposes; amplitude is the OS's choice, not ours.
 *
 * Android deliberately goes through Haptics.vibrate({duration}) instead of the
 * plugin's presets. The presets are notification-weight, not detent-weight:
 * selectionChanged is 100ms at amplitude 100 and impact LIGHT is 50ms at 110,
 * against the few-millisecond tap this nav bar wants. iOS gets the Taptic
 * presets, which expose no duration and are already calibrated by the OS.
 *
 * Feel is tuned by these two constants alone. Keep the tick at or below the
 * confirm: the tick repeats under a sliding finger, the confirm fires once.
 */
const TICK_MS = 5
const CONFIRM_MS = 12

type HapticsApi = typeof import('@capacitor/haptics')

let api: HapticsApi | null = null
let pending: Promise<HapticsApi | null> | null = null

function isNative(): boolean {
  return process.client && Capacitor.isNativePlatform()
}

/** Lazy so the plugin never enters the SSR path or the web bundle's critical work. */
function loadNative(): Promise<HapticsApi | null> {
  if (api) return Promise.resolve(api)
  if (!pending) {
    pending = import('@capacitor/haptics')
      .then((m) => (api = m))
      .catch(() => null) // shell built before the plugin existed → web fallback
  }
  return pending
}

function webPulse(ms: number): void {
  if (typeof navigator !== 'undefined' && 'vibrate' in navigator) navigator.vibrate(ms)
}

export function useHaptics() {
  // Warm the import so the first tick of a drag isn't the one that pays for it
  if (isNative()) void loadNative()

  /** Faint detent when the finger crosses onto a different target. */
  function hapticTick(): void {
    if (!isNative()) return webPulse(TICK_MS)
    void loadNative()
      .then((m) => {
        if (!m) return webPulse(TICK_MS)
        return Capacitor.getPlatform() === 'ios'
          ? m.Haptics.selectionChanged()
          : m.Haptics.vibrate({ duration: TICK_MS })
      })
      .catch(() => webPulse(TICK_MS))
  }

  /** Confirm pulse when a selection commits to a screen change. */
  function hapticSelect(): void {
    if (!isNative()) return webPulse(CONFIRM_MS)
    void loadNative()
      .then((m) => {
        if (!m) return webPulse(CONFIRM_MS)
        return Capacitor.getPlatform() === 'ios'
          ? m.Haptics.impact({ style: m.ImpactStyle.Light })
          : m.Haptics.vibrate({ duration: CONFIRM_MS })
      })
      .catch(() => webPulse(CONFIRM_MS))
  }

  /**
   * Bracket a drag gesture. iOS needs it: selectionChanged() is silent unless a
   * UISelectionFeedbackGenerator was armed by selectionStart(), and holding it
   * open for the gesture is also what keeps the Taptic Engine pre-warmed.
   * No-op on Android and the web, which pulse per tick with no state to keep.
   */
  function hapticSelectionStart(): void {
    if (!isNative() || Capacitor.getPlatform() !== 'ios') return
    void loadNative().then((m) => m?.Haptics.selectionStart()).catch(() => {})
  }

  function hapticSelectionEnd(): void {
    if (!isNative() || Capacitor.getPlatform() !== 'ios') return
    void loadNative().then((m) => m?.Haptics.selectionEnd()).catch(() => {})
  }

  return { hapticTick, hapticSelect, hapticSelectionStart, hapticSelectionEnd }
}
