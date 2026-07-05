<template>
  <div class="relative w-full" :style="{ paddingBottom: '56.25%' }">
    <!-- Loading skeleton -->
    <div
      v-if="loading"
      class="absolute inset-0 bg-neutral-200 dark:bg-neutral-700 animate-pulse rounded-lg flex items-center justify-center"
    >
      <Play class="w-12 h-12 text-neutral-400 dark:text-neutral-500" />
    </div>

    <iframe
      v-show="!loading"
      ref="iframeRef"
      :src="embedSrc"
      class="absolute inset-0 w-full h-full rounded-lg"
      :title="title || 'Video'"
      sandbox="allow-same-origin allow-scripts allow-popups allow-forms"
      allowfullscreen
      @load="onIframeLoad"
    />
  </div>
</template>

<script setup lang="ts">
import { Play } from 'lucide-vue-next'
import type { PeerTubePlayer as PeerTubePlayerType } from '@peertube/embed-api'

const props = withDefaults(defineProps<{
  embedUrl: string
  title?: string
  autoplay?: boolean
  muted?: boolean
  startTime?: number
  /** Automatically pause when the browser tab becomes hidden. Default: true. */
  pauseOnHidden?: boolean
}>(), {
  pauseOnHidden: true,
})

const emit = defineEmits<{
  play: []
  pause: []
  /** Playback reached the end of the clip (derived — see onIframeLoad). */
  ended: []
  ready: [player: PeerTubePlayerType]
  timeupdate: [currentTime: number]
}>()

const loading = ref(true)
const iframeRef = ref<HTMLIFrameElement | null>(null)
let player: PeerTubePlayerType | null = null
let wasPlayingBeforeHide = false
let hasEnded = false

const embedSrc = computed(() => {
  const url = new URL(props.embedUrl)
  url.searchParams.set('api', '1')
  if (props.autoplay) url.searchParams.set('autoplay', '1')
  if (props.muted) url.searchParams.set('muted', '1')
  if (props.startTime) url.searchParams.set('start', String(props.startTime))
  url.searchParams.set('controls', '1')
  // The title is always shown in surrounding UI, so hide the redundant in-player
  // overlay (auto-named uploads like "1477" look like noise). Disable P2P: it
  // shares the viewer's IP with other peers for peer-assisted delivery — useless
  // on our single-server instance and a privacy leak. warningTitle=0 drops the
  // "your IP address is visible" notice (moot once p2p is off, but explicit).
  url.searchParams.set('title', '0')
  url.searchParams.set('p2p', '0')
  url.searchParams.set('warningTitle', '0')
  return url.toString()
})

const onIframeLoad = async () => {
  loading.value = false

  // embed-api is browser-only (postMessage); guard SSR just in case.
  if (!import.meta.client || !iframeRef.value) return

  try {
    const { PeerTubePlayer } = await import('@peertube/embed-api')
    player = new PeerTubePlayer(iframeRef.value)
    await player.ready

    const markEnded = () => { if (!hasEnded) { hasEnded = true; emit('ended') } }

    player.addEventListener('play', () => { hasEnded = false; emit('play') })
    player.addEventListener('pause', () => emit('pause'))
    // embed-api@0.2.0 has NO dedicated 'ended' event. The AUTHORITATIVE end signal
    // is playbackStatusChange === 'ended' (PeerTube wires it to video.js 'ended').
    // playbackStatusUpdate alone is NOT enough: it's throttled to 500ms off
    // `timeupdate`, which stops at end — so the last emitted frame can sit beyond
    // our position≈duration window and no post-end frame carries playbackState
    // 'ended'. We still keep the position backstop in case the change event is lost.
    player.addEventListener('playbackStatusChange', (state: any) => {
      if (state === 'ended') markEnded()
    })
    player.addEventListener('playbackStatusUpdate', (ev: any) => {
      if (typeof ev?.position === 'number') emit('timeupdate', ev.position)
      const dur = typeof ev?.duration === 'number' ? ev.duration : 0
      if (ev?.playbackState === 'ended' || (dur > 0 && ev?.position >= dur - 0.4)) markEnded()
    })

    emit('ready', player)
  } catch (err) {
    // embed-api failed — player still works as a plain iframe, just without JS control.
    console.warn('[VideoPlayer] embed-api init failed:', err)
  }
}

const onVisibilityChange = async () => {
  if (!props.pauseOnHidden || !player) return
  if (document.hidden) {
    try {
      wasPlayingBeforeHide = await player.isPlaying()
      if (wasPlayingBeforeHide) await player.pause()
    } catch { /* ignore */ }
  }
  // Intentionally do NOT auto-resume on visible — let the user decide.
}

onMounted(() => {
  if (import.meta.client) {
    document.addEventListener('visibilitychange', onVisibilityChange)
  }
})

onBeforeUnmount(() => {
  if (import.meta.client) {
    document.removeEventListener('visibilitychange', onVisibilityChange)
  }
  if (player) {
    try { player.destroy() } catch { /* ignore */ }
    player = null
  }
})

defineExpose({
  /** Imperative handle for parent components: play/pause/seek/getCurrentTime/... */
  getPlayer: () => player,
})
</script>
