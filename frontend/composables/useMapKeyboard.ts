/**
 * Arrow/WASD keyboard movement (Factorio-style continuous) + Q/E zoom
 * + avatar actions (Space/R/T/Enter).
 *
 * Hold arrow keys or WASD to walk continuously. Diagonal movement supported.
 * Speed adapts to zoom level for consistent visual speed.
 * Hold Q/E to zoom out/in smoothly (same rAF loop as movement).
 */

import { nextTick, ref } from 'vue'
import type { Ref } from 'vue'

interface KeyboardOptions {
  getMap: () => any
  isActive: Ref<boolean>
  mapPresenceEnabled: Ref<boolean>
  authStore: { isAuthenticated: boolean; activeProfile: any }
  presenceActions: {
    setState: (state: 'idle' | 'walking' | 'jumping' | 'sitting' | 'emoting') => void
    setSpeechBubble: (text: string) => void
  }
  currentSpeechBubble: Ref<string>
  currentAvatarState: Ref<'idle' | 'walking' | 'jumping' | 'sitting' | 'emoting'>
  currentAvatarType: Ref<string>
  // Panel interactions
  activeAvatarPanel: Ref<'own' | 'other' | null>
  selectedOtherAvatar: Ref<any>
  setSelectedFeature: (f: any) => void
  setClickedFeatures: (f: any[]) => void
  setClickCoordinates: (c: any) => void
  featurePanelRef: Ref<any>
}

// Movement keys → direction vector { dx (East+), dy (North+) }
const MOVE_KEYS: Record<string, { dx: number; dy: number }> = {
  arrowup:    { dx: 0, dy: 1 },
  arrowdown:  { dx: 0, dy: -1 },
  arrowleft:  { dx: -1, dy: 0 },
  arrowright: { dx: 1, dy: 0 },
  w:          { dx: 0, dy: 1 },
  s:          { dx: 0, dy: -1 },
  a:          { dx: -1, dy: 0 },
  d:          { dx: 1, dy: 0 },
}

// LPC sprite directions (must match MapPresenceOverlay SPRITE_CONFIG.directions)
const DIR_UP = 0
const DIR_LEFT = 1
const DIR_DOWN = 2
const DIR_RIGHT = 3

/** Convert dx/dy vector to LPC sprite direction.
 *  Direction is INVERTED horizontally because we move the MAP, not the character:
 *  pressing Right moves map East → character visually walks West.
 *  But we want Factorio-feel where pressing Right = character faces Right,
 *  so we do NOT invert here (keyboard = direct character control). */
function vectorToDirection(dx: number, dy: number): number {
  // Prefer vertical when both axes active (matches Factorio)
  if (Math.abs(dy) >= Math.abs(dx)) {
    return dy > 0 ? DIR_UP : DIR_DOWN
  }
  return dx > 0 ? DIR_RIGHT : DIR_LEFT
}

// Zoom keys → zoom direction (held for smooth continuous zoom)
const ZOOM_KEYS: Record<string, number> = {
  q: -1, // zoom out
  e: 1,  // zoom in
}

// Walking speed in pixels/second at any zoom (visual consistency)
const WALK_SPEED_PX_PER_SEC = 120

// Zoom levels per second while Q/E held
const ZOOM_SPEED_PER_SEC = 1.6

export function useMapKeyboard(opts: KeyboardOptions) {
  const isKeyboardMoving = ref(false)
  const keyboardDirection = ref<number>(DIR_DOWN) // current facing direction

  const pressedMoveKeys = new Set<string>()
  const pressedZoomKeys = new Set<string>()
  let animFrameId: number | null = null
  let lastFrameTime = 0

  let keydownHandler: ((e: KeyboardEvent) => void) | null = null
  let keyupHandler: ((e: KeyboardEvent) => void) | null = null

  function isTyping(e: KeyboardEvent): boolean {
    const t = e.target as HTMLElement
    return t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable
  }

  /** Degrees per pixel at given zoom level (equator approximation, good enough for walking) */
  function degreesPerPx(zoom: number): number {
    // At zoom 0, world = 256px = 360°. Each zoom doubles resolution.
    return 360 / (256 * Math.pow(2, zoom))
  }

  /** Movement/zoom loop — called every frame while any move or zoom key is held */
  function movementTick(timestamp: number) {
    const map = opts.getMap()
    if (!map || (pressedMoveKeys.size === 0 && pressedZoomKeys.size === 0)) {
      stopLoop()
      return
    }

    if (lastFrameTime === 0) lastFrameTime = timestamp
    const dt = Math.min((timestamp - lastFrameTime) / 1000, 0.1) // cap at 100ms to avoid jumps
    lastFrameTime = timestamp

    // Zoom (Q/E) — smooth continuous zoom; MapLibre clamps to min/maxZoom
    let dz = 0
    for (const key of pressedZoomKeys) dz += ZOOM_KEYS[key] ?? 0
    if (dz !== 0) {
      map.setZoom(map.getZoom() + dz * ZOOM_SPEED_PER_SEC * dt)
    }

    // Sum direction vectors from all pressed movement keys
    let dx = 0
    let dy = 0
    for (const key of pressedMoveKeys) {
      const v = MOVE_KEYS[key]
      if (v) { dx += v.dx; dy += v.dy }
    }

    // Normalize diagonal so speed is consistent
    const len = Math.sqrt(dx * dx + dy * dy)
    if (len > 0) {
      dx /= len
      dy /= len

      // Convert pixel speed to degrees (zoom re-read after Q/E applied above)
      const zoom = map.getZoom()
      const degPerPx = degreesPerPx(zoom)
      const moveDeg = WALK_SPEED_PX_PER_SEC * degPerPx * dt

      const center = map.getCenter()
      map.setCenter([
        center.lng + dx * moveDeg,
        center.lat + dy * moveDeg,
      ])

      // Update direction for sprite
      keyboardDirection.value = vectorToDirection(dx, dy)
    }

    animFrameId = requestAnimationFrame(movementTick)
  }

  function startLoop() {
    if (animFrameId !== null) return // already running
    lastFrameTime = 0
    animFrameId = requestAnimationFrame(movementTick)
  }

  function stopLoop() {
    isKeyboardMoving.value = false
    if (animFrameId !== null) {
      cancelAnimationFrame(animFrameId)
      animFrameId = null
    }
    lastFrameTime = 0
  }

  /** Walking-sprite state follows MOVE keys only (zoom keys don't animate the avatar) */
  function syncMovingState() {
    const moving = pressedMoveKeys.size > 0
    if (moving && !isKeyboardMoving.value) {
      isKeyboardMoving.value = true
      // Stand up if sitting
      if (opts.currentAvatarState.value === 'sitting') {
        opts.presenceActions.setState('idle')
      }
    } else if (!moving) {
      isKeyboardMoving.value = false
    }
  }

  function attach() {
    // Idempotent — detach first to prevent double-registration
    if (keydownHandler) detach()

    keydownHandler = (e: KeyboardEvent) => {
      const map = opts.getMap()
      if (!map || !opts.isActive.value) return
      if (isTyping(e)) return
      // Don't hijack browser shortcuts (Ctrl+S, Ctrl+E, Cmd+Q, Alt+D, ...)
      if (e.ctrlKey || e.metaKey || e.altKey) return

      const key = e.key.toLowerCase()

      // Movement keys
      if (key in MOVE_KEYS) {
        e.preventDefault()
        if (!pressedMoveKeys.has(key)) {
          pressedMoveKeys.add(key)
          // Update direction immediately on new key press
          let dx = 0, dy = 0
          for (const k of pressedMoveKeys) {
            const v = MOVE_KEYS[k]
            if (v) { dx += v.dx; dy += v.dy }
          }
          if (dx !== 0 || dy !== 0) {
            keyboardDirection.value = vectorToDirection(dx, dy)
          }
          syncMovingState()
          startLoop()
        }
        return
      }

      // Zoom keys (Q/E) — held for smooth continuous zoom
      if (key in ZOOM_KEYS) {
        e.preventDefault()
        pressedZoomKeys.add(key)
        startLoop()
        return
      }

      // Action keys (non-movement)
      switch (key) {
        case ' ': // Jump (one-shot); Space, not E — E is zoom-in
          e.preventDefault()
          if (e.repeat) break
          if (opts.currentAvatarState.value === 'jumping') break
          if (opts.authStore.isAuthenticated && opts.mapPresenceEnabled.value) {
            opts.presenceActions.setState('jumping')
            setTimeout(() => {
              if (opts.currentAvatarState.value === 'jumping') {
                opts.presenceActions.setState('idle')
              }
            }, 600)
          }
          break
        case 'r': // Sit (toggle)
          e.preventDefault()
          if (e.repeat) break
          if (opts.authStore.isAuthenticated && opts.mapPresenceEnabled.value) {
            if (opts.currentAvatarState.value === 'sitting') {
              opts.presenceActions.setState('idle')
            } else {
              opts.presenceActions.setState('sitting')
            }
          }
          break
        case 't': // Emote (one-shot)
          e.preventDefault()
          if (e.repeat) break
          if (opts.currentAvatarState.value === 'emoting') break
          if (opts.authStore.isAuthenticated && opts.mapPresenceEnabled.value) {
            opts.presenceActions.setState('emoting')
            setTimeout(() => {
              if (opts.currentAvatarState.value === 'emoting') {
                opts.presenceActions.setState('idle')
              }
            }, 400)
          }
          break
        case 'enter': // Open panel and focus speech input
          if (e.repeat) break
          if (opts.authStore.isAuthenticated && opts.mapPresenceEnabled.value) {
            e.preventDefault()
            if (opts.activeAvatarPanel.value !== 'own') {
              opts.setSelectedFeature(null)
              opts.setClickedFeatures([])
              opts.setClickCoordinates(null)
              opts.activeAvatarPanel.value = 'own'
              opts.selectedOtherAvatar.value = null
            }
            nextTick(() => {
              opts.featurePanelRef.value?.focusSpeechInput()
            })
          }
          break
      }
    }

    keyupHandler = (e: KeyboardEvent) => {
      const key = e.key.toLowerCase()
      if (key in ZOOM_KEYS) {
        pressedZoomKeys.delete(key)
        // Loop self-terminates in movementTick once nothing is pressed
        return
      }
      if (key in MOVE_KEYS) {
        pressedMoveKeys.delete(key)
        syncMovingState()
        if (pressedMoveKeys.size > 0) {
          // Recalculate direction from remaining keys
          let dx = 0, dy = 0
          for (const k of pressedMoveKeys) {
            const v = MOVE_KEYS[k]
            if (v) { dx += v.dx; dy += v.dy }
          }
          if (dx !== 0 || dy !== 0) {
            keyboardDirection.value = vectorToDirection(dx, dy)
          }
        }
      }
    }

    window.addEventListener('keydown', keydownHandler)
    window.addEventListener('keyup', keyupHandler)
  }

  function detach() {
    stopLoop()
    pressedMoveKeys.clear()
    pressedZoomKeys.clear()
    if (keydownHandler) {
      window.removeEventListener('keydown', keydownHandler)
      keydownHandler = null
    }
    if (keyupHandler) {
      window.removeEventListener('keyup', keyupHandler)
      keyupHandler = null
    }
  }

  return { attach, detach, isKeyboardMoving, keyboardDirection }
}
