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
      @load="loading = false"
    />
  </div>
</template>

<script setup lang="ts">
import { Play } from 'lucide-vue-next'

const props = defineProps<{
  embedUrl: string
  title?: string
  autoplay?: boolean
  muted?: boolean
  startTime?: number
}>()

const loading = ref(true)
const iframeRef = ref<HTMLIFrameElement | null>(null)

const embedSrc = computed(() => {
  const url = new URL(props.embedUrl)
  url.searchParams.set('api', '1')
  if (props.autoplay) url.searchParams.set('autoplay', '1')
  if (props.muted) url.searchParams.set('muted', '1')
  if (props.startTime) url.searchParams.set('start', String(props.startTime))
  // Allow embedding from parahub.io
  url.searchParams.set('controls', '1')
  return url.toString()
})
</script>
