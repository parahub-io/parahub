/**
 * Gamepad input system — singleton GamepadManager + per-component composable.
 *
 * Handler priority: stack-based. Last registered = highest priority.
 * Handler returns `false` to pass-through to lower-priority handler.
 * rAF loop only runs when a gamepad is connected.
 */

export const GAMEPAD_BUTTON = {
  A: 0, B: 1, X: 2, Y: 3,
  LB: 4, RB: 5, LT: 6, RT: 7,
  BACK: 8, START: 9, L3: 10, R3: 11,
  DPAD_UP: 12, DPAD_DOWN: 13, DPAD_LEFT: 14, DPAD_RIGHT: 15,
} as const

export type GamepadButtonIndex = (typeof GAMEPAD_BUTTON)[keyof typeof GAMEPAD_BUTTON]

type HandlerFn = () => boolean | void
type AxisHandlerFn = (value: number) => boolean | void
interface HandlerEntry { id: symbol; handler: HandlerFn }
interface AxisHandlerEntry { id: symbol; handler: AxisHandlerFn }

const REPEAT_DELAY = 500
const REPEAT_RATE = 100
const DEAD_ZONE = 0.15
const AXIS_REPEAT_DELAY = 300
const AXIS_REPEAT_RATE = 120

class GamepadManager {
  connected = false
  gamepadIndex = -1
  gamepadId = ''

  buttonHandlers = new Map<number, HandlerEntry[]>()
  axisHandlers = new Map<number, AxisHandlerEntry[]>()

  onAnyInput: (() => void) | null = null

  private _prevButtons: boolean[] = []
  private _buttonTimers = new Map<number, { startTime: number; lastRepeat: number }>()
  private _prevAxes: number[] = []
  private _axisRepeatTimers = new Map<number, { dir: number; startTime: number; lastRepeat: number }>()
  private _rafId = 0
  private _started = false
  private _boundPoll: (time: number) => void

  constructor() {
    this._boundPoll = this._poll.bind(this)
  }

  start() {
    if (this._started) return
    this._started = true
    window.addEventListener('gamepadconnected', this._onConnect)
    window.addEventListener('gamepaddisconnected', this._onDisconnect)
    // Check if already connected
    const gps = navigator.getGamepads()
    for (let i = 0; i < gps.length; i++) {
      if (gps[i]) { this._activate(i, gps[i]!.id); break }
    }
  }

  stop() {
    if (!this._started) return
    this._started = false
    window.removeEventListener('gamepadconnected', this._onConnect)
    window.removeEventListener('gamepaddisconnected', this._onDisconnect)
    this._stopLoop()
    this.connected = false
    this.gamepadIndex = -1
  }

  registerButton(button: number, handler: HandlerFn): symbol {
    const id = Symbol()
    if (!this.buttonHandlers.has(button)) this.buttonHandlers.set(button, [])
    this.buttonHandlers.get(button)!.push({ id, handler })
    return id
  }

  unregisterButton(button: number, id: symbol) {
    const stack = this.buttonHandlers.get(button)
    if (!stack) return
    const idx = stack.findIndex(e => e.id === id)
    if (idx !== -1) stack.splice(idx, 1)
  }

  registerAxis(axis: number, handler: AxisHandlerFn): symbol {
    const id = Symbol()
    if (!this.axisHandlers.has(axis)) this.axisHandlers.set(axis, [])
    this.axisHandlers.get(axis)!.push({ id, handler })
    return id
  }

  unregisterAxis(axis: number, id: symbol) {
    const stack = this.axisHandlers.get(axis)
    if (!stack) return
    const idx = stack.findIndex(e => e.id === id)
    if (idx !== -1) stack.splice(idx, 1)
  }

  // ── Private ──

  private _onConnect = (e: GamepadEvent) => {
    this._activate(e.gamepad.index, e.gamepad.id)
  }

  private _onDisconnect = (e: GamepadEvent) => {
    if (e.gamepad.index === this.gamepadIndex) {
      this.connected = false
      this.gamepadIndex = -1
      this.gamepadId = ''
      this._stopLoop()
      document.body.removeAttribute('data-gamepad-active')
    }
  }

  private _activate(index: number, id: string) {
    this.gamepadIndex = index
    this.gamepadId = id
    this.connected = true
    this._prevButtons = []
    this._buttonTimers.clear()
    this._prevAxes = []
    this._axisRepeatTimers.clear()
    this._startLoop()
  }

  private _startLoop() {
    if (this._rafId) return
    this._rafId = requestAnimationFrame(this._boundPoll)
  }

  private _stopLoop() {
    if (this._rafId) {
      cancelAnimationFrame(this._rafId)
      this._rafId = 0
    }
  }

  private _poll(time: number) {
    this._rafId = 0
    if (!this.connected) return

    const gp = navigator.getGamepads()[this.gamepadIndex]
    if (!gp) { this._rafId = requestAnimationFrame(this._boundPoll); return }

    let anyInput = false

    // Buttons
    for (let i = 0; i < gp.buttons.length; i++) {
      const pressed = gp.buttons[i].pressed
      const wasPressed = this._prevButtons[i] || false

      if (pressed && !wasPressed) {
        // Fresh press
        if (this._fireButton(i)) anyInput = true
        this._buttonTimers.set(i, { startTime: time, lastRepeat: time })
      } else if (pressed && wasPressed) {
        // Held — handle repeat
        const timer = this._buttonTimers.get(i)
        if (timer) {
          const held = time - timer.startTime
          if (held > REPEAT_DELAY && time - timer.lastRepeat > REPEAT_RATE) {
            if (this._fireButton(i)) anyInput = true
            timer.lastRepeat = time
          }
        }
      } else if (!pressed && wasPressed) {
        // Released
        this._buttonTimers.delete(i)
      }

      this._prevButtons[i] = pressed
    }

    // Axes (sticks)
    for (let a = 0; a < gp.axes.length; a++) {
      const raw = gp.axes[a]
      const value = Math.abs(raw) < DEAD_ZONE ? 0 : raw
      const prevValue = this._prevAxes[a] || 0
      const dir = value === 0 ? 0 : (value > 0 ? 1 : -1)
      const prevDir = prevValue === 0 ? 0 : (prevValue > 0 ? 1 : -1)

      if (value !== 0) {
        if (dir !== prevDir) {
          // Direction changed or new input
          if (this._fireAxis(a, value)) anyInput = true
          this._axisRepeatTimers.set(a, { dir, startTime: time, lastRepeat: time })
        } else {
          // Same direction held — repeat
          const timer = this._axisRepeatTimers.get(a)
          if (timer) {
            const held = time - timer.startTime
            if (held > AXIS_REPEAT_DELAY && time - timer.lastRepeat > AXIS_REPEAT_RATE) {
              if (this._fireAxis(a, value)) anyInput = true
              timer.lastRepeat = time
            }
          }
        }
      } else if (prevValue !== 0) {
        this._axisRepeatTimers.delete(a)
      }

      this._prevAxes[a] = value
    }

    if (anyInput && this.onAnyInput) this.onAnyInput()

    this._rafId = requestAnimationFrame(this._boundPoll)
  }

  private _fireButton(button: number): boolean {
    const stack = this.buttonHandlers.get(button)
    if (!stack || stack.length === 0) return false
    // Fire from top (last registered) to bottom
    for (let i = stack.length - 1; i >= 0; i--) {
      const result = stack[i].handler()
      if (result !== false) return true
    }
    return false
  }

  private _fireAxis(axis: number, value: number): boolean {
    const stack = this.axisHandlers.get(axis)
    if (!stack || stack.length === 0) return false
    for (let i = stack.length - 1; i >= 0; i--) {
      const result = stack[i].handler(value)
      if (result !== false) return true
    }
    return false
  }
}

// Lazy singleton
let _manager: GamepadManager | null = null
function _getOrCreateManager(): GamepadManager {
  if (!_manager) {
    _manager = new GamepadManager()
    _manager.start()
  }
  return _manager
}

export function useGamepad() {
  const manager = _getOrCreateManager()
  const isConnected = ref(manager.connected)

  // Sync reactive state at low frequency
  let syncInterval: ReturnType<typeof setInterval> | null = null
  if (import.meta.client) {
    syncInterval = setInterval(() => {
      isConnected.value = manager.connected
    }, 200)
  }

  // Track registrations for auto-cleanup
  const registrations: Array<{ type: 'button' | 'axis'; key: number; id: symbol }> = []

  function onButton(button: number, handler: HandlerFn): symbol {
    const id = manager.registerButton(button, handler)
    registrations.push({ type: 'button', key: button, id })
    return id
  }

  function onAxis(axis: number, handler: AxisHandlerFn): symbol {
    const id = manager.registerAxis(axis, handler)
    registrations.push({ type: 'axis', key: axis, id })
    return id
  }

  function offButton(button: number, id: symbol) {
    manager.unregisterButton(button, id)
    const idx = registrations.findIndex(r => r.id === id)
    if (idx !== -1) registrations.splice(idx, 1)
  }

  function offAxis(axis: number, id: symbol) {
    manager.unregisterAxis(axis, id)
    const idx = registrations.findIndex(r => r.id === id)
    if (idx !== -1) registrations.splice(idx, 1)
  }

  onUnmounted(() => {
    if (syncInterval) clearInterval(syncInterval)
    for (const reg of registrations) {
      if (reg.type === 'button') manager.unregisterButton(reg.key, reg.id)
      else manager.unregisterAxis(reg.key, reg.id)
    }
    registrations.length = 0
  })

  return {
    isConnected,
    onButton,
    onAxis,
    offButton,
    offAxis,
    BUTTON: GAMEPAD_BUTTON,
    /** Direct access to manager for plugin use */
    _manager: manager,
  }
}
