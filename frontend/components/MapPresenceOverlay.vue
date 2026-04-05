<template>
  <!-- Sprite overlay canvas (pointer-events: none to allow map interaction) -->
  <canvas
    v-if="map && canvasReady"
    ref="spriteCanvas"
    class="sprite-overlay"
    aria-hidden="true"
    :style="{
      position: 'absolute',
      top: 0,
      left: 0,
      width: '100%',
      height: '100%',
      pointerEvents: 'none',
      zIndex: 10
    }"
  />
</template>

<script setup lang="ts">
import { watch, onBeforeUnmount, ref, onMounted } from 'vue'
import type { Avatar } from '~/composables/useMapPresence'
import type { Map as MapLibreMap } from 'maplibre-gl'

interface Props {
  map: MapLibreMap | null
  avatars: Avatar[]  // Other users from WebSocket
  ownProfileId: string | null
  ownAvatarType?: string  // Current user's avatar type
  ownSpeechBubble?: string  // Current user's speech bubble
  ownAvatarState?: string  // Current user's state (idle, dancing, jumping)
  isKeyboardMoving?: boolean  // Factorio-style continuous keyboard movement active
  keyboardDirection?: number  // LPC direction (0=Up, 1=Left, 2=Down, 3=Right)
}

const props = defineProps<Props>()

// Own avatar position (animated, not instantly at map center)
const ownAvatarPosition = ref<{ lat: number; lon: number } | null>(null)

// Animation state for own avatar movement
const ownMovementAnimation = ref<{
  startPosition: { lat: number; lon: number } | null
  targetPosition: { lat: number; lon: number } | null
  startTime: number
  duration: number  // 2 seconds
  isAnimating: boolean
}>({
  startPosition: null,
  targetPosition: null,
  startTime: 0,
  duration: 2000,
  isAnimating: false
})

// Track if we're zooming (to ignore position changes during zoom)
const isZooming = ref(false)
let zoomTimeout: ReturnType<typeof setTimeout> | null = null

// Track if map is being dragged/moved (to keep avatar stationary during drag)
const isMapMoving = ref(false)
const lastStablePosition = ref<{ lat: number; lon: number } | null>(null)

const emit = defineEmits<{
  avatarClick: [avatar: Avatar, isOwn: boolean]
}>()

const LAYER_ID = 'avatar-sprites-layer'

const layerAdded = ref(false)
const spritesheetImages = ref<Map<string, HTMLImageElement>>(new Map())
const spriteCanvas = ref<HTMLCanvasElement | null>(null)
let throttledRenderSprites: (() => void) | null = null
const canvasReady = ref(false)

// Hover tracking
const mousePosition = ref<{ x: number; y: number } | null>(null)
const hoveredAvatarId = ref<string | null>(null)

// Spatial audio for avatar sounds
let audioContext: AudioContext | null = null
let jumpSoundBuffer: AudioBuffer | null = null
let skinSoundBuffer: AudioBuffer | null = null
let saySoundBuffer: AudioBuffer | null = null
const playedJumpSounds = ref<Set<string>>(new Set()) // Track which avatars have played jump this cycle
const lastAvatarTypes = ref<Map<string, string>>(new Map()) // Track avatar types for skin change detection
const lastSpeechBubbles = ref<Map<string, string>>(new Map()) // Track speech bubbles for say detection

// LPC Spritesheet configuration (64x64 frames, 4 directions)
// Source: https://liberatedpixelcup.github.io/Universal-LPC-Spritesheet-Character-Generator/
const SPRITE_CONFIG = {
  frameWidth: 64,
  frameHeight: 64,

  // LPC uses 4 directions: Up (North), Left (West), Down (South), Right (East)
  // Each animation has 4 consecutive rows for these directions
  directions: {
    UP: 0,     // North - away from viewer
    LEFT: 1,   // West - facing left
    DOWN: 2,   // South - facing viewer
    RIGHT: 3,  // East - facing right
  },

  // Animation definitions: { startRow, frames }
  // LPC row layout (each animation has 4 rows for Up/Left/Down/Right):
  // Animation behavior: 'loop' (repeat), 'once' (play then idle), 'freeze' (stop on last frame)
  animations: {
    walk:      { startRow: 8, frames: 9, behavior: 'loop' },
    hurt:      { startRow: 20, frames: 6, behavior: 'once' },
    idle:      { startRow: 22, frames: 2, behavior: 'loop' },
    jump:      { startRow: 26, frames: 5, behavior: 'once' },
    sit:       { startRow: 30, frames: 2, behavior: 'freeze' },  // frames: 2 to freeze on frame 1 (sitting), not frame 2 (crouch)
    emote:     { startRow: 34, frames: 3, behavior: 'once' },
    run:       { startRow: 38, frames: 8, behavior: 'loop' },
  }
}

// Avatar tracking for animation and direction
interface AvatarState {
  profile_id: string
  currentFrame: number
  direction: number  // 0=Up, 1=Left, 2=Down, 3=Right
  animation: keyof typeof SPRITE_CONFIG.animations  // Current animation type
  lastPosition: { lat: number; lon: number } | null
  lastUpdateTime: number
  isMoving: boolean  // True if avatar is currently moving
  lastMovementTime: number  // Last time movement was detected
  lastOneShotAction: string | null  // Track completed one-shot to prevent restart
}

const avatarStates = ref<Map<string, AvatarState>>(new Map())

/**
 * Get all avatars to render (others + own)
 */
function getAllAvatars(): Avatar[] {
  // Filter out own avatar from WebSocket list (we'll add it at map center)
  const others = props.avatars.filter(a => a.profile_id !== props.ownProfileId)

  // Always add own avatar at exact map center (not from Redis which has delay)
  if (props.ownProfileId && ownAvatarPosition.value) {
    others.push({
      profile_id: props.ownProfileId,
      lat: ownAvatarPosition.value.lat,
      lon: ownAvatarPosition.value.lon,
      zoom: 14,
      avatar_type: props.ownAvatarType || 'p1',
      avatar_state: props.ownAvatarState || 'idle',
      speech_bubble: props.ownSpeechBubble || '',
      profile_hna: '',
      profile_name: 'You'
    })
  }

  return others
}

/**
 * Load spritesheet image for specific avatar type
 */
function loadSpritesheet(avatarType: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    // Check if already loaded
    const cached = spritesheetImages.value.get(avatarType)
    if (cached) {
      resolve(cached)
      return
    }

    const img = new Image()
    img.onload = () => {
      spritesheetImages.value.set(avatarType, img)
      resolve(img)
    }
    img.onerror = (err) => {
      console.error(`[Sprites] Failed to load spritesheet for ${avatarType}:`, err)
      // Fallback to p1 if specific sprite not found
      if (avatarType !== 'p1') {
        loadSpritesheet('p1').then(resolve).catch(reject)
      } else {
        reject(err)
      }
    }
    img.src = `/sprites/avatars/${avatarType}.png`
  })
}

/**
 * Calculate direction from position delta (4 directions for LPC)
 * Returns direction index: 0=Up, 1=Left, 2=Down, 3=Right
 *
 * IMPORTANT: Direction is INVERTED because we're moving the MAP, not the character.
 * When map moves East (D key), character visually "walks West" to stay in place.
 */
function calculateDirection(fromLat: number, fromLon: number, toLat: number, toLon: number): number {
  // Invert horizontal: map moves East -> character faces West
  const dx = fromLon - toLon  // Inverted horizontal
  const dy = toLat - fromLat  // Normal vertical

  // Calculate angle in degrees (0-360) from North
  let angle = Math.atan2(dx, dy) * 180 / Math.PI
  if (angle < 0) angle += 360

  // Convert to 4 directions (each sector is 90°)
  // Add 45 to center sectors
  const sector = Math.floor(((angle + 45) % 360) / 90)

  // Map sector to LPC direction:
  // sector 0 = North (moving up) = UP (0)
  // sector 1 = East = LEFT (1) - swapped for correct visual
  // sector 2 = South = DOWN (2)
  // sector 3 = West = RIGHT (3) - swapped for correct visual
  const sectorToDirection = [
    SPRITE_CONFIG.directions.UP,
    SPRITE_CONFIG.directions.LEFT,
    SPRITE_CONFIG.directions.DOWN,
    SPRITE_CONFIG.directions.RIGHT
  ]

  return sectorToDirection[sector] ?? SPRITE_CONFIG.directions.DOWN
}

/**
 * Update avatar state (direction, frame, animation)
 */
function updateAvatarState(avatar: Avatar) {
  const now = Date.now()
  let state = avatarStates.value.get(avatar.profile_id)

  if (!state) {
    // Initialize new avatar state
    state = {
      profile_id: avatar.profile_id,
      currentFrame: 0,
      direction: SPRITE_CONFIG.directions.DOWN, // Default facing south (viewer)
      animation: 'idle',
      lastPosition: { lat: avatar.lat, lon: avatar.lon },
      lastUpdateTime: now,
      isMoving: false,
      lastMovementTime: now,
      lastOneShotAction: null
    }
    avatarStates.value.set(avatar.profile_id, state)
  }

  // Check if position changed (movement detection)
  let positionChanged = false
  if (state.lastPosition) {
    const distLat = Math.abs(avatar.lat - state.lastPosition.lat)
    const distLon = Math.abs(avatar.lon - state.lastPosition.lon)
    positionChanged = distLat > 0.000001 || distLon > 0.000001  // ~0.1 meter threshold
  }

  // Update animation based on avatar_state from backend
  if (avatar.avatar_state === 'jumping') {
    // Only start jump if not already completed this action AND not already playing
    if (state.lastOneShotAction !== 'jumping' && state.animation !== 'jump') {
      state.animation = 'jump'
      state.currentFrame = 0
      state.lastUpdateTime = now // Show frame 0 for full interval before advancing
      state.isMoving = true
      state.lastMovementTime = now

      // Play jump sound (only once per jump action)
      if (!playedJumpSounds.value.has(avatar.profile_id) && props.map) {
        playedJumpSounds.value.add(avatar.profile_id)
        const point = props.map.project([avatar.lon, avatar.lat])
        const isOwn = avatar.profile_id === props.ownProfileId
        playJumpSound(point.x, point.y, isOwn)
      }
    }
  } else if (avatar.avatar_state === 'sitting') {
    if (state.animation !== 'sit') {
      state.animation = 'sit'
      state.currentFrame = 0
      state.lastUpdateTime = now - 101 // Must be > frameInterval (100) to advance immediately
    }
    state.isMoving = true
    state.lastMovementTime = now
    state.lastOneShotAction = null // Reset one-shot tracker
  } else if (avatar.avatar_state === 'emoting') {
    // Only start emote if not already completed this action AND not already playing
    if (state.lastOneShotAction !== 'emoting' && state.animation !== 'emote') {
      state.animation = 'emote'
      state.currentFrame = 0
      state.lastUpdateTime = now // Show frame 0 for full interval before advancing
      state.isMoving = true
      state.lastMovementTime = now
    }
  } else {
    // Reset one-shot tracker when state changes to idle/walking
    state.lastOneShotAction = null
    // Clear jump sound tracker so avatar can play sound on next jump
    playedJumpSounds.value.delete(avatar.profile_id)
    // Walking or idle based on movement
    if (positionChanged) {
      const newDirection = calculateDirection(
        state.lastPosition!.lat,
        state.lastPosition!.lon,
        avatar.lat,
        avatar.lon
      )
      state.direction = newDirection
      state.lastPosition = { lat: avatar.lat, lon: avatar.lon }
      state.animation = 'walk'
      state.isMoving = true
      state.lastMovementTime = now
    } else {
      // Switch to idle after 1 second of no movement
      if (now - state.lastMovementTime > 1000) {
        state.animation = 'idle'
        state.isMoving = false
        state.currentFrame = 0
      }
    }
  }

  // Advance animation frame based on behavior
  const animConfig = SPRITE_CONFIG.animations[state.animation] as {
    startRow: number
    frames: number
    behavior: 'loop' | 'once' | 'freeze'
  }

  const frameInterval = 100 // ms per frame
  if (now - state.lastUpdateTime > frameInterval) {
    const nextFrame = state.currentFrame + 1

    if (nextFrame >= animConfig.frames) {
      // Animation finished one cycle
      if (animConfig.behavior === 'loop') {
        // Loop: restart from frame 0
        state.currentFrame = 0
      } else if (animConfig.behavior === 'once') {
        // Once: mark as completed and switch to idle
        // Map animation name back to avatar_state
        if (state.animation === 'jump') {
          state.lastOneShotAction = 'jumping'
        } else if (state.animation === 'emote') {
          state.lastOneShotAction = 'emoting'
        }
        state.animation = 'idle'
        state.currentFrame = 0
        state.isMoving = false
      } else if (animConfig.behavior === 'freeze') {
        // Freeze: stay on last frame
        state.currentFrame = animConfig.frames - 1
      }
    } else {
      state.currentFrame = nextFrame
    }
    state.lastUpdateTime = now
  }
}

/**
 * Find avatar under mouse cursor
 */
function findHoveredAvatar(allAvatars: Avatar[]): string | null {
  if (!props.map || !mousePosition.value) return null

  const hoverRadius = 24 // pixels

  for (const avatar of allAvatars) {
    if (!avatar.lat || !avatar.lon) continue

    const avatarPoint = props.map.project([avatar.lon, avatar.lat])
    // Check distance to avatar center (sprite center, not feet)
    const spriteCenter = { x: avatarPoint.x, y: avatarPoint.y - 24 } // 48/2 = 24px up from feet
    const distance = Math.sqrt(
      Math.pow(mousePosition.value.x - spriteCenter.x, 2) +
      Math.pow(mousePosition.value.y - spriteCenter.y, 2)
    )

    if (distance <= hoverRadius) {
      return avatar.profile_id
    }
  }
  return null
}

/**
 * Draw selection ring (ellipse) under avatar feet
 */
function drawSelectionRing(ctx: CanvasRenderingContext2D, x: number, y: number, isOwn: boolean, pulsePhase: number) {
  const ringWidth = 32
  const ringHeight = 12
  const centerX = x
  const centerY = y + 2 // Slightly below feet

  // Pulse animation (0.7 to 1.0 opacity)
  const pulse = 0.7 + 0.3 * Math.sin(pulsePhase)

  // Color: success for own, secondary for others
  const color = isOwn ? `rgba(5, 150, 105, ${pulse})` : `rgba(8, 145, 178, ${pulse})`
  const strokeColor = isOwn ? 'rgba(4, 120, 87, 0.8)' : 'rgba(14, 116, 144, 0.8)'

  ctx.save()
  ctx.beginPath()
  ctx.ellipse(centerX, centerY, ringWidth / 2, ringHeight / 2, 0, 0, Math.PI * 2)
  ctx.fillStyle = color
  ctx.fill()
  ctx.strokeStyle = strokeColor
  ctx.lineWidth = 2
  ctx.stroke()
  ctx.restore()
}

/**
 * Draw nameplate above avatar
 */
function drawNameplate(ctx: CanvasRenderingContext2D, x: number, y: number, name: string, isHovered: boolean, isOwn: boolean) {
  if (!name) return

  const displayName = name.length > 15 ? name.slice(0, 15) + '...' : name

  // Style based on hover state
  const fontSize = isHovered ? 13 : 11
  const opacity = isHovered ? 1 : 0.5
  const fontWeight = isHovered ? 'bold' : 'normal'

  ctx.save()
  ctx.font = `${fontWeight} ${fontSize}px sans-serif`
  const metrics = ctx.measureText(displayName)
  const textWidth = metrics.width
  const padding = 4
  const bgWidth = textWidth + padding * 2
  const bgHeight = fontSize + padding

  const bgX = x - bgWidth / 2
  const bgY = y - 52 - (isHovered ? 4 : 0) // Higher when hovered

  // Background
  ctx.fillStyle = `rgba(0, 0, 0, ${opacity * 0.6})`
  ctx.beginPath()
  const radius = 3
  ctx.roundRect(bgX, bgY, bgWidth, bgHeight, radius)
  ctx.fill()

  // Text color: success for own, white for others
  const textColor = isOwn
    ? `rgba(110, 231, 183, ${opacity})` // success-300
    : `rgba(255, 255, 255, ${opacity})`

  ctx.fillStyle = textColor
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(displayName, x, bgY + bgHeight / 2)
  ctx.restore()
}

/**
 * Initialize Web Audio API and load sounds
 */
async function initAudio() {
  try {
    // Create audio context (lazily on first user interaction)
    if (!audioContext) {
      audioContext = new (window.AudioContext || (window as any).webkitAudioContext)()
    }

    // Load all sounds in parallel
    const loadSound = async (url: string): Promise<AudioBuffer> => {
      const response = await fetch(url)
      const arrayBuffer = await response.arrayBuffer()
      return audioContext!.decodeAudioData(arrayBuffer)
    }

    const [jump, skin, say] = await Promise.all([
      !jumpSoundBuffer ? loadSound('/sounds/jump.wav') : Promise.resolve(jumpSoundBuffer),
      !skinSoundBuffer ? loadSound('/sounds/skin.wav') : Promise.resolve(skinSoundBuffer),
      !saySoundBuffer ? loadSound('/sounds/say.wav') : Promise.resolve(saySoundBuffer),
    ])

    jumpSoundBuffer = jump
    skinSoundBuffer = skin
    saySoundBuffer = say

  } catch (error) {
    console.error('[Audio] Failed to initialize:', error)
  }
}

/**
 * Play spatial sound with stereo pan and distance-based volume
 * @param buffer - Audio buffer to play
 * @param avatarScreenX - Avatar X position on screen
 * @param avatarScreenY - Avatar Y position on screen
 * @param isOwn - Whether this is the user's own avatar
 * @param ownVolume - Volume for own avatar (0-1)
 * @param otherVolume - Base volume for other avatars (0-1)
 */
function playSpatialSound(
  buffer: AudioBuffer,
  avatarScreenX: number,
  avatarScreenY: number,
  isOwn: boolean,
  ownVolume: number = 0.8,
  otherVolume: number = 0.6
) {
  if (!audioContext || !spriteCanvas.value) return

  // Resume audio context if suspended (browser autoplay policy)
  if (audioContext.state === 'suspended') {
    audioContext.resume()
  }

  const canvasWidth = spriteCanvas.value.width
  const canvasHeight = spriteCanvas.value.height
  const centerX = canvasWidth / 2
  const centerY = canvasHeight / 2

  // Calculate stereo pan (-1 = left, 0 = center, 1 = right)
  const pan = Math.max(-1, Math.min(1, (avatarScreenX - centerX) / (canvasWidth / 2)))

  // Calculate distance from center (0 to 1)
  const dx = avatarScreenX - centerX
  const dy = avatarScreenY - centerY
  const maxDistance = Math.sqrt(canvasWidth * canvasWidth + canvasHeight * canvasHeight) / 2
  const distance = Math.sqrt(dx * dx + dy * dy)
  const normalizedDistance = Math.min(1, distance / maxDistance)

  // Volume: own avatar is full volume, others fade with distance
  const volume = isOwn
    ? ownVolume
    : otherVolume * (1 - normalizedDistance * 0.8)

  // Create audio nodes
  const source = audioContext.createBufferSource()
  const gainNode = audioContext.createGain()
  const pannerNode = audioContext.createStereoPanner()

  // Connect nodes: source -> gain -> panner -> destination
  source.buffer = buffer
  source.connect(gainNode)
  gainNode.connect(pannerNode)
  pannerNode.connect(audioContext.destination)

  // Set values
  gainNode.gain.value = volume
  pannerNode.pan.value = pan

  // Play sound
  source.start(0)
}

/**
 * Play jump sound
 */
function playJumpSound(x: number, y: number, isOwn: boolean) {
  if (jumpSoundBuffer) playSpatialSound(jumpSoundBuffer, x, y, isOwn, 0.8, 0.6)
}

/**
 * Play skin change sound
 */
function playSkinSound(x: number, y: number, isOwn: boolean) {
  if (skinSoundBuffer) playSpatialSound(skinSoundBuffer, x, y, isOwn, 0.7, 0.5)
}

/**
 * Play speech bubble sound
 */
function playSaySound(x: number, y: number, isOwn: boolean) {
  if (saySoundBuffer) playSpatialSound(saySoundBuffer, x, y, isOwn, 0.5, 0.4)
}

/**
 * Render sprites on overlay canvas
 */
function renderSprites() {
  if (!props.map || !spriteCanvas.value || spritesheetImages.value.size === 0) return

  const canvas = spriteCanvas.value
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  // Match canvas size to map's CSS size (not internal resolution)
  const mapContainer = props.map.getContainer()
  const displayWidth = mapContainer.clientWidth
  const displayHeight = mapContainer.clientHeight

  if (canvas.width !== displayWidth || canvas.height !== displayHeight) {
    canvas.width = displayWidth
    canvas.height = displayHeight
  }

  // Disable image smoothing for crisp pixel art
  ctx.imageSmoothingEnabled = false

  // Clear entire canvas
  ctx.clearRect(0, 0, displayWidth, displayHeight)

  // Pulse animation phase (for selection ring)
  const pulsePhase = Date.now() / 200

  // Update own avatar position with animation
  // Logic:
  // - Keyboard moving (Factorio): avatar locked to map center, walk animation, direction from keys
  // - During zoom: avatar stays at current geo position (screen position changes)
  // - During drag/pan: avatar stays at lastStablePosition (doesn't follow map)
  // - After moveend: avatar runs from lastStablePosition to new center (2 sec animation)
  // - During run animation: interpolate position
  if (props.map && props.ownProfileId) {
    const center = props.map.getCenter()
    const newTarget = { lat: center.lat, lon: center.lng }

    if (props.isKeyboardMoving) {
      // Factorio-style: avatar is always at map center, walking with keyboard direction
      ownAvatarPosition.value = newTarget
      lastStablePosition.value = newTarget
      // Cancel any pending run animation
      ownMovementAnimation.value.isAnimating = false

      const state = avatarStates.value.get(props.ownProfileId)
      if (state) {
        state.animation = 'walk'
        state.isMoving = true
        state.lastMovementTime = Date.now()
        if (props.keyboardDirection !== undefined) {
          state.direction = props.keyboardDirection
        }
      }
    } else if (ownMovementAnimation.value.isAnimating) {
      // Currently animating - interpolate position
      const now = Date.now()
      const elapsed = now - ownMovementAnimation.value.startTime
      const progress = Math.min(elapsed / ownMovementAnimation.value.duration, 1)

      // Ease-out function for smoother deceleration
      const easeOut = 1 - Math.pow(1 - progress, 3)

      const start = ownMovementAnimation.value.startPosition!
      const target = ownMovementAnimation.value.targetPosition!

      ownAvatarPosition.value = {
        lat: start.lat + (target.lat - start.lat) * easeOut,
        lon: start.lon + (target.lon - start.lon) * easeOut
      }

      // Animation complete
      if (progress >= 1) {
        ownMovementAnimation.value.isAnimating = false
        ownAvatarPosition.value = target
        lastStablePosition.value = target

        // Update avatar state to idle after arriving
        const state = avatarStates.value.get(props.ownProfileId)
        if (state) {
          state.animation = 'idle'
          state.isMoving = false
          state.lastMovementTime = now
        }
      }
    } else if (isZooming.value || isMapMoving.value) {
      // During zoom or drag - avatar stays at current geo position
      // Don't update ownAvatarPosition - avatar visually moves on screen
      // After zoom/drag ends, avatar will run to new center
    } else {
      // Not moving, not animating - avatar should be at current map center
      if (!ownAvatarPosition.value) {
        // First time - set initial position instantly
        ownAvatarPosition.value = newTarget
        lastStablePosition.value = newTarget
      }
      // Otherwise keep current position (will be updated by moveend handler)
    }
  }

  // Get all avatars (others + own)
  const allAvatars = getAllAvatars()

  // Check for skin changes and speech bubbles (play sounds)
  allAvatars.forEach(avatar => {
    if (!avatar.lat || !avatar.lon || !props.map) return

    const profileId = avatar.profile_id
    const isOwn = profileId === props.ownProfileId
    const point = props.map.project([avatar.lon, avatar.lat])

    // Detect skin change
    const lastType = lastAvatarTypes.value.get(profileId)
    if (lastType !== undefined && lastType !== avatar.avatar_type) {
      playSkinSound(point.x, point.y, isOwn)
    }
    lastAvatarTypes.value.set(profileId, avatar.avatar_type)

    // Detect new speech bubble
    const lastBubble = lastSpeechBubbles.value.get(profileId)
    const currentBubble = avatar.speech_bubble || ''
    if (lastBubble !== undefined && currentBubble && lastBubble !== currentBubble) {
      playSaySound(point.x, point.y, isOwn)
    }
    lastSpeechBubbles.value.set(profileId, currentBubble)
  })

  // Detect hovered avatar
  hoveredAvatarId.value = findHoveredAvatar(allAvatars)

  // Update cursor based on hover
  if (spriteCanvas.value) {
    spriteCanvas.value.style.cursor = hoveredAvatarId.value ? 'pointer' : 'default'
  }

  // First pass: Draw selection rings (under sprites)
  allAvatars.forEach(avatar => {
    if (!avatar.lat || !avatar.lon) return

    const isHovered = avatar.profile_id === hoveredAvatarId.value
    if (!isHovered) return // Only draw ring for hovered avatar

    const point = props.map!.project([avatar.lon, avatar.lat])
    const isOwn = avatar.profile_id === props.ownProfileId
    drawSelectionRing(ctx, point.x, point.y, isOwn, pulsePhase)
  })

  // Second pass: Draw sprites
  allAvatars.forEach(avatar => {
    if (!avatar.lat || !avatar.lon) return

    // Update avatar animation state
    updateAvatarState(avatar)

    const state = avatarStates.value.get(avatar.profile_id)
    if (!state) return

    // Project lat/lon to screen coordinates
    const point = props.map!.project([avatar.lon, avatar.lat])

    // Get animation config
    const animConfig = SPRITE_CONFIG.animations[state.animation]

    // Calculate row: animation startRow + direction offset
    // LPC layout: each animation has 4 consecutive rows (Up/Left/Down/Right)
    const row = animConfig.startRow + state.direction
    const col = state.currentFrame

    // Source position in spritesheet (LPC sprites are properly aligned, no margin needed)
    const sx = col * SPRITE_CONFIG.frameWidth
    const sy = row * SPRITE_CONFIG.frameHeight

    // Draw sprite centered on point
    // Scale down slightly for map display (64px is quite large)
    const drawSize = 48  // Display size on map
    const x = Math.round(point.x - drawSize / 2)
    const y = Math.round(point.y - drawSize)  // Position feet at the point

    // Get spritesheet for this avatar type
    const avatarType = avatar.avatar_type || 'p1'
    const spritesheet = spritesheetImages.value.get(avatarType) || spritesheetImages.value.get('p1')
    if (!spritesheet) {
      // Try to load missing spritesheet asynchronously
      loadSpritesheet(avatarType)
      return
    }

    // Draw sprite from spritesheet
    ctx.drawImage(
      spritesheet,
      sx, sy, SPRITE_CONFIG.frameWidth, SPRITE_CONFIG.frameHeight,
      x, y, drawSize, drawSize
    )
  })

  // Third pass: Draw nameplates (above sprites)
  allAvatars.forEach(avatar => {
    if (!avatar.lat || !avatar.lon) return

    const point = props.map!.project([avatar.lon, avatar.lat])
    const isOwn = avatar.profile_id === props.ownProfileId
    const isHovered = avatar.profile_id === hoveredAvatarId.value
    const name = avatar.profile_name || avatar.profile_hna || ''

    drawNameplate(ctx, point.x, point.y, name, isHovered, isOwn)
  })

  // Fourth pass: Draw speech bubbles (topmost layer)
  allAvatars.forEach(avatar => {
    if (!avatar.lat || !avatar.lon) return
    if (!avatar.speech_bubble || !avatar.speech_bubble.trim()) return

    const point = props.map!.project([avatar.lon, avatar.lat])
    const drawSize = 48
    const x = Math.round(point.x - drawSize / 2)
    const y = Math.round(point.y - drawSize)

    const text = avatar.speech_bubble.slice(0, 50) // Max 50 chars
    const bubbleX = x + drawSize / 2
    const bubbleY = y - 5  // Above sprite head

    // Measure text
    ctx.font = '12px sans-serif'
    const metrics = ctx.measureText(text)
    const textWidth = metrics.width
    const padding = 6
    const bubbleWidth = textWidth + padding * 2
    const bubbleHeight = 18

    // Draw bubble background
    ctx.fillStyle = 'rgba(255, 255, 255, 0.95)'
    ctx.strokeStyle = '#3F3F46' // neutral-700
    ctx.lineWidth = 1

    const bx = bubbleX - bubbleWidth / 2
    const by = bubbleY - bubbleHeight

    // Rounded rect
    const radius = 6
    ctx.beginPath()
    ctx.moveTo(bx + radius, by)
    ctx.lineTo(bx + bubbleWidth - radius, by)
    ctx.quadraticCurveTo(bx + bubbleWidth, by, bx + bubbleWidth, by + radius)
    ctx.lineTo(bx + bubbleWidth, by + bubbleHeight - radius)
    ctx.quadraticCurveTo(bx + bubbleWidth, by + bubbleHeight, bx + bubbleWidth - radius, by + bubbleHeight)
    ctx.lineTo(bx + radius, by + bubbleHeight)
    ctx.quadraticCurveTo(bx, by + bubbleHeight, bx, by + bubbleHeight - radius)
    ctx.lineTo(bx, by + radius)
    ctx.quadraticCurveTo(bx, by, bx + radius, by)
    ctx.closePath()
    ctx.fill()
    ctx.stroke()

    // Draw small triangle pointer
    ctx.beginPath()
    ctx.moveTo(bubbleX - 4, by + bubbleHeight)
    ctx.lineTo(bubbleX, by + bubbleHeight + 5)
    ctx.lineTo(bubbleX + 4, by + bubbleHeight)
    ctx.closePath()
    ctx.fillStyle = 'rgba(255, 255, 255, 0.95)'
    ctx.fill()
    ctx.stroke()

    // Draw text
    ctx.fillStyle = '#18181B' // neutral-900
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(text, bubbleX, by + bubbleHeight / 2)
  })

  // No continuous rAF loop — redraws are triggered by throttled map events
}

/**
 * Initialize sprite rendering system
 */
async function initializeLayer() {
  if (!props.map || layerAdded.value) return

  try {
    // Preload all avatar spritesheets
    await loadSpritesheet('p1')
    // Preload others in background
    loadSpritesheet('p0').catch(() => {})
    loadSpritesheet('p2').catch(() => {})
    loadSpritesheet('p3').catch(() => {})
    loadSpritesheet('p4').catch(() => {})

    // Setup canvas overlay
    canvasReady.value = true

    // Wait for canvas to mount
    await new Promise(resolve => setTimeout(resolve, 100))

    if (!spriteCanvas.value) {
      console.error('[Sprites] Canvas not mounted')
      return
    }

    // Match canvas size to map
    const mapCanvas = props.map.getCanvas()
    spriteCanvas.value.width = mapCanvas.width
    spriteCanvas.value.height = mapCanvas.height

    // Map events to trigger rerender (throttled to ~5fps to save CPU)
    let spriteRafPending = false
    throttledRenderSprites = () => {
      if (spriteRafPending) return
      spriteRafPending = true
      requestAnimationFrame(() => {
        spriteRafPending = false
        renderSprites()
      })
    }
    props.map.on('move', throttledRenderSprites)
    props.map.on('zoom', throttledRenderSprites)
    props.map.on('resize', () => {
      if (spriteCanvas.value && props.map) {
        const mapCanvas = props.map.getCanvas()
        spriteCanvas.value.width = mapCanvas.width
        spriteCanvas.value.height = mapCanvas.height
        renderSprites()
      }
    })

    // Track zoom events to prevent avatar movement during zoom
    props.map.on('zoomstart', () => {
      isZooming.value = true
      if (zoomTimeout) {
        clearTimeout(zoomTimeout)
        zoomTimeout = null
      }
    })

    props.map.on('zoomend', () => {
      // Delay resetting zoom flag slightly
      zoomTimeout = setTimeout(() => {
        isZooming.value = false

        // After zoom ends, start running animation to new center (same as drag)
        if (props.map && props.ownProfileId) {
          const center = props.map.getCenter()
          const newTarget = { lat: center.lat, lon: center.lng }
          const startPos = ownAvatarPosition.value

          if (startPos) {
            const distLat = Math.abs(newTarget.lat - startPos.lat)
            const distLon = Math.abs(newTarget.lon - startPos.lon)
            const hasMoved = distLat > 0.00001 || distLon > 0.00001

            if (hasMoved) {
              // Start running animation from current position to new center
              ownMovementAnimation.value = {
                startPosition: { ...startPos },
                targetPosition: newTarget,
                startTime: Date.now(),
                duration: 2000,
                isAnimating: true
              }

              const state = avatarStates.value.get(props.ownProfileId)
              if (state) {
                state.animation = 'run'
                state.isMoving = true
                state.lastMovementTime = Date.now()
                state.direction = calculateDirection(
                  startPos.lat, startPos.lon,
                  newTarget.lat, newTarget.lon
                )
              }
            } else {
              // Small change - just sync
              ownAvatarPosition.value = newTarget
              lastStablePosition.value = newTarget
            }
          }
        }
      }, 100)
    })

    // Track move events for running animation
    props.map.on('movestart', () => {
      // Don't set moving flag if it's just zoom or keyboard-driven movement
      if (!isZooming.value && !props.isKeyboardMoving) {
        isMapMoving.value = true
        // Remember position before move started
        if (ownAvatarPosition.value && !lastStablePosition.value) {
          lastStablePosition.value = { ...ownAvatarPosition.value }
        }
      }
    })

    props.map.on('moveend', () => {
      // Skip run animation during keyboard movement — renderSprites handles it directly
      if (props.isKeyboardMoving) {
        isMapMoving.value = false
        return
      }
      if (isMapMoving.value && !isZooming.value && props.ownProfileId) {
        isMapMoving.value = false

        const center = props.map!.getCenter()
        const newTarget = { lat: center.lat, lon: center.lng }

        // IMPORTANT: Use current avatar position (which may be mid-animation)
        // This allows interrupting running animation and starting new one from current spot
        const startPos = ownAvatarPosition.value

        if (startPos) {
          // Check if position changed significantly
          const distLat = Math.abs(newTarget.lat - startPos.lat)
          const distLon = Math.abs(newTarget.lon - startPos.lon)
          const hasMoved = distLat > 0.00001 || distLon > 0.00001  // ~1m threshold

          if (hasMoved) {
            // Start running animation from CURRENT position to new target
            ownMovementAnimation.value = {
              startPosition: { ...startPos },
              targetPosition: newTarget,
              startTime: Date.now(),
              duration: 2000,  // 2 seconds
              isAnimating: true
            }

            // Update avatar state to running with correct direction
            const state = avatarStates.value.get(props.ownProfileId)
            if (state) {
              state.animation = 'run'
              state.isMoving = true
              state.lastMovementTime = Date.now()
              state.direction = calculateDirection(
                startPos.lat, startPos.lon,
                newTarget.lat, newTarget.lon
              )
            }
          } else {
            // Small move - just sync position
            ownAvatarPosition.value = newTarget
            lastStablePosition.value = newTarget
          }
        }
      } else {
        isMapMoving.value = false
      }
    })

    // Avatar hover detection via map events (canvas has pointer-events: none)
    // Note: click handling is done in MapView to avoid duplicate handlers
    props.map.on('mousemove', handleMapMouseMove)

    layerAdded.value = true

    // Initial render
    renderSprites()

  } catch (error) {
    console.error('[Sprites] Failed to initialize:', error)
  }
}

/**
 * Handle map mouse move for hover detection (map event, not canvas)
 */
function handleMapMouseMove(e: any) {
  if (!spriteCanvas.value || !props.map) return

  // Initialize audio on first user interaction (browser autoplay policy)
  if (!audioContext) {
    initAudio()
  }

  // e.point contains {x, y} relative to map container
  mousePosition.value = {
    x: e.point.x,
    y: e.point.y
  }

  // Check if hovering over an avatar for cursor change
  const avatarAtPoint = findAvatarAtPoint(e.point.x, e.point.y)
  if (avatarAtPoint) {
    props.map.getCanvas().style.cursor = 'pointer'
  } else if (!hoveredAvatarId.value) {
    // Only reset cursor if not hovering any avatar
    props.map.getCanvas().style.cursor = ''
  }
}

/**
 * Handle map click for avatar selection (map event, not canvas)
 */
function handleMapClick(e: any) {
  if (!spriteCanvas.value || !props.map) return

  const avatarAtPoint = findAvatarAtPoint(e.point.x, e.point.y)
  if (avatarAtPoint) {
    emit('avatarClick', avatarAtPoint)
  }
}

/**
 * Find avatar at screen coordinates
 */
function findAvatarAtPoint(x: number, y: number): Avatar | null {
  if (!props.map) return null

  // Use getAllAvatars() to include own avatar (not just props.avatars)
  for (const avatar of getAllAvatars()) {
    const pos = props.map.project([avatar.lon, avatar.lat])
    const avatarX = pos.x
    const avatarY = pos.y - 32 // Adjust for sprite anchor

    // Check if click is within avatar sprite bounds (64x64)
    const hitboxPadding = 10
    if (
      x >= avatarX - 32 - hitboxPadding &&
      x <= avatarX + 32 + hitboxPadding &&
      y >= avatarY - hitboxPadding &&
      y <= avatarY + 64 + hitboxPadding
    ) {
      return avatar
    }
  }
  return null
}

/**
 * Handle mouse leave - reset hover state (called from parent via map container)
 */
function handleMouseLeave() {
  mousePosition.value = null
  hoveredAvatarId.value = null
  if (spriteCanvas.value) {
    spriteCanvas.value.style.cursor = 'default'
  }
}

// Watch for map ready
watch(() => props.map, (map) => {
  if (map) {
    let attempts = 0
    const maxAttempts = 50

    const checkReady = () => {
      attempts++
      const loaded = map.loaded()
      const styleLoaded = map.isStyleLoaded()

      if (loaded && styleLoaded) {
        initializeLayer()
      } else if (attempts < maxAttempts) {
        setTimeout(checkReady, 100)
      }
    }

    checkReady()
  }
}, { immediate: true })

// Re-render when avatar data changes (WS updates)
watch(() => props.avatars, () => {
  if (layerAdded.value) renderSprites()
}, { deep: true })

// Cleanup
onBeforeUnmount(() => {
  if (zoomTimeout) {
    clearTimeout(zoomTimeout)
    zoomTimeout = null
  }

  if (props.map && layerAdded.value) {
    if (throttledRenderSprites) {
      props.map.off('move', throttledRenderSprites)
      props.map.off('zoom', throttledRenderSprites)
    }
    props.map.off('resize', renderSprites)
    props.map.off('mousemove', handleMapMouseMove)
  }
})
</script>

<style>
/* No styles - rendered on canvas */
</style>
