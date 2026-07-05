/**
 * A short, pleasant two-note chime via the Web Audio API — no audio asset.
 *
 * Used to give a rental manager an audible cue the moment a live booking
 * arrives (a customer self-books while the board is open). Synthesised with an
 * oscillator + gain envelope, so it ships zero bytes, works offline, and needs
 * no `/sounds/*` file. Browsers gate audio behind a user gesture; the manager
 * has already navigated/clicked to reach the board, so `resume()` succeeds. If
 * audio is unavailable the call is a silent no-op — never fatal.
 *
 * The AudioContext is module-level (one per tab, reused across plays).
 */
let ctx: AudioContext | null = null

export function useChime() {
  function play() {
    if (typeof window === 'undefined') return
    try {
      const AC = window.AudioContext || (window as any).webkitAudioContext
      if (!AC) return
      ctx = ctx || new AC()
      if (ctx.state === 'suspended') ctx.resume()
      const now = ctx.currentTime
      // Two ascending sine notes (A5 → E6): a friendly "ti-ding".
      const notes = [
        { f: 880, t: 0, d: 0.18 },
        { f: 1318.5, t: 0.11, d: 0.32 },
      ]
      for (const n of notes) {
        const osc = ctx.createOscillator()
        const gain = ctx.createGain()
        osc.type = 'sine'
        osc.frequency.value = n.f
        const start = now + n.t
        // Quick attack, smooth exponential decay — avoids click artefacts.
        gain.gain.setValueAtTime(0.0001, start)
        gain.gain.exponentialRampToValueAtTime(0.2, start + 0.02)
        gain.gain.exponentialRampToValueAtTime(0.0001, start + n.d)
        osc.connect(gain).connect(ctx.destination)
        osc.start(start)
        osc.stop(start + n.d + 0.02)
      }
    } catch {
      /* audio unavailable — non-fatal */
    }
  }
  return { play }
}
